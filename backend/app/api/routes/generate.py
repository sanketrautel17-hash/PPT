import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.api.dependencies import get_db
from app.database import get_generated_bucket
from app.models.generation import GenerateRequest, GenerateResponse
from app.services.generation_service import GenerationService
from app.tools.storage import retrieve_generated_pptx

router = APIRouter(prefix="/api/generate", tags=["generation"])


@router.post("", response_model=GenerateResponse, status_code=202)
async def generate_presentation(
    payload: GenerateRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
) -> GenerateResponse:
    service = GenerationService(db)
    try:
        generation_id = await service.start_generation(payload.template_id, payload.prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    background_tasks.add_task(service.run_generation, generation_id)
    return GenerateResponse(generation_id=generation_id, status="processing")


@router.get("/{generation_id}/status")
async def stream_status(generation_id: str, db=Depends(get_db)) -> EventSourceResponse:
    service = GenerationService(db)

    async def event_generator() -> AsyncGenerator[dict, None]:
        while True:
            status = await service.get_status(generation_id)
            if status is None:
                yield {"event": "error", "data": json.dumps({"message": "Generation not found"})}
                break

            yield {"event": "progress", "data": json.dumps(status)}

            if status["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/{generation_id}/download")
async def download_pptx(generation_id: str, db=Depends(get_db)) -> StreamingResponse:
    """Download the completed PPTX file as a binary stream."""
    service = GenerationService(db)

    status = await service.get_status(generation_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Generation not found")

    if status["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Generation not completed yet (status={status['status']})",
        )

    file_id = status.get("output_file_id")
    if not file_id:
        raise HTTPException(status_code=500, detail="Output file ID missing from generation record")

    bucket = get_generated_bucket()
    try:
        pptx_bytes = await retrieve_generated_pptx(file_id, bucket)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file: {e}")

    filename = f"presentation_{generation_id}.pptx"
    return StreamingResponse(
        iter([pptx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
