"""Uploader-only, auditable manual capture of exact PDF chart labels."""

import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.core.config import Settings
from app.ingestion.registry import BY_KEY, REGISTRY_VERSION
from app.models.tables import (
    ChartMetricReview,
    PlayerSession,
    SessionMetricValue,
    SourceAthleteRow,
    SourceMetricObservation,
)
from app.schemas.v1 import (
    ChartReviewConfirmation,
    ChartReviewOut,
    ChartReviewProposal,
    ChartReviewsOut,
)
from app.services.authorization import require_upload
from app.services.transaction_locks import lock_resource

CHART_REVIEW_VERSION = "chart_review_v1"
CHART_LABEL = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,3})?\Z")
logger = logging.getLogger(__name__)


def _out(value: ChartMetricReview) -> ChartReviewOut:
    return ChartReviewOut(
        id=value.id,
        source_athlete_row_id=value.athlete_row_id,
        metric_key=value.metric_key,
        raw_label=value.raw_label,
        parsed_value=str(value.parsed_value),
        unit=BY_KEY[value.metric_key].canonical_unit,
        source_locator=value.source_locator,
        capture_method=value.capture_method,
        status=value.status,
        proposed_by_user_id=value.proposed_by_user_id,
        reviewed_by_user_id=value.reviewed_by_user_id,
        reviewed_at=value.reviewed_at,
        review_reason=value.review_reason,
        source_observation_id=value.source_observation_id,
        created_at=value.created_at,
    )


def list_chart_reviews(session: Session, actor_id: UUID, upload_id: UUID) -> ChartReviewsOut:
    require_upload(session, actor_id, upload_id)
    values = session.scalars(
        select(ChartMetricReview)
        .join(SourceAthleteRow, SourceAthleteRow.id == ChartMetricReview.athlete_row_id)
        .where(SourceAthleteRow.report_upload_id == upload_id)
        .order_by(ChartMetricReview.created_at, ChartMetricReview.id)
        .limit(1001)
    ).all()
    if len(values) > 1000:
        raise AppError("chart_review_limit_exceeded", "Report has too many chart reviews to list", 422)
    return ChartReviewsOut(items=[_out(value) for value in values])


def propose_chart_value(session: Session, actor_id: UUID, upload_id: UUID, body: ChartReviewProposal) -> ChartReviewOut:
    upload = require_upload(session, actor_id, upload_id)
    if upload.status != "awaiting_link":
        raise AppError("upload_not_ready", "Report is not ready for chart review", 409)
    lock_resource(session, "source-row", str(body.source_athlete_row_id))
    row = session.scalar(
        select(SourceAthleteRow).where(
            SourceAthleteRow.id == body.source_athlete_row_id,
            SourceAthleteRow.report_upload_id == upload_id,
        )
    )
    if row is None:
        raise AppError("row_not_found", "Athlete row not found in this report", 404)
    if row.participation_state != "ready":
        raise AppError("row_requires_review", "Athlete row is not eligible for a player session", 422)
    raw = body.raw_label.strip()
    if CHART_LABEL.fullmatch(raw) is None:
        raise AppError("invalid_chart_label", "Enter the exact printed nonnegative numeric label", 422)
    pending = session.scalar(
        select(ChartMetricReview).where(
            ChartMetricReview.athlete_row_id == row.id,
            ChartMetricReview.metric_key == body.metric_key,
            ChartMetricReview.status == "proposed",
        )
    )
    if pending is not None:
        if pending.raw_label == raw:
            return _out(pending)
        raise AppError("chart_review_pending", "Confirm the pending value before proposing another", 409)
    current = session.scalar(
        select(ChartMetricReview).where(
            ChartMetricReview.athlete_row_id == row.id,
            ChartMetricReview.metric_key == body.metric_key,
            ChartMetricReview.status == "confirmed",
        )
    )
    if current is not None and current.raw_label == raw:
        return _out(current)
    value = ChartMetricReview(
        athlete_row_id=row.id,
        metric_key=body.metric_key,
        raw_label=raw,
        parsed_value=Decimal(raw),
        source_locator=f"page:2/chart:{body.metric_key}/table_row_ordinal:{row.row_ordinal}",
        capture_method="manual",
        status="proposed",
        proposed_by_user_id=actor_id,
    )
    session.add(value)
    session.flush()
    return _out(value)


def confirm_chart_value(
    session: Session,
    actor_id: UUID,
    upload_id: UUID,
    review_id: UUID,
    body: ChartReviewConfirmation,
    settings: Settings,
) -> ChartReviewOut:
    require_upload(session, actor_id, upload_id)
    review = session.scalar(select(ChartMetricReview).where(ChartMetricReview.id == review_id))
    if review is None:
        raise AppError("chart_review_not_found", "Chart review not found", 404)
    lock_resource(session, "source-row", str(review.athlete_row_id))
    # Reload after waiting so a concurrent confirmation cannot use stale state.
    session.refresh(review)
    row = session.scalar(
        select(SourceAthleteRow).where(
            SourceAthleteRow.id == review.athlete_row_id, SourceAthleteRow.report_upload_id == upload_id
        )
    )
    if row is None:
        raise AppError("chart_review_not_found", "Chart review not found", 404)
    if body.source_athlete_row_id != row.id or body.raw_label.strip() != review.raw_label:
        raise AppError("chart_confirmation_mismatch", "Confirmed athlete row and label must match the proposal", 409)
    if review.status in ("confirmed", "held"):
        return _out(review)
    if review.status != "proposed":
        raise AppError("chart_review_closed", "Chart review is no longer pending", 409)
    suspicious = review.metric_key == "maximum_velocity_kmh" and review.parsed_value > settings.max_velocity_review_kmh
    previous = session.scalar(
        select(ChartMetricReview)
        .where(
            ChartMetricReview.athlete_row_id == row.id,
            ChartMetricReview.metric_key == review.metric_key,
            ChartMetricReview.status == "confirmed",
        )
        .with_for_update()
    )
    if previous is not None:
        previous.status = "superseded"
        session.flush()
    review.status = "held" if suspicious else "confirmed"
    review.reviewed_by_user_id = actor_id
    review.reviewed_at = datetime.now(UTC)
    review.review_reason = body.review_reason.strip() if body.review_reason else None
    definition = BY_KEY[review.metric_key]
    observation = SourceMetricObservation(
        scope="athlete",
        athlete_row_id=row.id,
        source_label=definition.source_aliases[0],
        raw_value=review.raw_label,
        raw_unit="km/h" if review.metric_key == "maximum_velocity_kmh" else None,
        parsed_value=review.parsed_value,
        source_locator=review.source_locator,
        parser_version=CHART_REVIEW_VERSION,
        quality_state="accepted" if review.status == "confirmed" else "needs_review",
    )
    session.add(observation)
    session.flush()
    review.source_observation_id = observation.id
    linked = session.scalar(select(PlayerSession).where(PlayerSession.source_athlete_row_id == row.id))
    if linked is not None and linked.quality_state == "accepted":
        _sync_linked_metric(
            session, linked, review, upload_parser_key=require_upload(session, actor_id, upload_id).parser_key
        )
    session.flush()
    logger.info("chart_review_processed review_id=%s status=%s", review.id, review.status)
    return _out(review)


def sync_confirmed_chart_metrics(session: Session, linked: PlayerSession, parser_key: str | None) -> None:
    for key in ("maximum_velocity_kmh", "player_load_reported"):
        confirmed = session.scalar(
            select(ChartMetricReview).where(
                ChartMetricReview.athlete_row_id == linked.source_athlete_row_id,
                ChartMetricReview.metric_key == key,
                ChartMetricReview.status == "confirmed",
            )
        )
        if confirmed is not None:
            _sync_linked_metric(session, linked, confirmed, parser_key)


def _sync_linked_metric(
    session: Session, linked: PlayerSession, review: ChartMetricReview, upload_parser_key: str | None
) -> None:
    existing = session.get(SessionMetricValue, (linked.id, review.metric_key))
    if review.status != "confirmed":
        if existing is not None:
            session.delete(existing)
        return
    if review.source_observation_id is None:
        raise RuntimeError("Confirmed chart value has no source observation")
    definition = BY_KEY[review.metric_key]
    comparability_key = (
        f"unverified:{upload_parser_key or 'activity_report_pdf_v1'}:{review.metric_key}"
        if definition.source_specific
        else f"{REGISTRY_VERSION}:{review.metric_key}"
    )
    if existing is None:
        existing = SessionMetricValue(player_session_id=linked.id, metric_key=review.metric_key)
        session.add(existing)
    existing.value = review.parsed_value
    existing.unit = definition.canonical_unit
    existing.source_observation_id = review.source_observation_id
    existing.definition_id = None if definition.source_specific else REGISTRY_VERSION
    existing.comparability_key = comparability_key
    existing.quality_state = "accepted"
