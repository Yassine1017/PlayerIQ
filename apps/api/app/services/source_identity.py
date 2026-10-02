"""Explicit source-label ownership and narrow recognition within a report scope."""

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.core.config import Settings
from app.models.tables import (
    ActivityReport,
    Player,
    PlayerSession,
    PlayerSourceIdentity,
    ReportUpload,
    SourceAthleteRow,
    TeamMembership,
)
from app.schemas.v1 import LinkRequest
from app.services.authorization import require_player, require_team, require_team_player, require_upload
from app.services.transaction_locks import lock_resource


def normalize_source_label(value: str) -> str:
    """Case/space normalization and explicit PDF hyphen-wrap repair only."""
    value = unicodedata.normalize("NFKC", value).replace("\u00ad", "")
    value = re.sub(r"-\s*\n\s*", "", value)
    return " ".join(value.split()).casefold()


def source_scope(upload: ReportUpload, report: ActivityReport | None) -> str:
    if upload.team_id is not None:
        return f"team:{upload.team_id}"
    team_name = normalize_source_label(report.source_team_name) if report and report.source_team_name else ""
    if team_name:
        return f"private:{upload.uploaded_by_user_id}:{team_name}"
    # An absent team label cannot prove future reports share the same context.
    return f"report:{upload.id}"


def recognized_identity(
    session: Session,
    upload: ReportUpload,
    report: ActivityReport | None,
    row: SourceAthleteRow,
    label_counts: Mapping[str, int] | None = None,
) -> PlayerSourceIdentity | None:
    if row.participation_state != "ready" or not upload.parser_key:
        return None
    key = normalize_source_label(row.source_name)
    if not key:
        return None
    if label_counts is None:
        report_labels = session.scalars(
            select(SourceAthleteRow.source_name).where(SourceAthleteRow.report_upload_id == upload.id)
        ).all()
        label_counts = Counter(normalize_source_label(label) for label in report_labels)
    if label_counts.get(key) != 1:
        return None
    matches = session.scalars(
        select(PlayerSourceIdentity)
        .where(
            PlayerSourceIdentity.scope_key == source_scope(upload, report),
            PlayerSourceIdentity.parser_key == upload.parser_key,
            PlayerSourceIdentity.normalized_label == key,
            PlayerSourceIdentity.revoked_at.is_(None),
        )
        .limit(2)
    ).all()
    if len(matches) != 1:
        return None
    identity = matches[0]
    player = session.get(Player, identity.player_id)
    if player is None or player.archived_at is not None:
        return None
    if (
        upload.team_id is not None
        and session.scalar(
            select(TeamMembership.user_id).where(
                TeamMembership.team_id == upload.team_id,
                TeamMembership.player_id == identity.player_id,
                TeamMembership.revoked_at.is_(None),
            )
        )
        is None
    ):
        return None
    return identity


def claim_self(
    session: Session,
    actor_id: UUID,
    upload_id: UUID,
    row_id: UUID,
    player_id: UUID,
    confirmed_source_label: str,
    session_type: Literal["training", "match", "unknown"],
    settings: Settings,
) -> tuple[PlayerSourceIdentity, UUID]:
    require_player(session, actor_id, player_id, manage=True)
    return _confirm_identity(
        session, actor_id, upload_id, row_id, player_id, confirmed_source_label, session_type, settings
    )


def confirm_team_player(
    session: Session,
    actor_id: UUID,
    upload_id: UUID,
    row_id: UUID,
    player_id: UUID,
    confirmed_source_label: str,
    session_type: Literal["training", "match", "unknown"],
    settings: Settings,
) -> tuple[PlayerSourceIdentity, UUID]:
    upload = require_upload(session, actor_id, upload_id)
    if upload.team_id is None:
        raise AppError("team_required", "Assign the report to a team first", 409)
    require_team(session, actor_id, upload.team_id, manager=True)
    require_team_player(session, upload.team_id, player_id)
    return _confirm_identity(
        session, actor_id, upload_id, row_id, player_id, confirmed_source_label, session_type, settings
    )


def _confirm_identity(
    session: Session,
    actor_id: UUID,
    upload_id: UUID,
    row_id: UUID,
    player_id: UUID,
    confirmed_source_label: str,
    session_type: Literal["training", "match", "unknown"],
    settings: Settings,
) -> tuple[PlayerSourceIdentity, UUID]:
    upload = require_upload(session, actor_id, upload_id)
    # Same order as linking: player, source row, then mapping. No UPDATE grants
    # are needed on the read-only player/source tables, including team members.
    lock_resource(session, "player-session", str(player_id))
    lock_resource(session, "source-row", str(row_id))
    row = session.scalar(
        select(SourceAthleteRow).where(SourceAthleteRow.id == row_id, SourceAthleteRow.report_upload_id == upload_id)
    )
    if row is None:
        raise AppError("row_not_found", "Athlete row not found", 404)
    if confirmed_source_label.strip() != row.source_name:
        raise AppError("source_label_changed", "Confirm the exact source athlete label", 409)
    if row.participation_state != "ready":
        raise AppError("row_requires_review", "Athlete row requires review before linking", 422)
    report = session.get(ActivityReport, upload_id)
    if not upload.parser_key or report is None:
        raise AppError("upload_not_ready", "Report is not ready for identity confirmation", 409)
    scope = source_scope(upload, report)
    normalized = normalize_source_label(row.source_name)
    if not normalized or len(normalized) > 255:
        raise AppError("source_label_unavailable", "Source athlete label is unavailable", 422)
    report_labels = session.scalars(
        select(SourceAthleteRow.source_name).where(SourceAthleteRow.report_upload_id == upload_id)
    ).all()
    if sum(normalize_source_label(label) == normalized for label in report_labels) != 1:
        raise AppError("identity_ambiguous", "Source athlete label is not unique in this report", 409)
    lock_resource(session, "source-identity", f"{scope}:{upload.parser_key}:{normalized}")
    existing = session.scalar(
        select(PlayerSourceIdentity).where(
            PlayerSourceIdentity.scope_key == scope,
            PlayerSourceIdentity.parser_key == upload.parser_key,
            PlayerSourceIdentity.normalized_label == normalized,
            PlayerSourceIdentity.revoked_at.is_(None),
        )
    )
    if existing is not None and existing.player_id != player_id:
        raise AppError("identity_conflict", "Source label is already connected in this scope", 409)
    existing_session = session.scalar(select(PlayerSession).where(PlayerSession.source_athlete_row_id == row.id))
    if existing_session is not None:
        if existing_session.player_id != player_id or existing_session.quality_state != "accepted":
            raise AppError("row_already_linked", "Athlete row is linked to another player or requires review", 409)
        session_type = cast(Literal["training", "match", "unknown"], existing_session.session_type)
    # The existing link service rechecks participation, date, ownership, and metrics.
    from app.services.linking import link_athlete_row

    linked = link_athlete_row(
        session,
        actor_id,
        upload_id,
        LinkRequest(source_athlete_row_id=row_id, player_id=player_id, session_type=session_type),
        settings,
    )
    if existing is not None:
        return existing, linked.session_id
    identity = PlayerSourceIdentity(
        player_id=player_id,
        team_id=upload.team_id,
        scope_key=scope,
        parser_key=upload.parser_key,
        normalized_label=normalized,
        original_label=row.source_name,
        confirmed_row_id=row.id,
        created_by_user_id=actor_id,
        confirmed_by_user_id=actor_id,
    )
    session.add(identity)
    session.flush()
    return identity, linked.session_id


def list_own_identities(session: Session, actor_id: UUID) -> list[PlayerSourceIdentity]:
    return list(
        session.scalars(
            select(PlayerSourceIdentity)
            .join(Player, Player.id == PlayerSourceIdentity.player_id)
            .where(Player.owner_user_id == actor_id)
            .order_by(PlayerSourceIdentity.confirmed_at.desc(), PlayerSourceIdentity.id.desc())
            .limit(50)
        ).all()
    )


def revoke_identity(session: Session, actor_id: UUID, identity_id: UUID) -> PlayerSourceIdentity:
    identity = session.get(PlayerSourceIdentity, identity_id)
    if identity is None:
        raise AppError("identity_not_found", "GPS identity not found", 404)
    require_player(session, actor_id, identity.player_id, manage=True)
    lock_resource(session, "source-identity", f"{identity.scope_key}:{identity.parser_key}:{identity.normalized_label}")
    session.refresh(identity)
    if identity.revoked_at is None:
        identity.revoked_at = datetime.now(UTC)
        session.flush()
    return identity
