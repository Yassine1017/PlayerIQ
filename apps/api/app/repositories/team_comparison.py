"""Bounded canonical projection; membership is checked by the service first."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.domain import MetricValue, SessionValue
from app.analytics.team_comparison import COMPARISON_METRICS, TeamSessionValue
from app.api.errors import AppError
from app.models.tables import PlayerSession, SessionMetricValue


def report_comparison_history(session: Session, team_id: UUID, report_id: UUID) -> list[TeamSessionValue]:
    rows = list(
        session.scalars(
            select(PlayerSession)
            .where(
                PlayerSession.team_id == team_id,
                PlayerSession.report_upload_id == report_id,
                PlayerSession.quality_state == "accepted",
            )
            .order_by(PlayerSession.id)
            .limit(201)
        )
    )
    if not rows:
        raise AppError("team_session_not_found", "Team session not found", 404)
    if len(rows) > 200:
        raise AppError("team_comparison_limit", "Team activity exceeds the supported comparison limit", 422)
    values: dict[UUID, dict[str, MetricValue]] = {row.id: {} for row in rows}
    for metric in session.scalars(
        select(SessionMetricValue).where(
            SessionMetricValue.player_session_id.in_(values), SessionMetricValue.metric_key.in_(COMPARISON_METRICS)
        )
    ):
        values[metric.player_session_id][metric.metric_key] = MetricValue(
            key=metric.metric_key,
            value=metric.value,
            unit=metric.unit,
            comparability_key=metric.comparability_key,
            definition_id=metric.definition_id,
            source_observation_id=metric.source_observation_id,
            quality_state=metric.quality_state,
        )
    return [
        TeamSessionValue(
            team_id=team_id,
            report_id=report_id,
            player_id=row.player_id,
            session=SessionValue(
                id=row.id,
                local_date=row.local_date,
                started_at=row.started_at,
                session_type=row.session_type,
                quality_state=row.quality_state,
                metrics=values[row.id],
            ),
        )
        for row in rows
    ]
