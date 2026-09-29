"""Uploader-only candidate review and player-scoped session projections."""

import base64
import binascii
from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.models.tables import (
    ActivityReport,
    IngestionFinding,
    PlayerSession,
    ReportUpload,
    SessionMetricValue,
    SourceAthleteRow,
    SourceMetricObservation,
)
from app.schemas.v1 import (
    ActivityOut,
    CandidateRowOut,
    ExistingLinkOut,
    FindingOut,
    SessionMetricOut,
    SessionOut,
    SessionProvenanceOut,
    SessionsOut,
    SourceMetricOut,
    UploadStatusOut,
)


def _finding_out(value: IngestionFinding) -> FindingOut:
    return FindingOut(
        code=value.code,
        message=value.message,
        severity=value.severity,
        scope=value.scope,
        row_ordinal=value.row_ordinal,
        metric_key=value.metric_key,
    )


def upload_status(session: Session, upload: ReportUpload) -> UploadStatusOut:
    report = session.get(ActivityReport, upload.id)
    rows = session.scalars(
        select(SourceAthleteRow)
        .where(SourceAthleteRow.report_upload_id == upload.id)
        .order_by(SourceAthleteRow.row_ordinal)
    ).all()
    findings = session.scalars(
        select(IngestionFinding)
        .where(IngestionFinding.report_upload_id == upload.id)
        .order_by(IngestionFinding.created_at, IngestionFinding.id)
    ).all()
    observations: dict[UUID, list[SourceMetricObservation]] = defaultdict(list)
    links: dict[UUID, list[PlayerSession]] = defaultdict(list)
    row_ids = [row.id for row in rows]
    if row_ids:
        for observation in session.scalars(
            select(SourceMetricObservation)
            .where(SourceMetricObservation.athlete_row_id.in_(row_ids))
            .order_by(SourceMetricObservation.source_locator)
        ):
            if observation.athlete_row_id is not None:
                observations[observation.athlete_row_id].append(observation)
        for link in session.scalars(select(PlayerSession).where(PlayerSession.source_athlete_row_id.in_(row_ids))):
            links[link.source_athlete_row_id].append(link)
    candidate_rows = [
        CandidateRowOut(
            id=row.id,
            row_ordinal=row.row_ordinal,
            source_name=row.source_name,
            source_position_code=row.source_position_code,
            quality_state=row.participation_state,
            metrics=[
                SourceMetricOut(
                    source_label=observation.source_label,
                    raw_value=observation.raw_value,
                    raw_unit=observation.raw_unit,
                    parsed_value=str(observation.parsed_value) if observation.parsed_value is not None else None,
                    quality_state=observation.quality_state,
                    source_locator=observation.source_locator,
                )
                for observation in observations[row.id]
                if observation.raw_value is not None
            ],
            missing_metrics=[
                observation.source_label for observation in observations[row.id] if observation.raw_value is None
            ],
            findings=[_finding_out(value) for value in findings if value.row_ordinal == row.row_ordinal],
            links=[
                ExistingLinkOut(session_id=link.id, player_id=link.player_id, quality_state=link.quality_state)
                for link in links[row.id]
            ],
        )
        for row in rows
    ]
    return UploadStatusOut(
        upload_id=upload.id,
        status=upload.status,
        error_code=upload.error_code,
        activity=(
            ActivityOut(
                source_title=report.source_title,
                source_team_name=report.source_team_name,
                source_venue_name=report.source_venue_name,
                reported_local_datetime=report.reported_local_datetime,
                timezone=report.timezone,
                activity_total_time_s=report.activity_total_time_s,
            )
            if report is not None
            else None
        ),
        findings=[_finding_out(value) for value in findings],
        candidate_rows=candidate_rows,
    )


def _session_out(session: Session, player_session: PlayerSession) -> SessionOut:
    source_row = session.get(SourceAthleteRow, player_session.source_athlete_row_id)
    if source_row is None:
        raise AppError("source_unavailable", "Session source is unavailable", 503)
    metrics = session.execute(
        select(SessionMetricValue, SourceMetricObservation.source_label)
        .join(
            SourceMetricObservation,
            SessionMetricValue.source_observation_id == SourceMetricObservation.id,
        )
        .where(SessionMetricValue.player_session_id == player_session.id)
        .order_by(SessionMetricValue.metric_key)
    ).all()
    findings = session.scalars(
        select(IngestionFinding).where(
            IngestionFinding.report_upload_id == source_row.report_upload_id,
            IngestionFinding.row_ordinal == source_row.row_ordinal,
            IngestionFinding.severity.in_(["warning", "error"]),
        )
    ).all()
    return SessionOut(
        id=player_session.id,
        player_id=player_session.player_id,
        local_date=player_session.local_date,
        session_type=player_session.session_type,
        quality_state=player_session.quality_state,
        metrics=[
            SessionMetricOut(
                metric_key=value.metric_key,
                value=str(value.value),
                unit=value.unit,
                source_label=source_label,
                definition_id=value.definition_id,
                comparability_key=value.comparability_key,
                quality_state=value.quality_state,
            )
            for value, source_label in metrics
        ],
        warnings=[_finding_out(value) for value in findings],
        provenance=SessionProvenanceOut(
            source_athlete_row_id=source_row.id,
            report_upload_id=source_row.report_upload_id,
        ),
    )


def get_session(session: Session, player_id: UUID, session_id: UUID) -> SessionOut:
    player_session = session.scalar(
        select(PlayerSession).where(PlayerSession.id == session_id, PlayerSession.player_id == player_id)
    )
    if player_session is None:
        raise AppError("session_not_found", "Session not found", 404)
    return _session_out(session, player_session)


def list_sessions(
    session: Session,
    player_id: UUID,
    *,
    limit: int,
    cursor: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    session_type: str | None = None,
) -> SessionsOut:
    if from_date and to_date and from_date > to_date:
        raise AppError("invalid_date_range", "from must be on or before to", 400)
    query = select(PlayerSession).where(PlayerSession.player_id == player_id)
    if from_date:
        query = query.where(PlayerSession.local_date >= from_date)
    if to_date:
        query = query.where(PlayerSession.local_date <= to_date)
    if session_type:
        query = query.where(PlayerSession.session_type == session_type)
    if cursor:
        cursor_date, cursor_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                PlayerSession.local_date < cursor_date,
                and_(PlayerSession.local_date == cursor_date, PlayerSession.id < cursor_id),
            )
        )
    found = session.scalars(
        query.order_by(PlayerSession.local_date.desc(), PlayerSession.id.desc()).limit(limit + 1)
    ).all()
    page = found[:limit]
    next_cursor = _encode_cursor(page[-1]) if len(found) > limit else None
    return SessionsOut(items=[_session_out(session, item) for item in page], next_cursor=next_cursor)


def _encode_cursor(value: PlayerSession) -> str:
    raw = f"{value.local_date.isoformat()}|{value.id}".encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> tuple[date, UUID]:
    try:
        if len(value) > 128:
            raise ValueError("Cursor too long")
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("ascii")
        date_text, id_text = raw.split("|", 1)
        return date.fromisoformat(date_text), UUID(id_text)
    except (binascii.Error, UnicodeError, ValueError) as exc:
        raise AppError("invalid_cursor", "Invalid session cursor", 400) from exc
