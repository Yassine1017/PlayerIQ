"""Versioned, report-grounded V1 athlete metric definitions."""

from dataclasses import dataclass
from enum import StrEnum

REGISTRY_VERSION = "metrics_v1"


class ValueType(StrEnum):
    DECIMAL = "decimal"
    COUNT = "count"


class AnalyticalRole(StrEnum):
    RUNNING_VOLUME = "running_volume"
    INTENSITY = "intensity"
    HIGH_SPEED = "high_speed"
    EFFORTS = "efforts"
    SPRINTING = "sprinting"
    SPEED = "speed"
    SOURCE_ONLY = "source_only"


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    key: str
    display_name: str
    canonical_unit: str
    value_type: ValueType
    source_aliases: tuple[str, ...]
    analytical_role: AnalyticalRole
    trend_eligible: bool
    personal_record_eligible: bool
    source_specific: bool
    quality_requirements: tuple[str, ...]


METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "total_distance_m",
        "Total distance",
        "m",
        ValueType.DECIMAL,
        ("Distance (m)",),
        AnalyticalRole.RUNNING_VOLUME,
        True,
        False,
        False,
        ("finite", "nonnegative", "active_row", "not_held"),
    ),
    MetricDefinition(
        "reported_meterage_per_minute",
        "Meterage per minute",
        "m/min",
        ValueType.DECIMAL,
        ("Meterage Per Minute",),
        AnalyticalRole.INTENSITY,
        True,
        False,
        True,
        ("finite", "nonnegative", "matching_source_definition", "not_held"),
    ),
    MetricDefinition(
        "source_overall_raw",
        "Overall (source label)",
        "% (unverified)",
        ValueType.DECIMAL,
        ("Overall (%)",),
        AnalyticalRole.SOURCE_ONLY,
        False,
        False,
        True,
        ("preserve_raw", "definition_unresolved", "exclude_from_analytics"),
    ),
    MetricDefinition(
        "reported_high_speed_distance_m",
        "High speed distance (reported)",
        "m",
        ValueType.DECIMAL,
        ("High Speed Distance (m)",),
        AnalyticalRole.HIGH_SPEED,
        True,
        False,
        True,
        ("finite", "nonnegative", "not_above_total_distance", "matching_source_definition"),
    ),
    MetricDefinition(
        "reported_accel_decel_efforts_combined",
        "Acceleration + deceleration efforts",
        "count",
        ValueType.COUNT,
        ("Accel&Decel Efforts",),
        AnalyticalRole.EFFORTS,
        True,
        False,
        True,
        ("whole_count", "nonnegative", "matching_source_definition"),
    ),
    MetricDefinition(
        "reported_accel_decel_efforts_per_min",
        "Acceleration + deceleration efforts/min",
        "count/min",
        ValueType.DECIMAL,
        ("Accel&Decel Efforts Per Minute",),
        AnalyticalRole.INTENSITY,
        True,
        False,
        True,
        ("finite", "nonnegative", "matching_source_definition"),
    ),
    MetricDefinition(
        "velocity_band_2_distance_m",
        "Velocity band 2 distance",
        "m",
        ValueType.DECIMAL,
        ("Velocity Band 2 Distance (m)",),
        AnalyticalRole.RUNNING_VOLUME,
        True,
        False,
        True,
        ("finite", "nonnegative", "not_above_total_distance", "unknown_band"),
    ),
    MetricDefinition(
        "velocity_band_4_distance_m",
        "Velocity band 4 distance",
        "m",
        ValueType.DECIMAL,
        ("Velocity Band 4 Distance (m)",),
        AnalyticalRole.RUNNING_VOLUME,
        True,
        False,
        True,
        ("finite", "nonnegative", "not_above_total_distance", "unknown_band"),
    ),
    MetricDefinition(
        "reported_sprint_efforts",
        "Sprint efforts (reported)",
        "count",
        ValueType.COUNT,
        ("Sprint Efforts",),
        AnalyticalRole.SPRINTING,
        True,
        False,
        True,
        ("whole_count", "nonnegative", "unknown_threshold", "matching_source_definition"),
    ),
    MetricDefinition(
        "player_load_reported",
        "Player Load (reported)",
        "source units",
        ValueType.DECIMAL,
        ("Player Load",),
        AnalyticalRole.SOURCE_ONLY,
        True,
        False,
        True,
        ("exact_chart_value", "finite", "nonnegative", "unknown_formula"),
    ),
    MetricDefinition(
        "maximum_velocity_kmh",
        "Maximum velocity",
        "km/h",
        ValueType.DECIMAL,
        ("Maximum Velocity",),
        AnalyticalRole.SPEED,
        True,
        True,
        False,
        ("exact_chart_value", "finite", "nonnegative", "speed_review_limit", "not_held"),
    ),
)

BY_KEY = {definition.key: definition for definition in METRICS}
BY_SOURCE_ALIAS = {alias: definition for definition in METRICS for alias in definition.source_aliases}


def definition_for_source_label(label: str) -> MetricDefinition | None:
    """Resolve only athlete-scope source labels; aggregates retain their own scope."""
    return BY_SOURCE_ALIAS.get(label)
