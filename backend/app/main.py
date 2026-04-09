from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.middleware import setup_exception_handlers, setup_middleware
from app.api.routes.generate import router as generate_router
from app.api.routes.health import router as health_router
from app.api.routes.templates import router as templates_router
from app.config import get_settings
from app.core.logging import configure_logging
from app.database import db_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    await db_manager.connect()
    yield
    await db_manager.disconnect()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    setup_middleware(app)
    setup_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(templates_router)
    app.include_router(generate_router)

    return app


app = create_app()
