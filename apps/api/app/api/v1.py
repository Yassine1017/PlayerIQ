"""Authenticated Phase 2 HTTP surface."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.api.errors import AppError
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import Database, get_database
from app.models.tables import Player, PlayerCoach, Profile
from app.schemas.v1 import (
    ChartReviewConfirmation,
    ChartReviewOut,
    ChartReviewProposal,
    ChartReviewsOut,
    LinkOut,
    LinkRequest,
    MeOut,
    PlayerCreate,
    PlayerOut,
    PlayersOut,
    ProfileOut,
    ProfileUpdate,
    SessionOut,
    SessionsOut,
    UploadCreated,
    UploadStatusOut,
)
from app.services.authorization import require_player, require_upload
from app.services.chart_reviews import confirm_chart_value, list_chart_reviews, propose_chart_value
from app.services.linking import link_athlete_row
from app.services.reading import get_session, list_sessions, upload_status
from app.services.storage import ReportStorage, get_storage
from app.services.uploads import create_upload

router = APIRouter(prefix="/v1", tags=["v1"])
User = Annotated[CurrentUser, Depends(get_current_user)]
DB = Annotated[Database, Depends(get_database)]
Storage = Annotated[ReportStorage, Depends(get_storage)]
ConfiguredSettings = Annotated[Settings, Depends(get_settings)]


def _player_out(player: Player) -> PlayerOut:
    return PlayerOut(
        id=player.id,
        display_name=player.display_name,
        owner_user_id=player.owner_user_id,
        created_at=player.created_at,
    )


@router.get("/me", response_model=MeOut)
def me(user: User, database: DB) -> MeOut:
    with database.user_transaction(user.id) as session:
        profile = session.get(Profile, user.id)
        return MeOut(
            user_id=user.id,
            profile=(
                ProfileOut(display_name=profile.display_name, timezone=profile.timezone)
                if profile is not None
                else None
            ),
        )


@router.patch("/me", response_model=MeOut)
def update_me(body: ProfileUpdate, user: User, database: DB) -> MeOut:
    with database.user_transaction(user.id) as session:
        profile = session.get(Profile, user.id)
        if profile is None:
            profile = Profile(
                user_id=user.id,
                display_name=body.display_name or "Player",
                timezone=body.timezone or "UTC",
            )
            session.add(profile)
        else:
            if body.display_name is not None:
                profile.display_name = body.display_name
            if body.timezone is not None:
                profile.timezone = body.timezone
        session.flush()
        return MeOut(
            user_id=user.id,
            profile=ProfileOut(display_name=profile.display_name, timezone=profile.timezone),
        )


@router.post("/players", response_model=PlayerOut, status_code=201)
def create_player(body: PlayerCreate, user: User, database: DB) -> PlayerOut:
    try:
        with database.user_transaction(user.id) as session:
            if session.scalar(select(Player.id).where(Player.owner_user_id == user.id)) is not None:
                raise AppError("player_exists", "This account already owns a player profile", 409)
            player = Player(owner_user_id=user.id, display_name=body.display_name)
            session.add(player)
            session.flush()
            return _player_out(player)
    except IntegrityError as exc:
        raise AppError("player_exists", "This account already owns a player profile", 409) from exc


@router.get("/players", response_model=PlayersOut)
def list_players(user: User, database: DB) -> PlayersOut:
    with database.user_transaction(user.id) as session:
        players = session.scalars(
            select(Player)
            .outerjoin(
                PlayerCoach,
                (PlayerCoach.player_id == Player.id)
                & (PlayerCoach.coach_user_id == user.id)
                & PlayerCoach.revoked_at.is_(None),
            )
            .where(
                Player.archived_at.is_(None),
                or_(Player.owner_user_id == user.id, PlayerCoach.coach_user_id == user.id),
            )
            .distinct()
            .order_by(Player.created_at.desc())
        ).all()
        return PlayersOut(items=[_player_out(player) for player in players])


@router.get("/players/{player_id}", response_model=PlayerOut)
def player_detail(player_id: UUID, user: User, database: DB) -> PlayerOut:
    with database.user_transaction(user.id) as session:
        return _player_out(require_player(session, user.id, player_id))


@router.post("/report-uploads", response_model=UploadCreated, status_code=202)
async def upload_report(
    user: User,
    database: DB,
    storage: Storage,
    file: Annotated[UploadFile, File()],
    settings: ConfiguredSettings,
) -> UploadCreated:
    try:
        content = await file.read(settings.max_upload_bytes + 1)
        upload = create_upload(database, storage, settings, user.id, file.filename, file.content_type, content)
        return UploadCreated(upload_id=upload.id, status=upload.status)
    finally:
        await file.close()


@router.get("/report-uploads/{upload_id}", response_model=UploadStatusOut)
def report_status(upload_id: UUID, user: User, database: DB) -> UploadStatusOut:
    with database.user_transaction(user.id) as session:
        upload = require_upload(session, user.id, upload_id)
        return upload_status(session, upload)


@router.post("/report-uploads/{upload_id}/links", response_model=LinkOut)
def link_report_row(
    upload_id: UUID,
    body: LinkRequest,
    user: User,
    database: DB,
    settings: ConfiguredSettings,
) -> LinkOut:
    try:
        with database.user_transaction(user.id) as session:
            return link_athlete_row(session, user.id, upload_id, body, settings)
    except IntegrityError as exc:
        raise AppError("link_conflict", "Athlete row link conflicts with existing data", 409) from exc


@router.get("/report-uploads/{upload_id}/chart-reviews", response_model=ChartReviewsOut)
def chart_reviews(upload_id: UUID, user: User, database: DB) -> ChartReviewsOut:
    with database.user_transaction(user.id) as session:
        return list_chart_reviews(session, user.id, upload_id)


@router.post("/report-uploads/{upload_id}/chart-reviews", response_model=ChartReviewOut, status_code=201)
def propose_chart_review(upload_id: UUID, body: ChartReviewProposal, user: User, database: DB) -> ChartReviewOut:
    with database.user_transaction(user.id) as session:
        return propose_chart_value(session, user.id, upload_id, body)


@router.post("/report-uploads/{upload_id}/chart-reviews/{review_id}/confirm", response_model=ChartReviewOut)
def confirm_chart_review(
    upload_id: UUID,
    review_id: UUID,
    body: ChartReviewConfirmation,
    user: User,
    database: DB,
    settings: ConfiguredSettings,
) -> ChartReviewOut:
    with database.user_transaction(user.id) as session:
        return confirm_chart_value(session, user.id, upload_id, review_id, body, settings)


@router.get("/report-uploads/{upload_id}/file")
def download_report(upload_id: UUID, user: User, database: DB, storage: Storage) -> StreamingResponse:
    with database.user_transaction(user.id) as session:
        key = require_upload(session, user.id, upload_id).storage_key
    try:
        content = storage.get(key)
    except Exception as exc:
        raise AppError("storage_unavailable", "Private report storage is unavailable", 503) from exc
    return StreamingResponse(
        iter((content,)),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="report-{upload_id}.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/players/{player_id}/sessions", response_model=SessionsOut)
def player_sessions(
    player_id: UUID,
    user: User,
    database: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=128)] = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    session_type: Annotated[Literal["training", "match", "unknown"] | None, Query(alias="type")] = None,
) -> SessionsOut:
    with database.user_transaction(user.id) as session:
        require_player(session, user.id, player_id)
        return list_sessions(
            session,
            player_id,
            limit=limit,
            cursor=cursor,
            from_date=from_date,
            to_date=to_date,
            session_type=session_type,
        )


@router.get("/players/{player_id}/sessions/{session_id}", response_model=SessionOut)
def player_session_detail(player_id: UUID, session_id: UUID, user: User, database: DB) -> SessionOut:
    with database.user_transaction(user.id) as session:
        require_player(session, user.id, player_id)
        return get_session(session, player_id, session_id)
