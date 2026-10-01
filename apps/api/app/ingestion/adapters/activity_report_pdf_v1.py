"""Deterministic table parser with bounded chart-label extraction."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

import pdfplumber

from app.ingestion.adapters.chart_metrics import extract_chart_metrics
from app.ingestion.domain import (
    ExtractionResult,
    QualityState,
    RawAthleteRow,
    RawMetricObservation,
    RawReport,
    Scope,
    Severity,
    ValidationFinding,
)

TABLE_FIELDS: tuple[tuple[str, str], ...] = (
    ("Distance (m)", "m"),
    ("Meterage Per Minute", "m/min"),
    ("Overall (%)", "%"),
    ("High Speed Distance (m)", "m"),
    ("Accel&Decel Efforts", "count"),
    ("Accel&Decel Efforts Per Minute", "count/min"),
    ("Velocity Band 2 Distance (m)", "m"),
    ("Velocity Band 4 Distance (m)", "m"),
    ("Sprint Efforts", "count"),
)

ROW_VALUES = re.compile(
    r"\b(?P<position>[A-Z]{2,4})\s+"
    r"(?P<values>[-+]?\d+(?:\.\d+)?(?:\s+[-+]?\d+(?:\.\d+)?){8})\b"
)
HEADER_DATE = re.compile(
    r"\b(?:MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY), "
    r"[A-Z]+ \d{1,2}, \d{4} - \d{1,2}:\d{2}:\d{2} [AP]M\b"
)
AVERAGE_VALUES = re.compile(r"\bAverages\s+(?P<values>\d+(?:\.\d+)?(?:\s+\d+(?:\.\d+)?){8})\b")


class ActivityReportPdfV1Adapter:
    parser_key = "activity_report_pdf_v1"
    version = "1.1.0"

    def detect(self, content: bytes) -> bool:
        if not content.startswith(b"%PDF"):
            return False
        try:
            with pdfplumber.open(BytesIO(content)) as pdf:
                if len(pdf.pages) != 5:
                    return False
                first = pdf.pages[0].extract_text() or ""
                athlete = pdf.pages[3].extract_text() or ""
                averages = pdf.pages[4].extract_text() or ""
                return (
                    "ACTIVITY REPORT" in first
                    and "TOTAL TIME" in first
                    and "Athlete Breakdown" in athlete
                    and "Distance (m)" in athlete
                    and "Overall (%)" in athlete
                    and "Averages" in averages
                )
        except Exception:
            # A malformed or encrypted PDF is unsupported, not a stack trace to the caller.
            return False

    def extract(self, content: bytes) -> ExtractionResult:
        if not self.detect(content):
            return ExtractionResult(
                report=None,
                supported=False,
                findings=[
                    ValidationFinding(
                        code="unsupported_layout",
                        message="Not a supported five-page Activity Report PDF layout.",
                        severity=Severity.ERROR,
                        scope=Scope.REPORT,
                    )
                ],
            )

        with pdfplumber.open(BytesIO(content)) as pdf:
            first = pdf.pages[0].extract_text() or ""
            fourth = pdf.pages[3]
            fifth = pdf.pages[4].extract_text() or ""
            findings: list[ValidationFinding] = []
            rows = self._extract_rows(fourth, findings)
            if not rows or not any(row.observations for row in rows):
                return ExtractionResult(report=None, findings=findings, supported=False)
            try:
                findings.extend(extract_chart_metrics(pdf.pages[1], rows, self.version))
            except Exception:
                # Chart extraction must not discard validated table observations.
                findings.append(
                    ValidationFinding(
                        code="chart_only_unavailable",
                        message="Chart labels could not be safely extracted; manual review remains available.",
                        severity=Severity.WARNING,
                        scope=Scope.REPORT,
                    )
                )
            averages = self._extract_averages(fifth, findings)
            report = RawReport(
                parser_key=self.parser_key,
                parser_version=self.version,
                report_kind="activity_report",
                source_activity_id=self._activity_id(first),
                source_title=self._source_title(first),
                source_team_name=self._header_field(first, "TEAM", "VENUE"),
                source_venue_name=self._header_field(first, "VENUE", None),
                reported_local_datetime=self._header_datetime(first),
                timezone=None,
                activity_total_time_s=self._total_time(first),
                reported_athlete_count=None,
                athlete_rows=rows,
                report_observations=averages,
            )
            findings.extend(
                [
                    ValidationFinding(
                        code="period_image_unavailable",
                        message="Period values are embedded in an image and were not transcribed.",
                        severity=Severity.WARNING,
                        scope=Scope.PERIOD,
                    ),
                    ValidationFinding(
                        code="summary_image_unavailable",
                        message=(
                            "MD comparison and summary chart values are embedded in images and were not transcribed."
                        ),
                        severity=Severity.WARNING,
                        scope=Scope.REPORT,
                    ),
                ]
            )
            return ExtractionResult(report=report, findings=findings, supported=True)

    def _extract_rows(self, page, findings: list[ValidationFinding]) -> list[RawAthleteRow]:  # type: ignore[no-untyped-def]
        tables = page.find_tables()
        if not tables:
            findings.append(
                ValidationFinding(
                    code="athlete_table_missing",
                    message="No athlete table was found on page 4.",
                    severity=Severity.ERROR,
                    scope=Scope.REPORT,
                )
            )
            return []
        cells = [row[0] for row in tables[0].extract() if row and row[0]]
        rows: list[RawAthleteRow] = []
        for ordinal, cell in enumerate(cells, start=1):
            match = ROW_VALUES.search(cell)
            if match is None:
                rows.append(
                    RawAthleteRow(
                        row_ordinal=ordinal,
                        source_name=" ".join(cell.split()),
                        observations=[],
                        quality_state=QualityState.NEEDS_REVIEW,
                    )
                )
                findings.append(
                    ValidationFinding(
                        code="athlete_row_unparsed",
                        message="Athlete row did not match nine table values.",
                        severity=Severity.ERROR,
                        scope=Scope.ATHLETE,
                        row_ordinal=ordinal,
                        source_locator=f"p4 row {ordinal}",
                    )
                )
                continue
            tokens = match.group("values").split()
            raw_name = f"{cell[: match.start()]} {cell[match.end() :]}"
            source_name = " ".join(raw_name.replace("-\n", "").split())
            observations = [
                RawMetricObservation(
                    source_label=label,
                    raw_value=token,
                    raw_unit=unit,
                    parsed_value=self._decimal(token),
                    source_locator=f"p4 row {ordinal} col {label}",
                    scope=Scope.ATHLETE,
                    row_ordinal=ordinal,
                    parser_version=self.version,
                )
                for (label, unit), token in zip(TABLE_FIELDS, tokens, strict=True)
            ]
            observations.extend(
                RawMetricObservation(
                    source_label=label,
                    raw_value=None,
                    raw_unit=unit,
                    parsed_value=None,
                    source_locator=f"p2 chart row {ordinal} {label}",
                    scope=Scope.ATHLETE,
                    row_ordinal=ordinal,
                    parser_version=self.version,
                    quality_state=QualityState.MISSING,
                )
                for label, unit in (("Player Load", None), ("Maximum Velocity", "km/h"))
            )
            rows.append(
                RawAthleteRow(
                    row_ordinal=ordinal,
                    source_name=source_name,
                    source_position_code=match.group("position"),
                    observations=observations,
                )
            )
        return rows

    def _extract_averages(self, text: str, findings: list[ValidationFinding]) -> list[RawMetricObservation]:
        match = AVERAGE_VALUES.search(text)
        if match is None:
            findings.append(
                ValidationFinding(
                    code="averages_unavailable",
                    message="The report averages row was not extractable.",
                    severity=Severity.WARNING,
                    scope=Scope.REPORT,
                )
            )
            return []
        return [
            RawMetricObservation(
                source_label=label,
                raw_value=token,
                raw_unit=unit,
                parsed_value=self._decimal(token),
                source_locator=f"p5 Averages col {label}",
                scope=Scope.REPORT,
                parser_version=self.version,
            )
            for (label, unit), token in zip(TABLE_FIELDS, match.group("values").split(), strict=True)
        ]

    @staticmethod
    def _decimal(raw: str) -> Decimal | None:
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None

    @staticmethod
    def _activity_id(text: str) -> str | None:
        match = re.search(r"\bActivity (\d{14})\b", text)
        return match.group(1) if match else None

    @staticmethod
    def _source_title(text: str) -> str:
        match = re.search(r"\bActivity \d{14}\b", text)
        return match.group(0) if match else "Activity Report"

    @staticmethod
    def _header_datetime(text: str) -> datetime | None:
        match = HEADER_DATE.search(text)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(0).title(), "%A, %B %d, %Y - %I:%M:%S %p")
        except ValueError:
            return None

    @staticmethod
    def _total_time(text: str) -> int | None:
        match = re.search(r"\bTOTAL TIME\s+(\d+):(\d{2}):(\d{2})\b", text)
        if not match:
            return None
        hours, minutes, seconds = map(int, match.groups())
        return hours * 3600 + minutes * 60 + seconds if minutes < 60 and seconds < 60 else None

    @staticmethod
    def _header_field(text: str, start: str, end: str | None) -> str | None:
        pattern = rf"\b{start}\s+(.+?)(?=\s+{end}\b|$)" if end else rf"\b{start}\s+(.+)$"
        for line in text.splitlines():
            if start in line:
                match = re.search(pattern, line)
                if match:
                    return match.group(1).strip()
        return None
