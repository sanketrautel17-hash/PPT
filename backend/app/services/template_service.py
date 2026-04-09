"""
Template Service — Orchestrates template upload, parsing, and persistence.
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import UploadFile

from app.config import get_settings
from app.database import get_generated_bucket, get_template_bucket
from app.schemas.template_profile import TemplateProfile
from app.tools.guidance_extractor import extract_guidance
from app.tools.storage import store_template_binary
from app.tools.template_parser import parse_template

logger = logging.getLogger(__name__)


class TemplateService:
    def __init__(self, db):
        self.db = db

    async def upload_template(self, file: UploadFile, name: str) -> str:
        """
        1. Validate file is a PPTX.
        2. Save raw binary to GridFS.
        3. Create a 'analyzing' record in MongoDB.
        Returns template_id string.
        """
        settings = get_settings()

        # Read bytes
        pptx_bytes = await file.read()

        # Size check
        max_bytes = settings.max_template_size_mb * 1024 * 1024
        if len(pptx_bytes) > max_bytes:
            raise ValueError(
                f"File too large: {len(pptx_bytes)/1024/1024:.1f}MB (max {settings.max_template_size_mb}MB)"
            )

        # Basic PPTX magic bytes check (PK zip header)
        if not pptx_bytes.startswith(b"PK"):
            raise ValueError("File does not appear to be a valid .pptx file")

        template_id = str(ObjectId())

        # Store binary in GridFS
        bucket = get_template_bucket()
        file_id = await store_template_binary(pptx_bytes, template_id, name, bucket)

        # Create MongoDB record
        await self.db.template_profiles.insert_one(
            {
                "_id": ObjectId(template_id),
                "name": name,
                "status": "analyzing",
                "template_file_id": file_id,
                "file_size_bytes": len(pptx_bytes),
                "created_at": datetime.now(timezone.utc),
            }
        )

        logger.info(f"Uploaded template '{name}' → id={template_id}, file_id={file_id}")
        return template_id

    async def analyze_template(self, template_id: str, name: str) -> None:
        """
        Background task: parse → extract guidance → persist profile.
        Runs after upload_template returns 201.
        """
        try:
            # Load binary from GridFS
            doc = await self.db.template_profiles.find_one({"_id": ObjectId(template_id)})
            if not doc:
                logger.error(f"analyze_template: template {template_id} not found")
                return

            from app.tools.storage import retrieve_template_binary

            bucket = get_template_bucket()
            pptx_bytes = await retrieve_template_binary(doc["template_file_id"], bucket)

            # Parse structural metadata
            await self._update_status(template_id, "analyzing", "Parsing template structure...")
            profile: TemplateProfile = await parse_template(pptx_bytes, name)

            # Extract guidance + brand rules via Groq
            await self._update_status(template_id, "analyzing", "Extracting brand rules via AI...")
            profile = await extract_guidance(profile)
            profile.total_slides = len(profile.slides)
            profile.usable_layouts = len(profile.content_slides())

            # Persist
            await self.db.template_profiles.update_one(
                {"_id": ObjectId(template_id)},
                {
                    "$set": {
                        "status": "ready",
                        "profile": profile.model_dump(),
                        "total_slides": profile.total_slides,
                        "usable_layouts": profile.usable_layouts,
                        "layout_indices": sorted(s.slide_index for s in profile.content_slides()),
                        "analyzed_at": datetime.now(timezone.utc),
                    }
                },
            )
            logger.info(
                f"Template '{name}' ({template_id}) analysis complete: "
                f"{profile.total_slides} slides, {profile.usable_layouts} usable"
            )

        except Exception as e:
            logger.exception(f"analyze_template failed for {template_id}: {e}")
            await self.db.template_profiles.update_one(
                {"_id": ObjectId(template_id)},
                {"$set": {"status": "failed", "error": str(e)}},
            )

    async def re_profile_template(self, template_id: str) -> None:
        """
        Re-run guidance extraction and profiling on an already-uploaded template.
        Useful when prompt logic has changed and the stored brand rules need refreshing.
        """
        try:
            doc = await self.db.template_profiles.find_one({"_id": ObjectId(template_id)})
            if not doc:
                logger.error(f"re_profile_template: template {template_id} not found")
                return

            name = doc.get("name", "Unnamed")
            await self.analyze_template(template_id, name)
            logger.info(f"Re-profiling complete for template {template_id}")
        except Exception as e:
            logger.exception(f"re_profile_template failed for {template_id}: {e}")
            await self.db.template_profiles.update_one(
                {"_id": ObjectId(template_id)},
                {"$set": {"status": "failed", "error": str(e)}},
            )

    async def _update_status(self, template_id: str, status: str, message: str) -> None:
        await self.db.template_profiles.update_one(
            {"_id": ObjectId(template_id)},
            {"$set": {"status": status, "status_message": message}},
        )

    async def list_templates(self) -> list[dict]:
        cursor = self.db.template_profiles.find().sort("created_at", -1)
        items = []
        async for item in cursor:
            template_id = str(item["_id"])
            total_slides = item.get("total_slides", 0)
            items.append(
                {
                    "id": template_id,
                    "_id": template_id,  # compatibility alias; remove after frontend migration
                    "name": item.get("name", "Unnamed"),
                    "status": item.get("status", "unknown"),
                    "total_slides": total_slides,
                    "slide_count": total_slides,  # compatibility alias; remove after frontend migration
                    "usable_layouts": item.get("usable_layouts", 0),
                    "file_size_bytes": item.get("file_size_bytes", 0),
                    "created_at": item.get("created_at", "").isoformat() if item.get("created_at") else "",
                }
            )
        return items

    async def get_template(self, template_id: str) -> dict | None:
        try:
            doc = await self.db.template_profiles.find_one({"_id": ObjectId(template_id)})
        except Exception:
            return None
        if not doc:
            return None

        resolved_id = str(doc["_id"])
        return {
            "id": resolved_id,
            "_id": resolved_id,  # compatibility alias; remove after frontend migration
            "name": doc.get("name", "Unnamed"),
            "status": doc.get("status", "unknown"),
            "total_slides": doc.get("total_slides", 0),
            "usable_layouts": doc.get("usable_layouts", 0),
            "profile": doc.get("profile"),
            "created_at": doc.get("created_at", "").isoformat() if doc.get("created_at") else "",
        }

