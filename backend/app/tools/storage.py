"""
Storage — Phase 5
Motor + GridFS helpers for file upload/download.
"""

import io
import logging

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

logger = logging.getLogger(__name__)


async def store_file(
    data: bytes,
    filename: str,
    bucket: AsyncIOMotorGridFSBucket,
) -> str:
    """
    Upload bytes to GridFS.

    Args:
        data: Raw file bytes.
        filename: Filename to store (e.g. "generated_abc123.pptx").
        bucket: Motor AsyncIOMotorGridFSBucket instance.

    Returns:
        file_id as string (str(ObjectId)).
    """
    file_id = await bucket.upload_from_stream(filename, io.BytesIO(data))
    logger.info(f"Stored file '{filename}' → GridFS id={file_id} ({len(data)} bytes)")
    return str(file_id)


async def retrieve_file(
    file_id: str,
    bucket: AsyncIOMotorGridFSBucket,
) -> bytes:
    """
    Download bytes from GridFS by file ID.

    Args:
        file_id: String ObjectId of the GridFS file.
        bucket: Motor AsyncIOMotorGridFSBucket instance.

    Returns:
        Raw file bytes.
    """
    stream = await bucket.open_download_stream(ObjectId(file_id))
    data = await stream.read()
    logger.info(f"Retrieved file id={file_id} ({len(data)} bytes)")
    return data


async def store_template_binary(
    pptx_bytes: bytes,
    template_id: str,
    template_name: str,
    bucket: AsyncIOMotorGridFSBucket,
) -> str:
    """Upload a template PPTX binary to the template GridFS bucket."""
    filename = f"template_{template_id}.pptx"
    return await store_file(pptx_bytes, filename, bucket)


async def retrieve_template_binary(
    file_id: str,
    bucket: AsyncIOMotorGridFSBucket,
) -> bytes:
    """Download a template PPTX binary from GridFS."""
    return await retrieve_file(file_id, bucket)


async def store_generated_pptx(
    pptx_bytes: bytes,
    generation_id: str,
    bucket: AsyncIOMotorGridFSBucket,
) -> str:
    """Upload a generated PPTX to the generated GridFS bucket."""
    filename = f"generated_{generation_id}.pptx"
    return await store_file(pptx_bytes, filename, bucket)


async def retrieve_generated_pptx(
    file_id: str,
    bucket: AsyncIOMotorGridFSBucket,
) -> bytes:
    """Download a generated PPTX from GridFS."""
    return await retrieve_file(file_id, bucket)
