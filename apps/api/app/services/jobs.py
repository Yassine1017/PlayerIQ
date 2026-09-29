"""Claim and process one durable ingestion job per invocation."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.core.config import Settings
from app.db.session import Database
from app.ingestion.domain import ValidationFinding
from app.ingestion.service import IngestionService
from app.models.tables import ActivityReport, IngestionFinding, IngestionJob, ReportUpload
from app.repositories.ingestion import persist_inspection
from app.repositories.uploads import content_sha256
from app.services.storage import ReportStorage

MAX_ATTEMPTS = 3
STALE_LOCK_AFTER = timedelta(minutes=5)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedJob:
    job_id: UUID
    upload_id: UUID
    storage_key: str
    sha256: str


def claim_next_job(database: Database) -> ClaimedJob | None:
    while True:
        now = datetime.now(UTC)
        with database.worker_transaction() as session:
            job = session.scalar(
                select(IngestionJob)
                .where(
                    or_(
                        and_(
                            IngestionJob.status.in_(["queued", "failed_retryable"]),
                            IngestionJob.next_attempt_at <= now,
                        ),
                        and_(
                            IngestionJob.status == "extracting",
                            IngestionJob.locked_at < now - STALE_LOCK_AFTER,
                        ),
                    )
                )
                .order_by(IngestionJob.next_attempt_at, IngestionJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            upload = session.get(ReportUpload, job.upload_id)
            if upload is None:
                job.status = "rejected"
                job.locked_at = None
                job.last_error_code = "upload_missing"
                continue
            if session.get(ActivityReport, upload.id) is not None:
                job.status = "complete"
                job.locked_at = None
                upload.status = "awaiting_link"
                continue
            job.status = "extracting"
            job.attempts += 1
            job.locked_at = now
            upload.status = "extracting"
            return ClaimedJob(job.id, upload.id, upload.storage_key, upload.sha256)


def process_next_job(database: Database, storage: ReportStorage, settings: Settings) -> bool:
    claim = claim_next_job(database)
    if claim is None:
        return False
    try:
        content = storage.get(claim.storage_key)
    except Exception as exc:
        logger.warning(
            "ingestion_retry job_id=%s code=storage_unavailable error_type=%s",
            claim.job_id,
            type(exc).__name__,
        )
        _retry_or_reject(database, claim, "storage_unavailable")
        return True
    if content_sha256(content) != claim.sha256:
        _reject(database, claim, "storage_hash_mismatch")
        return True
    try:
        inspection = IngestionService(settings).inspect_pdf(content)
        if inspection.validation is None:
            _reject(database, claim, "unsupported_layout", inspection.extraction.findings)
            return True
        with database.worker_transaction() as session:
            job = session.get(IngestionJob, claim.job_id, with_for_update=True)
            upload = session.get(ReportUpload, claim.upload_id, with_for_update=True)
            if job is None or upload is None:
                raise RuntimeError("Claimed job or upload disappeared")
            if session.get(ActivityReport, upload.id) is None:
                upload.status = "validating"
                persist_inspection(session, upload, inspection)
            job.status = "complete"
            job.locked_at = None
            job.last_error_code = None
            upload.status = "awaiting_link"
            upload.error_code = None
            upload.processed_at = datetime.now(UTC)
        return True
    except Exception as exc:
        logger.warning(
            "ingestion_retry job_id=%s code=processing_failed error_type=%s",
            claim.job_id,
            type(exc).__name__,
        )
        _retry_or_reject(database, claim, "processing_failed")
        return True


def _reject(
    database: Database,
    claim: ClaimedJob,
    code: str,
    findings: list[ValidationFinding] | None = None,
) -> None:
    with database.worker_transaction() as session:
        job = session.get(IngestionJob, claim.job_id, with_for_update=True)
        upload = session.get(ReportUpload, claim.upload_id, with_for_update=True)
        if job is None or upload is None:
            return
        job.status = "rejected"
        job.locked_at = None
        job.last_error_code = code
        upload.status = "rejected"
        upload.error_code = code
        upload.processed_at = datetime.now(UTC)
        for finding in findings or []:
            session.add(
                IngestionFinding(
                    report_upload_id=upload.id,
                    code=finding.code,
                    message=finding.message,
                    severity=finding.severity.value,
                    scope=finding.scope.value,
                    row_ordinal=finding.row_ordinal,
                    metric_key=finding.metric_key,
                    source_locator=finding.source_locator,
                )
            )


def _retry_or_reject(database: Database, claim: ClaimedJob, code: str) -> None:
    with database.worker_transaction() as session:
        job = session.get(IngestionJob, claim.job_id, with_for_update=True)
        upload = session.get(ReportUpload, claim.upload_id, with_for_update=True)
        if job is None or upload is None:
            return
        job.locked_at = None
        job.last_error_code = code
        upload.error_code = code
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "rejected"
            upload.status = "rejected"
            upload.processed_at = datetime.now(UTC)
        else:
            job.status = "failed_retryable"
            upload.status = "failed_retryable"
            job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=30 * (2 ** (job.attempts - 1)))
