"""Private report-object boundary. Only the backend holds Storage credentials."""

from typing import Protocol

from fastapi import Request
from supabase import create_client

from app.api.errors import AppError
from app.core.config import Settings


class ReportStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class SupabaseReportStorage:
    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_url or not settings.supabase_storage_secret_key:
            raise ValueError("Supabase Storage configuration is required")
        self.bucket = create_client(
            settings.supabase_url,
            settings.supabase_storage_secret_key,
        ).storage.from_(settings.supabase_storage_bucket)

    def put(self, key: str, content: bytes) -> None:
        self.bucket.upload(
            path=key,
            file=content,
            file_options={"content-type": "application/pdf", "upsert": "false"},
        )

    def get(self, key: str) -> bytes:
        return self.bucket.download(key)

    def delete(self, key: str) -> None:
        self.bucket.remove([key])


def get_storage(request: Request) -> ReportStorage:
    storage: ReportStorage | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise AppError("storage_not_configured", "Private storage is not configured", 503)
    return storage
