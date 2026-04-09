"""
LangGraph Nodes
Each node is an async function that receives PipelineState and returns a dict of updates.
Node order: load_profile -> plan_outline -> fan-out per slide -> aggregate -> aggregate_validation -> render -> store
"""

import asyncio
import json
import logging
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.graph.state import PipelineState
from app.schemas.slide_plan import SlideOutlineItem, SlidePlan, SlidePlanItem
from app.schemas.template_profile import TemplateProfile
from app.tools.renderer import render_pptx
from app.tools.validator import validate_aggregate_plan, validate_single_slide

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _get_planner_llm():
    settings = get_settings()
    if settings.openrouter_api_key:
        return ChatOpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            model=settings.planner_model,
            temperature=0.3,
            max_tokens=32768,
            default_headers={
                "HTTP-Referer": "https://github.com/ppt-project",
                "X-Title": "PPT Generator",
            },
        )
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.planner_model,
        temperature=0.3,
        max_tokens=32768,
    )


def _parse_retry_after(error_message: str) -> float:
    """Extract seconds to wait from a Groq 429 error message."""
    m = re.search(r"(?:(\d+)m)?(\d+(?:\.\d+)?)s", str(error_message))
    if m:
        minutes = float(m.group(1) or 0)
        seconds = float(m.group(2))
        return minutes * 60 + seconds
    return 60.0


async def _invoke_with_retry(llm, messages: list, *, max_wait: float = 120.0) -> object:
    """
    Invoke the LLM, automatically waiting and retrying once on a 429 rate-limit error.
    Raises the original exception if the retry also fails or if wait > max_wait.
    """
    try:
        return await llm.ainvoke(messages)
    except Exception as e:
        err_str = str(e)
        if "429" not in err_str and "rate_limit" not in err_str.lower():
            raise
        wait_seconds = _parse_retry_after(err_str)
        if wait_seconds > max_wait:
            raise RuntimeError(
                f"Planner rate limit hit. Retry in {wait_seconds:.0f}s "
                f"(exceeds max_wait={max_wait}s)."
            ) from e
        logger.warning(f"Planner 429 rate limit: waiting {wait_seconds:.1f}s before retry")
        await asyncio.sleep(wait_seconds)
        return await llm.ainvoke(messages)


def _strip_json_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _sanitize_plan_data(plan_data: dict) -> dict:
    """Normalize LLM JSON so SlidePlan parsing is resilient to null/typed drift."""
    slides = plan_data.get("slides")
    if not isinstance(slides, list):
        return plan_data

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        content = slide.get("content")
        if not isinstance(content, dict):
            continue
        placeholders = content.get("placeholders")
        if not isinstance(placeholders, dict):
            continue

        normalized_placeholders: dict[str, str | list[str]] = {}
        for key, value in placeholders.items():
            key_str = str(key)
            if value is None:
                normalized_placeholders[key_str] = ""
            elif isinstance(value, list):
                normalized_placeholders[key_str] = ["" if v is None else str(v) for v in value]
            else:
                normalized_placeholders[key_str] = str(value)

        content["placeholders"] = normalized_placeholders

    return plan_data


def _backfill_missing_text_placeholders(slide_plan: SlidePlan, profile: TemplateProfile) -> SlidePlan:
    """
    Backfill only explicit empty placeholder keys from the LLM output.

    We intentionally avoid creating brand-new placeholder entries, because that can
    write fallback text into decorative or tightly constrained text boxes.
    """
    layout_by_index = {s.slide_index: s for s in profile.slides}

    for item in slide_plan.slides:
        layout = layout_by_index.get(item.template_slide_index)
        if not layout:
            continue

        purpose_text = (item.purpose or "").strip() or "Key insights"
        fill_counter = 0
        ph_map = {str(ph.idx): ph for ph in layout.placeholders}

        for key, val in list(item.content.placeholders.items()):
            ph = ph_map.get(str(key))
            if not ph:
                continue

            is_empty = False
            if val is None:
                is_empty = True
            elif isinstance(val, str) and not val.strip():
                is_empty = True
            elif isinstance(val, list) and not any(str(v).strip() for v in val):
                is_empty = True

            if not is_empty:
                continue

            # Never force-fill title placeholders; let deterministic validation drive retries.
            if str(ph.type).upper() in {"TITLE", "CENTER_TITLE"}:
                continue

            # Avoid injecting long fallback into compact placeholders (circle callouts, eyebrow labels).
            if ph.max_chars_estimate <= 18:
                continue

            fill_counter += 1
            fallback = purpose_text if fill_counter == 1 else f"{purpose_text} ({fill_counter})"
            item.content.placeholders[str(key)] = fallback

    return slide_plan


_GUIDANCE_LAYOUT_PATTERNS = [
    "using slides templates",
    "familiarize yourself with the template",
    "start building your presentation",
    "follow brand guidelines",
    "proofread and review",
    "read this info slide. this is not a template",
    "to download fonts",
    "brand guidelines",
    "powerpoint icon library",
    "accessible presentations in powerpoint",
    "use the accessibility checker",
    "set reading order of slide contents",
    "add alt text to images",
    "do not merge or split cells in tables",
    "best practices checklist",
]


_COVER_LAYOUT_PATTERNS = [
    "presentation title",
    "presenter name",
    "date",
    "presentation subtitle",
]


def _looks_like_cover_layout(layout) -> bool:
    """Detect cover/title-page template layouts that should not appear mid-deck."""
    text_chunks = []
    for ph in getattr(layout, "placeholders", []):
        current = str(getattr(ph, "current_text", "") or "").strip().lower()
        if current:
            text_chunks.append(current)

    joined = "\n".join(text_chunks)
    if not joined:
        return False

    # require at least two cover signals to avoid false positives
    hits = sum(1 for p in _COVER_LAYOUT_PATTERNS if p in joined)
    return hits >= 2


def _looks_like_guidance_layout(layout) -> bool:
    if str(getattr(layout, "classification", "")).lower() == "guidance":
        return True

    text_chunks = []
    for ph in getattr(layout, "placeholders", []):
        current = str(getattr(ph, "current_text", "") or "").strip().lower()
        if current:
            text_chunks.append(current)

    joined = "\n".join(text_chunks)
    if not joined:
        return False

    return any(pattern in joined for pattern in _GUIDANCE_LAYOUT_PATTERNS)


def _usable_content_slides(profile: TemplateProfile):
    """Filter slides to usable content layouts, guarding against stale misclassification."""
    usable = []
    for s in profile.slides:
        if _looks_like_guidance_layout(s):
            continue
        if _looks_like_cover_layout(s):
            continue
        usable.append(s)
    return usable


def _layout_capabilities(layout) -> dict:
    has_title = any(str(p.type).upper() in {"TITLE", "CENTER_TITLE"} for p in layout.placeholders)
    has_chart = bool(layout.charts)
    has_table = bool(layout.tables)
    compact_count = sum(1 for p in layout.placeholders if int(getattr(p, "max_chars_estimate", 0) or 0) <= 12)
    text_slots = sum(1 for p in layout.placeholders if str(p.type).upper() in {"TITLE", "CENTER_TITLE", "BODY", "SUBTITLE"})
    return {
        "has_title": has_title,
        "has_chart": has_chart,
        "has_table": has_table,
        "compact_count": compact_count,
        "text_slots": text_slots,
    }


def _format_available_layouts(content_slides) -> str:
    lines = []
    for s in content_slides:
        caps = _layout_capabilities(s)
        ph_types = ", ".join(p.type for p in s.placeholders) or "no_placeholders"
        lines.append(
            f"  index={s.slide_index}: "
            f"placeholders=[{ph_types}], "
            f"title={caps['has_title']}, chart={caps['has_chart']}, table={caps['has_table']}, "
            f"compact_labels={caps['compact_count']}"
        )
    return "\n".join(lines)


def _template_guidance_notes(profile: TemplateProfile) -> str:
    notes: list[str] = []
    for s in profile.slides:
        if not _looks_like_guidance_layout(s):
            continue
        for p in s.placeholders:
            t = str(p.current_text or "").strip().replace("\n", " ")
            if not t:
                continue
            tl = t.lower()
            if any(k in tl for k in (
                "do not", "use", "avoid", "ensure", "font", "color", "contrast",
                "accessibility", "guides", "grid", "brand", "template"
            )):
                notes.append(t)

    # Stable de-dup
    uniq: list[str] = []
    seen: set[str] = set()
    for n in notes:
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(n)

    if not uniq:
        return "  - Follow template guidance for fonts, spacing, and accessibility."

    return "\n".join(f"  - {n[:180]}" for n in uniq[:10])


def _prompt_needs_chart(prompt: str) -> bool:
    q = (prompt or "").lower()
    keywords = [
        "chart", "graph", "trend", "growth", "revenue", "sales", "kpi", "metric",
        "quarter", "yoy", "forecast", "comparison", "performance", "data",
    ]
    hits = sum(1 for k in keywords if k in q)
    return hits >= 2


def _choose_best_layout(content_slides, used_indices: set[int], *, need_title: bool = False, need_chart: bool = False, need_table: bool = False):
    candidates = [s for s in content_slides if s.slide_index not in used_indices]
    if not candidates:
        candidates = list(content_slides)
    if not candidates:
        return None

    best = None
    best_score = -10**9

    for s in candidates:
        caps = _layout_capabilities(s)
        score = 0

        if need_title:
            score += 60 if caps["has_title"] else -30
        if need_chart:
            score += 90 if caps["has_chart"] else -45
        if need_table:
            score += 90 if caps["has_table"] else -45

        if not need_chart and caps["has_chart"]:
            score -= 8
        if not need_table and caps["has_table"]:
            score -= 5

        if caps["text_slots"] == 0 and not caps["has_chart"] and not caps["has_table"]:
            score -= 80

        score -= caps["compact_count"] * 3
        score -= s.slide_index / 1000.0

        if score > best_score:
            best_score = score
            best = s

    return best


def _adapt_outline_to_template(outline: list[dict], content_slides, prompt: str) -> list[dict]:
    """Deterministically adapt LLM outline to the best matching template variants."""
    if not outline:
        return outline

    by_idx = {s.slide_index: s for s in content_slides}
    allowed = set(by_idx.keys())

    adapted: list[dict] = []
    used: set[int] = set()

    for pos, item in enumerate(outline):
        current = int(item.get("template_slide_index", -1))
        stype = str(item.get("slide_type", "content")).lower()

        need_title = pos == 0 or any(k in stype for k in ("title", "opening", "cover"))
        need_chart = "chart" in stype
        need_table = "table" in stype

        valid = current in allowed and current not in used
        if valid:
            caps = _layout_capabilities(by_idx[current])
            if need_title and not caps["has_title"]:
                valid = False
            if need_chart and not caps["has_chart"]:
                valid = False
            if need_table and not caps["has_table"]:
                valid = False

        if not valid:
            pick = _choose_best_layout(
                content_slides,
                used,
                need_title=need_title,
                need_chart=need_chart,
                need_table=need_table,
            )
            if pick is not None:
                current = pick.slide_index

        used.add(current)
        updated = dict(item)
        updated["template_slide_index"] = int(current)
        adapted.append(updated)

    # Ensure opener is title-capable.
    if adapted:
        first_idx = int(adapted[0].get("template_slide_index", -1))
        first_layout = by_idx.get(first_idx)
        if not first_layout or not _layout_capabilities(first_layout)["has_title"]:
            title_pick = _choose_best_layout(content_slides, set(), need_title=True)
            if title_pick is not None:
                adapted[0]["template_slide_index"] = title_pick.slide_index

    # Ensure at least one chart layout when prompt is data-driven.
    if _prompt_needs_chart(prompt):
        has_chart_slide = any(
            _layout_capabilities(by_idx[int(it.get("template_slide_index", -1))])["has_chart"]
            for it in adapted
            if (not _is_closing_outline_item(it)) and int(it.get("template_slide_index", -1)) in by_idx
        )
        if not has_chart_slide:
            chart_pick = _choose_best_layout(content_slides, set(int(it.get("template_slide_index", -1)) for it in adapted), need_chart=True)
            if chart_pick is not None and adapted:
                replace_at = len(adapted) - 1
                if _is_closing_outline_item(adapted[-1]):
                    replace_at = max(0, len(adapted) - 2)
                adapted[replace_at]["template_slide_index"] = chart_pick.slide_index
                adapted[replace_at]["slide_type"] = "chart_bar"
                if not str(adapted[replace_at].get("purpose", "")).strip():
                    adapted[replace_at]["purpose"] = "Data-driven chart slide aligned to the prompt."

    # Final pass: unique indices where possible.
    used_final: set[int] = set()
    for i, it in enumerate(adapted):
        idx = int(it.get("template_slide_index", -1))
        if idx in used_final:
            stype = str(it.get("slide_type", "content")).lower()
            repl = _choose_best_layout(
                content_slides,
                used_final,
                need_title=(i == 0 or "title" in stype),
                need_chart=("chart" in stype),
                need_table=("table" in stype),
            )
            if repl is not None:
                idx = repl.slide_index
                it["template_slide_index"] = idx
        used_final.add(idx)

    # Keep closing slides on non-specialized layouts where possible.
    # If a closing slide ended up on a chart/table layout, swap that layout
    # onto a non-closing content slide that can absorb it.
    for ci, item in enumerate(adapted):
        if not _is_closing_outline_item(item):
            continue
        c_idx = int(item.get("template_slide_index", -1))
        c_layout = by_idx.get(c_idx)
        if not c_layout:
            continue
        c_caps = _layout_capabilities(c_layout)
        if not (c_caps["has_chart"] or c_caps["has_table"]):
            continue

        swap_at = None
        for j in range(max(0, ci - 1), -1, -1):
            cand = adapted[j]
            if _is_closing_outline_item(cand):
                continue
            cand_idx = int(cand.get("template_slide_index", -1))
            cand_layout = by_idx.get(cand_idx)
            if not cand_layout:
                continue
            cand_caps = _layout_capabilities(cand_layout)
            cand_type = str(cand.get("slide_type", "")).lower()
            if "chart" in cand_type or "table" in cand_type:
                continue
            if cand_caps["has_chart"] or cand_caps["has_table"]:
                continue
            swap_at = j
            break

        if swap_at is None:
            continue

        src_idx = int(adapted[swap_at]["template_slide_index"])
        adapted[swap_at]["template_slide_index"] = c_idx
        adapted[ci]["template_slide_index"] = src_idx

        moved_caps = _layout_capabilities(by_idx.get(c_idx))
        moved_type = str(adapted[swap_at].get("slide_type", "")).lower()
        if moved_caps["has_chart"] and "chart" not in moved_type:
            adapted[swap_at]["slide_type"] = "chart_bar"
        elif moved_caps["has_table"] and "table" not in moved_type:
            adapted[swap_at]["slide_type"] = "table"

    return adapted


def _profile_summary(profile: TemplateProfile) -> str:
    """Build a compact summary of the template profile for the outline prompt."""
    content_slides = _usable_content_slides(profile)
    lines = [
        f"Template: {profile.name}",
        f"Total slides: {profile.total_slides} ({len(content_slides)} usable content layouts)",
        f"Theme fonts: {profile.theme.fonts.major_font} (headings) / {profile.theme.fonts.minor_font} (body)",
        f"Brand tone: {profile.brand_rules.tone}",
        "",
        "Guidance from template instruction slides:",
        _template_guidance_notes(profile),
        "",
        "Content layout slides available:",
    ]
    for s in content_slides:
        caps = _layout_capabilities(s)
        ph_types = ", ".join(p.type for p in s.placeholders) or "no_placeholders"
        lines.append(
            f"  - index={s.slide_index}: placeholders=[{ph_types}], "
            f"title={caps['has_title']}, chart={caps['has_chart']}, table={caps['has_table']}, "
            f"compact_labels={caps['compact_count']}"
        )
    return "\n".join(lines)


def _slide_details_for_single(profile: TemplateProfile, outline_item: dict) -> str:
    """Build strict layout constraints for one slide prompt."""
    idx = int(outline_item.get("template_slide_index", -1))
    layout = next((s for s in profile.slides if s.slide_index == idx), None)
    if not layout:
        return f"Layout index {idx} not found in template profile."

    slide_type = outline_item.get("slide_type", "unknown")
    lines = [
        f"[Slide type={slide_type}, template_index={idx}]",
        f"Purpose: {outline_item.get('purpose', '')}",
    ]

    for ph in layout.placeholders:
        font_pt = ph.text_style.font_size_pt if ph.text_style.font_size_pt > 0 else 0.0
        font_family = ph.text_style.font_family or "theme/default"
        lines.append(
            f"  Placeholder idx={ph.idx} ({ph.type} '{ph.name}'): "
            f"font={font_pt:.1f}pt, family={font_family}, "
            f"max_chars={ph.max_chars_estimate}, REPLACE_THIS_TEXT='{ph.current_text[:40]}'"
        )

    for ch in layout.charts:
        lines.append(
            f"  Chart: type={ch.chart_type}, series_count={ch.series_count}, "
            f"category_count={ch.category_count}, categories={ch.categories}"
        )

    for tb in layout.tables:
        lines.append(f"  Table: {tb.rows} rows x {tb.cols} cols, headers={tb.header_row}")

    return "\n".join(lines)


def _is_closing_outline_item(item: dict) -> bool:
    slide_type = str(item.get("slide_type", "")).strip().lower().replace("_", " ").replace("-", " ")
    purpose = str(item.get("purpose", "")).strip().lower()

    closing_markers = {
        "closing",
        "closing slide",
        "thank you",
        "thankyou",
        "thanks",
        "q a",
        "qa",
        "questions",
    }

    if slide_type in closing_markers:
        return True
    if any(marker in purpose for marker in ("thank you", "thanks", "q&a", "questions", "closing")):
        return True
    return False


def _reorder_outline_for_closing(outline: list[dict]) -> list[dict]:
    """Force closing/thank-you slides to the end of the deck sequence."""
    non_closing = [item for item in outline if not _is_closing_outline_item(item)]
    closing = [item for item in outline if _is_closing_outline_item(item)]
    return non_closing + closing


def _parse_outline(raw: str) -> list[dict]:
    """Parse and validate outline JSON array from LLM."""
    try:
        outline = json.loads(raw)
    except json.JSONDecodeError:
        from json_repair import repair_json

        outline = json.loads(repair_json(raw))
        logger.warning("[plan_outline] Used json_repair to fix malformed JSON")

    if not isinstance(outline, list):
        raise ValueError("Outline must be a JSON array")

    normalized: list[dict] = []
    for i, item in enumerate(outline):
        if not isinstance(item, dict):
            raise ValueError(f"Outline item {i} is not an object")
        parsed = SlideOutlineItem(**item)
        normalized.append(parsed.model_dump())

    return normalized


def _parse_single_slide_item(raw: str, outline_item: dict) -> SlidePlanItem:
    """Parse one slide item from LLM output."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        from json_repair import repair_json

        data = json.loads(repair_json(raw))
        logger.warning("[plan_single_slide] Used json_repair to fix malformed JSON")

    if not isinstance(data, dict):
        raise ValueError("Single-slide output must be a JSON object")

    item_data: dict
    if "slide" in data and isinstance(data["slide"], dict):
        item_data = data["slide"]
    elif all(key in data for key in ("slide_type", "template_slide_index", "purpose", "content")):
        item_data = data
    elif "slides" in data and isinstance(data["slides"], list) and data["slides"]:
        if not isinstance(data["slides"][0], dict):
            raise ValueError("First element in 'slides' is not an object")
        item_data = data["slides"][0]
    else:
        raise ValueError("Could not find slide item in model output")

    expected_slide_type = str(outline_item.get("slide_type", "")).strip()
    expected_template_index = int(outline_item.get("template_slide_index", 0))
    expected_purpose = str(outline_item.get("purpose", "")).strip()

    # Lock structural fields to the outline item so per-slide generation
    # can never drift deck ordering or assigned layout.
    item_data["slide_type"] = expected_slide_type or str(item_data.get("slide_type", "content"))
    item_data["template_slide_index"] = expected_template_index
    item_data["purpose"] = expected_purpose or str(item_data.get("purpose", ""))

    normalized_wrapper = _sanitize_plan_data({"slides": [item_data]})
    normalized_item = normalized_wrapper["slides"][0]
    return SlidePlanItem(**normalized_item)


async def load_profile_node(state: PipelineState) -> dict:
    """Load template profile and binary from MongoDB/GridFS."""
    from app.database import get_db, get_template_bucket
    from app.tools.storage import retrieve_template_binary
    from bson import ObjectId

    template_id = state["template_id"]
    db = get_db()
    bucket = get_template_bucket()

    doc = await db.template_profiles.find_one({"_id": ObjectId(template_id)})
    if not doc:
        return {
            "status": "failed",
            "error": f"Template {template_id} not found in database.",
            "stage": "load_profile",
            "progress": 0,
        }

    if doc.get("status") != "ready":
        return {
            "status": "failed",
            "error": f"Template {template_id} is not ready (status={doc.get('status')}).",
            "stage": "load_profile",
            "progress": 0,
        }

    template_file_id = doc.get("template_file_id")
    template_bytes = b""
    if template_file_id:
        try:
            template_bytes = await retrieve_template_binary(template_file_id, bucket)
        except Exception as e:
            logger.warning(f"Could not load template binary {template_file_id}: {e}")

    return {
        "status": "running",
        "stage": "load_profile",
        "progress": 10,
        "message": f"Loaded template '{doc.get('name')}' ({doc.get('total_slides', 0)} slides)",
        "profile": doc.get("profile", {}),
        "template_bytes": template_bytes,
    }


async def plan_outline_node(state: PipelineState) -> dict:
    """Plan presentation structure once, then fan out by slide."""
    profile = TemplateProfile(**state["profile"])
    prompt_template = _load_prompt("planner_outline.txt")

    content_slides = _usable_content_slides(profile)
    if not content_slides:
        return {
            "status": "failed",
            "error": "Template has no usable content layouts.",
            "stage": "plan_outline",
            "progress": 15,
        }

    available_layouts = _format_available_layouts(content_slides)
    guidance_notes = _template_guidance_notes(profile)

    formatting_lines = "\n".join(f"  - {r}" for r in profile.brand_rules.formatting) or "  - Use clear, concise language"

    prompt = prompt_template.format(
        profile_summary=_profile_summary(profile),
        template_guidance=guidance_notes,
        user_prompt=state["prompt"],
        tone=profile.brand_rules.tone,
        formatting=formatting_lines,
        min_slides=3,
        max_slides=min(20, len(content_slides)),
        available_layouts=available_layouts,
    )

    llm = _get_planner_llm()
    try:
        response = await _invoke_with_retry(
            llm,
            [
                SystemMessage(content="You are an expert presentation architect. Return only valid JSON as instructed."),
                HumanMessage(content=prompt),
            ],
        )
        raw = _strip_json_fences(response.content)
        logger.info(f"[plan_outline] LLM raw response: {raw[:600]}")
        outline = _parse_outline(raw)
        outline = _reorder_outline_for_closing(outline)
        outline = _adapt_outline_to_template(outline, content_slides, state["prompt"])

        if not outline:
            raise ValueError("Outline is empty")

        allowed_layout_indices = {s.slide_index for s in content_slides}
        invalid_indices = [
            item.get("template_slide_index") for item in outline
            if int(item.get("template_slide_index", -1)) not in allowed_layout_indices
        ]
        if invalid_indices:
            raise ValueError(
                f"Outline used non-allowed template slide indices: {sorted(set(int(i) for i in invalid_indices))}"
            )
    except Exception as e:
        logger.error(f"plan_outline failed: {e}")
        return {
            "status": "failed",
            "error": f"Outline planning failed: {e}",
            "stage": "plan_outline",
            "progress": 15,
        }

    return {
        "slide_outline": outline,
        "stage": "plan_outline",
        "progress": 25,
        "message": f"Planned {len(outline)}-slide presentation structure",
    }


async def plan_single_slide_node(state: PipelineState) -> dict:
    """Generate and validate one slide with slide-local retries only."""
    settings = get_settings()
    profile = TemplateProfile(**state["profile"])
    outline_item = state["outline_item"]
    slide_index = int(state["slide_index"])
    total_slides = len(state.get("slide_outline", [])) or 1

    prompt_template = _load_prompt("planner_single_slide.txt")
    brand = profile.brand_rules
    font_rules = (
        f"Headings: {brand.font_rules.headings or 'Keep template heading size; <= 6 words'}\n"
        f"Body: {brand.font_rules.body or 'Keep template body size; concise phrasing'}\n"
        f"Bullets: {brand.font_rules.bullets or 'max 5 bullets; short phrase per bullet'}"
    )
    slide_position = slide_index + 1

    llm = _get_planner_llm()
    max_retries = settings.max_retries
    error_context = ""
    last_item: SlidePlanItem | None = None
    last_validation: dict | None = None

    for attempt in range(max_retries + 1):
        prompt = prompt_template.format(
            user_prompt=state["prompt"],
            tone=brand.tone,
            font_rules=font_rules,
            color_rules=brand.color_rules or "Use brand primary colors",
            formatting="\n".join(f"  - {r}" for r in brand.formatting) or "  - Use clear, concise language",
            restrictions="\n".join(f"  - {r}" for r in brand.restrictions) or "  - No clip art",
            full_outline=json.dumps(state.get("slide_outline", []), indent=2),
            outline_item=json.dumps(outline_item, indent=2),
            slide_position=slide_position,
            total_slides=total_slides,
            slide_details=_slide_details_for_single(profile, outline_item),
            error_context=f"\n## ERRORS TO FIX\n{error_context}" if error_context else "",
        )

        try:
            response = await _invoke_with_retry(
                llm,
                [
                    SystemMessage(content="You are an expert business presentation writer. Return only valid JSON as instructed."),
                    HumanMessage(content=prompt),
                ],
            )
            raw = _strip_json_fences(response.content)
            logger.info(f"[plan_single_slide] idx={slide_index} attempt={attempt+1}: {raw[:400]}")
            item = _parse_single_slide_item(raw, outline_item)

            backfilled = _backfill_missing_text_placeholders(SlidePlan(slides=[item]), profile)
            item = backfilled.slides[0]

            validation = validate_single_slide(item, profile)
            last_item = item
            last_validation = validation

            if validation["valid"]:
                break

            error_context = validation.get("retry_context", "") or "Slide validation failed"
        except Exception as e:
            logger.warning(f"plan_single_slide idx={slide_index} attempt={attempt+1} failed: {e}")
            error_context = str(e)

    if last_item is None:
        last_item = SlidePlanItem(
            slide_type=str(outline_item.get("slide_type", "content")),
            template_slide_index=int(outline_item.get("template_slide_index", 0)),
            purpose=str(outline_item.get("purpose", "")),
            content={"placeholders": {}},
        )
        last_validation = validate_single_slide(last_item, profile)

    attempts_used = max_retries + 1 if not (last_validation and last_validation.get("valid")) else (attempt + 1)
    valid_flag = bool(last_validation and last_validation.get("valid"))

    return {
        "completed_slides": [
            {
                "slide_index": slide_index,
                "item": last_item.model_dump(),
                "valid": valid_flag,
                "attempts": attempts_used,
                "errors": (last_validation or {}).get("errors", []),
            }
        ],
    }


async def aggregate_node(state: PipelineState) -> dict:
    """Collect per-slide outputs and construct final ordered SlidePlan."""
    completed = state.get("completed_slides", [])
    if not completed:
        return {
            "status": "failed",
            "error": "No slides were generated during fan-out.",
            "stage": "aggregate",
            "progress": 70,
        }

    sorted_items = sorted(completed, key=lambda x: x.get("slide_index", 0))

    slide_items: list[SlidePlanItem] = []
    outline_indices: list[int] = []
    invalid_count = 0
    max_attempts = 0

    for entry in sorted_items:
        outline_indices.append(int(entry.get("slide_index", 0)))
        max_attempts = max(max_attempts, int(entry.get("attempts", 1)))
        if not entry.get("valid", True):
            invalid_count += 1

        try:
            slide_items.append(SlidePlanItem(**entry["item"]))
        except Exception as e:
            logger.warning(f"aggregate: skipping invalid slide item at index {entry.get('slide_index')}: {e}")

    if not slide_items:
        return {
            "status": "failed",
            "error": "All per-slide results were invalid after aggregation.",
            "stage": "aggregate",
            "progress": 70,
        }

    slide_plan = SlidePlan(
        metadata={
            "prompt": state["prompt"],
            "total_slides": len(slide_items),
            "outline_indices": outline_indices,
        },
        slides=slide_items,
    )

    return {
        "slide_plan": slide_plan.model_dump(),
        "stage": "aggregate",
        "progress": 72,
        "message": (
            f"Aggregated {len(slide_items)} slides "
            f"({invalid_count} best-effort, max attempts per slide: {max_attempts})"
        ),
    }


async def aggregate_validation_node(state: PipelineState) -> dict:
    """Deck-level validation after per-slide fan-in."""
    slide_plan = SlidePlan(**state["slide_plan"])
    outline = state.get("slide_outline", [])
    result = validate_aggregate_plan(slide_plan, outline)

    if not result["valid"]:
        return {
            "status": "failed",
            "validation_result": result,
            "error": f"Aggregate validation failed: {len(result['errors'])} error(s)",
            "stage": "aggregate_validation",
            "progress": 78,
            "message": "Deck-level validation failed",
        }

    return {
        "validation_result": result,
        "stage": "aggregate_validation",
        "progress": 78,
        "message": "Deck-level validation passed",
    }


async def render_node(state: PipelineState) -> dict:
    """Render the PPTX using python-pptx."""
    slide_plan = SlidePlan(**state["slide_plan"])
    template_bytes = state.get("template_bytes", b"")

    if not template_bytes:
        return {
            "status": "failed",
            "error": "Template binary not available for rendering.",
            "stage": "render",
            "progress": 82,
        }

    try:
        pptx_bytes, slide_count = await render_pptx(
            plan=slide_plan,
            template_id=state["template_id"],
            template_bytes=template_bytes,
        )
    except Exception as e:
        logger.error(f"render_pptx failed: {e}")
        return {
            "status": "failed",
            "error": f"Rendering failed: {e}",
            "stage": "render",
            "progress": 82,
        }

    return {
        "pptx_bytes": pptx_bytes,
        "slide_count": slide_count,
        "stage": "render",
        "progress": 90,
        "message": f"Rendered {slide_count}-slide presentation ({len(pptx_bytes):,} bytes)",
    }


async def store_node(state: PipelineState) -> dict:
    """Store the rendered PPTX in GridFS and persist the generation record."""
    from datetime import datetime, timezone

    from bson import ObjectId

    from app.database import get_db, get_generated_bucket
    from app.tools.storage import store_generated_pptx

    generation_id = state["generation_id"]
    pptx_bytes = state["pptx_bytes"]
    db = get_db()
    bucket = get_generated_bucket()

    try:
        file_id = await store_generated_pptx(pptx_bytes, generation_id, bucket)
    except Exception as e:
        logger.error(f"GridFS store failed: {e}")
        return {
            "status": "failed",
            "error": f"Storage failed: {e}",
            "stage": "store",
            "progress": 95,
        }

    await db.generations.update_one(
        {"_id": ObjectId(generation_id)},
        {
            "$set": {
                "output_file_id": file_id,
                "slides_generated": state.get("slide_count", 0),
                "output_size_bytes": len(pptx_bytes),
                "completed_at": datetime.now(timezone.utc),
            }
        },
    )

    return {
        "output_file_id": file_id,
        "status": "completed",
        "stage": "store",
        "progress": 100,
        "message": "Presentation ready for download",
    }
