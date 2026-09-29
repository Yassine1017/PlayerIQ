"""Authenticated analytics HTTP boundary; all calculations live below this layer."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics.domain import ANALYTICS_RULE_VERSION, AnalyticsFact, display_decimal
from app.api.errors import AppError
from app.core.auth import CurrentUser, get_current_user
from app.db.session import Database, get_database
from app.ingestion.registry import BY_KEY
from app.repositories.analytics import HistoryLimitExceeded
from app.schemas.analytics import (
    AnalyticsFactOut,
    AnalyticsOutliersOut,
    AnalyticsOverviewOut,
    SupportingMetricOut,
    TrendPointOut,
)
from app.services.analytics import AnalyticsService
from app.services.authorization import require_player

router = APIRouter(prefix="/v1/players/{player_id}/analytics", tags=["analytics"])
User = Annotated[CurrentUser, Depends(get_current_user)]
DB = Annotated[Database, Depends(get_database)]


def _fact_out(value: AnalyticsFact) -> AnalyticsFactOut:
    def decimal(raw: Decimal | None) -> str | None:
        return str(raw) if raw is not None else None

    return AnalyticsFactOut(
        kind=value.kind,
        status=value.status,
        rule_version=value.rule_version,
        metric_key=value.metric_key,
        value=decimal(value.value),
        display_value=display_decimal(value.value, value.unit),
        unit=value.unit,
        baseline_value=decimal(value.baseline_value),
        delta=decimal(value.delta),
        percent_change=decimal(value.percent_change),
        slope_per_week=decimal(value.slope_per_week),
        median_value=decimal(value.median_value),
        mad=decimal(value.mad),
        score=decimal(value.score),
        sample_size=value.sample_size,
        session_ids=list(value.session_ids),
        source_observation_ids=list(value.source_observation_ids),
        points=[
            TrendPointOut(
                session_id=point.session_id,
                local_date=point.local_date,
                value=str(point.value),
                source_observation_id=point.source_observation_id,
            )
            for point in value.points
        ],
        supporting_metrics=[
            SupportingMetricOut(
                metric_key=metric.metric_key,
                value=str(metric.value),
                display_value=display_decimal(metric.value, metric.unit) or str(metric.value),
                unit=metric.unit,
                source_observation_id=metric.source_observation_id,
                definition_id=metric.definition_id,
                comparability_key=metric.comparability_key,
            )
            for metric in value.supporting_metrics
        ],
        from_date=value.from_date,
        to_date=value.to_date,
        definition_id=value.definition_id,
        comparability_key=value.comparability_key,
        note=value.note,
    )


def _service(actor_id: UUID, player_id: UUID, session: Session) -> AnalyticsService:
    require_player(session, actor_id, player_id)
    try:
        return AnalyticsService(session, player_id)
    except HistoryLimitExceeded as exc:
        raise AppError("history_limit_exceeded", str(exc), 422) from exc


@router.get("/overview", response_model=AnalyticsOverviewOut)
def overview(player_id: UUID, user: User, database: DB) -> AnalyticsOverviewOut:
    with database.user_transaction(user.id) as session:
        result = _service(user.id, player_id, session).overview()
        return AnalyticsOverviewOut(
            player_id=result.player_id,
            history_fingerprint=result.history_fingerprint,
            rule_version=result.rule_version,
            facts=[_fact_out(fact) for fact in result.facts],
        )


@router.get("/trend", response_model=AnalyticsFactOut)
def trend(
    player_id: UUID,
    user: User,
    database: DB,
    metric: Annotated[str, Query(min_length=1, max_length=100)],
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
    session_type: Annotated[Literal["training", "match", "unknown"] | None, Query(alias="type")] = None,
) -> AnalyticsFactOut:
    definition = BY_KEY.get(metric)
    if definition is None or not definition.trend_eligible:
        raise AppError("unsupported_metric", "Metric is not available for trends", 422)
    if from_date > to_date or (to_date - from_date).days > 3660:
        raise AppError("invalid_date_range", "Date range must be ordered and at most ten years", 400)
    with database.user_transaction(user.id) as session:
        result = _service(user.id, player_id, session).trend(metric, from_date, to_date, session_type)
        return _fact_out(result)


@router.get("/outliers", response_model=AnalyticsOutliersOut)
def outliers(
    player_id: UUID,
    user: User,
    database: DB,
    session_type: Annotated[Literal["training", "match"], Query(alias="type")] = "training",
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> AnalyticsOutliersOut:
    with database.user_transaction(user.id) as session:
        service = _service(user.id, player_id, session)
        return AnalyticsOutliersOut(
            history_fingerprint=service.fingerprint(),
            rule_version=ANALYTICS_RULE_VERSION,
            items=[_fact_out(fact) for fact in service.workload_outliers(session_type, limit)],
        )
