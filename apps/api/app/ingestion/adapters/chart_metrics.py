"""Page-two chart labels: PDF text first, then bounded local image OCR.

Only printed numeric labels are read. Bar heights never supply metric values.
The raster geometry below belongs to the reviewed Activity Report layout.
"""

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from PIL import Image

from app.ingestion.domain import QualityState, RawAthleteRow, RawMetricObservation, Scope, Severity, ValidationFinding

CHART_LABELS = (("Player Load", "player_load_reported", None), ("Maximum Velocity", "maximum_velocity_kmh", "km/h"))
NUMBER = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,3})?\Z")
OCR_LOAD = re.compile(r"(?:0|[1-9][0-9]{0,8})\Z")
OCR_SPEED = re.compile(r"(?:0|[1-9][0-9]{0,2})\.[0-9]{2}\Z")
MAX_CHART_ROWS = 24
MAX_IMAGE_PIXELS = 4_000_000


def _name_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Z0-9]+", value.upper().replace("-\n", ""))


def _matching_rows(label: str, rows: list[RawAthleteRow]) -> list[RawAthleteRow]:
    """Exact source label, or the report's FIRSTNAME I. chart abbreviation."""
    tokens = _name_tokens(label)
    compact = "".join(tokens)
    matches: list[RawAthleteRow] = []
    for row in rows:
        source = _name_tokens(row.source_name)
        if compact and compact == "".join(source):
            matches.append(row)
        elif (
            len(tokens) == 2
            and len(tokens[1]) == 1
            and len(source) >= 2
            and tokens[0] == source[0]
            and tokens[1] == source[1][:1]
        ):
            matches.append(row)
    return matches


def _observation(
    label: str,
    raw: str,
    method: str,
    bbox: tuple[float, float, float, float],
    row: RawAthleteRow,
    version: str,
    *,
    confidence: tuple[float, float] | None = None,
    reads_agree: bool = False,
    review: bool = False,
) -> RawMetricObservation:
    unit = next(unit for source, _, unit in CHART_LABELS if source == label)
    try:
        parsed = Decimal(raw) if NUMBER.fullmatch(raw) else None
    except InvalidOperation:
        parsed = None
    x0, top, x1, bottom = bbox
    locator = (
        f"p2 chart:{label.replace(' ', '_').lower()} method:{method} "
        f"bbox:{x0:.1f},{top:.1f},{x1:.1f},{bottom:.1f} "
        f"confidence:athlete={confidence[0]:.2f},numeric={confidence[1]:.2f} agree:{int(reads_agree)}"
        if confidence is not None
        else f"p2 chart:{label.replace(' ', '_').lower()} method:{method} "
        f"bbox:{x0:.1f},{top:.1f},{x1:.1f},{bottom:.1f} confidence:deterministic"
    )
    return RawMetricObservation(
        source_label=label,
        raw_value=raw,
        raw_unit=unit,
        parsed_value=parsed,
        source_locator=locator,
        scope=Scope.ATHLETE,
        row_ordinal=row.row_ordinal,
        parser_version=version,
        quality_state=QualityState.NEEDS_REVIEW if review or parsed is None else QualityState.ACCEPTED,
    )


def _finding(code: str, message: str, row: RawAthleteRow | None = None, label: str | None = None) -> ValidationFinding:
    key = next((key for source, key, _ in CHART_LABELS if source == label), None)
    return ValidationFinding(
        code=code,
        message=message,
        severity=Severity.WARNING,
        scope=Scope.ATHLETE if row else Scope.REPORT,
        row_ordinal=row.row_ordinal if row else None,
        metric_key=key,
    )


def _title_and_image(page: Any) -> tuple[float, dict[str, Any] | None] | None:
    headings = page.search(r"Player Load\s*&\s*Maximum Velocity", regex=True)
    if len(headings) != 1:
        return None
    title_bottom = float(headings[0]["bottom"])
    below = [image for image in page.images if title_bottom <= image["top"] <= title_bottom + 90]
    image = min(below, key=lambda value: value["top"]) if below else None
    return title_bottom, image


def _text_rows(
    page: Any, title_bottom: float, rows: list[RawAthleteRow], version: str
) -> tuple[dict[tuple[int, str], RawMetricObservation], list[ValidationFinding]]:
    """Associate a text-layer athlete column with adjacent labelled numeric columns."""
    words = [word for word in page.extract_words() if title_bottom < word["top"] < title_bottom + 300]
    lines: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for word in words:
        lines[round(float(word["top"]) / 3)].append(word)
    ordered = sorted(lines.values(), key=lambda line: min(word["top"] for word in line))
    header_index = next(
        (
            index
            for index, line in enumerate(ordered)
            if {"Athlete", "Player", "Load", "Maximum", "Velocity"} <= {word["text"] for word in line}
        ),
        None,
    )
    if header_index is None:
        return {}, []
    header = ordered[header_index]
    x_athlete = next(float(word["x0"]) for word in header if word["text"] == "Athlete")
    x_load = next(float(word["x0"]) for word in header if word["text"] == "Player")
    x_speed = next(float(word["x0"]) for word in header if word["text"] == "Maximum")
    if not x_athlete + 20 < x_load < x_speed - 20:
        return {}, []
    left_boundary = (x_athlete + x_load) / 2
    right_boundary = (x_load + x_speed) / 2
    captured: dict[tuple[int, str], RawMetricObservation] = {}
    findings: list[ValidationFinding] = []
    for line in ordered[header_index + 1 :]:
        if len(captured) >= MAX_CHART_ROWS * 2:
            break
        name_words = [word for word in line if word["x0"] < left_boundary]
        name = " ".join(word["text"] for word in sorted(name_words, key=lambda word: word["x0"]))
        if not name:
            continue
        matches = _matching_rows(name, rows)
        if len(matches) != 1:
            if matches:
                findings.append(
                    _finding("chart_athlete_ambiguous", "Chart athlete label matches multiple source rows.")
                )
            continue
        row = matches[0]
        for label, _, _ in CHART_LABELS:
            column = (
                [word for word in line if left_boundary <= word["x0"] < right_boundary]
                if label == "Player Load"
                else [word for word in line if word["x0"] >= right_boundary]
            )
            if len(column) != 1:
                continue
            word = column[0]
            key = (row.row_ordinal, label)
            if key in captured:
                findings.append(
                    _finding("chart_value_ambiguous", "Repeated chart value for one source row.", row, label)
                )
                captured[key].quality_state = QualityState.NEEDS_REVIEW
                continue
            raw = str(word["text"]).strip()
            captured[key] = _observation(
                label,
                raw,
                "pdf_position",
                (word["x0"], word["top"], word["x1"], word["bottom"]),
                row,
                version,
            )
            if captured[key].quality_state is QualityState.NEEDS_REVIEW:
                findings.append(_finding("chart_value_unreadable", "Printed chart value needs review.", row, label))
    return captured, findings


def _ocr_result(engine: Any, image: Image.Image) -> list[tuple[Any, str, float]]:
    result, _ = engine(image)
    return result or []


def _ocr_chart(
    image_info: dict[str, Any], rows: list[RawAthleteRow], version: str, requested: set[tuple[int, str]]
) -> tuple[dict[tuple[int, str], RawMetricObservation], list[ValidationFinding]]:
    width, height = image_info.get("srcsize") or (0, 0)
    if not (400 <= width <= 3000 and 160 <= height <= 1200 and width * height <= MAX_IMAGE_PIXELS):
        return {}, [_finding("chart_ocr_unavailable", "Chart image is outside the bounded OCR layout.")]
    if len(rows) > MAX_CHART_ROWS or len(rows) < 2:
        return {}, [_finding("chart_ocr_unavailable", "Chart athlete count is outside the bounded OCR layout.")]
    try:
        from rapidocr_onnxruntime import RapidOCR

        image = Image.frombytes("RGB", (width, height), image_info["stream"].get_data())
        engine = RapidOCR()
        detections = _ocr_result(engine, image)
    except Exception:
        return {}, [_finding("chart_ocr_unavailable", "Local chart OCR could not read this image.")]
    labels = sorted(
        (
            (box, text, confidence)
            for box, text, confidence in detections
            if min(point[1] for point in box) >= height * 0.77 and re.search(r"[A-Za-z]", text)
        ),
        key=lambda item: min(point[0] for point in item[0]),
    )
    if len(labels) != len(rows):
        return {}, [_finding("chart_athlete_ambiguous", "Chart athlete labels could not be uniquely counted.")]
    rights = [max(point[0] for point in box) for box, _, _ in labels]
    gaps = [next_right - right for right, next_right in zip(rights[:-1], rights[1:], strict=True)]
    pitch = median(gaps)
    if pitch <= 0 or any(not pitch * 0.75 <= gap <= pitch * 1.25 for gap in gaps):
        return {}, [_finding("chart_athlete_ambiguous", "Chart athlete positions are not regular.")]
    matched: dict[int, tuple[RawAthleteRow, float, float]] = {}
    used_rows: set[int] = set()
    findings: list[ValidationFinding] = []
    for (_box, name, confidence), right in zip(labels, rights, strict=True):
        candidates = _matching_rows(name, rows)
        if len(candidates) != 1 or candidates[0].row_ordinal in used_rows or confidence < 0.90:
            findings.append(_finding("chart_athlete_ambiguous", "Chart athlete label requires manual matching."))
            continue
        row = candidates[0]
        used_rows.add(row.row_ordinal)
        matched[row.row_ordinal] = row, right, confidence
    captured: dict[tuple[int, str], RawMetricObservation] = {}
    top = round(height * 0.14)
    bottom = round(height * 0.79)
    for ordinal, (row, right, name_confidence) in matched.items():
        for label, key, _ in CHART_LABELS:
            if (ordinal, label) not in requested:
                continue
            offset = -0.23 if key == "player_load_reported" else 0.07
            x = round(right + pitch * offset)
            if x - 18 < 0 or x + 18 > width:
                continue
            crop = image.crop((x - 18, top, x + 18, bottom)).rotate(270, expand=True)
            try:
                first = _ocr_result(engine, crop.resize((crop.width * 3, crop.height * 3)))
                if len(first) != 1:
                    continue
                raw = first[0][1].strip()
                first_conf = float(first[0][2])
                grammar = OCR_LOAD if key == "player_load_reported" else OCR_SPEED
                # The exact, unique same-report name match already gates the athlete.
                # Numeric acceptance depends on two independent scale reads agreeing.
                trusted = bool(grammar.fullmatch(raw)) and first_conf >= 0.98
                reads_agree = False
                if trusted:
                    second = _ocr_result(engine, crop.resize((crop.width * 2, crop.height * 2)))
                    reads_agree = len(second) == 1 and second[0][1].strip() == raw and float(second[0][2]) >= 0.95
                    trusted = reads_agree
                x0 = float(image_info["x0"]) + (x - 18) * (image_info["x1"] - image_info["x0"]) / width
                x1 = float(image_info["x0"]) + (x + 18) * (image_info["x1"] - image_info["x0"]) / width
                y0 = float(image_info["top"]) + top * (image_info["bottom"] - image_info["top"]) / height
                y1 = float(image_info["top"]) + bottom * (image_info["bottom"] - image_info["top"]) / height
                captured[(ordinal, label)] = _observation(
                    label,
                    raw,
                    "ocr",
                    (x0, y0, x1, y1),
                    row,
                    version,
                    confidence=(name_confidence, first_conf),
                    reads_agree=reads_agree,
                    review=not trusted,
                )
                if not trusted:
                    findings.append(_finding("chart_ocr_review", "OCR chart label needs manual review.", row, label))
            except Exception:
                findings.append(_finding("chart_ocr_unavailable", "Local chart OCR failed for a label.", row, label))
    return captured, findings


def extract_chart_metrics(page: Any, rows: list[RawAthleteRow], version: str) -> list[ValidationFinding]:
    """Replace each row's two missing placeholders when printed evidence is safe."""
    located = _title_and_image(page)
    if located is None:
        return [_finding("chart_only_unavailable", "Chart heading is unavailable from PDF text.")]
    title_bottom, image_info = located
    captured, findings = _text_rows(page, title_bottom, rows, version)
    requested = {(row.row_ordinal, label) for row in rows for label, _, _ in CHART_LABELS} - set(captured)
    if requested and image_info is not None:
        ocr, ocr_findings = _ocr_chart(image_info, rows, version, requested)
        captured.update({key: value for key, value in ocr.items() if key in requested})
        findings.extend(ocr_findings)
    for row in rows:
        for index, observation in enumerate(row.observations):
            replacement = captured.get((row.row_ordinal, observation.source_label))
            if replacement is not None:
                row.observations[index] = replacement
    if not captured:
        findings.append(_finding("chart_only_unavailable", "Exact chart labels require manual review."))
    return findings
