"""Deterministic quality checks; source observations are never rewritten."""

from decimal import Decimal
from statistics import median

from app.ingestion.domain import (
    NormalizedMetric,
    QualityState,
    RawAthleteRow,
    RawReport,
    Scope,
    Severity,
    ValidatedAthleteRow,
    ValidationFinding,
    ValidationResult,
)
from app.ingestion.registry import (
    REGISTRY_VERSION,
    ValueType,
    definition_for_source_label,
)


class ReportValidator:
    def __init__(
        self,
        max_velocity_review_kmh: Decimal = Decimal("45"),
        distance_peer_review_multiplier: Decimal = Decimal("3"),
    ) -> None:
        if max_velocity_review_kmh <= 0 or distance_peer_review_multiplier <= 1:
            raise ValueError("Review thresholds must be positive and meaningful")
        self.max_velocity_review_kmh = max_velocity_review_kmh
        self.distance_peer_review_multiplier = distance_peer_review_multiplier

    def validate(self, report: RawReport) -> ValidationResult:
        rows = [self._validate_row(row, report.parser_key) for row in report.athlete_rows]
        self._apply_peer_distance_review(rows)
        findings: list[ValidationFinding] = []
        if report.timezone is None:
            findings.append(
                ValidationFinding(
                    code="timezone_unknown",
                    message="The source report does not state a timezone; no UTC start is inferred.",
                    severity=Severity.WARNING,
                    scope=Scope.REPORT,
                )
            )
        if report.reported_local_datetime is None:
            findings.append(
                ValidationFinding(
                    code="activity_clock_missing",
                    message="The source report has no extractable activity header clock time.",
                    severity=Severity.WARNING,
                    scope=Scope.REPORT,
                )
            )
        return ValidationResult(report=report, rows=rows, findings=findings)

    def _validate_row(self, row: RawAthleteRow, parser_key: str) -> ValidatedAthleteRow:
        result = ValidatedAthleteRow(row_ordinal=row.row_ordinal, quality_state=QualityState.READY)
        seen: set[str] = set()
        for observation in row.observations:
            definition = definition_for_source_label(observation.source_label)
            if definition is None:
                result.findings.append(
                    self._finding(
                        row,
                        "unmapped_metric",
                        "Unrecognized athlete metric.",
                        observation.source_locator,
                        severity=Severity.WARNING,
                    )
                )
                continue
            key = definition.key
            if key in seen:
                result.findings.append(
                    self._finding(
                        row,
                        "duplicate_metric",
                        "Duplicate source metric for athlete.",
                        observation.source_locator,
                        key,
                        Severity.ERROR,
                    )
                )
                result.quality_state = QualityState.NEEDS_REVIEW
                continue
            seen.add(key)
            if key == "source_overall_raw":
                result.findings.append(
                    self._finding(
                        row,
                        "definition_unresolved",
                        "Overall (%) is source-specific and excluded from analytics.",
                        observation.source_locator,
                        key,
                        Severity.WARNING,
                    )
                )
                if observation.parsed_value is not None and observation.parsed_value > 100:
                    result.findings.append(
                        self._finding(
                            row,
                            "invalid_percentage_label",
                            "Overall (%) exceeds 100; preserve its raw value unchanged.",
                            observation.source_locator,
                            key,
                            Severity.WARNING,
                        )
                    )
                continue
            if observation.raw_value is None:
                result.findings.append(
                    self._finding(
                        row,
                        "metric_missing",
                        "Metric is unavailable from this PDF.",
                        observation.source_locator,
                        key,
                        Severity.INFO,
                    )
                )
                continue
            if observation.parsed_value is None:
                result.findings.append(
                    self._finding(
                        row,
                        "metric_unreadable",
                        "Printed source label could not be parsed; review the original report.",
                        observation.source_locator,
                        key,
                        Severity.WARNING,
                    )
                )
                continue
            value = observation.parsed_value
            if not value.is_finite() or value < 0:
                result.findings.append(
                    self._finding(
                        row,
                        "invalid_numeric",
                        "Metric must be finite and nonnegative.",
                        observation.source_locator,
                        key,
                        Severity.ERROR,
                    )
                )
                result.quality_state = QualityState.NEEDS_REVIEW
                continue
            if definition.value_type is ValueType.COUNT and value != value.to_integral_value():
                result.findings.append(
                    self._finding(
                        row,
                        "non_whole_count",
                        "Effort count must be a whole number.",
                        observation.source_locator,
                        key,
                        Severity.ERROR,
                    )
                )
                result.quality_state = QualityState.NEEDS_REVIEW
                continue
            if observation.raw_unit not in (None, definition.canonical_unit) and key != "player_load_reported":
                result.findings.append(
                    self._finding(
                        row,
                        "unit_mismatch",
                        "Source unit does not match metric definition.",
                        observation.source_locator,
                        key,
                        Severity.ERROR,
                    )
                )
                result.quality_state = QualityState.NEEDS_REVIEW
                continue
            metric_state = (
                QualityState.NEEDS_REVIEW
                if observation.quality_state is QualityState.NEEDS_REVIEW
                else QualityState.ACCEPTED
            )
            if key == "maximum_velocity_kmh" and value > self.max_velocity_review_kmh:
                metric_state = QualityState.NEEDS_REVIEW
                result.findings.append(
                    self._finding(
                        row,
                        "maximum_velocity_review",
                        "Maximum velocity exceeds the configured review limit.",
                        observation.source_locator,
                        key,
                        Severity.WARNING,
                    )
                )
            comparability_key = (
                f"unverified:{parser_key}:{key}" if definition.source_specific else f"{REGISTRY_VERSION}:{key}"
            )
            result.metrics[key] = NormalizedMetric(
                metric_key=key,
                value=value,
                unit=definition.canonical_unit,
                source_label=observation.source_label,
                source_locator=observation.source_locator,
                definition_id=None if definition.source_specific else REGISTRY_VERSION,
                comparability_key=comparability_key,
                quality_state=metric_state,
            )

        distance = result.metrics.get("total_distance_m")
        if distance is None:
            result.quality_state = QualityState.NEEDS_REVIEW
            result.findings.append(
                self._finding(
                    row,
                    "distance_missing",
                    "Total distance is required for an active row.",
                    metric_key="total_distance_m",
                    severity=Severity.ERROR,
                )
            )
        elif distance.value == 0:
            result.quality_state = QualityState.ZERO_RECORDED
            result.findings.append(
                self._finding(
                    row,
                    "zero_distance_row",
                    "Zero distance does not establish athlete participation.",
                    metric_key="total_distance_m",
                    severity=Severity.WARNING,
                )
            )
            load = result.metrics.get("player_load_reported")
            if load is not None and load.value > 0:
                result.findings.append(
                    self._finding(
                        row,
                        "zero_distance_with_load",
                        "Source Player Load is nonzero despite zero distance; preserve both.",
                        metric_key="player_load_reported",
                        severity=Severity.WARNING,
                    )
                )
        else:
            for key in (
                "reported_high_speed_distance_m",
                "velocity_band_2_distance_m",
                "velocity_band_4_distance_m",
            ):
                candidate = result.metrics.get(key)
                if candidate is not None and candidate.value > distance.value:
                    result.quality_state = QualityState.NEEDS_REVIEW
                    candidate.quality_state = QualityState.NEEDS_REVIEW
                    result.findings.append(
                        self._finding(
                            row,
                            "distance_exceeds_total",
                            "Source distance exceeds total distance for this athlete.",
                            metric_key=key,
                            severity=Severity.ERROR,
                        )
                    )
        return result

    def _apply_peer_distance_review(self, rows: list[ValidatedAthleteRow]) -> None:
        active_distances = [
            metric.value
            for row in rows
            if (metric := row.metrics.get("total_distance_m")) is not None and metric.value > 0
        ]
        if len(active_distances) < 5:
            return
        peer_median = median(active_distances)
        if peer_median <= 0:
            return
        for row in rows:
            distance = row.metrics.get("total_distance_m")
            if distance is not None and distance.value > peer_median * self.distance_peer_review_multiplier:
                row.quality_state = QualityState.NEEDS_REVIEW
                distance.quality_state = QualityState.NEEDS_REVIEW
                row.findings.append(
                    ValidationFinding(
                        code="distance_peer_review",
                        message="Distance is unusually high relative to listed active rows; review exposure/device.",
                        severity=Severity.WARNING,
                        scope=Scope.ATHLETE,
                        row_ordinal=row.row_ordinal,
                        metric_key="total_distance_m",
                    )
                )

    @staticmethod
    def _finding(
        row: RawAthleteRow,
        code: str,
        message: str,
        source_locator: str | None = None,
        metric_key: str | None = None,
        severity: Severity = Severity.WARNING,
    ) -> ValidationFinding:
        return ValidationFinding(
            code=code,
            message=message,
            severity=severity,
            scope=Scope.ATHLETE,
            row_ordinal=row.row_ordinal,
            metric_key=metric_key,
            source_locator=source_locator,
        )
