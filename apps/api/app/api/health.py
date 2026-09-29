"""Unauthenticated process health and database readiness routes."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.db.session import Database

router = APIRouter()


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadinessResponse)
def readyz(request: Request, response: Response) -> ReadinessResponse:
    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:
        response.status_code = 503
        return ReadinessResponse(status="not_ready", checks={"application": "ok", "database": "not_configured"})
    try:
        database.check_connection()
    except Exception:
        response.status_code = 503
        return ReadinessResponse(status="not_ready", checks={"application": "ok", "database": "unavailable"})
    return ReadinessResponse(status="ready", checks={"application": "ok", "database": "ok"})
