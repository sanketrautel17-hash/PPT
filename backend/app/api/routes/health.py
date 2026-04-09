from fastapi import APIRouter, Depends

from app.api.dependencies import get_db
from app.config import get_settings


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(db=Depends(get_db)) -> dict:
    await db.command("ping")
    settings = get_settings()
    return {
        "status": "ok",
        "db": "connected",
        "llm_model": settings.planner_model,
        "guidance_model": settings.guidance_model,
        "max_template_size_mb": settings.max_template_size_mb,
        "max_prompt_chars": settings.max_prompt_chars,
        "max_retries": settings.max_retries,
        "slide_generation_concurrency": settings.slide_generation_concurrency,
    }
