"""Authenticated team workspace over accepted, linked player sessions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError

from app.api.analytics import _fact_out
from app.api.errors import AppError
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import Database, get_database
from app.schemas.analytics import AnalyticsOverviewOut
from app.schemas.team_imports import ImportResolution, TeamImportOut, TeamImportRequest
from app.schemas.teams import (
    ApproveJoinRequest,
    AssignReportTeam,
    JoinRequestsOut,
    TeamCreate,
    TeamDashboardOut,
    TeamJoinRequestOut,
    TeamOut,
    TeamPlayersOut,
    TeamReportsOut,
    TeamSessionDetailOut,
    TeamSessionsOut,
    TeamsOut,
)
from app.services.analytics import AnalyticsService
from app.services.authorization import require_team, require_team_player
from app.services.teams import (
    approve_join_request,
    assign_report_team,
    create_team,
    list_join_requests,
    list_teams,
    request_to_join,
    team_dashboard,
    team_out,
    team_players,
    team_reports,
    team_session_detail,
    team_sessions,
)

router = APIRouter(prefix="/v1", tags=["teams"])
User = Annotated[CurrentUser, Depends(get_current_user)]
DB = Annotated[Database, Depends(get_database)]


@router.post("/report-uploads/{upload_id}/team-import", response_model=TeamImportOut, status_code=202)
def request_team_import_route(upload_id: UUID, body: TeamImportRequest, user: User, database: DB) -> TeamImportOut:
    from app.services.team_imports import request_import

    with database.user_transaction(user.id) as session:
        return request_import(session, user.id, upload_id, body)


@router.get("/report-uploads/{upload_id}/team-import", response_model=TeamImportOut)
def get_team_import_route(upload_id: UUID, user: User, database: DB) -> TeamImportOut:
    from app.services.team_imports import import_out

    with database.user_transaction(user.id) as session:
        return import_out(session, user.id, upload_id)


@router.post("/report-uploads/{upload_id}/team-import/rows/{row_id}/resolve", response_model=TeamImportOut)
def resolve_team_import_route(
    upload_id: UUID,
    row_id: UUID,
    body: ImportResolution,
    user: User,
    database: DB,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TeamImportOut:
    from app.services.team_imports import resolve_row

    with database.user_transaction(user.id) as session:
        return resolve_row(session, user.id, upload_id, row_id, body, settings)


@router.post("/teams", response_model=TeamOut, status_code=201)
def create_team_route(body: TeamCreate, user: User, database: DB) -> TeamOut:
    with database.user_transaction(user.id) as session:
        return create_team(session, user.id, body.name)


@router.get("/teams", response_model=TeamsOut)
def list_teams_route(user: User, database: DB) -> TeamsOut:
    with database.user_transaction(user.id) as session:
        return list_teams(session, user.id)


@router.get("/teams/{team_id}", response_model=TeamOut)
def get_team_route(team_id: UUID, user: User, database: DB) -> TeamOut:
    with database.user_transaction(user.id) as session:
        team, membership = require_team(session, user.id, team_id)
        return team_out(team, membership)


@router.post("/teams/{team_id}/join-requests", response_model=TeamJoinRequestOut, status_code=202)
def request_join_route(team_id: UUID, user: User, database: DB) -> TeamJoinRequestOut:
    try:
        with database.user_transaction(user.id) as session:
            return request_to_join(session, user.id, team_id)
    except IntegrityError as exc:
        raise AppError("team_unavailable", "Team is unavailable or request already exists", 404) from exc


@router.get("/teams/{team_id}/join-requests", response_model=JoinRequestsOut)
def join_requests_route(team_id: UUID, user: User, database: DB) -> JoinRequestsOut:
    with database.user_transaction(user.id) as session:
        return list_join_requests(session, user.id, team_id)


@router.post("/teams/{team_id}/join-requests/{request_id}/approve", response_model=TeamOut)
def approve_join_route(team_id: UUID, request_id: UUID, body: ApproveJoinRequest, user: User, database: DB) -> TeamOut:
    try:
        with database.user_transaction(user.id) as session:
            return approve_join_request(session, user.id, team_id, request_id, body.role)
    except IntegrityError as exc:
        raise AppError("membership_conflict", "Team membership conflicts with existing data", 409) from exc


@router.post("/report-uploads/{upload_id}/team", response_model=TeamOut)
def assign_report_team_route(upload_id: UUID, body: AssignReportTeam, user: User, database: DB) -> TeamOut:
    with database.user_transaction(user.id) as session:
        team_id = assign_report_team(session, user.id, upload_id, body.team_id)
        team, membership = require_team(session, user.id, team_id)
        return team_out(team, membership)


@router.get("/teams/{team_id}/dashboard", response_model=TeamDashboardOut)
def team_dashboard_route(team_id: UUID, user: User, database: DB) -> TeamDashboardOut:
    with database.user_transaction(user.id) as session:
        return team_dashboard(session, user.id, team_id)


@router.get("/teams/{team_id}/sessions", response_model=TeamSessionsOut)
def team_sessions_route(
    team_id: UUID, user: User, database: DB, limit: Annotated[int, Query(ge=1, le=50)] = 30
) -> TeamSessionsOut:
    with database.user_transaction(user.id) as session:
        return team_sessions(session, user.id, team_id, limit)


@router.get("/teams/{team_id}/sessions/{report_id}", response_model=TeamSessionDetailOut)
def team_session_route(team_id: UUID, report_id: UUID, user: User, database: DB) -> TeamSessionDetailOut:
    with database.user_transaction(user.id) as session:
        return team_session_detail(session, user.id, team_id, report_id)


@router.get("/teams/{team_id}/players", response_model=TeamPlayersOut)
def team_players_route(team_id: UUID, user: User, database: DB) -> TeamPlayersOut:
    with database.user_transaction(user.id) as session:
        return team_players(session, user.id, team_id)


@router.get("/teams/{team_id}/players/{player_id}", response_model=AnalyticsOverviewOut)
def team_player_route(team_id: UUID, player_id: UUID, user: User, database: DB) -> AnalyticsOverviewOut:
    with database.user_transaction(user.id) as session:
        _, membership = require_team(session, user.id, team_id)
        require_team_player(session, team_id, player_id)
        if membership.role == "player" and membership.player_id != player_id:
            raise AppError("player_not_found", "Player not found", 404)
        result = AnalyticsService(session, player_id, team_id=team_id).overview()
        return AnalyticsOverviewOut(
            player_id=result.player_id,
            history_fingerprint=result.history_fingerprint,
            rule_version=result.rule_version,
            facts=[_fact_out(fact) for fact in result.facts],
        )


@router.get("/teams/{team_id}/reports", response_model=TeamReportsOut)
def team_reports_route(team_id: UUID, user: User, database: DB) -> TeamReportsOut:
    with database.user_transaction(user.id) as session:
        return team_reports(session, user.id, team_id)
