"""Explicit, authorized row-to-player promotion with source provenance."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.core.config import Settings
from app.ingestion.domain import QualityState, RawAthleteRow, RawMetricObservation, RawReport, Scope
from app.ingestion.validation import ReportValidator
from app.models.tables import (
    ActivityReport,
    Player,
    PlayerSession,
    SessionMetricValue,
    SourceAthleteRow,
    SourceMetricObservation,
)
from app.schemas.v1 import LinkOut, LinkRequest
from app.services.authorization import require_player, require_upload
from app.services.chart_reviews import sync_confirmed_chart_metrics


def link_athlete_row(
    session: Session,
    actor_id: UUID,
    upload_id: UUID,
    request: LinkRequest,
    settings: Settings,
) -> LinkOut:
    upload = require_upload(session, actor_id, upload_id)
    require_player(session, actor_id, request.player_id, manage=True)
    if upload.status != "awaiting_link":
        raise AppError("upload_not_ready", "Report is not ready for linking", 409)
    # Serializes same-player/date checks on PostgreSQL.
    session.execute(select(Player.id).where(Player.id == request.player_id).with_for_update())
    source_row = session.scalar(
        select(SourceAthleteRow)
        .where(
            SourceAthleteRow.id == request.source_athlete_row_id,
            SourceAthleteRow.report_upload_id == upload_id,
        )
        .with_for_update()
    )
    if source_row is None:
        raise AppError("row_not_found", "Athlete row not found in this report", 404)
    existing = session.scalar(select(PlayerSession).where(PlayerSession.source_athlete_row_id == source_row.id))
    if existing is not None:
        if existing.player_id == request.player_id and existing.session_type == request.session_type:
            return LinkOut(
                session_id=existing.id,
                player_id=existing.player_id,
                source_athlete_row_id=source_row.id,
                quality_state=existing.quality_state,
            )
        raise AppError("row_already_linked", "Athlete row is already linked", 409)
    if source_row.participation_state != "ready":
        raise AppError("row_requires_review", "Athlete row requires review before linking", 422)
    report = session.get(ActivityReport, upload_id)
    if report is None or report.reported_local_datetime is None:
        raise AppError("activity_date_unavailable", "Activity date requires review", 422)
    local_date = report.reported_local_datetime.date()
    if (
        session.scalar(
            select(PlayerSession.id).where(
                PlayerSession.player_id == request.player_id,
                PlayerSession.local_date == local_date,
            )
        )
        is not None
    ):
        raise AppError("same_date_review", "This player already has a session on that date", 409)

    observations = _athlete_observations(session, upload_id)
    raw_rows = session.scalars(
        select(SourceAthleteRow)
        .where(SourceAthleteRow.report_upload_id == upload_id)
        .order_by(SourceAthleteRow.row_ordinal)
    ).all()
    raw_report = RawReport(
        parser_key=upload.parser_key or "activity_report_pdf_v1",
        parser_version=upload.parser_version or "unknown",
        report_kind=report.report_kind,
        source_title=report.source_title,
        reported_local_datetime=report.reported_local_datetime,
        timezone=report.timezone,
        athlete_rows=[
            RawAthleteRow(
                row_ordinal=row.row_ordinal,
                source_name=row.source_name,
                source_position_code=row.source_position_code,
                observations=[
                    RawMetricObservation(
                        source_label=observation.source_label,
                        raw_value=observation.raw_value,
                        raw_unit=observation.raw_unit,
                        parsed_value=observation.parsed_value,
                        source_locator=observation.source_locator,
                        scope=Scope.ATHLETE,
                        parser_version=observation.parser_version,
                        row_ordinal=row.row_ordinal,
                        quality_state=QualityState(observation.quality_state),
                    )
                    for observation in observations[row.id]
                ],
            )
            for row in raw_rows
        ],
    )
    validation = ReportValidator(
        max_velocity_review_kmh=settings.max_velocity_review_kmh,
        distance_peer_review_multiplier=settings.distance_peer_review_multiplier,
    ).validate(raw_report)
    validated = next(row for row in validation.rows if row.row_ordinal == source_row.row_ordinal)
    if validated.quality_state is not QualityState.READY:
        raise AppError("row_requires_review", "Athlete row requires review before linking", 422)

    player_session = PlayerSession(
        player_id=request.player_id,
        source_athlete_row_id=source_row.id,
        local_date=local_date,
        started_at=None,
        athlete_duration_s=None,
        session_type=request.session_type,
        quality_state="accepted",
    )
    session.add(player_session)
    session.flush()
    source_by_label = {observation.source_label: observation for observation in observations[source_row.id]}
    for metric in validated.metrics.values():
        if metric.quality_state is not QualityState.ACCEPTED:
            continue
        source = source_by_label[metric.source_label]
        if source.parsed_value != metric.value:
            raise AppError("source_mismatch", "Source metric changed during linking", 409)
        session.add(
            SessionMetricValue(
                player_session_id=player_session.id,
                metric_key=metric.metric_key,
                value=metric.value,
                unit=metric.unit,
                source_observation_id=source.id,
                definition_id=metric.definition_id,
                comparability_key=metric.comparability_key,
                quality_state=metric.quality_state.value,
            )
        )
    sync_confirmed_chart_metrics(session, player_session, upload.parser_key)
    return LinkOut(
        session_id=player_session.id,
        player_id=request.player_id,
        source_athlete_row_id=source_row.id,
        quality_state="accepted",
    )


def _athlete_observations(session: Session, upload_id: UUID) -> dict[UUID, list[SourceMetricObservation]]:
    rows = session.scalars(select(SourceAthleteRow.id).where(SourceAthleteRow.report_upload_id == upload_id)).all()
    grouped: dict[UUID, list[SourceMetricObservation]] = defaultdict(list)
    if rows:
        for observation in session.scalars(
            select(SourceMetricObservation).where(
                SourceMetricObservation.athlete_row_id.in_(rows),
                SourceMetricObservation.parser_version != "chart_review_v1",
            )
        ):
            if observation.athlete_row_id is not None:
                grouped[observation.athlete_row_id].append(observation)
    return grouped
