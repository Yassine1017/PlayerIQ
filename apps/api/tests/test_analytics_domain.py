"""Independent numeric examples for the pure Phase 3 analytics rules."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.analytics.domain import (
    MetricValue,
    SessionValue,
    hardest_session,
    history_fingerprint,
    largest_change,
    last_speed_exceedance,
    latest_comparison,
    metric_trend,
    personal_record,
    workload_outliers,
)

START = date(2025, 1, 1)


def session(
    ordinal: int,
    *,
    distance: str | None = None,
    speed: str | None = None,
    load: str | None = None,
    training: bool = True,
    day: date | None = None,
    load_key: str = "unverified:pdf:player_load_reported",
) -> SessionValue:
    metrics: dict[str, MetricValue] = {}
    for metric_key, raw, unit, key in (
        ("total_distance_m", distance, "m", "metrics_v1:total_distance_m"),
        ("maximum_velocity_kmh", speed, "km/h", "metrics_v1:maximum_velocity_kmh"),
        ("player_load_reported", load, "source units", load_key),
    ):
        if raw is not None:
            metrics[metric_key] = MetricValue(
                key=metric_key,
                value=Decimal(raw),
                unit=unit,
                comparability_key=key,
                definition_id=None if metric_key == "player_load_reported" else "metrics_v1",
                source_observation_id=UUID(int=ordinal * 100 + len(metrics) + 1),
            )
    return SessionValue(
        id=UUID(int=ordinal),
        local_date=day or START + timedelta(days=ordinal * 7),
        started_at=None,
        session_type="training" if training else "match",
        quality_state="accepted",
        metrics=metrics,
    )


def test_latest_previous_five_is_exact_and_zero_baseline_has_no_percent() -> None:
    history = [session(i, distance=str(100 + 10 * i)) for i in range(1, 7)]
    result = latest_comparison(history, "total_distance_m")
    assert result.status == "ok"
    assert result.value == Decimal("160")
    assert result.baseline_value == Decimal("130")
    assert result.delta == Decimal("30")
    assert result.percent_change == Decimal("30") / Decimal("130") * 100
    assert result.sample_size == 5
    assert len(result.session_ids) == 6
    assert result.rule_version == "analytics_v1"

    zero = latest_comparison([session(1, distance="0"), session(2, distance="10")], "total_distance_m")
    assert zero.status == "ok"
    assert zero.baseline_value == 0
    assert zero.percent_change is None
    assert latest_comparison([session(1, speed=None)], "maximum_velocity_kmh").status == "missing_metric"


def test_latest_uses_previous_comparable_sessions_only() -> None:
    first = session(1, speed="20")
    incompatible = session(2, speed="24")
    incompatible_speed = replace(incompatible.metrics["maximum_velocity_kmh"], comparability_key="other_provider")
    incompatible = replace(incompatible, metrics={"maximum_velocity_kmh": incompatible_speed})
    latest = session(3, speed="30")
    result = latest_comparison([first, incompatible, latest], "maximum_velocity_kmh")
    assert result.status == "ok"
    assert result.sample_size == 1
    assert result.baseline_value == Decimal("20")
    assert result.session_ids == (UUID(int=3), UUID(int=1))


def test_same_date_without_confirmed_start_is_ambiguous() -> None:
    history = [
        session(1, distance="100", day=START),
        session(2, distance="120", day=START),
    ]
    assert latest_comparison(history, "total_distance_m").status == "ambiguous_order"
    assert (
        last_speed_exceedance(
            [session(1, speed="31", day=START), session(2, speed="32", day=START)], Decimal("30")
        ).status
        == "ambiguous_order"
    )


def test_speed_threshold_is_strict_and_record_keeps_ties() -> None:
    history = [session(1, speed="30"), session(2, speed="31"), session(3, speed="31")]
    result = last_speed_exceedance(history, Decimal("30"))
    assert result.status == "ok"
    assert result.value == Decimal("31")
    assert result.session_ids == (UUID(int=3),)
    assert last_speed_exceedance([session(1, speed="30")], Decimal("30")).status == "not_found"
    best = personal_record(history)
    assert best.value == Decimal("31")
    assert best.session_ids == (UUID(int=2), UUID(int=3))
    assert hardest_session([session(1, distance="100"), session(2, distance="500", training=False)]).value == 100


def test_player_load_unknown_definition_cannot_be_compared() -> None:
    history = [session(1, load="100"), session(2, load="120")]
    assert latest_comparison(history, "player_load_reported").status == "not_comparable"
    assert metric_trend(history, "player_load_reported", START, START + timedelta(days=30)).status == "not_comparable"
    assert largest_change(history, improvement=True).status == "insufficient_history"
    confirmed = [
        session(1, load="100", load_key="reviewed:provider-config-1"),
        session(2, load="120", load_key="reviewed:provider-config-1"),
    ]
    assert latest_comparison(confirmed, "player_load_reported").delta == Decimal("20")
    assert largest_change(confirmed, improvement=False).note == "workload_change_not_improvement"


def test_workload_change_does_not_select_speed() -> None:
    history = [session(1, distance="100", speed="10"), session(2, distance="110", speed="30")]
    assert largest_change(history, improvement=True).metric_key == "maximum_velocity_kmh"
    result = largest_change(history, improvement=False)
    assert result.metric_key == "total_distance_m"
    assert result.percent_change == Decimal("10")
    assert result.note == "workload_change_not_improvement"


def test_trend_uses_distinct_dates_for_weekly_slope() -> None:
    history = [session(1, speed="10"), session(2, speed="20"), session(3, speed="30")]
    result = metric_trend(history, "maximum_velocity_kmh", START, START + timedelta(days=30))
    assert result.status == "ok"
    assert result.delta == Decimal("20")
    assert result.percent_change == Decimal("200")
    assert result.slope_per_week == Decimal("10")
    assert len(result.points) == 3


def test_trend_date_boundaries_and_single_date_slope() -> None:
    history = [session(1, speed="10"), session(2, speed="20"), session(3, speed="30")]
    start = history[1].local_date
    end = history[2].local_date
    result = metric_trend(history, "maximum_velocity_kmh", start, end)
    assert result.status == "ok"
    assert result.session_ids == (UUID(int=2), UUID(int=3))
    assert result.delta == Decimal("10")
    assert result.slope_per_week is None
    single = metric_trend(history, "maximum_velocity_kmh", start, start)
    assert single.status == "insufficient_history"
    assert single.sample_size == 1


def test_trend_does_not_mix_training_and_match() -> None:
    history = [session(1, speed="20"), session(2, speed="25", training=False)]
    result = metric_trend(history, "maximum_velocity_kmh", START, START + timedelta(days=30))
    assert result.status == "not_comparable"
    assert result.note == "mixed_session_types"
    training_only = metric_trend(history, "maximum_velocity_kmh", START, START + timedelta(days=30), "training")
    assert training_only.status == "insufficient_history"


def test_outlier_rule_and_zero_mad() -> None:
    baseline = [session(i, distance=str(99 + i)) for i in range(1, 7)]
    high = session(7, distance="120")
    result = workload_outliers([*baseline, high], "training", 1)[0]
    assert result.status == "ok"
    assert result.sample_size == 6
    assert result.median_value == Decimal("102.5")
    assert result.mad == Decimal("1.5")
    assert result.score == Decimal("0.6745") * Decimal("17.5") / Decimal("1.5")
    assert result.note == "high"
    flat = [session(i, distance="100") for i in range(1, 7)]
    unchanged = workload_outliers([*flat, session(7, distance="120")], "training", 1)[0]
    assert unchanged.status == "insufficient_history"
    assert unchanged.note == "insufficient_variation"


def test_outlier_uses_six_prior_sessions_before_metric_coverage() -> None:
    history = [session(i, distance=str(99 + i)) for i in range(1, 8)]
    history[2] = session(3, distance=None)
    current = session(8, distance="120")
    result = workload_outliers([*history, current], "training", 1)[0]
    assert result.status == "ok"
    assert result.sample_size == 5
    assert UUID(int=1) not in result.session_ids
    assert UUID(int=3) not in result.session_ids


def test_outlier_does_not_use_unverified_player_load_baseline() -> None:
    history = [session(i, load=str(100 + i)) for i in range(1, 8)]
    result = next(
        fact for fact in workload_outliers(history, "training", 1) if fact.metric_key == "player_load_reported"
    )
    assert result.status == "not_comparable"
    assert result.sample_size == 0


def test_fingerprint_changes_with_confirmed_history() -> None:
    before = [session(1, speed="25")]
    after = [session(1, speed="26")]
    assert history_fingerprint(before) != history_fingerprint(after)
    assert history_fingerprint(before) == history_fingerprint(list(before))


def test_hardest_session_includes_accepted_source_context() -> None:
    hardest = session(1, distance="500")
    high_speed = MetricValue(
        key="reported_high_speed_distance_m",
        value=Decimal("80"),
        unit="m",
        comparability_key="unverified:pdf:reported_high_speed_distance_m",
        definition_id=None,
        source_observation_id=UUID(int=900),
    )
    hardest = replace(hardest, metrics={**hardest.metrics, high_speed.key: high_speed})
    result = hardest_session([hardest, session(2, distance="400")])
    assert result.value == Decimal("500")
    assert len(result.supporting_metrics) == 1
    assert result.supporting_metrics[0].value == Decimal("80")
    assert result.supporting_metrics[0].source_observation_id == UUID(int=900)
