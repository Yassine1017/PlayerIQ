"""Pure import eligibility decisions. Ownership is never inferred here."""

from dataclasses import dataclass

MAX_IMPORT_ROWS = 200


@dataclass(frozen=True)
class RowEligibility:
    identifiable: bool
    unique_label: bool
    participation_state: str


def exclusion_reason(row: RowEligibility) -> str | None:
    if not row.identifiable:
        return "source_label_unavailable"
    if not row.unique_label:
        return "duplicate_source_label"
    if row.participation_state == "zero_recorded":
        return "no_recorded_activity"
    if row.participation_state != "ready":
        return "row_requires_review"
    return None
