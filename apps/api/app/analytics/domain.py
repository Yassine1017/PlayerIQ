"""Pure, versioned calculations over authorized, quality-accepted player history."""

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from uuid import UUID

ANALYTICS_RULE_VERSION = "analytics_v1"
OUTLIER_METRICS = (
    "total_distance_m",
    "reported_high_speed_distance_m",
    "reported_accel_decel_efforts_combined",
    "player_load_reported",
)


@dataclass(frozen=True, slots=True)
class MetricValue:
    key: str
    value: Decimal
    unit: str
    comparability_key: str
    definition_id: str | None
    source_observation_id: UUID
    quality_state: str = "accepted"


@dataclass(frozen=True, slots=True)
class SessionValue:
    id: UUID
    local_date: date
    started_at: datetime | None
    session_type: str
    quality_state: str
    metrics: dict[str, MetricValue]


@dataclass(frozen=True, slots=True)
class TrendPoint:
    session_id: UUID
    local_date: date
    session_type: str
    value: Decimal
    source_observation_id: UUID


@dataclass(frozen=True, slots=True)
class SupportingMetric:
    metric_key: str
    value: Decimal
    unit: str
    source_observation_id: UUID
    definition_id: str | None
    comparability_key: str


@dataclass(frozen=True, slots=True)
class AnalyticsFact:
    kind: str
    status: str
    metric_key: str | None = None
    value: Decimal | None = None
    unit: str | None = None
    baseline_value: Decimal | None = None
    delta: Decimal | None = None
    percent_change: Decimal | None = None
    slope_per_week: Decimal | None = None
    median_value: Decimal | None = None
    mad: Decimal | None = None
    score: Decimal | None = None
    sample_size: int = 0
    session_ids: tuple[UUID, ...] = ()
    source_observation_ids: tuple[UUID, ...] = ()
    points: tuple[TrendPoint, ...] = ()
    supporting_metrics: tuple[SupportingMetric, ...] = ()
    from_date: date | None = None
    to_date: date | None = None
    definition_id: str | None = None
    comparability_key: str | None = None
    note: str | None = None
    rule_version: str = field(default=ANALYTICS_RULE_VERSION)


def display_decimal(value: Decimal | None, unit: str | None) -> str | None:
    if value is None:
        return None
    places = Decimal("1") if unit == "m" else Decimal("0.1") if unit == "km/h" else Decimal("0.001")
    return format(value.quantize(places, rounding=ROUND_HALF_UP), "f")


def history_fingerprint(sessions: list[SessionValue]) -> str:
    """Change whenever accepted history, metric quality, or provenance changes."""
    rows: list[dict[str, object]] = []
    for item in sorted(sessions, key=lambda value: (value.local_date, str(value.id))):
        rows.append(
            {
                "id": str(item.id),
                "date": item.local_date.isoformat(),
                "started_at": item.started_at.isoformat() if item.started_at else None,
                "type": item.session_type,
                "quality": item.quality_state,
                "metrics": [
                    {
                        "key": metric.key,
                        "value": str(metric.value),
                        "unit": metric.unit,
                        "definition": metric.definition_id,
                        "comparability": metric.comparability_key,
                        "quality": metric.quality_state,
                        "source": str(metric.source_observation_id),
                    }
                    for _, metric in sorted(item.metrics.items())
                ],
            }
        )
    payload = json.dumps({"rule": ANALYTICS_RULE_VERSION, "sessions": rows}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _eligible(sessions: list[SessionValue]) -> list[SessionValue]:
    return [item for item in sessions if item.quality_state == "accepted"]


def _metric(item: SessionValue, key: str) -> MetricValue | None:
    value = item.metrics.get(key)
    return value if value is not None and value.quality_state == "accepted" else None


def _ordered(sessions: list[SessionValue]) -> tuple[list[SessionValue], bool]:
    ordered = sorted(
        sessions,
        key=lambda value: (
            value.local_date,
            value.started_at.isoformat() if value.started_at else "",
            str(value.id),
        ),
    )
    ambiguous = any(
        left.local_date == right.local_date
        and (left.started_at is None or right.started_at is None or left.started_at == right.started_at)
        for left, right in zip(ordered, ordered[1:], strict=False)
    )
    return ordered, ambiguous


def _matching_definition(values: list[MetricValue]) -> bool:
    if len(values) < 2:
        return True
    first = values[0]
    if first.comparability_key.startswith("unverified:"):
        return False
    return all(
        value.unit == first.unit
        and value.comparability_key == first.comparability_key
        and value.definition_id == first.definition_id
        for value in values[1:]
    )


def _evidence(sessions: list[SessionValue], key: str) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
    eligible = [(item, metric) for item in sessions if (metric := _metric(item, key)) is not None]
    return tuple(item.id for item, _ in eligible), tuple(metric.source_observation_id for _, metric in eligible)


def latest_comparison(sessions: list[SessionValue], metric_key: str, previous_count: int = 5) -> AnalyticsFact:
    if not 1 <= previous_count <= 5:
        raise ValueError("previous_count must be between 1 and 5")
    ordered, ambiguous = _ordered(_eligible(sessions))
    if not ordered:
        return AnalyticsFact("latest_comparison", "insufficient_history", metric_key)
    if ambiguous:
        _, sources = _evidence(ordered, metric_key)
        return AnalyticsFact(
            "latest_comparison",
            "ambiguous_order",
            metric_key,
            sample_size=len(ordered),
            session_ids=tuple(item.id for item in ordered),
            source_observation_ids=sources,
        )
    latest = ordered[-1]
    current = _metric(latest, metric_key)
    if current is None:
        return AnalyticsFact("latest_comparison", "missing_metric", metric_key, session_ids=(latest.id,))
    candidates = [
        (item, metric)
        for item in reversed(ordered[:-1])
        if item.session_type == latest.session_type
        if (metric := _metric(item, metric_key)) is not None
    ]
    prior = [(item, metric) for item, metric in candidates if _matching_definition([current, metric])][:previous_count]
    base = AnalyticsFact(
        kind="latest_comparison",
        status="insufficient_history",
        metric_key=metric_key,
        value=current.value,
        unit=current.unit,
        from_date=prior[-1][0].local_date
        if prior
        else candidates[0][0].local_date
        if candidates
        else latest.local_date,
        to_date=latest.local_date,
        definition_id=current.definition_id,
        comparability_key=current.comparability_key,
    )
    if not prior:
        return replace(
            base,
            status="not_comparable" if candidates else "insufficient_history",
            sample_size=0,
            session_ids=(latest.id, *(item.id for item, _ in candidates[:previous_count])),
            source_observation_ids=(
                current.source_observation_id,
                *(metric.source_observation_id for _, metric in candidates[:previous_count]),
            ),
        )
    mean = sum((metric.value for _, metric in prior), Decimal(0)) / len(prior)
    delta = current.value - mean
    return replace(
        base,
        status="ok",
        baseline_value=mean,
        delta=delta,
        percent_change=delta / mean * 100 if mean > 0 else None,
        sample_size=len(prior),
        session_ids=(latest.id, *(item.id for item, _ in prior)),
        source_observation_ids=(
            current.source_observation_id,
            *(metric.source_observation_id for _, metric in prior),
        ),
        note="limited_history" if len(prior) < previous_count else None,
    )


def metric_trend(
    sessions: list[SessionValue],
    metric_key: str,
    from_date: date,
    to_date: date,
    session_type: str | None = None,
) -> AnalyticsFact:
    if from_date > to_date:
        raise ValueError("from_date must not exceed to_date")
    selected = [
        item
        for item in _eligible(sessions)
        if from_date <= item.local_date <= to_date
        and (session_type is None or item.session_type == session_type)
        and _metric(item, metric_key) is not None
    ]
    ordered, ambiguous = _ordered(selected)
    if not ordered:
        in_range = [
            item.id
            for item in _eligible(sessions)
            if from_date <= item.local_date <= to_date and (session_type is None or item.session_type == session_type)
        ]
        return AnalyticsFact(
            "trend",
            "missing_metric",
            metric_key,
            from_date=from_date,
            to_date=to_date,
            session_ids=tuple(in_range),
        )
    values = [_metric(item, metric_key) for item in ordered]
    metrics = [value for value in values if value is not None]
    points = tuple(
        TrendPoint(item.id, item.local_date, item.session_type, metric.value, metric.source_observation_id)
        for item, metric in zip(ordered, metrics, strict=True)
    )
    ids, sources = _evidence(ordered, metric_key)
    common = AnalyticsFact(
        kind="trend",
        status="insufficient_history",
        metric_key=metric_key,
        value=metrics[-1].value,
        unit=metrics[-1].unit,
        sample_size=len(metrics),
        session_ids=ids,
        source_observation_ids=sources,
        points=points,
        from_date=from_date,
        to_date=to_date,
        definition_id=metrics[-1].definition_id,
        comparability_key=metrics[-1].comparability_key,
    )
    if len({item.session_type for item in ordered}) > 1:
        return replace(common, status="not_comparable", note="mixed_session_types")
    if not _matching_definition(metrics):
        return replace(common, status="not_comparable")
    if ambiguous:
        return replace(common, status="ambiguous_order")
    if len(metrics) < 2:
        return common
    delta = metrics[-1].value - metrics[0].value
    distinct_dates = {item.local_date for item in ordered}
    slope = None
    if len(distinct_dates) >= 3:
        xs = [Decimal((item.local_date - ordered[0].local_date).days) for item in ordered]
        ys = [metric.value for metric in metrics]
        avg_x = sum(xs, Decimal(0)) / len(xs)
        avg_y = sum(ys, Decimal(0)) / len(ys)
        denominator = sum(((x - avg_x) ** 2 for x in xs), Decimal(0))
        if denominator:
            slope = (
                Decimal(7)
                * sum(((x - avg_x) * (y - avg_y) for x, y in zip(xs, ys, strict=True)), Decimal(0))
                / denominator
            )
    return replace(
        common,
        status="ok",
        delta=delta,
        percent_change=delta / metrics[0].value * 100 if metrics[0].value > 0 else None,
        slope_per_week=slope,
        baseline_value=metrics[0].value,
    )


def personal_record(sessions: list[SessionValue], metric_key: str = "maximum_velocity_kmh") -> AnalyticsFact:
    selected = [(item, metric) for item in _eligible(sessions) if (metric := _metric(item, metric_key)) is not None]
    if not selected:
        return AnalyticsFact("personal_record", "missing_metric", metric_key)
    if not _matching_definition([metric for _, metric in selected]):
        return AnalyticsFact(
            "personal_record",
            "not_comparable",
            metric_key,
            sample_size=len(selected),
            session_ids=tuple(item.id for item, _ in selected),
            source_observation_ids=tuple(metric.source_observation_id for _, metric in selected),
        )
    maximum = max(metric.value for _, metric in selected)
    ties = sorted(
        [(item, metric) for item, metric in selected if metric.value == maximum],
        key=lambda pair: (pair[0].local_date, str(pair[0].id)),
    )
    metric = ties[0][1]
    return AnalyticsFact(
        "personal_record",
        "ok",
        metric_key,
        value=maximum,
        unit=metric.unit,
        sample_size=len(selected),
        session_ids=tuple(item.id for item, _ in ties),
        source_observation_ids=tuple(value.source_observation_id for _, value in ties),
        to_date=ties[0][0].local_date,
        definition_id=metric.definition_id,
        comparability_key=metric.comparability_key,
        note="highest_recorded_workload" if metric_key != "maximum_velocity_kmh" else None,
    )


def hardest_session(sessions: list[SessionValue], metric_key: str = "total_distance_m") -> AnalyticsFact:
    selected = [
        (item, metric)
        for item in _eligible(sessions)
        if item.session_type == "training"
        if (metric := _metric(item, metric_key)) is not None
    ]
    if not selected:
        return AnalyticsFact("hardest_session", "missing_metric", metric_key, note="confirmed_training_only")
    if not _matching_definition([metric for _, metric in selected]):
        return AnalyticsFact(
            "hardest_session",
            "not_comparable",
            metric_key,
            sample_size=len(selected),
            session_ids=tuple(item.id for item, _ in selected),
            source_observation_ids=tuple(metric.source_observation_id for _, metric in selected),
        )
    maximum = max(metric.value for _, metric in selected)
    ties = [(item, metric) for item, metric in selected if metric.value == maximum]
    metric = ties[0][1]
    context_keys = ("reported_high_speed_distance_m", "reported_accel_decel_efforts_combined")
    context = tuple(
        SupportingMetric(
            key, value.value, value.unit, value.source_observation_id, value.definition_id, value.comparability_key
        )
        for key in context_keys
        if (value := _metric(ties[0][0], key)) is not None
    )
    return AnalyticsFact(
        "hardest_session",
        "ok",
        metric_key,
        value=maximum,
        unit=metric.unit,
        sample_size=len(selected),
        session_ids=tuple(item.id for item, _ in ties),
        source_observation_ids=tuple(value.source_observation_id for _, value in ties),
        supporting_metrics=context,
        to_date=ties[0][0].local_date,
        definition_id=metric.definition_id,
        comparability_key=metric.comparability_key,
        note=f"highest_recorded_{metric_key}",
    )


def last_speed_exceedance(sessions: list[SessionValue], threshold_kmh: Decimal) -> AnalyticsFact:
    if not threshold_kmh.is_finite() or not Decimal(0) <= threshold_kmh <= Decimal(100):
        raise ValueError("threshold_kmh must be between 0 and 100")
    key = "maximum_velocity_kmh"
    available = [item for item in _eligible(sessions) if _metric(item, key) is not None]
    if not available:
        return AnalyticsFact("last_speed_exceedance", "missing_metric", key)
    exceeded = [
        item for item in available if (metric := _metric(item, key)) is not None and metric.value > threshold_kmh
    ]
    if not exceeded:
        ids, sources = _evidence(available, key)
        return AnalyticsFact(
            "last_speed_exceedance",
            "not_found",
            key,
            sample_size=len(available),
            session_ids=ids,
            source_observation_ids=sources,
        )
    ordered, ambiguous = _ordered(exceeded)
    if ambiguous:
        ids, sources = _evidence(ordered, key)
        return AnalyticsFact(
            "last_speed_exceedance",
            "ambiguous_order",
            key,
            sample_size=len(ordered),
            session_ids=ids,
            source_observation_ids=sources,
        )
    item = ordered[-1]
    metric = _metric(item, key)
    assert metric is not None
    return AnalyticsFact(
        "last_speed_exceedance",
        "ok",
        key,
        value=metric.value,
        unit=metric.unit,
        sample_size=len(available),
        session_ids=(item.id,),
        source_observation_ids=(metric.source_observation_id,),
        definition_id=metric.definition_id,
        comparability_key=metric.comparability_key,
        note=f"strictly_greater_than_{threshold_kmh}",
    )


def largest_change(sessions: list[SessionValue], *, improvement: bool) -> AnalyticsFact:
    keys = ("maximum_velocity_kmh",) if improvement else OUTLIER_METRICS
    candidates = [latest_comparison(sessions, key) for key in keys]
    comparable = [
        value
        for value in candidates
        if value.status == "ok" and value.percent_change is not None and (not improvement or value.percent_change > 0)
    ]
    if not comparable:
        return AnalyticsFact(
            "largest_improvement" if improvement else "largest_change",
            "insufficient_history",
            note="no_positive_speed_improvement" if improvement else None,
        )
    winner = max(comparable, key=lambda value: abs(value.percent_change or Decimal(0)))
    return AnalyticsFact(
        kind="largest_improvement" if improvement else "largest_change",
        status="ok",
        metric_key=winner.metric_key,
        value=winner.value,
        unit=winner.unit,
        baseline_value=winner.baseline_value,
        delta=winner.delta,
        percent_change=winner.percent_change,
        sample_size=winner.sample_size,
        session_ids=winner.session_ids,
        source_observation_ids=winner.source_observation_ids,
        definition_id=winner.definition_id,
        comparability_key=winner.comparability_key,
        note="workload_change_not_improvement"
        if not improvement and winner.metric_key != "maximum_velocity_kmh"
        else None,
    )


def workload_outliers(sessions: list[SessionValue], session_type: str, limit: int = 10) -> tuple[AnalyticsFact, ...]:
    if session_type not in ("training", "match") or not 1 <= limit <= 20:
        raise ValueError("Use a confirmed session type and limit 1-20")
    ordered, ambiguous = _ordered([item for item in _eligible(sessions) if item.session_type == session_type])
    if ambiguous:
        return (
            AnalyticsFact(
                "workload_outlier",
                "ambiguous_order",
                sample_size=len(ordered),
                session_ids=tuple(item.id for item in ordered),
            ),
        )
    facts: list[AnalyticsFact] = []
    for current_index in range(len(ordered) - 1, max(-1, len(ordered) - limit - 1), -1):
        current = ordered[current_index]
        for key in OUTLIER_METRICS:
            metric = _metric(current, key)
            if metric is None:
                continue
            prior_sessions = [
                item
                for item in reversed(ordered[:current_index])
                if item.local_date >= current.local_date - timedelta(days=60)
            ][:6]
            available = [(item, candidate) for item in prior_sessions if (candidate := _metric(item, key)) is not None]
            preceding = [
                (item, candidate) for item, candidate in available if _matching_definition([metric, candidate])
            ]
            common = AnalyticsFact(
                kind="workload_outlier",
                status="insufficient_history",
                metric_key=key,
                value=metric.value,
                unit=metric.unit,
                sample_size=len(preceding),
                session_ids=(current.id, *(item.id for item, _ in preceding)),
                source_observation_ids=(
                    metric.source_observation_id,
                    *(candidate.source_observation_id for _, candidate in preceding),
                ),
                from_date=current.local_date - timedelta(days=60),
                to_date=current.local_date,
                definition_id=metric.definition_id,
                comparability_key=metric.comparability_key,
            )
            if len(preceding) < 5 and len(available) > len(preceding):
                facts.append(
                    replace(
                        common,
                        status="not_comparable",
                        session_ids=(current.id, *(item.id for item, _ in available)),
                        source_observation_ids=(
                            metric.source_observation_id,
                            *(candidate.source_observation_id for _, candidate in available),
                        ),
                    )
                )
            elif len(preceding) < 5:
                facts.append(common)
            else:
                middle = median(candidate.value for _, candidate in preceding)
                mad = median(abs(candidate.value - middle) for _, candidate in preceding)
                if mad == 0:
                    facts.append(replace(common, median_value=middle, mad=mad, note="insufficient_variation"))
                else:
                    score = Decimal("0.6745") * (metric.value - middle) / mad
                    facts.append(
                        replace(
                            common,
                            status="ok",
                            median_value=middle,
                            mad=mad,
                            score=score,
                            note="high" if score >= Decimal("3.5") else "low" if score <= Decimal("-3.5") else "normal",
                        )
                    )
    return tuple(facts)
