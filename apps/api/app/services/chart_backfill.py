"""Bounded automatic chart upgrade for legacy uploads, without relinking players."""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import Database
from app.ingestion.domain import QualityState
from app.ingestion.registry import BY_KEY
from app.ingestion.service import IngestionService, Inspection
from app.models.tables import (
    ActivityReport,
    ChartMetricReview,
    IngestionFinding,
    PlayerSession,
    ReportUpload,
    SessionMetricValue,
    SourceAthleteRow,
    SourceMetricObservation,
)
from app.repositories.ingestion import _observation
from app.repositories.observations import BACKFILL_LOCATOR
from app.repositories.uploads import content_sha256
from app.services.authorization import require_upload
from app.services.storage import ReportStorage
from app.services.transaction_locks import lock_resource

BACKFILL_CODE = "automatic_chart_backfill_complete"
CHART_KEYS = ("maximum_velocity_kmh", "player_load_reported")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LegacyChartReport:
    upload_id: UUID
    uploader_id: UUID
    storage_key: str
    sha256: str


def next_legacy_chart_report(database: Database) -> LegacyChartReport | None:
    with database.worker_transaction() as session:
        upload = session.scalar(
            select(ReportUpload)
            .where(
                ReportUpload.status == "awaiting_link",
                ReportUpload.parser_key == "activity_report_pdf_v1",
                ReportUpload.parser_version == "1.0.0",
                ~exists().where(
                    IngestionFinding.report_upload_id == ReportUpload.id, IngestionFinding.code == BACKFILL_CODE
                ),
            )
            .order_by(ReportUpload.created_at, ReportUpload.id)
            .limit(1)
        )
        if upload is None:
            return None
        return LegacyChartReport(upload.id, upload.uploaded_by_user_id, upload.storage_key, upload.sha256)


def apply_chart_backfill(session: Session, claim: LegacyChartReport, inspection: Inspection) -> int:
    """Uploader-context transaction: append evidence and fill missing accepted slots.

    Never update the PDF, original observations, identities, session IDs, table
    values or manually confirmed/held charts. Row/date evidence must still match.
    """
    upload = require_upload(session, claim.uploader_id, claim.upload_id)
    if upload.sha256 != claim.sha256 or upload.status != "awaiting_link" or upload.parser_version != "1.0.0":
        raise ValueError("Legacy upload changed before chart backfill")
    report = inspection.extraction.report
    if report is None or inspection.validation is None or report.parser_key != upload.parser_key:
        raise ValueError("Legacy report is not supported by chart extraction")
    activity = session.get(ActivityReport, upload.id)
    if activity is None or activity.reported_local_datetime != report.reported_local_datetime:
        raise ValueError("Legacy report date no longer matches")
    lock_resource(session, "chart-backfill", str(upload.id))
    rows = session.scalars(
        select(SourceAthleteRow)
        .where(SourceAthleteRow.report_upload_id == upload.id)
        .order_by(SourceAthleteRow.row_ordinal)
    ).all()
    if [(r.row_ordinal, r.source_name, r.source_position_code) for r in rows] != [
        (r.row_ordinal, r.source_name, r.source_position_code) for r in report.athlete_rows
    ]:
        raise ValueError("Legacy source rows no longer match")
    validated = {r.row_ordinal: r for r in inspection.validation.rows}
    count = 0
    for stored, raw in zip(rows, report.athlete_rows, strict=True):
        lock_resource(session, "source-row", str(stored.id))
        accepted = session.scalar(select(PlayerSession).where(PlayerSession.source_athlete_row_id == stored.id))
        for key in CHART_KEYS:
            definition = BY_KEY[key]
            label = definition.source_aliases[0]
            observation = session.scalar(
                select(SourceMetricObservation).where(
                    SourceMetricObservation.athlete_row_id == stored.id,
                    SourceMetricObservation.source_label == label,
                    SourceMetricObservation.source_locator.contains(BACKFILL_LOCATOR),
                )
            )
            metric = validated[stored.row_ordinal].metrics.get(key)
            if observation is None:
                original = next(o for o in raw.observations if o.source_label == label)
                observation = _observation(original, athlete_row_id=stored.id)
                observation.source_locator = f"{original.source_locator} {BACKFILL_LOCATOR}"
                if len(observation.source_locator) > 255:
                    raise ValueError("Chart provenance exceeds storage bound")
                if metric is not None:
                    observation.quality_state = metric.quality_state.value
                session.add(observation)
                session.flush()
            if accepted is None or accepted.quality_state != "accepted" or stored.participation_state != "ready":
                continue
            if validated[stored.row_ordinal].quality_state != QualityState.READY:
                continue
            # Confirmed/held manual labels remain authoritative, including a held
            # reading that intentionally removed an earlier accepted metric.
            manual = session.scalar(
                select(ChartMetricReview.id).where(
                    ChartMetricReview.athlete_row_id == stored.id,
                    ChartMetricReview.metric_key == key,
                    ChartMetricReview.status.in_(["confirmed", "held"]),
                )
            )
            if manual or session.get(SessionMetricValue, (accepted.id, key)) is not None:
                continue
            if metric is None or metric.quality_state != QualityState.ACCEPTED:
                continue
            if observation.quality_state != "accepted" or observation.parsed_value != metric.value:
                continue
            session.add(
                SessionMetricValue(
                    player_session_id=accepted.id,
                    metric_key=key,
                    value=metric.value,
                    unit=metric.unit,
                    source_observation_id=observation.id,
                    definition_id=metric.definition_id,
                    comparability_key=metric.comparability_key,
                    quality_state="accepted",
                )
            )
            session.flush()
            count += 1
    return count


def process_next_chart_backfill(
    worker: Database,
    api: Database,
    storage: ReportStorage,
    settings: Settings,
) -> bool:
    claim = next_legacy_chart_report(worker)
    if claim is None:
        return False
    # Storage bytes stay in memory. Never log source labels, values, paths or keys.
    content = storage.get(claim.storage_key)
    if content_sha256(content) != claim.sha256:
        raise ValueError("Legacy storage hash does not match")
    inspection = IngestionService(settings).inspect_pdf(content)
    with api.user_transaction(claim.uploader_id) as session:
        count = apply_chart_backfill(session, claim, inspection)
    # Worker owns ingestion audit writes; it never gains accepted-history access.
    # A failure here is retry-safe: the uploader transaction reuses source IDs.
    with worker.worker_transaction() as session:
        lock_resource(session, "chart-backfill", str(claim.upload_id))
        if (
            session.scalar(
                select(IngestionFinding.id).where(
                    IngestionFinding.report_upload_id == claim.upload_id,
                    IngestionFinding.code == BACKFILL_CODE,
                )
            )
            is None
        ):
            session.add(
                IngestionFinding(
                    report_upload_id=claim.upload_id,
                    code=BACKFILL_CODE,
                    severity="info",
                    scope="report",
                    message="Legacy chart extraction completed; only validated chart values enter accepted history.",
                    source_locator=BACKFILL_LOCATOR,
                )
            )
            for finding in inspection.extraction.findings + [
                f
                for row in (inspection.validation.rows if inspection.validation else [])
                for f in row.findings
                if f.metric_key in CHART_KEYS
            ]:
                if not finding.code.startswith("chart") and finding.metric_key not in CHART_KEYS:
                    continue
                session.add(
                    IngestionFinding(
                        report_upload_id=claim.upload_id,
                        code=finding.code,
                        message=finding.message,
                        severity=finding.severity.value,
                        scope=finding.scope.value,
                        row_ordinal=finding.row_ordinal,
                        metric_key=finding.metric_key,
                        source_locator=finding.source_locator,
                    )
                )
    logger.info("automatic_chart_backfill_completed accepted_slots_added=%s", count)
    return True
