from app.graph.nodes import (
    _adapt_outline_to_template,
    _backfill_missing_text_placeholders,
    _reorder_outline_for_closing,
    _usable_content_slides,
)
from app.schemas.slide_plan import SlideContent, SlidePlan, SlidePlanItem
from app.schemas.template_profile import ChartMeta, Placeholder, PlaceholderPosition, SlideLayout, TemplateProfile


def _ph(
    idx: int,
    ph_type: str = "BODY",
    *,
    current_text: str = "",
    width_emu: int = 2_200_000,
    height_emu: int = 700_000,
    max_chars_estimate: int = 120,
) -> Placeholder:
    return Placeholder(
        idx=idx,
        name=f"ph-{idx}",
        type=ph_type,
        position=PlaceholderPosition(width_emu=width_emu, height_emu=height_emu),
        max_chars_estimate=max_chars_estimate,
        current_text=current_text,
    )


def _chart() -> ChartMeta:
    return ChartMeta(shape_index=1, chart_type="BAR_CLUSTERED", series_count=1, category_count=4)


def test_backfill_missing_text_placeholders_from_purpose():
    profile = TemplateProfile(
        name="t",
        slides=[
            SlideLayout(slide_index=2, placeholders=[_ph(0, "TITLE"), _ph(10002, "BODY")]),
        ],
        total_slides=1,
        usable_layouts=1,
    )

    plan = SlidePlan(
        slides=[
            SlidePlanItem(
                slide_type="content",
                template_slide_index=2,
                purpose="Regional performance summary",
                content=SlideContent(placeholders={"0": "Regional Performance", "10002": ""}),
            )
        ]
    )

    out = _backfill_missing_text_placeholders(plan, profile)
    assert out.slides[0].content.placeholders["0"] == "Regional Performance"
    assert out.slides[0].content.placeholders["10002"] == "Regional performance summary"


def test_backfill_does_not_add_new_placeholder_keys():
    profile = TemplateProfile(
        name="t",
        slides=[
            SlideLayout(slide_index=1, placeholders=[_ph(0, "TITLE"), _ph(10002, "BODY")]),
        ],
        total_slides=1,
        usable_layouts=1,
    )

    plan = SlidePlan(
        slides=[
            SlidePlanItem(
                slide_type="content",
                template_slide_index=1,
                purpose="New growth",
                content=SlideContent(placeholders={"0": "Growth Snapshot"}),
            )
        ]
    )

    out = _backfill_missing_text_placeholders(plan, profile)
    assert "10002" not in out.slides[0].content.placeholders


def test_reorder_outline_moves_closing_to_end():
    outline = [
        {"slide_type": "title", "template_slide_index": 0, "purpose": "Opening"},
        {"slide_type": "closing", "template_slide_index": 6, "purpose": "Thank you"},
        {"slide_type": "chart_bar", "template_slide_index": 2, "purpose": "Revenue by quarter"},
    ]

    ordered = _reorder_outline_for_closing(outline)
    assert ordered[-1]["slide_type"] == "closing"


def test_cover_layout_filtered_from_usable_content_slides():
    profile = TemplateProfile(
        name="t",
        slides=[
            SlideLayout(
                slide_index=0,
                classification="content_layout",
                placeholders=[
                    Placeholder(idx=0, name="t", type="TITLE", position=PlaceholderPosition(), max_chars_estimate=50, current_text="PRESENTATION TITLE"),
                    Placeholder(idx=1, name="b", type="BODY", position=PlaceholderPosition(), max_chars_estimate=50, current_text="Presenter Name | Date"),
                ],
            ),
            SlideLayout(slide_index=1, classification="content_layout", placeholders=[_ph(0, "TITLE")]),
        ],
    )

    usable = _usable_content_slides(profile)
    assert [s.slide_index for s in usable] == [1]


def test_adapt_outline_reassigns_title_and_chart_layouts():
    profile = TemplateProfile(
        name="t",
        slides=[
            SlideLayout(
                slide_index=0,
                classification="content_layout",
                placeholders=[
                    _ph(0, "TITLE", current_text="PRESENTATION TITLE"),
                    _ph(1, "BODY", current_text="Presenter Name | Date"),
                ],
            ),
            SlideLayout(slide_index=1, classification="content_layout", placeholders=[_ph(0, "TITLE"), _ph(1, "BODY")]),
            SlideLayout(
                slide_index=2,
                classification="content_layout",
                placeholders=[_ph(0, "TITLE"), _ph(1, "BODY")],
                charts=[_chart()],
            ),
            SlideLayout(
                slide_index=3,
                classification="content_layout",
                placeholders=[
                    _ph(0, "BODY", width_emu=380_000, height_emu=240_000, max_chars_estimate=6),
                    _ph(1, "BODY", width_emu=380_000, height_emu=240_000, max_chars_estimate=6),
                ],
            ),
        ],
    )
    content_slides = _usable_content_slides(profile)
    assert [s.slide_index for s in content_slides] == [1, 2, 3]

    outline = [
        {"slide_type": "title", "template_slide_index": 999, "purpose": "Opening"},
        {"slide_type": "chart_bar", "template_slide_index": 3, "purpose": "Revenue trend by quarter"},
        {"slide_type": "closing", "template_slide_index": 1, "purpose": "Thank you and Q&A"},
    ]

    adapted = _adapt_outline_to_template(_reorder_outline_for_closing(outline), content_slides, "Revenue trend data by quarter")
    assert adapted[0]["template_slide_index"] == 1
    assert adapted[1]["template_slide_index"] == 2
    assert adapted[-1]["slide_type"] == "closing"
    assert adapted[-1]["template_slide_index"] != adapted[0]["template_slide_index"]


def test_adapt_outline_injects_chart_layout_for_data_driven_prompt():
    profile = TemplateProfile(
        name="t",
        slides=[
            SlideLayout(slide_index=1, classification="content_layout", placeholders=[_ph(0, "TITLE"), _ph(1, "BODY")]),
            SlideLayout(slide_index=2, classification="content_layout", placeholders=[_ph(0, "TITLE"), _ph(1, "BODY")]),
            SlideLayout(
                slide_index=3,
                classification="content_layout",
                placeholders=[_ph(0, "TITLE"), _ph(1, "BODY")],
                charts=[_chart()],
            ),
        ],
    )
    content_slides = _usable_content_slides(profile)

    outline = [
        {"slide_type": "title", "template_slide_index": 1, "purpose": "Opening"},
        {"slide_type": "content", "template_slide_index": 2, "purpose": "Insights"},
        {"slide_type": "closing", "template_slide_index": 1, "purpose": "Thank you"},
    ]

    adapted = _adapt_outline_to_template(
        outline,
        content_slides,
        "Show quarterly revenue growth trend and KPI performance data comparison.",
    )

    non_closing = adapted[:-1]
    assert any(item["template_slide_index"] == 3 for item in non_closing)
    assert any(item["slide_type"] == "chart_bar" and item["template_slide_index"] == 3 for item in non_closing)
    assert adapted[-1]["slide_type"] == "closing"
