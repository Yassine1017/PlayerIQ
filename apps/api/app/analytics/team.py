"""Pure descriptive team averages within one source report, never across reports."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.analytics.domain import AnalyticsFact, MetricValue


@dataclass(frozen=True, slots=True)
class TeamMetricSample:
    report_id: UUID
    player_id: UUID
    session_id: UUID
    session_quality: str
    metric: MetricValue


def compatible_report_metrics(metrics: Sequence[MetricValue], unit: str) -> bool:
    """Matching source definitions are descriptive only within one report.

    The caller must establish report scope; this never verifies unverified keys.
    """
    return bool(metrics) and all(
        metric.value.is_finite()
        and metric.value >= 0
        and metric.unit == unit
        and metric.definition_id == metrics[0].definition_id
        and metric.comparability_key == metrics[0].comparability_key
        for metric in metrics
    )


def same_report_average(
    samples: list[TeamMetricSample],
    report_id: UUID,
    metric_key: Literal["total_distance_m", "player_load_reported"],
) -> AnalyticsFact:
    """Mean of accepted athlete values, with one observation per participant.

    Matching unverified definitions are allowed only within this single report:
    this describes its printed source index, not provider comparability over time.
    """
    unit = "m" if metric_key == "total_distance_m" else "source units"
    values = [
        s
        for s in samples
        if s.report_id == report_id
        and s.session_quality == "accepted"
        and s.metric.key == metric_key
        and s.metric.quality_state == "accepted"
    ]
    base = AnalyticsFact(
        kind="team_average",
        status="missing_metric",
        metric_key=metric_key,
        unit=unit,
        sample_size=len({s.player_id for s in values}),
        session_ids=tuple(s.session_id for s in values),
        source_observation_ids=tuple(s.metric.source_observation_id for s in values),
    )
    if not values:
        return base
    first = values[0].metric
    if (
        len({s.player_id for s in values}) != len(values)
        or len({s.metric.source_observation_id for s in values}) != len(values)
        or not compatible_report_metrics([s.metric for s in values], unit)
    ):
        return replace(base, status="not_comparable", note="Conflicting athlete values or source definitions")
    return replace(
        base,
        status="ok",
        value=sum((s.metric.value for s in values), Decimal(0)) / Decimal(len(values)),
        definition_id=first.definition_id,
        comparability_key=first.comparability_key,
        note="Same report only; Player Load is a reported index with unknown units/formula"
        if metric_key == "player_load_reported"
        else "Accepted participants with distance in this report",
    )
