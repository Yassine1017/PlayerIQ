"""Authenticated AI Analyst and creator-private chat routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, or_, select

from app.ai.orchestrator import Analyst, current_history_fingerprint, read_run, require_session, require_thread
from app.ai.provider import AIProvider
from app.api.errors import AppError
from app.core.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import Database, get_database
from app.models.tables import AiRun, ChatMessage, ChatThread
from app.schemas.ai import (
    AnalystResponse,
    GenerateAnalysis,
    MessageOut,
    MessagePage,
    SendMessage,
    ThreadCreate,
    ThreadOut,
    ThreadPage,
)
from app.services.authorization import require_player

router = APIRouter(prefix="/v1/players/{player_id}", tags=["ai-analyst"])
User = Annotated[CurrentUser, Depends(get_current_user)]
DB = Annotated[Database, Depends(get_database)]
Config = Annotated[Settings, Depends(get_settings)]


def get_ai_provider(request: Request) -> AIProvider:
    provider: AIProvider | None = getattr(request.app.state, "ai_provider", None)
    if provider is None:
        raise AppError("ai_not_configured", "AI Analyst is not configured", 503)
    return provider


Provider = Annotated[AIProvider, Depends(get_ai_provider)]


def _thread_out(value: ChatThread) -> ThreadOut:
    return ThreadOut(
        id=value.id,
        player_id=value.player_id,
        title=value.title,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


@router.post("/chats", response_model=ThreadOut, status_code=201)
def create_chat(player_id: UUID, body: ThreadCreate, user: User, database: DB) -> ThreadOut:
    with database.user_transaction(user.id) as session:
        require_player(session, user.id, player_id)
        thread = ChatThread(player_id=player_id, created_by_user_id=user.id, title=body.title or "New analysis")
        session.add(thread)
        session.flush()
        return _thread_out(thread)


@router.get("/chats", response_model=ThreadPage)
def list_chats(
    player_id: UUID,
    user: User,
    database: DB,
    limit: Annotated[int, Query(ge=1, le=30)] = 20,
    cursor: UUID | None = None,
) -> ThreadPage:
    with database.user_transaction(user.id) as session:
        require_player(session, user.id, player_id)
        query = select(ChatThread).where(ChatThread.player_id == player_id, ChatThread.created_by_user_id == user.id)
        if cursor is not None:
            marker = require_thread(session, user.id, player_id, cursor)
            query = query.where(
                or_(
                    ChatThread.created_at < marker.created_at,
                    and_(ChatThread.created_at == marker.created_at, ChatThread.id < marker.id),
                )
            )
        rows = session.scalars(
            query.order_by(ChatThread.created_at.desc(), ChatThread.id.desc()).limit(limit + 1)
        ).all()
        return ThreadPage(
            items=[_thread_out(item) for item in rows[:limit]],
            next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
        )


@router.get("/chats/{thread_id}/messages", response_model=MessagePage)
def list_messages(
    player_id: UUID,
    thread_id: UUID,
    user: User,
    database: DB,
    limit: Annotated[int, Query(ge=1, le=40)] = 30,
    cursor: UUID | None = None,
) -> MessagePage:
    with database.user_transaction(user.id) as session:
        require_thread(session, user.id, player_id, thread_id)
        query = select(ChatMessage).where(ChatMessage.thread_id == thread_id)
        if cursor is not None:
            marker = session.scalar(
                select(ChatMessage).where(ChatMessage.id == cursor, ChatMessage.thread_id == thread_id)
            )
            if marker is None:
                raise AppError("invalid_cursor", "Invalid chat cursor", 400)
            query = query.where(
                or_(
                    ChatMessage.created_at < marker.created_at,
                    and_(ChatMessage.created_at == marker.created_at, ChatMessage.id < marker.id),
                )
            )
        rows = session.scalars(
            query.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit + 1)
        ).all()
        items: list[MessageOut] = []
        current_fingerprint = (
            current_history_fingerprint(session, user.id, player_id)
            if any(item.ai_run_id for item in rows[:limit])
            else None
        )
        for item in reversed(rows[:limit]):
            run = session.get(AiRun, item.ai_run_id) if item.ai_run_id else None
            items.append(
                MessageOut(
                    id=item.id,
                    role="user" if item.role == "user" else "assistant",
                    question=str(item.content_json.get("question", "")) if item.role == "user" else None,
                    analysis=read_run(
                        session, user.id, player_id, run, thread_id=thread_id, current_fingerprint=current_fingerprint
                    )
                    if run
                    else None,
                    created_at=item.created_at,
                )
            )
        return MessagePage(items=items, next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None)


@router.post("/chats/{thread_id}/messages", response_model=AnalystResponse)
def send_message(
    player_id: UUID, thread_id: UUID, body: SendMessage, user: User, database: DB, settings: Config, provider: Provider
) -> AnalystResponse:
    return Analyst(database, provider, settings, user.id, player_id).ask(
        body.question.strip(), body.request_id, thread_id=thread_id
    )


@router.get("/sessions/{session_id}/analysis", response_model=AnalystResponse)
def get_analysis(player_id: UUID, session_id: UUID, user: User, database: DB) -> AnalystResponse:
    with database.user_transaction(user.id) as session:
        require_player(session, user.id, player_id)
        require_session(session, player_id, session_id)
        run = session.scalar(
            select(AiRun)
            .where(
                AiRun.player_id == player_id,
                AiRun.actor_user_id == user.id,
                AiRun.session_id == session_id,
                AiRun.kind == "session_analysis",
                AiRun.status != "pending",
            )
            .order_by(AiRun.created_at.desc(), AiRun.id.desc())
        )
        if run is None:
            raise AppError("analysis_not_found", "Analysis not found", 404)
        return read_run(session, user.id, player_id, run)


@router.post("/sessions/{session_id}/analysis", response_model=AnalystResponse)
def generate_analysis(
    player_id: UUID,
    session_id: UUID,
    body: GenerateAnalysis,
    user: User,
    database: DB,
    settings: Config,
    provider: Provider,
) -> AnalystResponse:
    return Analyst(database, provider, settings, user.id, player_id).ask(
        "Explain this accepted player session using its confirmed metrics and comparable history.",
        body.request_id,
        session_id=session_id,
    )
