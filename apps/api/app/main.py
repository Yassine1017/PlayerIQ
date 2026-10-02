"""FastAPI application factory for authenticated ingestion and analytics."""

import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.ai.provider import OpenAIProvider
from app.api.ai import router as ai_router
from app.api.analytics import router as analytics_router
from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.teams import router as teams_router
from app.api.v1 import router as v1_router
from app.core.auth import SupabaseJWTVerifier
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, request_id_context
from app.db.session import Database, make_engine
from app.services.storage import SupabaseReportStorage

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        yield
        database: Database | None = getattr(app.state, "database", None)
        if database is not None:
            database.engine.dispose()

    app = FastAPI(title="PlayerIQ API", version="0.3.0", lifespan=lifespan)
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.database = Database(make_engine(settings.database_url)) if settings.database_url else None
    app.state.jwt_verifier = SupabaseJWTVerifier(settings) if settings.supabase_url else None
    app.state.storage = (
        SupabaseReportStorage(settings) if settings.supabase_url and settings.supabase_storage_secret_key else None
    )
    app.state.ai_provider = (
        OpenAIProvider(
            key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.ai_request_timeout_seconds,
            max_tool_calls=settings.ai_max_tool_calls,
        )
        if settings.openai_api_key
        else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def request_ids(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = str(uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            route = request.scope.get("route")
            logger.info(
                "request_complete method=%s path=%s status=%s",
                request.method,
                getattr(route, "path", "unmatched"),
                response.status_code,
            )
            return response
        finally:
            request_id_context.reset(token)

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(v1_router)
    app.include_router(teams_router)
    app.include_router(analytics_router)
    app.include_router(ai_router)
    return app


app = create_app()
