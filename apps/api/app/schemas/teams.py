"""Bounded team projections; never expose raw ingestion rows or PDFs."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.v1 import StrictModel


class TeamCreate(StrictModel):
    name: str = Field(min_length=2, max_length=160)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Team name is too short")
        return value


class TeamOut(StrictModel):
    id: UUID
    name: str
    role: Literal["player", "coach", "admin"]
    player_id: UUID | None
    created_at: datetime


class TeamsOut(StrictModel):
    items: list[TeamOut]


class TeamJoinRequestOut(StrictModel):
    id: UUID
    team_id: UUID
    user_id: UUID
    display_name: str
    status: str
    created_at: datetime


class JoinRequestsOut(StrictModel):
    items: list[TeamJoinRequestOut]


class ApproveJoinRequest(StrictModel):
    role: Literal["player", "coach"]


class AssignReportTeam(StrictModel):
    team_id: UUID
    confirm_share: Literal[True]


class TeamSessionOut(StrictModel):
    report_upload_id: UUID
    local_date: date
    participant_count: int
    total_distance_m: str | None
    session_type: str


class TeamSessionsOut(StrictModel):
    items: list[TeamSessionOut]


class TeamMetricOut(StrictModel):
    metric_key: str
    value: str
    unit: str


class TeamParticipantOut(StrictModel):
    player_id: UUID
    display_name: str
    session_id: UUID
    metrics: list[TeamMetricOut]


class TeamSessionDetailOut(StrictModel):
    summary: TeamSessionOut
    participants: list[TeamParticipantOut]


class TeamPlayerOut(StrictModel):
    id: UUID
    display_name: str
    account_state: Literal["registered", "unclaimed"]
    participation_state: Literal["accepted_history", "no_accepted_activity"]
    latest_session_date: date | None
    latest_metrics: list[TeamMetricOut]


class TeamPlayersOut(StrictModel):
    items: list[TeamPlayerOut]
    limited_to_self: bool


class TeamDashboardOut(StrictModel):
    team: TeamOut
    latest_session: TeamSessionOut | None
    recent_sessions: list[TeamSessionOut]
    player_count: int | None
    rule_version: Literal["analytics_v1"] = "analytics_v1"


class TeamReportOut(StrictModel):
    upload_id: UUID
    status: str
    created_at: datetime
    accepted_player_count: int


class TeamReportsOut(StrictModel):
    items: list[TeamReportOut]
