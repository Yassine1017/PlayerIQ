"""PostgreSQL-compatible tables for source evidence and future player features."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class UuidId:
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Profile(Base, CreatedAt):
    __tablename__ = "profiles"

    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Player(Base, UuidId, CreatedAt):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("owner_user_id"),)

    owner_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CoachInvitation(Base, UuidId, CreatedAt):
    __tablename__ = "coach_invitations"
    __table_args__ = (
        CheckConstraint("status IN ('pending','accepted','expired','revoked')", name="status"),
        Index(
            "uq_coach_invitation_pending_email",
            "player_id",
            "email_normalized",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.players.id"), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")


class PlayerCoach(Base):
    __tablename__ = "player_coaches"
    __table_args__ = (Index("ix_player_coaches_coach_player", "coach_user_id", "player_id"),)

    player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.players.id"), primary_key=True)
    coach_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), primary_key=True)
    invitation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.coach_invitations.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Team(Base, UuidId, CreatedAt):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)


class TeamMembership(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (
        CheckConstraint("role IN ('player','coach','admin')", name="team_role"),
        Index("ix_team_memberships_player", "player_id"),
    )

    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.teams.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), primary_key=True)
    player_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.players.id"))
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TeamManagerGrant(Base):
    """Small RLS lookup table that avoids a recursive membership policy."""

    __tablename__ = "team_manager_grants"

    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.teams.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), primary_key=True)


class TeamJoinRequest(Base, UuidId, CreatedAt):
    __tablename__ = "team_join_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','declined')", name="join_status"),
        Index(
            "uq_team_join_pending",
            "team_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.teams.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    player_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.players.id"))
    display_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    decided_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlayerSourceIdentity(Base, UuidId, CreatedAt):
    """A player-owner confirmed source label within one report/provider scope."""

    __tablename__ = "player_source_identities"
    __table_args__ = (
        Index(
            "uq_source_identity_active",
            "scope_key",
            "parser_key",
            "normalized_label",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        Index("ix_source_identity_player", "player_id", "revoked_at"),
    )

    player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.players.id"), nullable=False)
    team_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.teams.id"))
    scope_key: Mapped[str] = mapped_column(String(300), nullable=False)
    parser_key: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_label: Mapped[str] = mapped_column(String(255), nullable=False)
    original_label: Mapped[str] = mapped_column(String(255), nullable=False)
    confirmed_row_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.source_athlete_rows.id"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    confirmed_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportUpload(Base, UuidId, CreatedAt):
    __tablename__ = "report_uploads"
    __table_args__ = (
        CheckConstraint("byte_size >= 0", name="byte_size_nonnegative"),
        CheckConstraint(
            "status IN ('received','queued','extracting','validating','awaiting_link',"
            "'rejected','failed_retryable','deleted')",
            name="status",
        ),
        Index(
            "uq_report_upload_active_hash",
            "uploaded_by_user_id",
            "sha256",
            unique=True,
            postgresql_where=text("status <> 'deleted'"),
            sqlite_where=text("status <> 'deleted'"),
        ),
        Index("ix_report_uploads_uploader_created", "uploaded_by_user_id", "created_at"),
    )

    uploaded_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    team_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.teams.id"))
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="received")
    parser_key: Mapped[str | None] = mapped_column(String(100))
    parser_version: Mapped[str | None] = mapped_column(String(40))
    error_code: Mapped[str | None] = mapped_column(String(100))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionJob(Base, UuidId, CreatedAt):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        Index("ix_ingestion_jobs_due", "status", "next_attempt_at"),
    )

    upload_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.report_uploads.id"), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ActivityReport(Base):
    __tablename__ = "activity_reports"
    __table_args__ = (
        CheckConstraint(
            "activity_total_time_s IS NULL OR activity_total_time_s >= 0",
            name="duration_nonnegative",
        ),
        CheckConstraint(
            "reported_athlete_count IS NULL OR reported_athlete_count >= 0",
            name="athlete_count_nonnegative",
        ),
    )

    report_upload_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.report_uploads.id"), primary_key=True
    )
    report_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_activity_id: Mapped[str | None] = mapped_column(String(120))
    source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_team_name: Mapped[str | None] = mapped_column(String(160))
    source_venue_name: Mapped[str | None] = mapped_column(String(160))
    reported_local_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    timezone: Mapped[str | None] = mapped_column(String(80))
    activity_total_time_s: Mapped[int | None] = mapped_column(Integer)
    reported_athlete_count: Mapped[int | None] = mapped_column(Integer)


class ReportPeriod(Base, UuidId):
    __tablename__ = "report_periods"
    __table_args__ = (
        UniqueConstraint("report_upload_id", "ordinal"),
        CheckConstraint("ordinal > 0", name="ordinal_positive"),
        CheckConstraint("duration_s IS NULL OR duration_s >= 0", name="duration_nonnegative"),
    )

    report_upload_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.report_uploads.id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source_label: Mapped[str] = mapped_column(String(160), nullable=False)
    start_local: Mapped[time | None] = mapped_column(Time(timezone=False))
    duration_s: Mapped[int | None] = mapped_column(Integer)
    reported_athlete_count: Mapped[int | None] = mapped_column(Integer)


class SourceAthleteRow(Base, UuidId):
    __tablename__ = "source_athlete_rows"
    __table_args__ = (
        UniqueConstraint("report_upload_id", "row_ordinal"),
        CheckConstraint("row_ordinal > 0", name="row_ordinal_positive"),
        CheckConstraint(
            "participation_state IN ('ready','zero_recorded','needs_review')",
            name="participation_state",
        ),
    )

    report_upload_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.report_uploads.id"), nullable=False
    )
    row_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_position_code: Mapped[str | None] = mapped_column(String(20))
    participation_state: Mapped[str] = mapped_column(String(20), nullable=False)


class SourceMetricObservation(Base, UuidId):
    __tablename__ = "source_metric_observations"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN report_upload_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN period_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN athlete_row_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="one_scope_parent",
        ),
        CheckConstraint(
            "(scope = 'report' AND report_upload_id IS NOT NULL) OR "
            "(scope = 'period' AND period_id IS NOT NULL) OR "
            "(scope = 'athlete' AND athlete_row_id IS NOT NULL)",
            name="scope_matches_parent",
        ),
        Index("ix_source_metric_athlete", "athlete_row_id"),
    )

    scope: Mapped[str] = mapped_column(String(12), nullable=False)
    report_upload_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.activity_reports.report_upload_id")
    )
    period_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.report_periods.id"))
    athlete_row_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.source_athlete_rows.id")
    )
    source_label: Mapped[str] = mapped_column(String(160), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(String(120))
    raw_unit: Mapped[str | None] = mapped_column(String(40))
    parsed_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    source_locator: Mapped[str] = mapped_column(String(255), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    quality_state: Mapped[str] = mapped_column(String(24), nullable=False)


class ChartMetricReview(Base, UuidId, CreatedAt):
    """Uploader-confirmed transcription of a printed page-two chart label."""

    __tablename__ = "chart_metric_reviews"
    __table_args__ = (
        CheckConstraint(
            "metric_key IN ('maximum_velocity_kmh','player_load_reported')",
            name="chart_metric_key",
        ),
        CheckConstraint(
            "status IN ('proposed','confirmed','held','superseded')",
            name="chart_review_status",
        ),
        CheckConstraint("parsed_value >= 0", name="chart_review_nonnegative"),
        Index("ix_chart_review_row_metric", "athlete_row_id", "metric_key", "created_at"),
    )

    athlete_row_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.source_athlete_rows.id"), nullable=False
    )
    metric_key: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_label: Mapped[str] = mapped_column(String(120), nullable=False)
    parsed_value: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    source_locator: Mapped[str] = mapped_column(String(255), nullable=False)
    capture_method: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed")
    proposed_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(String(500))
    source_observation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.source_metric_observations.id")
    )


class IngestionFinding(Base, UuidId, CreatedAt):
    """Structured extraction/validation evidence retained for manual review."""

    __tablename__ = "ingestion_findings"
    __table_args__ = (Index("ix_ingestion_findings_upload_row", "report_upload_id", "row_ordinal"),)

    report_upload_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.report_uploads.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False)
    scope: Mapped[str] = mapped_column(String(12), nullable=False)
    row_ordinal: Mapped[int | None] = mapped_column(Integer)
    metric_key: Mapped[str | None] = mapped_column(String(100))
    source_locator: Mapped[str | None] = mapped_column(String(255))


class PlayerSession(Base, UuidId, CreatedAt):
    __tablename__ = "player_sessions"
    __table_args__ = (
        CheckConstraint("session_type IN ('training','match','unknown')", name="session_type"),
        CheckConstraint("quality_state IN ('accepted','held')", name="quality_state"),
        CheckConstraint("link_method IN ('manual','recognized')", name="link_method"),
        Index("ix_player_sessions_player_date", "player_id", "local_date", "id"),
        Index("ix_player_sessions_team_report", "team_id", "report_upload_id"),
    )

    player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.players.id"), nullable=False)
    report_upload_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.report_uploads.id"), nullable=False
    )
    team_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.teams.id"))
    source_athlete_row_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.source_athlete_rows.id"), unique=True, nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    athlete_duration_s: Mapped[int | None] = mapped_column(Integer)
    session_type: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    quality_state: Mapped[str] = mapped_column(String(16), nullable=False, default="held")
    link_method: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    source_identity_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.player_source_identities.id")
    )


class SessionMetricValue(Base):
    __tablename__ = "session_metric_values"
    __table_args__ = (CheckConstraint("value >= 0", name="value_nonnegative"),)

    player_session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.player_sessions.id"), primary_key=True
    )
    metric_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    source_observation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playeriq.source_metric_observations.id"), nullable=False
    )
    definition_id: Mapped[str | None] = mapped_column(String(100))
    comparability_key: Mapped[str] = mapped_column(String(160), nullable=False)
    quality_state: Mapped[str] = mapped_column(String(24), nullable=False)


class ChatThread(Base, UuidId, CreatedAt):
    __tablename__ = "chat_threads"
    __table_args__ = (Index("ix_chat_threads_player_creator", "player_id", "created_by_user_id"),)

    player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.players.id"), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AiRun(Base, UuidId, CreatedAt):
    __tablename__ = "ai_runs"
    __table_args__ = (
        Index("ix_ai_runs_player_created", "player_id", "created_at"),
        UniqueConstraint("actor_user_id", "player_id", "idempotency_key", name="uq_ai_runs_actor_player_idempotency"),
    )

    player_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.players.id"), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    session_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.player_sessions.id"))
    message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="openai")
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(60), nullable=False)
    analytics_rule_version: Mapped[str] = mapped_column(String(40), nullable=False, default="analytics_v1")
    idempotency_key: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    data_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_snapshot: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    response_json: Mapped[dict | None] = mapped_column(JSON_VALUE)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiToolCall(Base, UuidId, CreatedAt):
    __tablename__ = "ai_tool_calls"
    __table_args__ = (UniqueConstraint("ai_run_id", "provider_call_id"),)

    ai_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.ai_runs.id"), nullable=False)
    provider_call_id: Mapped[str] = mapped_column(String(160), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments_json: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSON_VALUE)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class AiProviderRequest(Base, UuidId, CreatedAt):
    """One durable reservation and usage record per billable provider request."""

    __tablename__ = "ai_provider_requests"
    __table_args__ = (
        CheckConstraint("status IN ('reserved','completed','uncertain','unknown_pricing')", name="status"),
        CheckConstraint("reserved_cost_usd >= 0", name="reserved_cost_nonnegative"),
        CheckConstraint("estimated_cost_usd IS NULL OR estimated_cost_usd >= 0", name="estimated_cost_nonnegative"),
        Index("ix_ai_provider_requests_month", "budget_month", "created_at"),
    )

    ai_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.ai_runs.id"), nullable=False)
    budget_month: Mapped[date] = mapped_column(Date, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    pricing_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    reserved_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 9))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatMessage(Base, UuidId, CreatedAt):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="role"),
        Index("ix_chat_messages_thread_created", "thread_id", "created_at", "id"),
    )

    thread_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.chat_threads.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)
    ai_run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("playeriq.ai_runs.id"))
