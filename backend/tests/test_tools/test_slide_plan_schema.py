from app.schemas.slide_plan import SlidePlan


def test_slide_plan_coerces_null_placeholder_values():
    payload = {
        "slides": [
            {
                "slide_type": "overview",
                "template_slide_index": 3,
                "purpose": "Provide a high-level overview of TCS performance",
                "content": {
                    "placeholders": {
                        "12": None,
                        13: ["Revenue growth", None, 42],
                    }
                },
            }
        ]
    }

    plan = SlidePlan(**payload)
    placeholders = plan.slides[0].content.placeholders

    assert placeholders["12"] == ""
    assert placeholders["13"] == ["Revenue growth", "", "42"]



def test_slide_plan_placeholder_null_and_scalars_normalize_stably():
    payload = {
        "slides": [
            {
                "slide_type": "overview",
                "template_slide_index": 1,
                "purpose": "Overview",
                "content": {"placeholders": {12: None, "13": [None, 7, "ok"]}},
            }
        ]
    }
    plan = SlidePlan(**payload)
    ph = plan.slides[0].content.placeholders
    assert ph["12"] == ""
    assert ph["13"] == ["", "7", "ok"]
