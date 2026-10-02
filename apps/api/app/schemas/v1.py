"""Phase 2 HTTP contracts; no teammate data appears in player-session schemas."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    timezone: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Display name cannot be blank")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("Use an IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProfileUpdate":
        if self.display_name is None and self.timezone is None:
            raise ValueError("Provide at least one profile field")
        return self


class ProfileOut(StrictModel):
    display_name: str
    timezone: str


class MeOut(StrictModel):
    user_id: UUID
    profile: ProfileOut | None


class PlayerCreate(StrictModel):
    display_name: str = Field(min_length=1, max_length=160)

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name cannot be blank")
        return value


class PlayerOut(StrictModel):
    id: UUID
    display_name: str
    owner_user_id: UUID
    created_at: datetime


class PlayersOut(StrictModel):
    items: list[PlayerOut]


class UploadCreated(StrictModel):
    upload_id: UUID
    status: str


class UploadSummaryOut(StrictModel):
    upload_id: UUID
    original_filename: str
    status: str
    created_at: datetime
    processed_at: datetime | None
    athlete_row_count: int | None
    error_code: str | None


class UploadsOut(StrictModel):
    items: list[UploadSummaryOut]
    next_cursor: str | None


class SourceMetricOut(StrictModel):
    source_label: str
    raw_value: str | None
    raw_unit: str | None
    parsed_value: str | None
    quality_state: str
    source_locator: str


class FindingOut(StrictModel):
    code: str
    message: str
    severity: str
    scope: str
    row_ordinal: int | None
    metric_key: str | None


class ExistingLinkOut(StrictModel):
    session_id: UUID
    player_id: UUID
    quality_state: str


class CandidateRowOut(StrictModel):
    id: UUID
    row_ordinal: int
    source_name: str
    source_position_code: str | None
    quality_state: str
    metrics: list[SourceMetricOut]
    missing_metrics: list[str]
    findings: list[FindingOut]
    links: list[ExistingLinkOut]
    recognition_status: str = "unlinked"
    recognized_player_id: UUID | None = None
    source_identity_id: UUID | None = None


class ActivityOut(StrictModel):
    source_title: str
    source_team_name: str | None
    source_venue_name: str | None
    reported_local_datetime: datetime | None
    timezone: str | None
    activity_total_time_s: int | None


class UploadStatusOut(StrictModel):
    upload_id: UUID
    team_id: UUID | None = None
    status: str
    error_code: str | None
    activity: ActivityOut | None
    findings: list[FindingOut]
    candidate_rows: list[CandidateRowOut]


class LinkRequest(StrictModel):
    source_athlete_row_id: UUID
    player_id: UUID
    session_type: Literal["training", "match", "unknown"] = "unknown"
    source_identity_id: UUID | None = None


class LinkOut(StrictModel):
    session_id: UUID
    player_id: UUID
    source_athlete_row_id: UUID
    quality_state: str
    link_method: str = "manual"


class ClaimSelfRequest(StrictModel):
    source_athlete_row_id: UUID
    player_id: UUID
    confirmed_source_label: str = Field(min_length=1, max_length=255)
    session_type: Literal["training", "match", "unknown"] = "unknown"


class SourceIdentityOut(StrictModel):
    id: UUID
    player_id: UUID
    team_id: UUID | None
    original_label: str
    parser_key: str
    confirmed_row_id: UUID
    confirmed_at: datetime
    status: Literal["connected", "revoked"]


class SourceIdentitiesOut(StrictModel):
    items: list[SourceIdentityOut]


class ClaimSelfOut(StrictModel):
    session_id: UUID
    identity: SourceIdentityOut


class RevokeIdentityRequest(StrictModel):
    confirm: Literal[True]


class ChartReviewProposal(StrictModel):
    source_athlete_row_id: UUID
    metric_key: Literal["maximum_velocity_kmh", "player_load_reported"]
    raw_label: str = Field(min_length=1, max_length=120)


class ChartReviewConfirmation(StrictModel):
    source_athlete_row_id: UUID
    raw_label: str = Field(min_length=1, max_length=120)
    review_reason: str | None = Field(default=None, max_length=500)


class ChartReviewOut(StrictModel):
    id: UUID
    source_athlete_row_id: UUID
    metric_key: str
    raw_label: str
    parsed_value: str
    unit: str
    source_locator: str
    capture_method: str
    status: str
    proposed_by_user_id: UUID
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    review_reason: str | None
    source_observation_id: UUID | None
    created_at: datetime


class ChartReviewsOut(StrictModel):
    items: list[ChartReviewOut]


class SessionMetricOut(StrictModel):
    metric_key: str
    value: str
    unit: str
    source_label: str
    definition_id: str | None
    comparability_key: str
    quality_state: str


class SessionProvenanceOut(StrictModel):
    source_athlete_row_id: UUID
    report_upload_id: UUID
    link_method: str = "manual"


class SessionOut(StrictModel):
    id: UUID
    player_id: UUID
    local_date: date
    session_type: str
    quality_state: str
    metrics: list[SessionMetricOut]
    warnings: list[FindingOut]
    provenance: SessionProvenanceOut


class SessionsOut(StrictModel):
    items: list[SessionOut]
    next_cursor: str | None
