from decimal import Decimal
from pathlib import Path

import pytest
from app.ingestion.adapters.activity_report_pdf_v1 import ActivityReportPdfV1Adapter
from app.ingestion.domain import QualityState, RawMetricObservation, Scope
from app.ingestion.registry import BY_KEY, METRICS, REGISTRY_VERSION, ValueType
from app.ingestion.service import IngestionService
from app.ingestion.validation import ReportValidator


def test_registry_is_real_report_inventory() -> None:
    assert REGISTRY_VERSION == "metrics_v1"
    assert len(METRICS) == len(BY_KEY) == 11
    assert BY_KEY["velocity_band_4_distance_m"].display_name != "Sprint distance"
    assert BY_KEY["reported_sprint_efforts"].value_type is ValueType.COUNT
    assert BY_KEY["source_overall_raw"].trend_eligible is False
    assert BY_KEY["maximum_velocity_kmh"].personal_record_eligible is True
    assert all("threshold" not in definition.key for definition in METRICS)


def test_synthetic_pdf_extracts_twelve_separate_rows(synthetic_pdf: bytes) -> None:
    inspection = IngestionService().inspect_pdf(synthetic_pdf)
    assert inspection.extraction.supported
    report = inspection.extraction.report
    assert report is not None
    assert report.source_team_name == "DEMO CLUB"
    assert report.activity_total_time_s == 5400
    assert report.timezone is None
    assert len(report.athlete_rows) == 12
    assert len(report.report_observations) == 9
    assert all(observation.scope is Scope.REPORT for observation in report.report_observations)
    assert len(inspection.validation.rows) == 12  # type: ignore[union-attr]
    assert [row.quality_state for row in inspection.validation.rows].count(QualityState.ZERO_RECORDED) == 2  # type: ignore[union-attr]
    assert report.athlete_rows[1].observations[0].parsed_value == Decimal(0)
    assert report.athlete_rows[1].observations[-1].parsed_value is None
    assert all(observation.source_locator for row in report.athlete_rows for observation in row.observations)
    assert report.periods == []
    assert "chart_only_unavailable" in {f.code for f in inspection.extraction.findings}
    assert not hasattr(report.athlete_rows[0], "athlete_duration_s")


def test_bad_layout_fails_closed(synthetic_pdf: bytes) -> None:
    adapter = ActivityReportPdfV1Adapter()
    assert adapter.detect(b"not a PDF") is False
    assert adapter.extract(b"not a PDF").supported is False
    assert adapter.detect(synthetic_pdf.replace(b"%PDF", b"%PFX", 1)) is False


def test_anomalies_preserve_source_values(synthetic_pdf: bytes) -> None:
    inspection = IngestionService().inspect_pdf(synthetic_pdf)
    report = inspection.extraction.report
    assert report is not None and inspection.validation is not None
    row = report.athlete_rows[8]
    overall = next(o for o in row.observations if o.source_label == "Overall (%)")
    assert overall.raw_value == "1550"
    assert overall.parsed_value == Decimal("1550")
    assert "source_overall_raw" not in inspection.validation.rows[8].metrics
    assert {f.code for f in inspection.validation.rows[8].findings} >= {
        "invalid_percentage_label",
        "distance_peer_review",
    }
    assert inspection.validation.rows[8].quality_state is QualityState.NEEDS_REVIEW


def test_exact_chart_values_are_reviewed_without_repair(synthetic_pdf: bytes) -> None:
    inspection = IngestionService().inspect_pdf(synthetic_pdf)
    report = inspection.extraction.report
    assert report is not None
    row = report.athlete_rows[1]
    row.observations[-2] = RawMetricObservation(
        source_label="Player Load",
        raw_value="1",
        raw_unit=None,
        parsed_value=Decimal("1"),
        source_locator="p2 chart row 2 Player Load",
        scope=Scope.ATHLETE,
        row_ordinal=2,
        parser_version="1.0.0",
    )
    result = ReportValidator().validate(report)
    assert result.rows[1].metrics["player_load_reported"].value == 1
    assert result.rows[1].quality_state is QualityState.ZERO_RECORDED
    assert "zero_distance_with_load" in {f.code for f in result.rows[1].findings}
    row.observations[-1] = RawMetricObservation(
        source_label="Maximum Velocity",
        raw_value="72.25",
        raw_unit="km/h",
        parsed_value=Decimal("72.25"),
        source_locator="p2 chart row 2 Maximum Velocity",
        scope=Scope.ATHLETE,
        row_ordinal=2,
        parser_version="1.0.0",
    )
    result = ReportValidator().validate(report)
    speed = result.rows[1].metrics["maximum_velocity_kmh"]
    assert speed.value == Decimal("72.25")
    assert speed.quality_state is QualityState.NEEDS_REVIEW


def test_invalid_values_isolate_one_row(synthetic_pdf: bytes) -> None:
    report = IngestionService().inspect_pdf(synthetic_pdf).extraction.report
    assert report is not None
    first = report.athlete_rows[0]
    first.observations[3].parsed_value = Decimal("3500")
    first.observations[8].parsed_value = Decimal("2.5")
    result = ReportValidator().validate(report)
    assert result.rows[0].quality_state is QualityState.NEEDS_REVIEW
    assert result.rows[2].quality_state is QualityState.READY
    assert {f.code for f in result.rows[0].findings} >= {"distance_exceeds_total", "non_whole_count"}


def test_nonfinite_negative_and_unknown_values_are_not_accepted(synthetic_pdf: bytes) -> None:
    report = IngestionService().inspect_pdf(synthetic_pdf).extraction.report
    assert report is not None
    first = report.athlete_rows[0]
    first.observations[1].parsed_value = Decimal("NaN")
    first.observations[3].parsed_value = Decimal("-1")
    first.observations.append(
        RawMetricObservation(
            source_label="Undocumented Metric",
            raw_value="4",
            parsed_value=Decimal(4),
            source_locator="p4 row 1 unknown",
            scope=Scope.ATHLETE,
            row_ordinal=1,
            parser_version="1.0.0",
        )
    )
    result = ReportValidator().validate(report)
    assert result.rows[0].quality_state is QualityState.NEEDS_REVIEW
    assert "reported_meterage_per_minute" not in result.rows[0].metrics
    assert "reported_high_speed_distance_m" not in result.rows[0].metrics
    assert {finding.code for finding in result.rows[0].findings} >= {"invalid_numeric", "unmapped_metric"}


def test_optional_private_report_is_not_a_committed_fixture() -> None:
    path_text = __import__("os").environ.get("PLAYERIQ_LOCAL_REPORT")
    if not path_text:
        pytest.skip("Set PLAYERIQ_LOCAL_REPORT to inspect the private local PDF")
    report = IngestionService().inspect_pdf(Path(path_text).read_bytes()).extraction.report
    assert report is not None
    assert len(report.athlete_rows) > 0
