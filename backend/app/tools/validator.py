"""
Deterministic Validator — Phase 4
Pure Python validation of a SlidePlan against a TemplateProfile.
No LLM calls. Produces structured, actionable error feedback for the planner to fix.
"""

import logging

from app.schemas.slide_plan import SlidePlan, SlidePlanItem
from app.schemas.template_profile import SlideLayout, TemplateProfile

logger = logging.getLogger(__name__)


def _find_slide_layout(profile: TemplateProfile, slide_index: int) -> SlideLayout | None:
    """Look up a slide layout by index."""
    for slide in profile.slides:
        if slide.slide_index == slide_index:
            return slide
    return None


_FILLER_TEXT_PATTERNS = [
    "lorem ipsum",
    "sed ut perspiciatis",
    "topic 1",
    "optional eyebrow",
    "subheadline",
    "eiludusponderium",
    "bullet point text",
    "presentation subtitle",
    "presenter name",
    "presentation title",
    "delete before use",
    "source: lorem ipsum",
]


def _is_filler_text(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(p in t for p in _FILLER_TEXT_PATTERNS)


def _is_compact_placeholder(layout_ph) -> bool:
    """Identify compact placeholders (e.g. circular callouts / eyebrow labels)."""
    pos = layout_ph.position
    width = pos.width_emu or 0
    height = pos.height_emu or 0
    if width <= 0 or height <= 0:
        return False

    ratio = max(width, height) / max(1, min(width, height))
    if width < 700_000 or height < 400_000:
        return True
    if ratio < 1.25 and max(width, height) < 2_200_000:
        return True
    if layout_ph.max_chars_estimate <= 18:
        return True
    return False


def _flatten_text_value(value: str | list[str]) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value if str(v).strip())
    return str(value)


def _validate_char_limits(item: SlidePlanItem, layout: SlideLayout) -> list[dict]:
    """Check that all placeholder texts fit within max_chars_estimate."""
    errors = []
    ph_map = {str(ph.idx): ph for ph in layout.placeholders}

    for ph_key, text_value in item.content.placeholders.items():
        ph = ph_map.get(str(ph_key))
        if ph is None:
            continue  # unknown idx — not a hard error

        if ph.max_chars_estimate <= 0:
            continue  # no limit set

        if isinstance(text_value, list):
            # Bullets: check each line
            for i, bullet in enumerate(text_value):
                if len(bullet) > ph.max_chars_estimate:
                    errors.append({
                        "slide_index": item.template_slide_index,
                        "field": f"placeholders.{ph_key}[{i}]",
                        "message": (
                            f"Bullet {i} has {len(bullet)} chars but placeholder "
                            f"'{ph.name}' (idx={ph.idx}) allows max {ph.max_chars_estimate}. "
                            f"Shorten to <= {ph.max_chars_estimate} characters."
                        ),
                    })
        else:
            text = str(text_value)
            if len(text) > ph.max_chars_estimate:
                errors.append({
                    "slide_index": item.template_slide_index,
                    "field": f"placeholders.{ph_key}",
                    "message": (
                        f"Text has {len(text)} chars but placeholder "
                        f"'{ph.name}' (idx={ph.idx}) allows max {ph.max_chars_estimate}. "
                        f"Shorten to <= {ph.max_chars_estimate} characters."
                    ),
                })

        # Compact callout placeholders need very concise copy to prevent overflow.
        if _is_compact_placeholder(ph):
            compact_text = _flatten_text_value(text_value).strip()
            if isinstance(text_value, list) and len(text_value) > 1:
                errors.append({
                    "slide_index": item.template_slide_index,
                    "field": f"placeholders.{ph_key}",
                    "message": (
                        f"Compact placeholder '{ph.name}' (idx={ph.idx}) should be a short phrase, not a bullet list."
                    ),
                })
            if compact_text:
                word_count = len([w for w in compact_text.split() if w])
                if word_count > 4:
                    errors.append({
                        "slide_index": item.template_slide_index,
                        "field": f"placeholders.{ph_key}",
                        "message": (
                            f"Compact placeholder '{ph.name}' (idx={ph.idx}) has {word_count} words. "
                            f"Use <= 4 words to avoid overflow in small/circular callouts."
                        ),
                    })
    return errors


def _validate_chart(item: SlidePlanItem, layout: SlideLayout) -> list[dict]:
    """Validate chart data matches template chart structure."""
    errors = []
    if not layout.charts or not item.content.chart_data:
        return errors

    template_chart = layout.charts[0]  # validate against first chart
    plan_chart = item.content.chart_data

    # Check series count
    plan_series_count = len(plan_chart.series)
    if plan_series_count != template_chart.series_count and template_chart.series_count > 0:
        errors.append({
            "slide_index": item.template_slide_index,
            "field": "chart_data.series",
            "message": (
                f"Chart expects {template_chart.series_count} series but got {plan_series_count}. "
                f"Adjust to exactly {template_chart.series_count} series."
            ),
        })

    # Check category count
    plan_cat_count = len(plan_chart.categories)
    if plan_cat_count != template_chart.category_count and template_chart.category_count > 0:
        errors.append({
            "slide_index": item.template_slide_index,
            "field": "chart_data.categories",
            "message": (
                f"Chart expects {template_chart.category_count} categories but got {plan_cat_count}. "
                f"Adjust to exactly {template_chart.category_count} categories."
            ),
        })

    # Check each series has correct value count
    for i, series in enumerate(plan_chart.series):
        if template_chart.category_count > 0 and len(series.values) != template_chart.category_count:
            errors.append({
                "slide_index": item.template_slide_index,
                "field": f"chart_data.series[{i}].values",
                "message": (
                    f"Series '{series.name}' has {len(series.values)} values but needs "
                    f"{template_chart.category_count} (one per category). "
                    f"Use null for missing/future values."
                ),
            })

    # Pie chart: check values sum to ~100
    if "PIE" in template_chart.chart_type.upper():
        for i, series in enumerate(plan_chart.series):
            non_null = [v for v in series.values if v is not None]
            if non_null:
                total = sum(non_null)
                if not (99.0 <= total <= 101.0):
                    errors.append({
                        "slide_index": item.template_slide_index,
                        "field": f"chart_data.series[{i}].values",
                        "message": (
                            f"Pie chart series '{series.name}' values sum to {total:.1f} but must sum to 100. "
                            f"Adjust values to total exactly 100."
                        ),
                    })

    return errors


def _validate_required_fields(item: SlidePlanItem, layout: SlideLayout) -> list[dict]:
    """Check that required TITLE placeholders are populated, and that non-compact
    body/text placeholders whose template text is filler are also replaced."""
    errors = []

    for ph in layout.placeholders:
        val = item.content.placeholders.get(str(ph.idx))
        is_empty = not val or (isinstance(val, str) and not val.strip()) or (
            isinstance(val, list) and not any(str(v).strip() for v in val)
        )

        # Title placeholders are always required.
        if ph.type in ("TITLE", "CENTER_TITLE") and ph.max_chars_estimate > 0:
            if is_empty:
                errors.append({
                    "slide_index": item.template_slide_index,
                    "field": f"placeholders.{ph.idx}",
                    "message": (
                        f"Required placeholder '{ph.name}' (type={ph.type}, idx={ph.idx}) "
                        f"is missing or empty. Please provide a title."
                    ),
                })

        # Non-compact text placeholders that contain template filler (lorem ipsum etc.) MUST be replaced.
        elif (
            ph.type not in {"DATE", "SLIDE_NUMBER", "FOOTER", "PICTURE", "CHART", "TABLE", "SMART_ART", "MEDIA", "OBJECT"}
            and not _is_compact_placeholder(ph)
            and _is_filler_text(ph.current_text)
        ):
            if is_empty:
                errors.append({
                    "slide_index": item.template_slide_index,
                    "field": f"placeholders.{ph.idx}",
                    "message": (
                        f"Placeholder '{ph.name}' (type={ph.type}, idx={ph.idx}) contains template filler text "
                        f"('{ph.current_text[:50]}...'). You MUST replace it with real content relevant to the slide "
                        f"purpose. Do not omit this placeholder key from your JSON output."
                    ),
                })

    return errors


def _validate_bullet_count(item: SlidePlanItem) -> list[dict]:
    """Warn if bullet count exceeds 5."""
    warnings = []
    for ph_key, val in item.content.placeholders.items():
        if isinstance(val, list) and len(val) > 5:
            warnings.append({
                "slide_index": item.template_slide_index,
                "field": f"placeholders.{ph_key}",
                "message": (
                    f"Placeholder idx={ph_key} has {len(val)} bullets. "
                    f"Brand guidelines recommend max 5 bullets per slide."
                ),
            })
    return warnings


def validate_single_slide(item: SlidePlanItem, profile: TemplateProfile) -> dict:
    """Validate one slide item against its template layout."""
    errors: list[dict] = []
    warnings: list[dict] = []

    layout = _find_slide_layout(profile, item.template_slide_index)
    if layout is None:
        errors.append({
            "slide_index": item.template_slide_index,
            "field": "template_slide_index",
            "message": (
                f"Slide index {item.template_slide_index} does not exist in the template "
                f"(template has {profile.total_slides} slides, indices 0-{profile.total_slides-1}). "
                f"Choose a valid index."
            ),
        })
    elif layout.classification == "guidance":
        errors.append({
            "slide_index": item.template_slide_index,
            "field": "template_slide_index",
            "message": (
                f"Slide {item.template_slide_index} is a guidance slide and cannot be used for content. "
                f"Choose a content_layout slide instead."
            ),
        })
    else:
        errors.extend(_validate_required_fields(item, layout))
        errors.extend(_validate_char_limits(item, layout))
        errors.extend(_validate_chart(item, layout))
        warnings.extend(_validate_bullet_count(item))

    valid = len(errors) == 0
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "retry_context": _format_retry(errors) if not valid else "",
    }


def validate_aggregate_plan(plan: SlidePlan, outline: list[dict]) -> dict:
    """Deck-level validation after slide fan-in."""
    errors: list[dict] = []
    warnings: list[dict] = []

    if len(plan.slides) != len(outline):
        errors.append({
            "slide_index": -1,
            "field": "slides",
            "message": (
                f"Slide count mismatch: outline has {len(outline)} items but plan has {len(plan.slides)} slides."
            ),
        })

    seen_template_indices: set[int] = set()
    for item in plan.slides:
        if item.template_slide_index in seen_template_indices:
            errors.append({
                "slide_index": item.template_slide_index,
                "field": "template_slide_index",
                "message": (
                    f"Layout slide_index={item.template_slide_index} is assigned more than once in final plan."
                ),
            })
        seen_template_indices.add(item.template_slide_index)

    if outline:
        for pos, item in enumerate(plan.slides):
            if pos >= len(outline):
                break
            expected_idx = int(outline[pos].get("template_slide_index", -1))
            if item.template_slide_index != expected_idx:
                errors.append({
                    "slide_index": item.template_slide_index,
                    "field": "template_slide_index",
                    "message": (
                        f"Slide order drift at position {pos}: expected template_slide_index "
                        f"{expected_idx} from outline, got {item.template_slide_index}."
                    ),
                })

        expected = set(range(len(outline)))
        raw_indices = plan.metadata.get("outline_indices") if isinstance(plan.metadata, dict) else None
        if isinstance(raw_indices, list) and raw_indices:
            actual = {int(i) for i in raw_indices}
        else:
            actual = {i for i, _ in enumerate(plan.slides)}
        missing = sorted(expected - actual)
        if missing:
            errors.append({
                "slide_index": -1,
                "field": "slides",
                "message": f"Missing slide positions after aggregation: {missing}",
            })

    valid = len(errors) == 0
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "retry_context": _format_retry(errors) if not valid else "",
    }


def validate_slide_plan(plan: SlidePlan, profile: TemplateProfile) -> dict:
    """
    Backward-compatible full-plan validator.
    Combines per-slide checks and non-blocking duplicate warnings.
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    if not plan.slides:
        errors.append({"slide_index": -1, "field": "slides", "message": "Slide plan is empty. Generate at least 3 slides."})
        return {"valid": False, "errors": errors, "warnings": warnings, "retry_context": _format_retry(errors)}

    if len(plan.slides) < 3:
        errors.append({
            "slide_index": -1,
            "field": "slides",
            "message": f"Only {len(plan.slides)} slides. A complete presentation needs at least 3 slides.",
        })

    seen_layout_indices: set[int] = set()
    for item in plan.slides:
        if item.template_slide_index in seen_layout_indices:
            errors.append({
                "slide_index": item.template_slide_index,
                "field": "template_slide_index",
                "message": (
                    f"Layout slide_index={item.template_slide_index} is assigned more than once in final plan."
                ),
            })
        seen_layout_indices.add(item.template_slide_index)

        single = validate_single_slide(item, profile)
        errors.extend(single["errors"])
        warnings.extend(single["warnings"])

    valid = len(errors) == 0
    retry_context = _format_retry(errors) if not valid else ""

    logger.info(f"Validation result: valid={valid}, errors={len(errors)}, warnings={len(warnings)}")

    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "retry_context": retry_context,
    }


def _format_retry(errors: list[dict]) -> str:
    """Format errors into a clear, structured string for the LLM retry prompt."""
    if not errors:
        return ""
    lines = ["The previous slide plan had the following validation errors that MUST be fixed:\n"]
    for i, err in enumerate(errors, 1):
        slide = f"Slide {err['slide_index']}" if err.get("slide_index", -1) >= 0 else "Global"
        lines.append(f"{i}. [{slide}] Field: {err.get('field', '?')} - {err['message']}")
    lines.append("\nPlease regenerate the slide plan fixing ALL of the above errors.")
    return "\n".join(lines)
