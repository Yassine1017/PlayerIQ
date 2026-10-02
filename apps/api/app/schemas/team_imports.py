"""Uploader-private, bounded roster import contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.v1 import StrictModel


class TeamImportRequest(StrictModel):
    team_id: UUID
    confirm_share: Literal[True]
    session_type: Literal["training", "match", "unknown"] = "unknown"


class ImportResolution(StrictModel):
    player_id: UUID | None = None
    confirmed_source_label: str = Field(min_length=1, max_length=255)
    confirm_association: Literal[True]


class ImportRowOut(StrictModel):
    row_id: UUID
    row_ordinal: int
    source_name: str
    player_id: UUID | None
    session_id: UUID | None
    association_method: str
    outcome: str
    reason_code: str | None
    created_player: bool
    created_session: bool
    resolved_at: datetime | None


class TeamImportOut(StrictModel):
    upload_id: UUID
    team_id: UUID
    status: Literal["queued", "complete", "needs_review", "failed"]
    session_type: str
    attempts: int
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
    counts: dict[str, int]
    rows: list[ImportRowOut]
