"""Persist an inspected report as source evidence without linking any player."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.domain import RawMetricObservation, ValidationFinding
from app.ingestion.registry import definition_for_source_label
from app.ingestion.service import Inspection
from app.models.tables import (
    ActivityReport,
    IngestionFinding,
    ReportPeriod,
    ReportUpload,
    SourceAthleteRow,
    SourceMetricObservation,
)


def persist_inspection(session: Session, upload: ReportUpload, inspection: Inspection) -> None:
    """Stage source rows and findings in the caller's transaction.

    The caller owns commit/rollback and must authorize the upload identity before
    calling. Reprocessing an already persisted report is rejected.
    """
    if inspection.validation is None or inspection.extraction.report is None:
        raise ValueError("Unsupported report cannot be persisted")
    if upload.id is None:
        raise ValueError("Upload must have an assigned ID")
    if (
        session.scalar(select(ActivityReport.report_upload_id).where(ActivityReport.report_upload_id == upload.id))
        is not None
    ):
        raise ValueError("Report has already been persisted")

    report = inspection.extraction.report
    validation = inspection.validation
    session.add(
        ActivityReport(
            report_upload_id=upload.id,
            report_kind=report.report_kind,
            source_activity_id=report.source_activity_id,
            source_title=report.source_title,
            source_team_name=report.source_team_name,
            source_venue_name=report.source_venue_name,
            reported_local_datetime=report.reported_local_datetime,
            timezone=report.timezone,
            activity_total_time_s=report.activity_total_time_s,
            reported_athlete_count=report.reported_athlete_count,
        )
    )
    session.flush()
    for observation in report.report_observations:
        session.add(_observation(observation, report_upload_id=upload.id))
    for period in report.periods:
        source_period = ReportPeriod(
            report_upload_id=upload.id,
            ordinal=period.ordinal,
            source_label=period.source_label,
            start_local=period.start_local,
            duration_s=period.duration_s,
            reported_athlete_count=period.reported_athlete_count,
        )
        session.add(source_period)
        session.flush()
        for observation in period.observations:
            session.add(_observation(observation, period_id=source_period.id))
    states = {row.row_ordinal: row.quality_state for row in validation.rows}
    validated_by_ordinal = {row.row_ordinal: row for row in validation.rows}
    for row in report.athlete_rows:
        source_row = SourceAthleteRow(
            report_upload_id=upload.id,
            row_ordinal=row.row_ordinal,
            source_name=row.source_name,
            source_position_code=row.source_position_code,
            participation_state=states[row.row_ordinal].value,
        )
        session.add(source_row)
        session.flush()
        for observation in row.observations:
            definition = definition_for_source_label(observation.source_label)
            metric = (
                validated_by_ordinal[row.row_ordinal].metrics.get(definition.key) if definition is not None else None
            )
            source = _observation(observation, athlete_row_id=source_row.id)
            if metric is not None:
                source.quality_state = metric.quality_state.value
            session.add(source)
    for finding in (
        inspection.extraction.findings
        + validation.findings
        + [finding for row in validation.rows for finding in row.findings]
    ):
        session.add(_finding(upload.id, finding))
    upload.parser_key = report.parser_key
    upload.parser_version = report.parser_version
    upload.status = "awaiting_link"


def _observation(
    value: RawMetricObservation,
    *,
    report_upload_id=None,  # type: ignore[no-untyped-def]
    period_id=None,  # type: ignore[no-untyped-def]
    athlete_row_id=None,  # type: ignore[no-untyped-def]
) -> SourceMetricObservation:
    return SourceMetricObservation(
        scope=value.scope.value,
        report_upload_id=report_upload_id,
        period_id=period_id,
        athlete_row_id=athlete_row_id,
        source_label=value.source_label,
        raw_value=value.raw_value,
        raw_unit=value.raw_unit,
        parsed_value=value.parsed_value,
        source_locator=value.source_locator,
        parser_version=value.parser_version,
        quality_state=value.quality_state.value,
    )


def _finding(upload_id, value: ValidationFinding) -> IngestionFinding:  # type: ignore[no-untyped-def]
    return IngestionFinding(
        report_upload_id=upload_id,
        code=value.code,
        message=value.message,
        severity=value.severity.value,
        scope=value.scope.value,
        row_ordinal=value.row_ordinal,
        metric_key=value.metric_key,
        source_locator=value.source_locator,
    )
