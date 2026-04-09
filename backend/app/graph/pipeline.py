"""
LangGraph Pipeline
Flow:
  START
    -> load_profile
    -> plan_outline
    -> fan-out per slide (Send -> plan_single_slide)
    -> aggregate
    -> aggregate_validation
    -> render
    -> store
    -> END
"""

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.graph.nodes import (
    aggregate_node,
    aggregate_validation_node,
    load_profile_node,
    plan_outline_node,
    plan_single_slide_node,
    render_node,
    store_node,
)
from app.graph.state import PipelineState

logger = logging.getLogger(__name__)


def _fan_out_slides(state: PipelineState):
    """Emit one Send packet per outline item."""
    if state.get("status") == "failed":
        return END

    outline = state.get("slide_outline", [])
    if not outline:
        logger.error("plan_outline produced an empty outline; stopping pipeline")
        return END

    sends: list[Send] = []
    for idx, item in enumerate(outline):
        sends.append(
            Send(
                "plan_single_slide",
                {
                    "template_id": state["template_id"],
                    "prompt": state["prompt"],
                    "generation_id": state["generation_id"],
                    "profile": state["profile"],
                    "slide_outline": outline,
                    "outline_item": item,
                    "slide_index": idx,
                },
            )
        )

    return sends


def build_pipeline() -> StateGraph:
    """Build and compile the slide-by-slide generation pipeline."""
    builder = StateGraph(PipelineState)

    builder.add_node("load_profile", load_profile_node)
    builder.add_node("plan_outline", plan_outline_node)
    builder.add_node("plan_single_slide", plan_single_slide_node)
    builder.add_node("aggregate", aggregate_node)
    builder.add_node("aggregate_validation", aggregate_validation_node)
    builder.add_node("render", render_node)
    builder.add_node("store", store_node)

    builder.add_edge(START, "load_profile")

    builder.add_conditional_edges(
        "load_profile",
        lambda s: END if s.get("status") == "failed" else "plan_outline",
        {"plan_outline": "plan_outline", END: END},
    )

    builder.add_conditional_edges("plan_outline", _fan_out_slides, ["plan_single_slide", END])

    builder.add_edge("plan_single_slide", "aggregate")

    builder.add_conditional_edges(
        "aggregate",
        lambda s: END if s.get("status") == "failed" else "aggregate_validation",
        {"aggregate_validation": "aggregate_validation", END: END},
    )

    builder.add_conditional_edges(
        "aggregate_validation",
        lambda s: END if s.get("status") == "failed" else "render",
        {"render": "render", END: END},
    )

    builder.add_conditional_edges(
        "render",
        lambda s: END if s.get("status") == "failed" else "store",
        {"store": "store", END: END},
    )

    builder.add_edge("store", END)

    return builder.compile()


pipeline = build_pipeline()
