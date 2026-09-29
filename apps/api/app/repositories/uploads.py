"""Content-hash duplicate detection scoped to the uploading user."""

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import ReportUpload


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def find_active_duplicate(session: Session, user_id: UUID, digest: str) -> ReportUpload | None:
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("digest must be a lowercase SHA-256 hex string")
    return session.scalar(
        select(ReportUpload).where(
            ReportUpload.uploaded_by_user_id == user_id,
            ReportUpload.sha256 == digest,
            ReportUpload.status != "deleted",
        )
    )
