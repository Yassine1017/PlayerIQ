"""Stable HTTP projections of versioned deterministic facts."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TrendPointOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    local_date: date
    value: str
    source_observation_id: UUID


class SupportingMetricOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_key: str
    value: str
    display_value: str
    unit: str
    source_observation_id: UUID
    definition_id: str | None
    comparability_key: str


class AnalyticsFactOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    status: str
    rule_version: str
    metric_key: str | None
    value: str | None
    display_value: str | None
    unit: str | None
    baseline_value: str | None
    delta: str | None
    percent_change: str | None
    slope_per_week: str | None
    median_value: str | None
    mad: str | None
    score: str | None
    sample_size: int
    session_ids: list[UUID]
    source_observation_ids: list[UUID]
    points: list[TrendPointOut]
    supporting_metrics: list[SupportingMetricOut]
    from_date: date | None
    to_date: date | None
    definition_id: str | None
    comparability_key: str | None
    note: str | None


class AnalyticsOverviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: UUID
    history_fingerprint: str
    rule_version: str
    facts: list[AnalyticsFactOut]


class AnalyticsOutliersOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    history_fingerprint: str
    rule_version: str
    items: list[AnalyticsFactOut]
