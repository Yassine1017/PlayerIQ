"""Typed source evidence and validated data, independent of HTTP and ORM."""

from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class Scope(StrEnum):
    REPORT = "report"
    PERIOD = "period"
    ATHLETE = "athlete"


class QualityState(StrEnum):
    READY = "ready"
    ACCEPTED = "accepted"
    ZERO_RECORDED = "zero_recorded"
    NEEDS_REVIEW = "needs_review"
    MISSING = "missing"
    UNMAPPED = "unmapped"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RawMetricObservation(BaseModel):
    source_label: str
    raw_value: str | None
    raw_unit: str | None = None
    parsed_value: Decimal | None = None
    source_locator: str
    scope: Scope
    parser_version: str
    quality_state: QualityState = QualityState.READY
    row_ordinal: int | None = None


class RawAthleteRow(BaseModel):
    row_ordinal: int = Field(gt=0)
    source_name: str
    source_position_code: str | None = None
    observations: list[RawMetricObservation]
    quality_state: QualityState = QualityState.READY


class RawPeriod(BaseModel):
    ordinal: int = Field(gt=0)
    source_label: str
    start_local: time | None = None
    duration_s: int | None = None
    reported_athlete_count: int | None = None
    observations: list[RawMetricObservation] = Field(default_factory=list)


class RawReport(BaseModel):
    parser_key: str
    parser_version: str
    report_kind: str
    source_activity_id: str | None = None
    source_title: str
    source_team_name: str | None = None
    source_venue_name: str | None = None
    reported_local_datetime: datetime | None = None
    timezone: str | None = None
    activity_total_time_s: int | None = None
    reported_athlete_count: int | None = None
    periods: list[RawPeriod] = Field(default_factory=list)
    athlete_rows: list[RawAthleteRow] = Field(default_factory=list)
    report_observations: list[RawMetricObservation] = Field(default_factory=list)


class ValidationFinding(BaseModel):
    code: str
    message: str
    severity: Severity
    scope: Scope
    row_ordinal: int | None = None
    metric_key: str | None = None
    source_locator: str | None = None


class ExtractionResult(BaseModel):
    report: RawReport | None
    findings: list[ValidationFinding] = Field(default_factory=list)
    supported: bool


class NormalizedMetric(BaseModel):
    metric_key: str
    value: Decimal
    unit: str
    source_label: str
    source_locator: str
    definition_id: str | None = None
    comparability_key: str
    quality_state: QualityState


class ValidatedAthleteRow(BaseModel):
    row_ordinal: int
    quality_state: QualityState
    metrics: dict[str, NormalizedMetric] = Field(default_factory=dict)
    findings: list[ValidationFinding] = Field(default_factory=list)


class ValidationResult(BaseModel):
    report: RawReport
    rows: list[ValidatedAthleteRow]
    findings: list[ValidationFinding] = Field(default_factory=list)
