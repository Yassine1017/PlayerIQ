"""Small, versioned provider adapter contract."""

from typing import Protocol

from app.ingestion.domain import ExtractionResult


class ReportAdapter(Protocol):
    parser_key: str
    version: str

    def detect(self, content: bytes) -> bool: ...

    def extract(self, content: bytes) -> ExtractionResult: ...
