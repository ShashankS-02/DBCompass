"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_assessment, routes_explain, routes_export, routes_health, routes_help, routes_intake, routes_migration, routes_pricing, routes_questions, routes_requests
from app.config import APP_VERSION, get_settings
from app.db.session import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create tables on startup and warn loudly if auth is bypassed."""
    settings = get_settings()
    if settings.dev_auth_bypass:
        logger.warning("DEV_AUTH_BYPASS is on: all requests run as the dev user")
    init_db()
    yield


def create_app() -> FastAPI:
    """Build the FastAPI app with middleware and routers."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = FastAPI(title="DBCompass API", version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_health.router, prefix="/api")
    app.include_router(routes_help.router, prefix="/api")
    app.include_router(routes_questions.router, prefix="/api")
    app.include_router(routes_assessment.router, prefix="/api")
    app.include_router(routes_pricing.router, prefix="/api")
    app.include_router(routes_migration.router, prefix="/api")
    app.include_router(routes_requests.router, prefix="/api")
    app.include_router(routes_explain.router, prefix="/api")
    app.include_router(routes_export.router, prefix="/api")
    app.include_router(routes_intake.router, prefix="/api")
    return app


app = create_app()
