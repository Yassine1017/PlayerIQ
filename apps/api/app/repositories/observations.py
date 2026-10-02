"""Effective automatic observations while retaining original source evidence."""

from collections.abc import Iterable
from uuid import UUID

from app.models.tables import SourceMetricObservation

BACKFILL_LOCATOR = "backfill:chart_auto_v1"


def effective_observations(values: Iterable[SourceMetricObservation]) -> list[SourceMetricObservation]:
    observations = list(values)
    replacements: dict[tuple[UUID | None, str], UUID] = {}
    for value in observations:
        if BACKFILL_LOCATOR in value.source_locator:
            key = (value.athlete_row_id, value.source_label)
            if key in replacements:
                raise ValueError("Ambiguous automatic chart backfill evidence")
            replacements[key] = value.id
    return [
        value
        for value in observations
        if (value.athlete_row_id, value.source_label) not in replacements
        or value.id == replacements[(value.athlete_row_id, value.source_label)]
        or value.parser_version == "chart_review_v1"
    ]
