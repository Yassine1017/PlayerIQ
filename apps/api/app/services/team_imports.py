"""Atomic report-level roster import using canonical linking and restricted API transactions."""

import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.core.config import Settings
from app.db.session import Database
from app.domain.team_import import MAX_IMPORT_ROWS, RowEligibility, exclusion_reason
from app.models.tables import (
    ActivityReport,
    Player,
    PlayerSession,
    PlayerSourceIdentity,
    ReportUpload,
    SourceAthleteRow,
    SourceMetricObservation,
    TeamMembership,
    TeamReportImport,
    TeamReportImportRow,
    TeamRoster,
    TeamRosterResolution,
)
from app.schemas.team_imports import ImportResolution, ImportRowOut, TeamImportOut, TeamImportRequest
from app.schemas.v1 import LinkRequest
from app.services.authorization import require_team, require_team_player, require_upload
from app.services.linking import link_athlete_row
from app.services.source_identity import normalize_source_label, source_scope
from app.services.teams import assign_report_team
from app.services.transaction_locks import lock_resource

logger = logging.getLogger(__name__)


def ensure_roster(
    session: Session,
    actor_id: UUID,
    team_id: UUID,
    player_id: UUID,
    row: SourceAthleteRow | None = None,
    parser_key: str | None = None,
) -> TeamRoster:
    existing = session.get(TeamRoster, (team_id, player_id))
    if existing is not None:
        if existing.revoked_at is not None:
            raise AppError("roster_conflict", "Athlete roster association requires review", 409)
        return existing
    roster_ids = session.scalars(
        select(TeamRoster.player_id).where(TeamRoster.team_id == team_id, TeamRoster.revoked_at.is_(None)).limit(1000)
    ).all()
    if len(roster_ids) >= 1000:
        raise AppError("roster_limit", "Team roster exceeds the supported limit", 422)
    entry = TeamRoster(
        team_id=team_id,
        player_id=player_id,
        added_by_user_id=actor_id,
        source_row_id=row.id if row else None,
        parser_key=parser_key,
        normalized_label=normalize_source_label(row.source_name) if row else None,
    )
    session.add(entry)
    session.flush()
    return entry


def request_import(session: Session, actor_id: UUID, upload_id: UUID, body: TeamImportRequest) -> TeamImportOut:
    lock_resource(session, "team-import", str(upload_id))
    upload = require_upload(session, actor_id, upload_id)
    require_team(session, actor_id, body.team_id, manager=True)
    assign_report_team(session, actor_id, upload_id, body.team_id)
    run = session.get(TeamReportImport, upload_id)
    if run is None:
        run = TeamReportImport(
            upload_id=upload_id, team_id=body.team_id, requested_by_user_id=actor_id, session_type=body.session_type
        )
        session.add(run)
        session.flush()
    elif run.team_id != body.team_id or run.session_type != body.session_type:
        raise AppError("import_conflict", "Existing import team or session type differs", 409)
    elif run.status == "failed":
        run.status, run.attempts, run.error_code, run.finished_at = "queued", 0, None, None
        session.flush()
    # A repeat of a finished request is a read, not a new import or session.
    return import_out(session, actor_id, upload.id)


def import_out(session: Session, actor_id: UUID, upload_id: UUID) -> TeamImportOut:
    upload = require_upload(session, actor_id, upload_id)
    if upload.team_id is None:
        raise AppError("import_not_found", "No team import requested", 404)
    require_team(session, actor_id, upload.team_id, manager=True)
    run = session.get(TeamReportImport, upload_id)
    if run is None:
        raise AppError("import_not_found", "No team import requested", 404)
    values = session.execute(
        select(TeamReportImportRow, SourceAthleteRow)
        .join(SourceAthleteRow, SourceAthleteRow.id == TeamReportImportRow.row_id)
        .where(TeamReportImportRow.upload_id == upload_id)
        .order_by(SourceAthleteRow.row_ordinal)
        .limit(MAX_IMPORT_ROWS + 1)
    ).all()
    if len(values) > MAX_IMPORT_ROWS:
        raise AppError("import_row_limit", "Report exceeds the supported athlete limit", 422)
    rows = [
        ImportRowOut(
            row_id=value.row_id,
            row_ordinal=source.row_ordinal,
            source_name=source.source_name,
            player_id=value.player_id,
            session_id=value.session_id,
            association_method=value.association_method,
            outcome=value.outcome,
            reason_code=value.reason_code,
            created_player=value.created_player,
            created_session=value.created_session,
            resolved_at=value.resolved_at,
        )
        for value, source in values
    ]
    counts = dict(Counter(row.outcome for row in rows))
    counts.update(
        total=len(rows),
        created_players=sum(r.created_player for r in rows),
        created_sessions=sum(r.created_session for r in rows),
        accepted_sessions=sum(
            r.session_id is not None and r.outcome in ("accepted_session", "existing_session") for r in rows
        ),
    )
    return TeamImportOut(
        upload_id=run.upload_id,
        team_id=run.team_id,
        status=cast(Literal["queued", "complete", "needs_review", "failed"], run.status),
        session_type=run.session_type,
        attempts=run.attempts,
        error_code=run.error_code,
        created_at=run.created_at,
        finished_at=run.finished_at,
        counts=counts,
        rows=rows,
    )


def execute_import(session: Session, actor_id: UUID, upload_id: UUID, settings: Settings) -> None:
    lock_resource(session, "team-import", str(upload_id))
    upload = require_upload(session, actor_id, upload_id)
    run = session.get(TeamReportImport, upload_id)
    if run is None or run.status != "queued":
        return
    require_team(session, actor_id, run.team_id, manager=True)
    if upload.team_id != run.team_id or run.requested_by_user_id != actor_id:
        raise AppError("import_authorization_changed", "Team import authorization changed", 409)
    lock_resource(session, "team-roster", str(run.team_id))
    if upload.status != "awaiting_link":
        raise AppError("upload_not_ready", "Report is not ready for import", 409)
    run.attempts += 1
    report = session.get(ActivityReport, upload_id)
    if report is None or not upload.parser_key:
        raise AppError("upload_not_ready", "Extracted report is unavailable", 409)
    rows = session.scalars(
        select(SourceAthleteRow)
        .where(SourceAthleteRow.report_upload_id == upload_id)
        .order_by(SourceAthleteRow.row_ordinal)
        .limit(MAX_IMPORT_ROWS + 1)
    ).all()
    if not rows or len(rows) > MAX_IMPORT_ROWS:
        raise AppError("import_row_limit", "Report must contain between one and 200 extracted athletes", 422)
    labels = Counter(normalize_source_label(r.source_name) for r in rows)
    parsed_rows = set(
        session.scalars(
            select(SourceMetricObservation.athlete_row_id).where(
                SourceMetricObservation.athlete_row_id.in_([r.id for r in rows]),
                SourceMetricObservation.source_label == "Distance (m)",
                SourceMetricObservation.raw_value.is_not(None),
            )
        ).all()
    )
    for row in rows:
        outcome = session.get(TeamReportImportRow, row.id)
        if outcome is not None:
            continue
        outcome = TeamReportImportRow(
            row_id=row.id, upload_id=upload_id, association_method="unresolved", outcome="identity_review"
        )
        session.add(outcome)
        key = normalize_source_label(row.source_name)
        reason = exclusion_reason(
            RowEligibility(
                row.id in parsed_rows and bool(key) and len(key) <= 255 and len(row.source_name) <= 160,
                labels[key] == 1,
                row.participation_state,
            )
        )
        existing_session = session.scalar(select(PlayerSession).where(PlayerSession.source_athlete_row_id == row.id))
        if reason in ("source_label_unavailable", "duplicate_source_label") and existing_session is None:
            outcome.reason_code = reason
            session.flush()
            continue
        mappings = session.scalars(
            select(PlayerSourceIdentity)
            .where(
                PlayerSourceIdentity.scope_key == source_scope(upload, report),
                PlayerSourceIdentity.parser_key == upload.parser_key,
                PlayerSourceIdentity.normalized_label == key,
                PlayerSourceIdentity.revoked_at.is_(None),
            )
            .limit(2)
        ).all()
        entries = session.scalars(
            select(TeamRoster)
            .where(
                TeamRoster.team_id == run.team_id,
                TeamRoster.parser_key == upload.parser_key,
                TeamRoster.normalized_label == key,
                TeamRoster.revoked_at.is_(None),
            )
            .limit(2)
        ).all()
        if (
            len(mappings) > 1
            or len(entries) > 1
            or (mappings and entries and mappings[0].player_id != entries[0].player_id)
        ):
            outcome.reason_code = "identity_conflict"
            session.flush()
            continue
        if existing_session is not None:
            require_team_player(session, run.team_id, existing_session.player_id)
            if mappings and mappings[0].player_id != existing_session.player_id:
                outcome.reason_code = "identity_conflict"
                session.flush()
                continue
            player_id = existing_session.player_id
            outcome.association_method = "existing_link"
        elif mappings:
            player_id = mappings[0].player_id
            try:
                require_team_player(session, run.team_id, player_id)
            except AppError:
                outcome.reason_code = "mapped_player_unavailable"
                session.flush()
                continue
            outcome.association_method = "confirmed_identity"
        elif entries:
            # Name-based import provenance is not a confirmed cross-report identity.
            outcome.player_id = entries[0].player_id
            outcome.association_method = "roster_candidate"
            outcome.reason_code = "unconfirmed_source_identity"
            session.flush()
            continue
        else:
            player = Player(owner_user_id=None, origin_team_id=run.team_id, display_name=row.source_name)
            session.add(player)
            session.flush()
            player_id = player.id
            outcome.association_method, outcome.created_player = "team_report_import", True
        mapped_player = session.get(Player, player_id)
        if mapped_player is None or mapped_player.archived_at is not None:
            outcome.reason_code = "mapped_player_unavailable"
            session.flush()
            continue
        ensure_roster(session, actor_id, run.team_id, player_id, row, upload.parser_key)
        outcome.player_id = player_id
        if existing_session is not None:
            outcome.session_id, outcome.outcome = existing_session.id, "existing_session"
        elif reason is not None:
            outcome.outcome = "no_activity" if reason == "no_recorded_activity" else "metric_review"
            outcome.reason_code = reason
        else:
            _link_result(session, actor_id, run, row, outcome, settings, mappings[0].id if mappings else None)
        session.flush()
    _finish(session, run)


def _link_result(
    session: Session,
    actor_id: UUID,
    run: TeamReportImport,
    row: SourceAthleteRow,
    outcome: TeamReportImportRow,
    settings: Settings,
    identity_id: UUID | None = None,
) -> None:
    assert outcome.player_id is not None
    try:
        # A row conflict must not poison the rest of the atomic report transaction.
        with session.begin_nested():
            result = link_athlete_row(
                session,
                actor_id,
                run.upload_id,
                LinkRequest(
                    source_athlete_row_id=row.id,
                    player_id=outcome.player_id,
                    session_type=cast(Literal["training", "match", "unknown"], run.session_type),
                    source_identity_id=identity_id,
                ),
                settings,
            )
        outcome.session_id, outcome.created_session, outcome.outcome = result.session_id, True, "accepted_session"
        outcome.reason_code = None
    except AppError as exc:
        outcome.outcome = "session_conflict" if exc.status_code == 409 else "metric_review"
        outcome.reason_code = exc.code


def _finish(session: Session, run: TeamReportImport) -> None:
    session.flush()
    states = session.scalars(
        select(TeamReportImportRow.outcome).where(TeamReportImportRow.upload_id == run.upload_id)
    ).all()
    run.status = (
        "needs_review"
        if any(s in ("identity_review", "metric_review", "session_conflict") for s in states)
        else "complete"
    )
    run.finished_at, run.error_code = datetime.now(UTC), None
    session.flush()


def resolve_row(
    session: Session, actor_id: UUID, upload_id: UUID, row_id: UUID, body: ImportResolution, settings: Settings
) -> TeamImportOut:
    lock_resource(session, "team-import", str(upload_id))
    upload = require_upload(session, actor_id, upload_id)
    run = session.get(TeamReportImport, upload_id)
    if run is None or upload.team_id != run.team_id:
        raise AppError("import_not_found", "Team import not found", 404)
    require_team(session, actor_id, run.team_id, manager=True)
    lock_resource(session, "team-roster", str(run.team_id))
    row = session.get(SourceAthleteRow, row_id)
    outcome = session.get(TeamReportImportRow, row_id)
    if (
        row is None
        or outcome is None
        or outcome.upload_id != upload_id
        or row.source_name != body.confirmed_source_label
    ):
        raise AppError("source_label_changed", "Confirm the exact source row", 409)
    if not normalize_source_label(row.source_name) or len(row.source_name) > 160:
        raise AppError("source_label_unavailable", "Source athlete label requires correction", 422)
    if (
        session.scalar(
            select(SourceMetricObservation.id)
            .where(
                SourceMetricObservation.athlete_row_id == row_id,
                SourceMetricObservation.source_label == "Distance (m)",
                SourceMetricObservation.raw_value.is_not(None),
            )
            .limit(1)
        )
        is None
    ):
        raise AppError("source_label_unavailable", "An unparsed athlete row requires source correction", 422)
    target_id = body.player_id or outcome.player_id
    if (
        outcome.resolved_at is not None
        and outcome.player_id == target_id
        and outcome.outcome in ("accepted_session", "existing_session", "no_activity")
    ):
        return import_out(session, actor_id, upload_id)
    if target_id is None:
        # A duplicate label may deliberately become a separate unclaimed athlete.
        player = Player(owner_user_id=None, origin_team_id=run.team_id, display_name=row.source_name)
        session.add(player)
        session.flush()
        target_id, outcome.created_player = player.id, True
        ensure_roster(session, actor_id, run.team_id, target_id)
    require_team_player(session, run.team_id, target_id)
    target = session.get(Player, target_id)
    if target is None or target.archived_at is not None:
        raise AppError("player_unavailable", "Roster athlete is unavailable", 409)
    if outcome.player_id is not None and outcome.player_id != target_id:
        _associate_registered_player(session, actor_id, run.team_id, outcome.player_id, target_id, row.id)
    outcome.player_id, outcome.association_method = target_id, "manager_confirmed"
    outcome.resolved_by_user_id, outcome.resolved_at = actor_id, datetime.now(UTC)
    report = session.get(ActivityReport, upload_id)
    assert report is not None and upload.parser_key is not None
    key = normalize_source_label(row.source_name)
    labels = session.scalars(
        select(SourceAthleteRow.source_name).where(SourceAthleteRow.report_upload_id == upload_id)
    ).all()
    # Duplicate labels can be resolved per row, but must not become reusable mappings.
    if key and sum(normalize_source_label(label) == key for label in labels) == 1:
        lock_resource(session, "source-identity", f"{source_scope(upload, report)}:{upload.parser_key}:{key}")
        mapping = session.scalar(
            select(PlayerSourceIdentity).where(
                PlayerSourceIdentity.scope_key == source_scope(upload, report),
                PlayerSourceIdentity.parser_key == upload.parser_key,
                PlayerSourceIdentity.normalized_label == key,
                PlayerSourceIdentity.revoked_at.is_(None),
            )
        )
        if mapping is not None and mapping.player_id != target_id:
            raise AppError("identity_conflict", "Confirmed source identity belongs to another athlete", 409)
        if mapping is None:
            session.add(
                PlayerSourceIdentity(
                    player_id=target_id,
                    team_id=run.team_id,
                    scope_key=source_scope(upload, report),
                    parser_key=upload.parser_key,
                    normalized_label=key,
                    original_label=row.source_name,
                    confirmed_row_id=row.id,
                    created_by_user_id=actor_id,
                    confirmed_by_user_id=actor_id,
                )
            )
            session.flush()
    existing = session.scalar(select(PlayerSession).where(PlayerSession.source_athlete_row_id == row.id))
    if existing is not None:
        if existing.player_id != target_id:
            raise AppError("row_already_linked", "This row already has a different player", 409)
        outcome.session_id, outcome.outcome, outcome.reason_code = existing.id, "existing_session", None
    elif row.participation_state == "zero_recorded":
        outcome.outcome, outcome.reason_code = "no_activity", "no_recorded_activity"
    elif row.participation_state != "ready":
        outcome.outcome, outcome.reason_code = "metric_review", "row_requires_review"
    else:
        _link_result(session, actor_id, run, row, outcome, settings)
    _finish(session, run)
    return import_out(session, actor_id, upload_id)


def _associate_registered_player(
    session: Session, actor_id: UUID, team_id: UUID, from_id: UUID, to_id: UUID, row_id: UUID
) -> None:
    # This deliberate manager confirmation connects imported history to an already
    # approved real account. It never changes account ownership or membership.
    for player_id in sorted((from_id, to_id), key=str):
        lock_resource(session, "player-session", str(player_id))
    source, target = session.get(Player, from_id), session.get(Player, to_id)
    member = session.scalar(
        select(TeamMembership).where(
            TeamMembership.team_id == team_id, TeamMembership.player_id == to_id, TeamMembership.revoked_at.is_(None)
        )
    )
    if (
        source is None
        or source.owner_user_id is not None
        or source.origin_team_id != team_id
        or target is None
        or target.owner_user_id is None
        or member is None
    ):
        raise AppError(
            "ownership_resolution_required", "Select an approved account to associate unclaimed history", 409
        )
    history = session.scalars(select(PlayerSession).where(PlayerSession.player_id == from_id).limit(1001)).all()
    if len(history) > 1000 or any(h.team_id != team_id for h in history):
        raise AppError("history_resolution_limit", "Imported history requires additional review", 409)
    dates = {h.local_date for h in history}
    if len(dates) != len(history) or (
        dates
        and session.scalar(
            select(PlayerSession.id)
            .where(PlayerSession.player_id == to_id, PlayerSession.local_date.in_(dates))
            .limit(1)
        )
        is not None
    ):
        raise AppError("same_date_review", "The account already has a session on an imported date", 409)
    identities = session.scalars(select(PlayerSourceIdentity).where(PlayerSourceIdentity.player_id == from_id)).all()
    if any(i.team_id != team_id for i in identities):
        raise AppError("identity_conflict", "Imported identity has another scope", 409)
    session.add(
        TeamRosterResolution(
            team_id=team_id,
            from_player_id=from_id,
            to_player_id=to_id,
            source_row_id=row_id,
            confirmed_by_user_id=actor_id,
        )
    )
    session.flush()
    for h in history:
        h.player_id = to_id
    for identity in identities:
        identity.player_id = to_id
    for result in session.scalars(select(TeamReportImportRow).where(TeamReportImportRow.player_id == from_id)).all():
        result.player_id, result.resolved_by_user_id, result.resolved_at = to_id, actor_id, datetime.now(UTC)
    roster = session.get(TeamRoster, (team_id, from_id))
    if roster is not None:
        roster.revoked_at = datetime.now(UTC)
    source.archived_at = datetime.now(UTC)
    session.flush()


def process_next_team_import(worker: Database, api: Database, settings: Settings) -> bool:
    # The worker reads only queue metadata. Accepted history is written through
    # an API transaction as the recorded uploader, with current authorization.
    with worker.worker_transaction() as session:
        candidate = session.execute(
            select(TeamReportImport.upload_id, TeamReportImport.requested_by_user_id)
            .join(ReportUpload, ReportUpload.id == TeamReportImport.upload_id)
            .where(
                TeamReportImport.status == "queued", ReportUpload.status.in_(("awaiting_link", "rejected", "deleted"))
            )
            .order_by(TeamReportImport.created_at, TeamReportImport.upload_id)
            .limit(1)
        ).first()
    if candidate is None:
        return False
    upload_id, actor_id = candidate
    try:
        with api.user_transaction(actor_id) as session:
            execute_import(session, actor_id, upload_id, settings)
    except Exception as exc:
        code = exc.code if isinstance(exc, AppError) else "import_processing_failed"
        logger.warning("team_import_failed error_code=%s error_type=%s", code, type(exc).__name__)
        with api.user_transaction(actor_id) as session:
            lock_resource(session, "team-import", str(upload_id))
            run = session.get(TeamReportImport, upload_id)
            if run is not None and run.status == "queued":
                run.attempts += 1
                run.error_code = code
                run.status = "failed" if run.attempts >= 3 else "queued"
                run.finished_at = datetime.now(UTC) if run.status == "failed" else None
    return True
