"""Closed read-only tool boundary over the existing analytics service."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.analytics.domain import ANALYTICS_RULE_VERSION, AnalyticsFact, display_decimal
from app.ingestion.registry import BY_KEY
from app.services.analytics import AnalyticsService


class ToolError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ClosedArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


SessionType = Literal["training", "match", "unknown"]


class LatestArgs(ClosedArgs):
    metric_key: str
    session_type: SessionType | None
    previous_count: int = Field(ge=1, le=5)


class TrendArgs(ClosedArgs):
    metric_key: str
    from_date: str
    to_date: str
    session_type: SessionType | None


class RecordArgs(ClosedArgs):
    metric_key: Literal["maximum_velocity_kmh", "total_distance_m"]
    session_type: SessionType | None


class HardestArgs(ClosedArgs):
    metric_key: str


class SpeedArgs(ClosedArgs):
    threshold_kmh: str


class ChangeArgs(ClosedArgs):
    kind: Literal["improvement", "workload_change"]


class OutlierArgs(ClosedArgs):
    session_type: Literal["training", "match"]
    limit: int = Field(ge=1, le=10)


class SessionArgs(ClosedArgs):
    session_id: UUID


TOOL_MODELS: dict[str, type[ClosedArgs]] = {
    "get_latest_session_comparison": LatestArgs,
    "get_metric_trend": TrendArgs,
    "get_personal_records": RecordArgs,
    "get_hardest_session": HardestArgs,
    "get_last_speed_exceedance": SpeedArgs,
    "get_largest_change": ChangeArgs,
    "get_workload_outliers": OutlierArgs,
    "get_session_facts": SessionArgs,
}

DESCRIPTIONS = {
    "get_latest_session_comparison": (
        "Compare the latest accepted session with up to five prior comparable sessions; arithmetic is backend-only."
    ),
    "get_metric_trend": (
        "Find accepted metric points and backend-calculated trend/change over a bounded player-local date range."
    ),
    "get_personal_records": "Find confirmed top speed or highest recorded total-distance workload, including ties.",
    "get_hardest_session": (
        "Find the confirmed training session highest by requested metric; default total distance is a workload proxy."
    ),
    "get_last_speed_exceedance": "Find the last confirmed maximum velocity strictly greater than the km/h threshold.",
    "get_largest_change": (
        "Find supported top-speed improvement or largest comparable workload change; these are distinct."
    ),
    "get_workload_outliers": "Get backend median/MAD workload observations for a confirmed session type.",
    "get_session_facts": "Get accepted metrics for one authorized linked player session, without team or report data.",
}


def tool_schemas() -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    for name, model in TOOL_MODELS.items():
        schema = model.model_json_schema()
        schema.pop("title", None)
        schema["additionalProperties"] = False
        schema["required"] = list(schema.get("properties", {}))
        for property_schema in schema["properties"].values():
            property_schema.pop("title", None)
        if "metric_key" in schema["properties"] and "enum" not in schema["properties"]["metric_key"]:
            schema["properties"]["metric_key"]["enum"] = sorted(
                key for key, definition in BY_KEY.items() if definition.trend_eligible
            )
        schemas.append(
            {"type": "function", "name": name, "description": DESCRIPTIONS[name], "parameters": schema, "strict": True}
        )
    return schemas


def validate_args(name: str, raw: str) -> ClosedArgs:
    model = TOOL_MODELS.get(name)
    if model is None:
        raise ToolError("unknown_tool")
    if len(raw) > 2000:
        raise ToolError("arguments_too_large")
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise ToolError("invalid_tool_arguments") from exc


def _metric(key: str) -> None:
    definition = BY_KEY.get(key)
    if definition is None or not definition.trend_eligible:
        raise ToolError("unsupported_metric")


def execute_tool(
    name: str, args: ClosedArgs, service: AnalyticsService, *, max_date_days: int, max_session_results: int
) -> tuple[AnalyticsFact, ...]:
    if name == "get_latest_session_comparison" and isinstance(args, LatestArgs):
        _metric(args.metric_key)
        return (service.latest_comparison_for_type(args.metric_key, args.previous_count, args.session_type),)
    if name == "get_metric_trend" and isinstance(args, TrendArgs):
        _metric(args.metric_key)
        try:
            start, end = date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
        except ValueError as exc:
            raise ToolError("invalid_date_range") from exc
        if start > end or (end - start).days > max_date_days:
            raise ToolError("invalid_date_range")
        return (service.trend(args.metric_key, start, end, args.session_type),)
    if name == "get_personal_records" and isinstance(args, RecordArgs):
        return (service.personal_record_for_type(args.metric_key, args.session_type),)
    if name == "get_hardest_session" and isinstance(args, HardestArgs):
        _metric(args.metric_key)
        return (service.hardest_session(args.metric_key),)
    if name == "get_last_speed_exceedance" and isinstance(args, SpeedArgs):
        try:
            threshold = Decimal(args.threshold_kmh)
        except InvalidOperation as exc:
            raise ToolError("invalid_speed_threshold") from exc
        if not threshold.is_finite() or not Decimal(0) <= threshold <= Decimal(100):
            raise ToolError("invalid_speed_threshold")
        return (service.last_speed_exceedance(threshold),)
    if name == "get_largest_change" and isinstance(args, ChangeArgs):
        return (service.largest_change(improvement=args.kind == "improvement"),)
    if name == "get_workload_outliers" and isinstance(args, OutlierArgs):
        if args.limit > max_session_results:
            raise ToolError("result_limit_exceeded")
        return service.workload_outliers(args.session_type, args.limit)
    if name == "get_session_facts" and isinstance(args, SessionArgs):
        facts = service.session_facts(args.session_id)
        if not facts:
            raise ToolError("session_not_found")
        return facts
    raise ToolError("invalid_tool_arguments")


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    kind: str
    metric_key: str | None
    role: str
    raw_value: str
    display_value: str
    unit: str
    rule_version: str = ANALYTICS_RULE_VERSION
    status: str
    sample_size: int
    source_session_ids: list[UUID]
    source_observation_ids: list[UUID]
    definition_id: str | None
    comparability_key: str | None


class FactRegistry:
    def __init__(self, limit: int, max_session_results: int = 10) -> None:
        self.limit = limit
        self.max_session_results = max_session_results
        self.facts: dict[str, Fact] = {}
        self.results: list[dict[str, Any]] = []

    def add_result(self, name: str, values: tuple[AnalyticsFact, ...]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for value in values:
            ids: list[str] = []
            if value.status == "ok":
                for role, number, unit in (
                    ("value", value.value, value.unit),
                    ("baseline", value.baseline_value, value.unit),
                    ("delta", value.delta, value.unit),
                    ("percent_change", value.percent_change, "%"),
                    ("slope_per_week", value.slope_per_week, f"{value.unit}/week" if value.unit else None),
                    ("median", value.median_value, value.unit),
                    ("mad", value.mad, value.unit),
                    ("modified_z_score", value.score, "score"),
                ):
                    if number is None or unit is None:
                        continue
                    if len(self.facts) >= self.limit:
                        break
                    fact_id = f"FACT_{len(self.facts) + 1:03d}"
                    display = (
                        format(number.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f")
                        if unit == "%"
                        else (display_decimal(number, unit) or str(number))
                    )
                    if role in {"delta", "percent_change", "slope_per_week"} and number > 0:
                        display = "+" + display
                    if unit == "%":
                        display += "%"
                    self.facts[fact_id] = Fact(
                        fact_id=fact_id,
                        kind=value.kind,
                        metric_key=value.metric_key,
                        role=role,
                        raw_value=str(number),
                        display_value=display,
                        unit=unit,
                        status=value.status,
                        sample_size=value.sample_size,
                        source_session_ids=list(value.session_ids[: self.max_session_results]),
                        source_observation_ids=list(value.source_observation_ids[: self.max_session_results]),
                        definition_id=value.definition_id,
                        comparability_key=value.comparability_key,
                    )
                    ids.append(fact_id)
            items.append(
                {
                    "kind": value.kind,
                    "status": value.status,
                    "metric_key": value.metric_key,
                    "fact_ids": ids,
                    "session_ids": [str(item) for item in value.session_ids[: self.max_session_results]],
                    "source_observation_ids": [
                        str(item) for item in value.source_observation_ids[: self.max_session_results]
                    ],
                    "source_ids_truncated": len(value.session_ids) > self.max_session_results
                    or len(value.source_observation_ids) > self.max_session_results,
                    "from_date": value.from_date.isoformat() if value.from_date else None,
                    "to_date": value.to_date.isoformat() if value.to_date else None,
                    "note": value.note,
                    "rule_version": value.rule_version,
                }
            )
        result = {"tool": name, "items": items[:20]}
        self.results.append(result)
        return result

    def snapshot(self) -> dict[str, Any]:
        return {"facts": [fact.model_dump(mode="json") for fact in self.facts.values()], "results": self.results}
