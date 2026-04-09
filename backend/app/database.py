import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket

from app.config import get_settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self) -> None:
        self.client: AsyncIOMotorClient | None = None
        self.db = None
        self.template_bucket: AsyncIOMotorGridFSBucket | None = None
        self.generated_bucket: AsyncIOMotorGridFSBucket | None = None

    async def connect(self) -> None:
        settings = get_settings()
        self.client = AsyncIOMotorClient(settings.mongodb_uri)
        self.db = self.client[settings.mongodb_db_name]

        # Use Motor's async GridFS bucket (not sync GridFSBucket from gridfs package)
        self.template_bucket = AsyncIOMotorGridFSBucket(
            self.db, bucket_name=settings.template_bucket_name
        )
        self.generated_bucket = AsyncIOMotorGridFSBucket(
            self.db, bucket_name=settings.generated_bucket_name
        )

        # Verify connection
        await self.client.admin.command("ping")
        logger.info(f"Connected to MongoDB: {settings.mongodb_db_name}")

    async def disconnect(self) -> None:
        if self.client is not None:
            self.client.close()
            logger.info("Disconnected from MongoDB")


db_manager = DatabaseManager()


def get_db():
    if db_manager.db is None:
        raise RuntimeError("Database is not initialized. App lifespan not started.")
    return db_manager.db


def get_template_bucket() -> AsyncIOMotorGridFSBucket:
    if db_manager.template_bucket is None:
        raise RuntimeError("Template GridFS bucket is not initialized.")
    return db_manager.template_bucket


def get_generated_bucket() -> AsyncIOMotorGridFSBucket:
    if db_manager.generated_bucket is None:
        raise RuntimeError("Generated GridFS bucket is not initialized.")
    return db_manager.generated_bucket
