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
    def __init__(self, session: Session, player_id: UUID) -> None:
        self.player_id = player_id
        self.history: list[SessionValue] = load_player_history(session, player_id)

    def fingerprint(self) -> str:
        return domain.history_fingerprint(self.history)

    def latest_comparison(self, metric_key: str, previous_count: int = 5) -> AnalyticsFact:
        return domain.latest_comparison(self.history, metric_key, previous_count)

    def trend(self, metric_key: str, from_date: date, to_date: date, session_type: str | None = None) -> AnalyticsFact:
        return domain.metric_trend(self.history, metric_key, from_date, to_date, session_type)

    def personal_record(self, metric_key: str = "maximum_velocity_kmh") -> AnalyticsFact:
        return domain.personal_record(self.history, metric_key)

    def hardest_session(self, metric_key: str = "total_distance_m") -> AnalyticsFact:
        return domain.hardest_session(self.history, metric_key)

    def last_speed_exceedance(self, threshold_kmh: Decimal) -> AnalyticsFact:
        return domain.last_speed_exceedance(self.history, threshold_kmh)

    def largest_change(self, *, improvement: bool) -> AnalyticsFact:
        return domain.largest_change(self.history, improvement=improvement)

    def workload_outliers(self, session_type: str, limit: int = 10) -> tuple[AnalyticsFact, ...]:
        return domain.workload_outliers(self.history, session_type, limit)

    def overview(self) -> AnalyticsOverview:
        facts = (
            self.latest_comparison("total_distance_m"),
            self.latest_comparison("maximum_velocity_kmh"),
            self.latest_comparison("player_load_reported"),
            self.personal_record("maximum_velocity_kmh"),
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
