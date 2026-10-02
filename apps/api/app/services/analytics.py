"""Reusable read-only orchestration for HTTP and a future grounded AI runner."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.analytics import domain
from app.analytics.domain import AnalyticsFact, SessionValue
from app.repositories.analytics import load_player_history


@dataclass(frozen=True, slots=True)
class AnalyticsOverview:
    player_id: UUID
    history_fingerprint: str
    rule_version: str
    facts: tuple[AnalyticsFact, ...]


class AnalyticsService:
    def __init__(self, session: Session, player_id: UUID, *, team_id: UUID | None = None) -> None:
        self.player_id = player_id
        self.history: list[SessionValue] = load_player_history(session, player_id, team_id)

    def fingerprint(self) -> str:
        return domain.history_fingerprint(self.history)

    def latest_comparison(self, metric_key: str, previous_count: int = 5) -> AnalyticsFact:
        return domain.latest_comparison(self.history, metric_key, previous_count)

    def latest_comparison_for_type(
        self, metric_key: str, previous_count: int, session_type: str | None
    ) -> AnalyticsFact:
        history = (
            self.history
            if session_type is None
            else [item for item in self.history if item.session_type == session_type]
        )
        return domain.latest_comparison(history, metric_key, previous_count)

    def trend(self, metric_key: str, from_date: date, to_date: date, session_type: str | None = None) -> AnalyticsFact:
        return domain.metric_trend(self.history, metric_key, from_date, to_date, session_type)

    def personal_record(self, metric_key: str = "maximum_velocity_kmh") -> AnalyticsFact:
        return domain.personal_record(self.history, metric_key)

    def personal_record_for_type(self, metric_key: str, session_type: str | None) -> AnalyticsFact:
        history = (
            self.history
            if session_type is None
            else [item for item in self.history if item.session_type == session_type]
        )
        return domain.personal_record(history, metric_key)

    def hardest_session(self, metric_key: str = "total_distance_m") -> AnalyticsFact:
        return domain.hardest_session(self.history, metric_key)

    def last_speed_exceedance(self, threshold_kmh: Decimal) -> AnalyticsFact:
        return domain.last_speed_exceedance(self.history, threshold_kmh)

    def largest_change(self, *, improvement: bool) -> AnalyticsFact:
        return domain.largest_change(self.history, improvement=improvement)

    def workload_outliers(self, session_type: str, limit: int = 10) -> tuple[AnalyticsFact, ...]:
        return domain.workload_outliers(self.history, session_type, limit)

    def session_facts(self, session_id: UUID) -> tuple[AnalyticsFact, ...]:
        for item in self.history:
            if item.id == session_id:
                return tuple(
                    AnalyticsFact(
                        kind="session_metric",
                        status="ok",
                        metric_key=metric.key,
                        value=metric.value,
                        unit=metric.unit,
                        sample_size=1,
                        session_ids=(item.id,),
                        source_observation_ids=(metric.source_observation_id,),
                        from_date=item.local_date,
                        to_date=item.local_date,
                        definition_id=metric.definition_id,
                        comparability_key=metric.comparability_key,
                    )
                    for metric in item.metrics.values()
                    if metric.quality_state == "accepted"
                )
        return ()

    def overview(self) -> AnalyticsOverview:
        facts = (
            self.latest_comparison("total_distance_m"),
            self.latest_comparison("reported_high_speed_distance_m"),
            self.latest_comparison("maximum_velocity_kmh"),
            self.latest_comparison("player_load_reported"),
            self.personal_record("maximum_velocity_kmh"),
            self.personal_record("total_distance_m"),
            self.hardest_session(),
            self.largest_change(improvement=True),
            self.largest_change(improvement=False),
        ) + self.workload_outliers("training", 1)
        return AnalyticsOverview(
            player_id=self.player_id,
            history_fingerprint=self.fingerprint(),
            rule_version=domain.ANALYTICS_RULE_VERSION,
            facts=facts,
        )
