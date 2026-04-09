"""
Guidance Extractor — Phase 2
Uses Groq (llama-3.1-8b-instant) to:
1. Classify each slide as "guidance" or "content_layout"
2. Extract brand/tone/formatting rules from guidance slides
3. Build usable slide pool (content_layout slides only)
"""

import json
import logging

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.schemas.template_profile import BrandRules, FontRules, SlideLayout, TemplateProfile

logger = logging.getLogger(__name__)

# ─── Prompts ─────────────────────────────────────────────────────────────────

CLASSIFY_SYSTEM = """\
You are an expert PowerPoint template analyst.

Your job is to classify presentation slides into two categories:
- "guidance": Slides that contain instructions, branding guidelines, style notes, "how to use this template" instructions, tone examples, or rules for content creators. These are META slides about the template itself.
- "content_layout": Slides that are actual presentation layouts meant to be filled with real business content (title slides, agenda slides, data/chart slides, bullet point slides, divider slides, closing slides, etc.)

You will receive a description of slides (index, placeholder text, shape types).
Return a JSON array where each element is: {"slide_index": <int>, "classification": "guidance" | "content_layout", "reason": "<brief reason>"}
Return ONLY the JSON array, no extra text.
"""

BRAND_SYSTEM = """\
You are a brand analyst. You will receive text content from "guidance" slides of a PowerPoint template.
Extract brand and formatting rules. Return a JSON object with this exact structure:
{
  "tone": "<tone description>",
  "font_rules": {
    "headings": "<heading font rules>",
    "body": "<body font rules>",
    "bullets": "<bullet rules>"
  },
  "color_rules": "<color usage rules>",
  "formatting": ["<rule 1>", "<rule 2>", ...],
  "restrictions": ["<restriction 1>", "<restriction 2>", ...]
}
Return ONLY the JSON object, no extra text.
"""


def _slide_summary(slide: SlideLayout) -> str:
    """Build a text summary of a slide for the LLM to classify."""
    lines = [f"Slide index: {slide.slide_index}"]
    if slide.placeholders:
        texts = [f"  - [{p.type}] idx={p.idx}: '{p.current_text[:80]}'" for p in slide.placeholders]
        lines.append("Placeholders:\n" + "\n".join(texts))
    if slide.charts:
        lines.append(f"Charts: {len(slide.charts)} chart(s)")
    if slide.images:
        lines.append(f"Images: {len(slide.images)} image(s)")
    if slide.tables:
        lines.append(f"Tables: {len(slide.tables)} table(s)")
    return "\n".join(lines)


def _guidance_text(slide: SlideLayout) -> str:
    """Collect all text from a guidance slide for brand rule extraction."""
    texts = []
    for ph in slide.placeholders:
        if ph.current_text.strip():
            texts.append(ph.current_text.strip())
    return "\n".join(texts)


async def extract_guidance(profile: TemplateProfile) -> TemplateProfile:
    """
    Classify all slides in the profile and extract brand rules from guidance slides.
    Updates each SlideLayout.classification in-place.
    Returns the modified profile.
    """
    settings = get_settings()

    if not settings.groq_api_key:
        logger.warning("GROQ_API_KEY not set — keeping deterministic slide classifications from parser")
        profile.usable_layouts = len(profile.content_slides())
        return profile

    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.guidance_model,
        temperature=0.0,
        max_tokens=4096,
    )

    # ── Step 1: Classify slides ────────────────────────────────────────────
    batch_size = 20  # process in batches to avoid token limit
    all_classifications: dict[int, str] = {}

    for batch_start in range(0, len(profile.slides), batch_size):
        batch = profile.slides[batch_start: batch_start + batch_size]
        slides_text = "\n\n---\n\n".join(_slide_summary(s) for s in batch)

        try:
            response = await llm.ainvoke([
                SystemMessage(content=CLASSIFY_SYSTEM),
                HumanMessage(content=f"Classify these slides:\n\n{slides_text}"),
            ])
            raw = response.content.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            classifications = json.loads(raw)
            for item in classifications:
                all_classifications[item["slide_index"]] = item["classification"]
        except Exception as e:
            logger.warning(f"Classification batch {batch_start} failed: {e}. Defaulting to content_layout.")
            for s in batch:
                all_classifications[s.slide_index] = "content_layout"

    # Apply classifications, but keep deterministic parser-marked guidance slides as guidance
    for slide in profile.slides:
        if slide.classification == "guidance":
            continue
        slide.classification = all_classifications.get(slide.slide_index, "content_layout")

    guidance_slides = [s for s in profile.slides if s.classification == "guidance"]
    content_slides = [s for s in profile.slides if s.classification == "content_layout"]
    profile.usable_layouts = len(content_slides)

    logger.info(
        f"Classified {len(profile.slides)} slides: "
        f"{len(guidance_slides)} guidance, {len(content_slides)} content_layout"
    )

    # ── Step 2: Extract brand rules from guidance slides ───────────────────
    if guidance_slides:
        guidance_text = "\n\n---\n\n".join(
            f"[Slide {s.slide_index}]\n{_guidance_text(s)}"
            for s in guidance_slides
            if _guidance_text(s).strip()
        )

        if guidance_text.strip():
            try:
                response = await llm.ainvoke([
                    SystemMessage(content=BRAND_SYSTEM),
                    HumanMessage(content=f"Extract brand rules from these guidance slides:\n\n{guidance_text[:6000]}"),
                ])
                raw = response.content.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                brand_data = json.loads(raw)
                profile.brand_rules = BrandRules(
                    tone=brand_data.get("tone", "Professional"),
                    font_rules=FontRules(**brand_data.get("font_rules", {})),
                    color_rules=brand_data.get("color_rules", ""),
                    formatting=brand_data.get("formatting", []),
                    restrictions=brand_data.get("restrictions", []),
                )
                logger.info(f"Extracted brand rules: tone='{profile.brand_rules.tone}'")
            except Exception as e:
                logger.warning(f"Brand rule extraction failed: {e}. Using defaults.")
        else:
            logger.info("No text content found in guidance slides — using default brand rules.")
    else:
        logger.info("No guidance slides found — no brand rules extracted.")

    return profile
