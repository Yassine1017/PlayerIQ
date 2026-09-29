"""Local, side-effect-free inspection entry point for supported GPS PDFs."""

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.ingestion.adapters.activity_report_pdf_v1 import ActivityReportPdfV1Adapter
from app.ingestion.domain import ExtractionResult, ValidationResult
from app.ingestion.validation import ReportValidator

MAX_PDF_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class Inspection:
    extraction: ExtractionResult
    validation: ValidationResult | None


class IngestionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.adapter = ActivityReportPdfV1Adapter()
        self.validator = ReportValidator(
            max_velocity_review_kmh=self.settings.max_velocity_review_kmh,
            distance_peer_review_multiplier=self.settings.distance_peer_review_multiplier,
        )

    def inspect_pdf(self, content: bytes) -> Inspection:
        if len(content) > MAX_PDF_BYTES:
            raise ValueError("PDF exceeds the 25 MiB inspection limit")
        extraction = self.adapter.extract(content)
        validation = self.validator.validate(extraction.report) if extraction.report else None
        return Inspection(extraction=extraction, validation=validation)
