import operator
from typing import Annotated, Literal, TypedDict


def _latest_str(_: str | None, new: str | None) -> str | None:
    return new


def _latest_status(_: Literal["running", "completed", "failed"] | None, new: Literal["running", "completed", "failed"] | None):
    return new


def _max_progress(old: int | None, new: int | None) -> int | None:
    if old is None:
        return new
    if new is None:
        return old
    return max(old, new)


class SlideState(TypedDict, total=False):
    # Per-slide context for fan-out generation
    slide_index: int
    template_slide_index: int
    outline_item: dict
    full_outline: list[dict]
    profile: dict

    # Per-slide outputs/control
    slide_content: dict
    validation_result: dict
    retry_count: int
    error_context: str | None


class PipelineState(TypedDict, total=False):
    # ── Inputs ──────────────────────────────────────────────────────────────
    template_id: str
    prompt: str
    generation_id: str

    # ── Populated by nodes ───────────────────────────────────────────────────
    template_bytes: bytes  # raw PPTX binary from GridFS
    profile: dict  # TemplateProfile serialized as dict
    slide_outline: list[dict]  # from plan_outline node
    outline_item: dict  # single outline item for per-slide fan-out
    slide_index: int  # position in outline for per-slide fan-out
    slide_plan: dict  # SlidePlan serialized as dict
    validation_result: dict  # from validate node
    retry_count: int  # tracks retries (max 2)
    completed_slides: Annotated[list[dict], operator.add]  # reducer target for fan-out mode
    pptx_bytes: bytes  # from render node
    slide_count: int  # number of slides rendered
    output_file_id: str  # GridFS file id of generated PPTX

    # ── Pipeline control ─────────────────────────────────────────────────────
    status: Annotated[Literal["running", "completed", "failed"], _latest_status]
    stage: Annotated[str, _latest_str]  # current stage name for SSE streaming
    progress: Annotated[int, _max_progress]  # 0–100 for SSE progress
    message: Annotated[str, _latest_str]  # human-readable stage message
    error: Annotated[str | None, _latest_str]
