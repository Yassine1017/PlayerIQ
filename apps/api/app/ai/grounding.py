"""Server validation of model prose and evidence references."""

import json
import re
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.tools import FactRegistry

NUMERIC_TEXT = re.compile(r"\d|[%±+]|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|hundred)\b", re.I)
UNIT_TEXT = re.compile(r"\b(?:km/h|m/s|metres?|meters?|kilometres?|kilometers?|percent|source units)\b", re.I)
MEDICAL_TEXT = re.compile(
    r"\b(?:injur\w*|diagnos\w*|illness|overtraining syndrome|medical|risk score|"
    r"rest tomorrow|should rest|must rest|ready to play|readiness prescription)\b",
    re.I,
)
IMPROVEMENT_TEXT = re.compile(r"\b(?:improv\w*|better|performance gain|progress)\b", re.I)
CHANGE_TEXT = re.compile(r"\b(?:increas\w*|decreas\w*|ris\w*|fell|fall\w*|higher|lower|more|less)\b", re.I)
WORKLOAD_METRICS = {
    "total_distance_m",
    "reported_high_speed_distance_m",
    "reported_accel_decel_efforts_combined",
    "player_load_reported",
}


class GroundingError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class Sentence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: str = Field(min_length=1, max_length=250)
    fact_ids: list[str] = Field(max_length=12)
    session_ids: list[UUID] = Field(max_length=12)


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["answered", "insufficient_data"]
    sentences: list[Sentence] = Field(min_length=1, max_length=4)


def validate_answer(payload: dict[str, Any], registry: FactRegistry) -> GroundedAnswer:
    try:
        answer = GroundedAnswer.model_validate_json(json.dumps(payload))
    except ValidationError as exc:
        raise GroundingError("invalid_answer_schema") from exc
    has_fact = False
    for sentence in answer.sentences:
        if NUMERIC_TEXT.search(sentence.text):
            raise GroundingError("model_authored_number")
        if UNIT_TEXT.search(sentence.text):
            raise GroundingError("model_authored_unit")
        if MEDICAL_TEXT.search(sentence.text):
            raise GroundingError("medical_claim")
        cited = []
        for fact_id in sentence.fact_ids:
            fact = registry.facts.get(fact_id)
            if fact is None:
                raise GroundingError("unknown_fact_id")
            cited.append(fact)
            has_fact = True
        allowed_sessions = {item for fact in cited for item in fact.source_session_ids}
        if any(session_id not in allowed_sessions for session_id in sentence.session_ids):
            raise GroundingError("invalid_session_citation")
        if IMPROVEMENT_TEXT.search(sentence.text) and cited:
            metrics = {fact.metric_key for fact in cited}
            if metrics & WORKLOAD_METRICS:
                raise GroundingError("workload_called_improvement")
            if not any(
                fact.metric_key == "maximum_velocity_kmh"
                and fact.role in {"delta", "percent_change", "slope_per_week"}
                and Decimal(fact.raw_value) > 0
                for fact in cited
            ):
                raise GroundingError("unsupported_improvement_claim")
        if CHANGE_TEXT.search(sentence.text):
            compared_metrics = {
                fact.metric_key for fact in cited if fact.role in {"delta", "percent_change", "slope_per_week"}
            }
            if not compared_metrics or any(fact.metric_key not in compared_metrics for fact in cited):
                raise GroundingError("unsupported_change_claim")
        if answer.status == "answered" and not sentence.fact_ids:
            raise GroundingError("missing_fact_citation")
    if answer.status == "answered" and not has_fact:
        raise GroundingError("missing_fact_citation")
    if answer.status == "insufficient_data" and has_fact:
        # A partial current value can be shown, but it must not be treated as a complete answer.
        pass
    return answer


def unavailable_answer() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "sentences": [
            {"text": "PlayerIQ could not verify an AI explanation right now.", "fact_ids": [], "session_ids": []}
        ],
    }
