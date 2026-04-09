"""
Generation Service — Orchestrates the LangGraph pipeline and SSE streaming.
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId

from app.config import get_settings

logger = logging.getLogger(__name__)


_STAGE_ORDER = [
    "queued",
    "load_profile",
    "plan_outline",
    "plan_single_slide",
    "aggregate",
    "aggregate_validation",
    "render",
    "store",
]


def _completed_stages(current_stage: str | None) -> list[str]:
    if not current_stage:
        return []
    if current_stage not in _STAGE_ORDER:
        return []
    idx = _STAGE_ORDER.index(current_stage)
    return _STAGE_ORDER[:idx]


class GenerationService:
    def __init__(self, db):
        self.db = db

    async def start_generation(self, template_id: str, prompt: str) -> str:
        """Create a generation record and return the generation_id."""
        settings = get_settings()

        # Prompt length guard
        if len(prompt) > settings.max_prompt_chars:
            raise ValueError(
                f"Prompt too long: {len(prompt)} chars (max {settings.max_prompt_chars})"
            )

        generation_id = str(ObjectId())
        await self.db.generations.insert_one(
            {
                "_id": ObjectId(generation_id),
                "template_id": template_id,
                "prompt": prompt,
                "status": "processing",
                "stage": "queued",
                "progress": 5,
                "message": "Generation queued",
                "created_at": datetime.now(timezone.utc),
            }
        )
        logger.info(f"Started generation {generation_id} for template {template_id}")
        return generation_id

    async def run_generation(self, generation_id: str) -> None:
        """
        Run the full LangGraph pipeline as a background task.
        Progress is written to MongoDB so the SSE endpoint can stream it.
        """
        from app.graph.pipeline import pipeline

        doc = await self.db.generations.find_one({"_id": ObjectId(generation_id)})
        if not doc:
            logger.error(f"Generation {generation_id} not found")
            return

        initial_state = {
            "template_id": doc["template_id"],
            "prompt": doc["prompt"],
            "generation_id": generation_id,
            "status": "running",
            "retry_count": 0,
        }

        try:
            settings = get_settings()
            run_config = {"max_concurrency": settings.slide_generation_concurrency}

            # Stream the pipeline state updates to MongoDB
            async for chunk in pipeline.astream(initial_state, config=run_config, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    if not isinstance(node_output, dict):
                        continue

                    update: dict = {
                        k: v
                        for k, v in node_output.items()
                        if k in ("status", "stage", "progress", "message", "error")
                    }

                    # Persist output_file_id and slides_generated if present
                    if "output_file_id" in node_output:
                        update["output_file_id"] = node_output["output_file_id"]
                    if "slide_count" in node_output:
                        update["slides_generated"] = node_output["slide_count"]

                    if update:
                        await self.db.generations.update_one(
                            {"_id": ObjectId(generation_id)},
                            {"$set": update},
                        )
                        logger.debug(
                            f"Generation {generation_id} [{node_name}]: {update.get('message', '')}"
                        )

        except Exception as e:
            logger.exception(f"Pipeline execution failed for generation {generation_id}: {e}")
            await self.db.generations.update_one(
                {"_id": ObjectId(generation_id)},
                {
                    "$set": {
                        "status": "failed",
                        "stage": "pipeline_error",
                        "progress": 0,
                        "error": str(e),
                        "message": "Unexpected pipeline error",
                    }
                },
            )

    async def get_status(self, generation_id: str) -> dict | None:
        """Fetch current generation status for SSE streaming."""
        try:
            doc = await self.db.generations.find_one({"_id": ObjectId(generation_id)})
        except Exception:
            return None
        if not doc:
            return None

        stage = doc.get("stage")
        return {
            "generation_id": str(doc["_id"]),
            "template_id": doc.get("template_id"),
            "status": doc.get("status", "unknown"),
            "stage": stage,
            "current_step": stage,  # compatibility alias; remove after frontend migration
            "completed_steps": _completed_stages(stage),  # compatibility alias; remove later
            "progress": doc.get("progress", 0),
            "message": doc.get("message", ""),
            "error": doc.get("error"),
            "slides_generated": doc.get("slides_generated"),
            "output_file_id": doc.get("output_file_id"),
        }

    async def get_output_file_id(self, generation_id: str) -> str | None:
        """Return the GridFS file_id for a completed generation."""
        doc = await self.db.generations.find_one(
            {"_id": ObjectId(generation_id), "status": "completed"},
            {"output_file_id": 1},
        )
        if not doc:
            return None
        return doc.get("output_file_id")
