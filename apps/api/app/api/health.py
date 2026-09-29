"""Unauthenticated process health and Phase 1 readiness routes."""

from fastapi import APIRouter
from pydantic import BaseModel

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
def readyz() -> ReadinessResponse:
    # A database probe belongs here after Phase 1 configures a database connection.
    return ReadinessResponse(status="ready", checks={"application": "ok", "database": "not_checked"})
