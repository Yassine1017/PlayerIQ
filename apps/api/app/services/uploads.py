"""Authenticated, bounded PDF upload and durable job creation."""

from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.api.errors import AppError
from app.core.config import Settings
from app.db.session import Database
from app.ingestion.adapters.activity_report_pdf_v1 import ActivityReportPdfV1Adapter
from app.models.tables import IngestionJob, ReportUpload
from app.repositories.uploads import content_sha256, find_active_duplicate
from app.services.storage import ReportStorage


def validate_pdf_upload(
    filename: str | None,
    mime_type: str | None,
    content: bytes,
    settings: Settings,
) -> str:
    if not filename or len(filename) > 255 or any(c in filename for c in ("/", "\\", "\x00", "\r", "\n")):
        raise AppError("invalid_filename", "Use a simple PDF filename", 400)
    if not filename.lower().endswith(".pdf"):
        raise AppError("invalid_extension", "Only PDF files are supported", 415)
    if mime_type != "application/pdf":
        raise AppError("invalid_mime_type", "Expected application/pdf", 415)
    if len(content) > settings.max_upload_bytes:
        raise AppError("upload_too_large", "PDF exceeds upload size limit", 413)
    if not content.startswith(b"%PDF-"):
        raise AppError("invalid_pdf_magic", "File is not a PDF", 415)
    if not ActivityReportPdfV1Adapter().detect(content):
        raise AppError("unsupported_layout", "PDF layout is not supported", 415)
    return filename


def create_upload(
    database: Database,
    storage: ReportStorage,
    settings: Settings,
    actor_id: UUID,
    filename: str | None,
    mime_type: str | None,
    content: bytes,
) -> ReportUpload:
    display_filename = validate_pdf_upload(filename, mime_type, content, settings)
    digest = content_sha256(content)
    with database.user_transaction(actor_id) as session:
        if find_active_duplicate(session, actor_id, digest) is not None:
            raise AppError("duplicate_upload", "This report was already uploaded", 409)

    key = f"uploads/{actor_id}/{uuid4()}.pdf"
    try:
        storage.put(key, content)
    except Exception as exc:
        raise AppError("storage_unavailable", "Private report storage is unavailable", 503) from exc

    try:
        with database.user_transaction(actor_id) as session:
            upload = ReportUpload(
                uploaded_by_user_id=actor_id,
                storage_key=key,
                original_filename=display_filename,
                mime_type="application/pdf",
                byte_size=len(content),
                sha256=digest,
                status="queued",
            )
            session.add(upload)
            session.flush()
            session.add(IngestionJob(upload_id=upload.id, status="queued", attempts=0))
        return upload
    except Exception as exc:
        try:
            storage.delete(key)
        except Exception:
            # The object key is random and private; an operator can recover an orphan.
            pass
        if isinstance(exc, IntegrityError):
            raise AppError("duplicate_upload", "This report was already uploaded", 409) from exc
        raise
