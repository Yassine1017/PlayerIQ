"""Synthetic printed chart labels and bounded local-OCR decisions."""

from decimal import Decimal
from io import BytesIO

import pdfplumber
from app.ingestion.adapters.chart_metrics import _matching_rows, _ocr_chart, _text_rows
from app.ingestion.domain import QualityState, RawAthleteRow
from app.ingestion.service import IngestionService
from PIL import Image


def test_text_layer_chart_values_are_positionally_associated(synthetic_text_chart_pdf: bytes) -> None:
    inspection = IngestionService().inspect_pdf(synthetic_text_chart_pdf)
    report = inspection.extraction.report
    assert report is not None and inspection.validation is not None
    assert len(report.athlete_rows) == 4
    first, zero, suspicious, incomplete = report.athlete_rows
    assert first.observations[-2].raw_value == "420"
    assert first.observations[-1].parsed_value == Decimal("29.75")
    assert "p2" in first.observations[-1].source_locator
    assert "method:pdf_position" in first.observations[-1].source_locator
    assert "confidence:deterministic" in first.observations[-1].source_locator
    assert zero.observations[-2].raw_value == "0"
    assert zero.observations[-1].parsed_value == Decimal("0.00")
    assert inspection.validation.rows[1].quality_state is QualityState.ZERO_RECORDED
    assert suspicious.observations[-1].raw_value == "52.50"
    assert inspection.validation.rows[2].metrics["maximum_velocity_kmh"].quality_state is QualityState.NEEDS_REVIEW
    assert inspection.validation.rows[2].quality_state is QualityState.READY
    assert incomplete.observations[-2].raw_value is None
    assert incomplete.observations[-1].raw_value == "unreadable"
    assert incomplete.observations[-1].parsed_value is None
    assert "metric_unreadable" in {finding.code for finding in inspection.validation.rows[3].findings}
    assert all(observation.raw_value != "999" for row in report.athlete_rows for observation in row.observations)
    assert len(_matching_rows("CHARLIE THREE", report.athlete_rows)) == 1


def test_text_layer_does_not_invoke_ocr(monkeypatch, synthetic_text_chart_pdf: bytes) -> None:  # type: ignore[no-untyped-def]
    import rapidocr_onnxruntime

    def fail() -> None:
        raise AssertionError("OCR must not run for complete positional chart labels")

    monkeypatch.setattr(rapidocr_onnxruntime, "RapidOCR", fail)
    report = IngestionService().inspect_pdf(synthetic_text_chart_pdf).extraction.report
    assert report is not None
    assert report.athlete_rows[0].observations[-1].raw_value == "29.75"


def test_duplicate_chart_name_is_ambiguous(synthetic_text_chart_pdf: bytes) -> None:
    report = IngestionService().inspect_pdf(synthetic_text_chart_pdf).extraction.report
    assert report is not None
    duplicate = RawAthleteRow(row_ordinal=5, source_name="ALPHA ONE", observations=[])
    assert len(_matching_rows("ALPHA ONE", report.athlete_rows + [duplicate])) == 2
    with pdfplumber.open(BytesIO(synthetic_text_chart_pdf)) as pdf:
        title = pdf.pages[1].search("Player Load & Maximum Velocity")[0]
        captured, findings = _text_rows(pdf.pages[1], title["bottom"], report.athlete_rows + [duplicate], "1.1.0")
    assert (1, "Player Load") not in captured
    assert "chart_athlete_ambiguous" in {finding.code for finding in findings}


def test_ocr_requires_unique_name_and_two_agreeing_numeric_reads(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import rapidocr_onnxruntime

    class Stream:
        def get_data(self) -> bytes:
            return Image.new("RGB", (800, 240), "white").tobytes()

    box = [[0, 0], [20, 0], [20, 20], [0, 20]]
    labels = [
        ([[20, 190], [100, 190], [100, 225], [20, 225]], "ALPHA O.", 0.99),
        ([[220, 190], [300, 190], [300, 225], [220, 225]], "BRAVO T.", 0.99),
    ]
    reads = iter(
        [
            ("420", 0.99),
            ("420", 0.98),
            ("95.80", 0.99),
            ("95.80", 0.98),
            ("0", 0.99),
            ("0", 0.99),
            ("0.00", 0.70),
        ]
    )

    class FakeEngine:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, _image):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return labels, [0]
            raw, confidence = next(reads)
            return [(box, raw, confidence)], [0]

    engine = FakeEngine()
    monkeypatch.setattr(rapidocr_onnxruntime, "RapidOCR", lambda: engine)
    rows = [
        RawAthleteRow(row_ordinal=1, source_name="ALPHA ONE", observations=[]),
        RawAthleteRow(row_ordinal=2, source_name="BRAVO TWO", observations=[]),
    ]
    requested = {(row.row_ordinal, label) for row in rows for label in ("Player Load", "Maximum Velocity")}
    image_info = {"srcsize": (800, 240), "stream": Stream(), "x0": 40, "x1": 440, "top": 80, "bottom": 200}
    captured, findings = _ocr_chart(image_info, rows, "1.1.0", requested)
    assert engine.calls == 8
    assert captured[(1, "Player Load")].parsed_value == Decimal("420")
    assert captured[(1, "Maximum Velocity")].raw_value == "95.80"
    assert captured[(1, "Maximum Velocity")].quality_state is QualityState.ACCEPTED
    assert captured[(2, "Player Load")].parsed_value == Decimal(0)
    assert captured[(2, "Maximum Velocity")].quality_state is QualityState.NEEDS_REVIEW
    assert "method:ocr" in captured[(1, "Player Load")].source_locator
    assert "confidence:" in captured[(1, "Player Load")].source_locator
    assert "agree:1" in captured[(1, "Player Load")].source_locator
    assert "agree:0" in captured[(2, "Maximum Velocity")].source_locator
    assert "chart_ocr_review" in {finding.code for finding in findings}


def test_local_ocr_reads_printed_synthetic_raster_label(synthetic_raster_chart_pdf: bytes) -> None:
    report = IngestionService().inspect_pdf(synthetic_raster_chart_pdf).extraction.report
    assert report is not None
    first = report.athlete_rows[0]
    assert first.observations[-2].raw_value == "420"
    assert first.observations[-2].quality_state is QualityState.ACCEPTED
    assert first.observations[-1].parsed_value == Decimal("29.75")
    assert "method:ocr" in first.observations[-1].source_locator


def test_ocr_failure_preserves_missing_chart_values(monkeypatch, synthetic_raster_chart_pdf: bytes) -> None:  # type: ignore[no-untyped-def]
    import rapidocr_onnxruntime

    def fail() -> None:
        raise RuntimeError("synthetic local OCR failure")

    monkeypatch.setattr(rapidocr_onnxruntime, "RapidOCR", fail)
    inspection = IngestionService().inspect_pdf(synthetic_raster_chart_pdf)
    report = inspection.extraction.report
    assert report is not None
    assert len(report.athlete_rows) == 2
    assert report.athlete_rows[0].observations[0].parsed_value == Decimal(3000)
    assert report.athlete_rows[0].observations[-1].raw_value is None
    assert "chart_ocr_unavailable" in {finding.code for finding in inspection.extraction.findings}
