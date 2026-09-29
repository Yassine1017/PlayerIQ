"""FastAPI application factory. Ingestion is not exposed without authentication."""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, request_id_context

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="PlayerIQ API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
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
            logger.info(
                "request_complete method=%s path=%s status=%s",
                request.method,
                request.url.path,
                response.status_code,
            )
            return response
        finally:
            request_id_context.reset(token)

    register_exception_handlers(app)
    app.include_router(health_router)
    return app


app = create_app()
