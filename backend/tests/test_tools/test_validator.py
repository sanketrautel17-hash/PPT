"""
Extended unit tests for the deterministic validator.
No LLM calls, no DB — pure Python.
"""

import pytest

from app.schemas.slide_plan import ChartData, ChartSeries, SlideContent, SlidePlan, SlidePlanItem, TableData
from app.schemas.template_profile import (
    ChartMeta,
    Placeholder,
    PlaceholderPosition,
    SlideLayout,
    TableMeta,
    TemplateProfile,
)
from app.tools.validator import validate_slide_plan


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _ph(idx: int, ph_type: str = "BODY", max_chars: int = 100, name: str = "Text") -> Placeholder:
    return Placeholder(
        idx=idx,
        name=name,
        type=ph_type,
        max_chars_estimate=max_chars,
        current_text="",
        position=PlaceholderPosition(width_emu=5_000_000),
    )


def _title_ph(idx: int = 0, max_chars: int = 80) -> Placeholder:
    return _ph(idx=idx, ph_type="TITLE", max_chars=max_chars, name="Title")


def _slide(
    index: int,
    classification: str = "content_layout",
    placeholders: list[Placeholder] | None = None,
    charts: list[ChartMeta] | None = None,
    tables: list[TableMeta] | None = None,
) -> SlideLayout:
    return SlideLayout(
        slide_index=index,
        classification=classification,
        placeholders=placeholders or [_title_ph()],
        charts=charts or [],
        tables=tables or [],
    )


def _make_profile(slides: list[SlideLayout] | None = None) -> TemplateProfile:
    if slides is None:
        slides = [_slide(0), _slide(1), _slide(2)]
    return TemplateProfile(name="test_template", slides=slides, total_slides=len(slides))


def _item(
    index: int,
    slide_type: str = "bullet",
    placeholders: dict | None = None,
    chart_data: ChartData | None = None,
    table_data: TableData | None = None,
) -> SlidePlanItem:
    return SlidePlanItem(
        slide_type=slide_type,
        template_slide_index=index,
        purpose=f"Slide {index}",
        content=SlideContent(
            placeholders=placeholders or {"0": f"Title for slide {index}"},
            chart_data=chart_data,
            table_data=table_data,
        ),
    )


def _make_plan(items: list[SlidePlanItem]) -> SlidePlan:
    return SlidePlan(slides=items)


def _valid_3_item_plan() -> SlidePlan:
    return _make_plan([_item(0), _item(1), _item(2)])


# ─── 1. Empty plan ────────────────────────────────────────────────────────────

def test_empty_plan_is_invalid():
    result = validate_slide_plan(_make_plan([]), _make_profile())
    assert result["valid"] is False
    assert any("empty" in e["message"].lower() for e in result["errors"])


# ─── 2. Fewer than 3 slides ───────────────────────────────────────────────────

def test_two_slide_plan_is_invalid():
    """A plan with only 2 slides should fail."""
    plan = _make_plan([_item(0), _item(1)])
    result = validate_slide_plan(plan, _make_profile())
    assert result["valid"] is False
    assert any("3" in e["message"] for e in result["errors"])


# ─── 3. Missing required title ────────────────────────────────────────────────

def test_missing_required_title_fails():
    plan = _make_plan([
        SlidePlanItem(
            slide_type="title",
            template_slide_index=0,
            purpose="Opener",
            content=SlideContent(placeholders={}),  # no title
        ),
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, _make_profile())
    assert result["valid"] is False
    assert any("Required placeholder" in e["message"] for e in result["errors"])


def test_whitespace_only_title_fails():
    """A title with only whitespace counts as missing."""
    plan = _make_plan([
        SlidePlanItem(
            slide_type="title",
            template_slide_index=0,
            purpose="Opener",
            content=SlideContent(placeholders={"0": "   "}),
        ),
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, _make_profile())
    assert result["valid"] is False
    assert any("Required placeholder" in e["message"] for e in result["errors"])


# ─── 4. Char limit ────────────────────────────────────────────────────────────

def test_char_limit_exceeded_string_fails():
    """A single string exceeding max_chars_estimate should fail."""
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            placeholders=[_ph(idx=0, ph_type="TITLE", max_chars=30)],
        ),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(0, placeholders={"0": "A" * 50}),  # 50 chars > limit 30
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is False
    assert any("max" in e["message"].lower() for e in result["errors"])


def test_char_limit_exceeded_bullet_fails():
    """A bullet point exceeding the char limit should fail."""
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            placeholders=[_ph(idx=1, ph_type="BODY", max_chars=20)],
        ),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(0, placeholders={"1": ["This bullet is way too long for the placeholder"]}),
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is False
    assert any("max" in e["message"].lower() or "Bullet" in e["message"] for e in result["errors"])


def test_char_limit_exactly_at_max_passes():
    """Text exactly at the limit should pass."""
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            placeholders=[_ph(idx=0, ph_type="TITLE", max_chars=20)],
        ),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(0, placeholders={"0": "A" * 20}),  # exactly at limit
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is True


# ─── 5. Valid plan passes ─────────────────────────────────────────────────────

def test_valid_plan_passes():
    result = validate_slide_plan(_valid_3_item_plan(), _make_profile())
    assert result["valid"] is True
    assert result["errors"] == []


def test_valid_plan_has_no_retry_context():
    result = validate_slide_plan(_valid_3_item_plan(), _make_profile())
    assert result["retry_context"] == ""


# ─── 6. Duplicate layout index ────────────────────────────────────────────────

def test_duplicate_layout_index_fails():
    plan = _make_plan([
        _item(0),
        _item(0),  # duplicate!
        _item(2),
    ])
    result = validate_slide_plan(plan, _make_profile())
    assert result["valid"] is False
    assert any("more than once" in e["message"] for e in result["errors"])


# ─── 7. Guidance slide rejection ─────────────────────────────────────────────

def test_guidance_slide_rejected():
    profile = _make_profile([
        _slide(0, classification="guidance"),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(0),  # tries to use guidance slide
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is False
    assert any("guidance" in e["message"].lower() for e in result["errors"])


# ─── 8. Non-existent slide index ─────────────────────────────────────────────

def test_out_of_range_slide_index_fails():
    """Using a slide_index that doesn't exist in the template → error."""
    profile = _make_profile([_slide(0), _slide(1), _slide(2)])
    plan = _make_plan([
        _item(0), _item(1),
        _item(99),  # index 99 doesn't exist
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is False
    assert any("does not exist" in e["message"] for e in result["errors"])


# ─── 9. Chart — series count mismatch ────────────────────────────────────────

def test_chart_series_count_mismatch_fails():
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            charts=[ChartMeta(shape_index=1, chart_type="BAR_CLUSTERED", series_count=2, category_count=4)],
        ),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(
            0,
            chart_data=ChartData(
                categories=["Q1", "Q2", "Q3", "Q4"],
                series=[ChartSeries(name="2025", values=[10, 20, 30, 40])],  # only 1, need 2
            ),
        ),
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is False
    assert any("series" in e["message"].lower() for e in result["errors"])


def test_chart_category_count_mismatch_fails():
    """Wrong number of categories in chart data → fails validation."""
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            charts=[ChartMeta(shape_index=1, chart_type="LINE", series_count=1, category_count=4)],
        ),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(
            0,
            chart_data=ChartData(
                categories=["Q1", "Q2"],  # only 2, need 4
                series=[ChartSeries(name="Revenue", values=[10, 20])],
            ),
        ),
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is False
    assert any("categor" in e["message"].lower() for e in result["errors"])


def test_chart_correct_data_passes():
    """Matching series+category counts → passes."""
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            charts=[ChartMeta(shape_index=1, chart_type="BAR_CLUSTERED", series_count=2, category_count=3)],
        ),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(
            0,
            chart_data=ChartData(
                categories=["A", "B", "C"],
                series=[
                    ChartSeries(name="2024", values=[10, 20, 30]),
                    ChartSeries(name="2025", values=[15, 25, 35]),
                ],
            ),
        ),
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is True


# ─── 10. PIE chart sum check ─────────────────────────────────────────────────

def test_pie_chart_values_not_summing_to_100_fails():
    """Pie chart series values must sum to ~100."""
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            charts=[ChartMeta(shape_index=1, chart_type="PIE", series_count=1, category_count=3)],
        ),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(
            0,
            chart_data=ChartData(
                categories=["A", "B", "C"],
                series=[ChartSeries(name="Share", values=[10, 20, 30])],  # sums to 60, not 100
            ),
        ),
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is False
    assert any("100" in e["message"] for e in result["errors"])


def test_pie_chart_values_summing_to_100_passes():
    """Pie chart series values summing to 100 should pass."""
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            charts=[ChartMeta(shape_index=1, chart_type="PIE", series_count=1, category_count=3)],
        ),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(
            0,
            chart_data=ChartData(
                categories=["A", "B", "C"],
                series=[ChartSeries(name="Share", values=[30.0, 40.0, 30.0])],  # sums to 100
            ),
        ),
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is True


# ─── 11. Bullet count warning ────────────────────────────────────────────────

def test_too_many_bullets_generates_warning():
    """More than 5 bullets should produce a warning (not an error)."""
    plan = _make_plan([
        _item(0, placeholders={"0": "Title", "1": [f"Bullet {i}" for i in range(8)]}),
        _item(1), _item(2),
    ])
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            placeholders=[_title_ph(idx=0), _ph(idx=1, ph_type="BODY", max_chars=500)],
        ),
        _slide(1), _slide(2),
    ])
    result = validate_slide_plan(plan, profile)
    # should still be valid (warning, not error)
    assert len(result["warnings"]) >= 1
    assert any("bullets" in w["message"].lower() or "brand" in w["message"].lower() for w in result["warnings"])


# ─── 12. Retry context format ────────────────────────────────────────────────

def test_invalid_plan_produces_retry_context():
    """An invalid plan must produce a non-empty retry_context string for the LLM."""
    plan = _make_plan([])  # empty → invalid
    result = validate_slide_plan(plan, _make_profile())
    assert result["valid"] is False
    assert len(result["retry_context"]) > 0
    assert "MUST be fixed" in result["retry_context"] or "error" in result["retry_context"].lower()


def test_retry_context_lists_all_errors():
    """Each error should appear in the retry_context."""
    plan = _make_plan([_item(0), _item(0), _item(2)])  # duplicate index → 1 error + maybe warnings
    result = validate_slide_plan(plan, _make_profile())
    if not result["valid"]:
        for err in result["errors"]:
            # Each error message should be partially present in retry_context
            assert any(
                err["message"][:30] in result["retry_context"]
                or err["field"] in result["retry_context"]
                for _ in [1]
            )


# ─── 13. Unknown placeholder idx is ignored ───────────────────────────────────

def test_unknown_placeholder_idx_is_ignored():
    """Providing content for a placeholder idx not in the layout is not an error."""
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            placeholders=[_title_ph(idx=0)],
        ),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(0, placeholders={"0": "Title", "99": "Extra content for unknown placeholder"}),
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is True


# ─── 14. Zero max_chars_estimate means no limit ───────────────────────────────

def test_zero_max_chars_means_no_limit():
    """max_chars_estimate=0 means no limit — very long text should pass."""
    profile = _make_profile([
        SlideLayout(
            slide_index=0,
            classification="content_layout",
            placeholders=[_ph(idx=0, ph_type="TITLE", max_chars=0)],
        ),
        _slide(1), _slide(2),
    ])
    plan = _make_plan([
        _item(0, placeholders={"0": "A" * 10000}),
        _item(1), _item(2),
    ])
    result = validate_slide_plan(plan, profile)
    assert result["valid"] is True
