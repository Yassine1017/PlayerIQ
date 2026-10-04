"""Pure anonymous peer comparisons, restricted to one team report and type."""

import hashlib
import json
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.analytics.domain import ANALYTICS_RULE_VERSION, SessionValue, history_fingerprint
from app.analytics.team import compatible_report_metrics

ComparisonMetric = Literal[
    "total_distance_m", "reported_high_speed_distance_m", "maximum_velocity_kmh", "player_load_reported"
]
ComparisonStatus = Literal[
    "ok", "no_player_association", "not_participating", "missing_metric", "insufficient_cohort", "not_comparable"
]
Direction = Literal["above", "below", "equal"]
COMPARISON_METRICS: tuple[ComparisonMetric, ...] = (
    "total_distance_m",
    "reported_high_speed_distance_m",
    "maximum_velocity_kmh",
    "player_load_reported",
)
MINIMUM_TEAMMATES = 5


@dataclass(frozen=True, slots=True)
class TeamSessionValue:
    team_id: UUID
    report_id: UUID
    player_id: UUID
    session: SessionValue


@dataclass(frozen=True, slots=True)
class PeerComparison:
    metric_key: ComparisonMetric
    status: ComparisonStatus
    unit: str
    your_value: Decimal | None = None
    teammate_mean: Decimal | None = None
    absolute_difference: Decimal | None = None
    percentage_difference: Decimal | None = None
    direction: Direction | None = None
    teammate_sample_size: int = 0
    minimum_teammates: int = MINIMUM_TEAMMATES
    # Internal evidence only. Never serialize these into the anonymous API.
    supporting_session_ids: tuple[UUID, ...] = ()
    supporting_observation_ids: tuple[UUID, ...] = ()
    rule_version: str = field(default=ANALYTICS_RULE_VERSION)


def comparison_unit(key: ComparisonMetric) -> str:
    return "km/h" if key == "maximum_velocity_kmh" else "source units" if key == "player_load_reported" else "m"


def compare_with_teammates(
    history: list[TeamSessionValue], team_id: UUID, report_id: UUID, player_id: UUID | None
) -> tuple[PeerComparison, ...]:
    """Exclude self; never average incompatible or duplicate canonical values."""
    grouped = [
        item
        for item in history
        if item.team_id == team_id and item.report_id == report_id and item.session.quality_state == "accepted"
    ]
    own = [item for item in grouped if item.player_id == player_id]
    status: ComparisonStatus = (
        "no_player_association"
        if player_id is None
        else "not_participating"
        if not own
        else "not_comparable"
        if len(own) != 1
        else "ok"
    )
    if status != "ok":
        return tuple(PeerComparison(key, status, comparison_unit(key)) for key in COMPARISON_METRICS)
    subject = own[0]
    peers = [
        item
        for item in grouped
        if item.player_id != player_id and item.session.session_type == subject.session.session_type
    ]
    duplicate = len({item.player_id for item in peers}) != len(peers)
    return tuple(_compare_metric(subject, peers, key, duplicate) for key in COMPARISON_METRICS)


def _compare_metric(
    subject: TeamSessionValue, peers: list[TeamSessionValue], key: ComparisonMetric, duplicate: bool
) -> PeerComparison:
    unit = comparison_unit(key)
    own = subject.session.metrics.get(key)
    base = PeerComparison(key, "missing_metric", unit)
    if own is None or own.quality_state != "accepted":
        return base
    if not compatible_report_metrics([own], unit):
        return replace(base, status="not_comparable")
    metrics = [
        (item, metric)
        for item in peers
        if (metric := item.session.metrics.get(key)) is not None and metric.quality_state == "accepted"
    ]
    base = replace(base, your_value=own.value, teammate_sample_size=len(metrics))
    if (
        duplicate
        or len({m.source_observation_id for _, m in metrics} | {own.source_observation_id}) != len(metrics) + 1
    ):
        return replace(base, status="not_comparable", teammate_sample_size=0)
    if not compatible_report_metrics([own, *(m for _, m in metrics)], unit):
        return replace(base, status="not_comparable", teammate_sample_size=0)
    if len(metrics) < MINIMUM_TEAMMATES:
        return replace(base, status="insufficient_cohort")
    mean = sum((m.value for _, m in metrics), Decimal(0)) / Decimal(len(metrics))
    difference = own.value - mean
    return replace(
        base,
        status="ok",
        teammate_mean=mean,
        absolute_difference=difference,
        percentage_difference=difference / mean * 100 if mean > 0 else None,
        direction="above" if difference > 0 else "below" if difference < 0 else "equal",
        supporting_session_ids=(subject.session.id, *(item.session.id for item, _ in metrics)),
        supporting_observation_ids=(own.source_observation_id, *(m.source_observation_id for _, m in metrics)),
    )


def comparison_fingerprint(
    history: list[TeamSessionValue], team_id: UUID, report_id: UUID, player_id: UUID | None
) -> str:
    """Internal future-cache key; never send a peer-history hash to players.

    Live results are not cached. Callers must recheck membership and pass the
    current authorized association and canonical cohort on every read.
    """
    payload = {
        "rule": ANALYTICS_RULE_VERSION,
        "minimum": MINIMUM_TEAMMATES,
        "metrics": COMPARISON_METRICS,
        "team": str(team_id),
        "report": str(report_id),
        "subject": str(player_id),
        "history": [
            (str(item.team_id), str(item.report_id), str(item.player_id), history_fingerprint([item.session]))
            for item in sorted(history, key=lambda item: str(item.session.id))
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
