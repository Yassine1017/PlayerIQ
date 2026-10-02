"""Bounded player-history projection. Caller must authorize the player first."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.domain import MetricValue, SessionValue
from app.models.tables import PlayerSession, SessionMetricValue

MAX_ANALYTICS_SESSIONS = 1000


class HistoryLimitExceeded(ValueError):
    pass


def load_player_history(session: Session, player_id: UUID, team_id: UUID | None = None) -> list[SessionValue]:
    query = select(PlayerSession).where(PlayerSession.player_id == player_id, PlayerSession.quality_state == "accepted")
    if team_id is not None:
        query = query.where(PlayerSession.team_id == team_id)
    rows = session.scalars(
        query.order_by(PlayerSession.local_date, PlayerSession.id).limit(MAX_ANALYTICS_SESSIONS + 1)
    ).all()
    if len(rows) > MAX_ANALYTICS_SESSIONS:
        raise HistoryLimitExceeded("Player history exceeds the supported analytics limit")
    if not rows:
        return []
    by_session: dict[UUID, dict[str, MetricValue]] = {row.id: {} for row in rows}
    values = session.scalars(
        select(SessionMetricValue).where(
            SessionMetricValue.player_session_id.in_(tuple(by_session)),
            SessionMetricValue.quality_state == "accepted",
        )
    ).all()
    for metric in values:
        by_session[metric.player_session_id][metric.metric_key] = MetricValue(
            key=metric.metric_key,
            value=metric.value,
            unit=metric.unit,
            comparability_key=metric.comparability_key,
            definition_id=metric.definition_id,
            source_observation_id=metric.source_observation_id,
            quality_state=metric.quality_state,
        )
    return [
        SessionValue(
            id=row.id,
            local_date=row.local_date,
            started_at=row.started_at,
            session_type=row.session_type,
            quality_state=row.quality_state,
            metrics=by_session[row.id],
        )
        for row in rows
    ]
