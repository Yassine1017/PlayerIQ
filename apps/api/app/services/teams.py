"""Team membership and accepted-session projections over canonical player history."""

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.models.tables import (
    Player,
    PlayerSession,
    Profile,
    ReportUpload,
    SessionMetricValue,
    SourceAthleteRow,
    Team,
    TeamJoinRequest,
    TeamManagerGrant,
    TeamMembership,
    TeamRoster,
)
from app.schemas.teams import (
    JoinRequestsOut,
    TeamDashboardOut,
    TeamJoinRequestOut,
    TeamMetricOut,
    TeamOut,
    TeamParticipantOut,
    TeamPlayerOut,
    TeamPlayersOut,
    TeamReportOut,
    TeamReportsOut,
    TeamSessionDetailOut,
    TeamSessionOut,
    TeamSessionsOut,
    TeamsOut,
)
from app.services.authorization import require_team, require_team_admin, require_team_player, require_upload
from app.services.transaction_locks import lock_resource


def team_out(team: Team, membership: TeamMembership) -> TeamOut:
    return TeamOut(
        id=team.id,
        name=team.name,
        role=cast(Literal["player", "coach", "admin"], membership.role),
        player_id=membership.player_id,
        created_at=team.created_at,
    )


def create_team(session: Session, actor_id: UUID, name: str) -> TeamOut:
    player = session.scalar(select(Player).where(Player.owner_user_id == actor_id, Player.archived_at.is_(None)))
    if player is None:
        raise AppError("player_required", "Create your player profile before a team", 422)
    team = Team(name=name, created_by_user_id=actor_id)
    session.add(team)
    session.flush()
    membership = TeamMembership(team_id=team.id, user_id=actor_id, player_id=player.id, role="admin")
    session.add(membership)
    session.add(TeamManagerGrant(team_id=team.id, user_id=actor_id))
    session.flush()
    from app.services.team_imports import ensure_roster

    ensure_roster(session, actor_id, team.id, player.id)
    return team_out(team, membership)


def list_teams(session: Session, actor_id: UUID) -> TeamsOut:
    rows = session.execute(
        select(Team, TeamMembership)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .where(TeamMembership.user_id == actor_id, TeamMembership.revoked_at.is_(None))
        .order_by(Team.created_at.desc(), Team.id.desc())
        .limit(30)
    ).all()
    return TeamsOut(items=[team_out(team, membership) for team, membership in rows])


def request_to_join(session: Session, actor_id: UUID, team_id: UUID) -> TeamJoinRequestOut:
    if session.get(TeamMembership, (team_id, actor_id)) is not None:
        raise AppError("already_member", "You already belong to this team", 409)
    pending = session.scalar(
        select(TeamJoinRequest).where(
            TeamJoinRequest.team_id == team_id,
            TeamJoinRequest.user_id == actor_id,
            TeamJoinRequest.status == "pending",
        )
    )
    if pending is not None:
        return join_request_out(pending)
    profile = session.get(Profile, actor_id)
    player = session.scalar(select(Player).where(Player.owner_user_id == actor_id, Player.archived_at.is_(None)))
    if profile is None or player is None:
        raise AppError("profile_required", "Complete your player profile before joining a team", 422)
    request = TeamJoinRequest(
        team_id=team_id,
        user_id=actor_id,
        player_id=player.id,
        display_name_snapshot=profile.display_name,
        status="pending",
    )
    session.add(request)
    session.flush()
    return join_request_out(request)


def join_request_out(value: TeamJoinRequest) -> TeamJoinRequestOut:
    return TeamJoinRequestOut(
        id=value.id,
        team_id=value.team_id,
        user_id=value.user_id,
        display_name=value.display_name_snapshot,
        status=value.status,
        created_at=value.created_at,
    )


def list_join_requests(session: Session, actor_id: UUID, team_id: UUID) -> JoinRequestsOut:
    require_team_admin(session, actor_id, team_id)
    rows = session.scalars(
        select(TeamJoinRequest)
        .where(TeamJoinRequest.team_id == team_id, TeamJoinRequest.status == "pending")
        .order_by(TeamJoinRequest.created_at, TeamJoinRequest.id)
        .limit(100)
    ).all()
    return JoinRequestsOut(items=[join_request_out(row) for row in rows])


def approve_join_request(session: Session, actor_id: UUID, team_id: UUID, request_id: UUID, role: str) -> TeamOut:
    team = require_team_admin(session, actor_id, team_id)
    request = session.scalar(
        select(TeamJoinRequest)
        .where(TeamJoinRequest.id == request_id, TeamJoinRequest.team_id == team_id)
        .with_for_update()
    )
    if request is None or request.status != "pending":
        raise AppError("join_request_not_found", "Pending request not found", 404)
    if session.get(TeamMembership, (team_id, request.user_id)) is not None:
        raise AppError("membership_conflict", "Account already belongs to this team", 409)
    if role == "player":
        player = session.get(Player, request.player_id) if request.player_id else None
        if player is None or player.owner_user_id != request.user_id or player.archived_at is not None:
            raise AppError("player_unavailable", "Applicant player profile is unavailable", 409)
    membership = TeamMembership(
        team_id=team_id,
        user_id=request.user_id,
        player_id=request.player_id if role == "player" else None,
        role=role,
    )
    session.add(membership)
    if role == "coach":
        session.add(TeamManagerGrant(team_id=team_id, user_id=request.user_id))
    request.status = "approved"
    request.decided_by_user_id = actor_id
    request.decided_at = datetime.now(UTC)
    session.flush()
    if membership.player_id is not None:
        from app.services.team_imports import ensure_roster

        ensure_roster(session, actor_id, team_id, membership.player_id)
    return team_out(team, membership)


def assign_report_team(session: Session, actor_id: UUID, upload_id: UUID, team_id: UUID) -> UUID:
    lock_resource(session, "team-import", str(upload_id))
    upload = require_upload(session, actor_id, upload_id)
    require_team(session, actor_id, team_id, manager=True)
    if upload.team_id is not None and upload.team_id != team_id:
        raise AppError("team_assignment_conflict", "Report is already assigned to another team", 409)
    linked = session.scalars(
        select(PlayerSession)
        .where(
            PlayerSession.source_athlete_row_id.in_(
                select(SourceAthleteRow.id).where(SourceAthleteRow.report_upload_id == upload_id)
            )
        )
        .with_for_update()
    ).all()
    for player_session in linked:
        require_team_player(session, team_id, player_session.player_id)
    upload.team_id = team_id
    for player_session in linked:
        player_session.team_id = team_id
        player_session.report_upload_id = upload_id
    session.flush()
    return team_id


def _accepted_sessions(session: Session, team_id: UUID) -> list[PlayerSession]:
    rows = session.scalars(
        select(PlayerSession)
        .where(PlayerSession.team_id == team_id, PlayerSession.quality_state == "accepted")
        .order_by(PlayerSession.local_date.desc(), PlayerSession.id.desc())
        .limit(1001)
    ).all()
    if len(rows) > 1000:
        raise AppError("team_history_limit", "Team history exceeds the supported limit", 422)
    return list(rows)


def _metrics_by_session(session: Session, ids: list[UUID]) -> dict[UUID, list[SessionMetricValue]]:
    by_session: dict[UUID, list[SessionMetricValue]] = defaultdict(list)
    if ids:
        metrics = session.scalars(
            select(SessionMetricValue).where(
                SessionMetricValue.player_session_id.in_(ids), SessionMetricValue.quality_state == "accepted"
            )
        ).all()
        for metric in metrics:
            by_session[metric.player_session_id].append(metric)
    return by_session


def _team_session_summaries(
    sessions: list[PlayerSession], metrics: dict[UUID, list[SessionMetricValue]]
) -> list[TeamSessionOut]:
    grouped: dict[UUID, list[PlayerSession]] = defaultdict(list)
    for item in sessions:
        if item.report_upload_id is not None:
            grouped[item.report_upload_id].append(item)
    summaries: list[TeamSessionOut] = []
    for report_id, values in grouped.items():
        distances = [
            metric.value
            for item in values
            for metric in metrics.get(item.id, [])
            if metric.metric_key == "total_distance_m"
        ]
        types = {item.session_type for item in values}
        summaries.append(
            TeamSessionOut(
                report_upload_id=report_id,
                local_date=max(item.local_date for item in values),
                participant_count=len({item.player_id for item in values}),
                total_distance_m=str(sum(distances, Decimal(0))) if distances else None,
                session_type=next(iter(types)) if len(types) == 1 else "mixed",
            )
        )
    return sorted(summaries, key=lambda item: (item.local_date, item.report_upload_id), reverse=True)


def team_sessions(session: Session, actor_id: UUID, team_id: UUID, limit: int = 50) -> TeamSessionsOut:
    require_team(session, actor_id, team_id)
    history = _accepted_sessions(session, team_id)
    metrics = _metrics_by_session(session, [item.id for item in history])
    return TeamSessionsOut(items=_team_session_summaries(history, metrics)[:limit])


def team_dashboard(session: Session, actor_id: UUID, team_id: UUID) -> TeamDashboardOut:
    team, membership = require_team(session, actor_id, team_id)
    history = _accepted_sessions(session, team_id)
    metrics = _metrics_by_session(session, [item.id for item in history])
    recent = _team_session_summaries(history, metrics)[:5]
    player_count = (
        session.scalar(
            select(func.count(TeamRoster.player_id)).where(
                TeamRoster.team_id == team_id,
                TeamRoster.revoked_at.is_(None),
            )
        )
        or 0
    )
    return TeamDashboardOut(
        team=team_out(team, membership),
        latest_session=recent[0] if recent else None,
        recent_sessions=recent,
        player_count=player_count if membership.role in ("coach", "admin") else None,
    )


def team_session_detail(session: Session, actor_id: UUID, team_id: UUID, report_id: UUID) -> TeamSessionDetailOut:
    _, membership = require_team(session, actor_id, team_id)
    history = _accepted_sessions(session, team_id)
    grouped = [item for item in history if item.report_upload_id == report_id]
    if not grouped:
        raise AppError("team_session_not_found", "Team session not found", 404)
    metrics = _metrics_by_session(session, [item.id for item in grouped])
    summary = _team_session_summaries(grouped, metrics)[0]
    permitted = (
        grouped
        if membership.role in ("coach", "admin")
        else [item for item in grouped if item.player_id == membership.player_id]
    )
    players = (
        session.scalars(select(Player).where(Player.id.in_([item.player_id for item in permitted]))).all()
        if permitted
        else []
    )
    names = {player.id: player.display_name for player in players}
    return TeamSessionDetailOut(
        summary=summary,
        participants=[
            TeamParticipantOut(
                player_id=item.player_id,
                display_name=names.get(item.player_id, "Player"),
                session_id=item.id,
                metrics=[
                    TeamMetricOut(metric_key=m.metric_key, value=str(m.value), unit=m.unit) for m in metrics[item.id]
                ],
            )
            for item in permitted
        ],
    )


def team_players(session: Session, actor_id: UUID, team_id: UUID) -> TeamPlayersOut:
    _, membership = require_team(session, actor_id, team_id)
    memberships = session.scalars(
        select(TeamRoster)
        .where(
            TeamRoster.team_id == team_id,
            TeamRoster.revoked_at.is_(None),
        )
        .order_by(TeamRoster.created_at, TeamRoster.player_id)
        .limit(1001)
    ).all()
    if len(memberships) > 1000:
        raise AppError("roster_limit", "Team roster exceeds the supported limit", 422)
    if membership.role == "player":
        memberships = [item for item in memberships if item.player_id == membership.player_id]
    ids = [item.player_id for item in memberships if item.player_id is not None]
    players = session.scalars(select(Player).where(Player.id.in_(ids))).all() if ids else []
    names = {player.id: player.display_name for player in players}
    claimed = {player.id: player.owner_user_id is not None for player in players}
    history = _accepted_sessions(session, team_id)
    metrics = _metrics_by_session(session, [item.id for item in history])
    latest: dict[UUID, PlayerSession] = {}
    for item in history:
        latest.setdefault(item.player_id, item)
    return TeamPlayersOut(
        items=[
            TeamPlayerOut(
                id=player_id,
                display_name=names.get(player_id, "Player"),
                account_state="registered" if claimed.get(player_id) else "unclaimed",
                participation_state="accepted_history" if player_id in latest else "no_accepted_activity",
                latest_session_date=latest[player_id].local_date if player_id in latest else None,
                latest_metrics=[
                    TeamMetricOut(metric_key=m.metric_key, value=str(m.value), unit=m.unit)
                    for m in metrics.get(latest[player_id].id, [])
                    if m.metric_key in ("total_distance_m", "maximum_velocity_kmh")
                ]
                if player_id in latest
                else [],
            )
            for player_id in ids
        ],
        limited_to_self=membership.role == "player",
    )


def team_reports(session: Session, actor_id: UUID, team_id: UUID) -> TeamReportsOut:
    require_team(session, actor_id, team_id, manager=True)
    uploads = session.scalars(
        select(ReportUpload)
        .where(ReportUpload.team_id == team_id, ReportUpload.status != "deleted")
        .order_by(ReportUpload.created_at.desc(), ReportUpload.id.desc())
        .limit(50)
    ).all()
    counts = dict(
        session.execute(
            select(PlayerSession.report_upload_id, func.count(PlayerSession.id))
            .where(PlayerSession.team_id == team_id, PlayerSession.quality_state == "accepted")
            .group_by(PlayerSession.report_upload_id)
        ).all()
    )
    return TeamReportsOut(
        items=[
            TeamReportOut(
                upload_id=upload.id,
                status=upload.status,
                created_at=upload.created_at,
                accepted_player_count=counts.get(upload.id, 0),
            )
            for upload in uploads
        ]
    )
