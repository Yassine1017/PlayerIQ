"""Player-scoped, idempotent AI runs with deterministic evidence and audit."""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.grounding import GroundingError, unavailable_answer, validate_answer
from app.ai.provider import AIProvider
from app.ai.tools import FactRegistry, ToolError, execute_tool, tool_schemas, validate_args
from app.analytics.domain import ANALYTICS_RULE_VERSION
from app.api.errors import AppError
from app.core.config import Settings
from app.db.session import Database
from app.models.tables import AiRun, AiToolCall, ChatMessage, ChatThread, PlayerSession
from app.repositories.analytics import HistoryLimitExceeded
from app.schemas.ai import AnalystResponse
from app.services.analytics import AnalyticsService
from app.services.authorization import require_player

logger = logging.getLogger(__name__)
PROMPT_VERSION = "analyst_v1"


def require_thread(session: Session, actor_id: UUID, player_id: UUID, thread_id: UUID) -> ChatThread:
    require_player(session, actor_id, player_id)
    thread = session.scalar(
        select(ChatThread).where(
            ChatThread.id == thread_id,
            ChatThread.player_id == player_id,
            ChatThread.created_by_user_id == actor_id,
        )
    )
    if thread is None:
        raise AppError("chat_not_found", "Chat not found", 404)
    return thread


def require_session(session: Session, player_id: UUID, session_id: UUID) -> PlayerSession:
    item = session.scalar(
        select(PlayerSession).where(
            PlayerSession.id == session_id,
            PlayerSession.player_id == player_id,
            PlayerSession.quality_state == "accepted",
        )
    )
    if item is None:
        raise AppError("session_not_found", "Accepted session not found", 404)
    return item


def _analytics(session: Session, player_id: UUID) -> AnalyticsService:
    try:
        return AnalyticsService(session, player_id)
    except HistoryLimitExceeded as exc:
        raise AppError("history_limit_exceeded", str(exc), 422) from exc


def current_history_fingerprint(session: Session, actor_id: UUID, player_id: UUID) -> str:
    require_player(session, actor_id, player_id)
    return _analytics(session, player_id).fingerprint()


def _run_out(run: AiRun, current_fingerprint: str, *, thread_id: UUID | None = None) -> AnalystResponse:
    evidence = run.evidence_snapshot or {}
    return AnalystResponse.model_validate(
        {
            "run_id": run.id,
            "player_id": run.player_id,
            "thread_id": thread_id,
            "session_id": run.session_id,
            "answer": run.response_json or unavailable_answer(),
            "facts": evidence.get("facts", []),
            "results": evidence.get("results", []),
            "generated_at": run.completed_at,
            "model": run.model,
            "provider": run.provider,
            "prompt_version": run.prompt_version,
            "analytics_rule_version": run.analytics_rule_version,
            "history_fingerprint": run.data_fingerprint,
            "stale": run.data_fingerprint != current_fingerprint,
        }
    )


def read_run(
    session: Session,
    actor_id: UUID,
    player_id: UUID,
    run: AiRun,
    *,
    thread_id: UUID | None = None,
    current_fingerprint: str | None = None,
) -> AnalystResponse:
    require_player(session, actor_id, player_id)
    if run.player_id != player_id or run.actor_user_id != actor_id:
        raise AppError("analysis_not_found", "Analysis not found", 404)
    return _run_out(
        run,
        current_fingerprint if current_fingerprint is not None else _analytics(session, player_id).fingerprint(),
        thread_id=thread_id,
    )


class Analyst:
    def __init__(
        self, database: Database, provider: AIProvider, settings: Settings, actor_id: UUID, player_id: UUID
    ) -> None:
        self.database = database
        self.provider = provider
        self.settings = settings
        self.actor_id = actor_id
        self.player_id = player_id

    def _reserve(
        self, question: str, request_id: UUID, *, thread_id: UUID | None, session_id: UUID | None
    ) -> tuple[UUID, AnalystResponse | None]:
        if not question.strip() or len(question) > self.settings.ai_max_question_length:
            raise AppError("invalid_question", "Question length is outside the supported range", 422)
        try:
            with self.database.user_transaction(self.actor_id) as session:
                require_player(session, self.actor_id, self.player_id)
                if thread_id is not None:
                    require_thread(session, self.actor_id, self.player_id, thread_id)
                if session_id is not None:
                    require_session(session, self.player_id, session_id)
                existing = session.scalar(
                    select(AiRun).where(
                        AiRun.actor_user_id == self.actor_id,
                        AiRun.player_id == self.player_id,
                        AiRun.idempotency_key == request_id,
                    )
                )
                if existing is not None:
                    if (existing.kind == "chat") != (thread_id is not None) or existing.session_id != session_id:
                        raise AppError("idempotency_conflict", "Request ID was used for another operation", 409)
                    if thread_id is not None:
                        original = session.get(ChatMessage, existing.message_id) if existing.message_id else None
                        if (
                            original is None
                            or original.thread_id != thread_id
                            or original.content_json.get("question") != question
                        ):
                            raise AppError("idempotency_conflict", "Request ID was used for another message", 409)
                    if existing.status == "pending":
                        raise AppError("analysis_in_progress", "Analysis is already in progress", 409)
                    return existing.id, read_run(session, self.actor_id, self.player_id, existing, thread_id=thread_id)
                count = (
                    session.scalar(
                        select(func.count(AiRun.id)).where(
                            AiRun.actor_user_id == self.actor_id,
                            AiRun.created_at >= datetime.now(UTC) - timedelta(days=1),
                        )
                    )
                    or 0
                )
                if count >= self.settings.ai_daily_run_limit:
                    raise AppError("ai_quota_exceeded", "Daily AI Analyst limit reached", 429)
                fingerprint = _analytics(session, self.player_id).fingerprint()
                run = AiRun(
                    player_id=self.player_id,
                    actor_user_id=self.actor_id,
                    kind="chat" if thread_id is not None else "session_analysis",
                    session_id=session_id,
                    status="pending",
                    provider=self.provider.provider_name,
                    model=self.settings.openai_model,
                    prompt_version=PROMPT_VERSION,
                    analytics_rule_version=ANALYTICS_RULE_VERSION,
                    idempotency_key=request_id,
                    data_fingerprint=fingerprint,
                    evidence_snapshot={},
                )
                session.add(run)
                session.flush()
                if thread_id is not None:
                    message = ChatMessage(
                        thread_id=thread_id,
                        role="user",
                        content_json={"question": question},
                        created_at=datetime.now(UTC),
                    )
                    session.add(message)
                    session.flush()
                    run.message_id = message.id
                return run.id, None
        except IntegrityError as exc:
            # A concurrent same-key request can only reuse the reserved run; it must not call the provider.
            raise AppError("analysis_in_progress", "Analysis is already in progress", 409) from exc

    def _context(self, thread_id: UUID | None) -> list[str]:
        if thread_id is None or self.settings.ai_max_context_messages == 0:
            return []
        with self.database.user_transaction(self.actor_id) as session:
            require_thread(session, self.actor_id, self.player_id, thread_id)
            messages = session.scalars(
                select(ChatMessage)
                .where(ChatMessage.thread_id == thread_id, ChatMessage.role == "user")
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                .limit(self.settings.ai_max_context_messages + 1)
            ).all()
            return [
                str(message.content_json.get("question", ""))[: self.settings.ai_max_question_length]
                for message in reversed(messages[1:])
            ]

    def _tool(self, run_id: UUID, call_id: str, name: str, arguments: str, registry: FactRegistry) -> dict[str, Any]:
        started = monotonic()
        status = "rejected"
        result: dict[str, Any] = {"error": "invalid_tool"}
        validated: dict[str, Any] = {"raw_length": len(arguments)}
        try:
            args = validate_args(name, arguments)
            validated = args.model_dump(mode="json")
            with self.database.user_transaction(self.actor_id) as session:
                require_player(session, self.actor_id, self.player_id)
                run = session.get(AiRun, run_id)
                if run is None or run.actor_user_id != self.actor_id:
                    raise ToolError("run_not_found")
                service = _analytics(session, self.player_id)
                if service.fingerprint() != run.data_fingerprint:
                    raise ToolError("history_changed")
                values = execute_tool(
                    name,
                    args,
                    service,
                    max_date_days=self.settings.ai_max_date_range_days,
                    max_session_results=self.settings.ai_max_session_results,
                )
                result = registry.add_result(name, values)
                status = "ok"
        except ToolError as exc:
            result = {"error": exc.code}
        except ValueError:
            result = {"error": "invalid_tool_arguments"}
        duration = max(0, int((monotonic() - started) * 1000))
        digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        with self.database.user_transaction(self.actor_id) as session:
            require_player(session, self.actor_id, self.player_id)
            session.add(
                AiToolCall(
                    ai_run_id=run_id,
                    provider_call_id=call_id[:160],
                    tool_name=name[:100],
                    arguments_json=validated,
                    result_json=result,
                    result_hash=digest,
                    status=status,
                    duration_ms=duration,
                )
            )
        logger.info("ai_tool run_id=%s tool=%s status=%s duration_ms=%s", run_id, name[:100], status, duration)
        return result

    def ask(
        self, question: str, request_id: UUID, *, thread_id: UUID | None = None, session_id: UUID | None = None
    ) -> AnalystResponse:
        run_id, cached = self._reserve(question, request_id, thread_id=thread_id, session_id=session_id)
        if cached is not None:
            return cached
        registry = FactRegistry(self.settings.ai_max_result_facts, self.settings.ai_max_session_results)
        input_tokens = output_tokens = 0
        answer = unavailable_answer()
        error_code: str | None = None
        try:
            internal_call_id = "internal_session_facts"
            if session_id is not None:
                self._tool(
                    run_id,
                    internal_call_id,
                    "get_session_facts",
                    json.dumps({"session_id": str(session_id)}),
                    registry,
                )
            turn = self.provider.select(question, self._context(thread_id), tool_schemas())
            input_tokens += turn.input_tokens or 0
            output_tokens += turn.output_tokens or 0
            outputs: list[tuple[str, str]] = []
            seen: set[str] = {internal_call_id} if session_id is not None else set()
            for index, call in enumerate(turn.calls):
                if call.call_id in seen or not call.call_id:
                    raise ToolError("duplicate_tool_call")
                seen.add(call.call_id)
                if index >= self.settings.ai_max_tool_calls:
                    result = {"error": "tool_call_limit"}
                    with self.database.user_transaction(self.actor_id) as session:
                        require_player(session, self.actor_id, self.player_id)
                        session.add(
                            AiToolCall(
                                ai_run_id=run_id,
                                provider_call_id=call.call_id[:160],
                                tool_name=call.name[:100],
                                arguments_json={"raw_length": len(call.arguments)},
                                result_json=result,
                                result_hash=hashlib.sha256(json.dumps(result).encode()).hexdigest(),
                                status="rejected",
                                duration_ms=0,
                            )
                        )
                else:
                    result = self._tool(run_id, call.call_id, call.name, call.arguments, registry)
                outputs.append((call.call_id, json.dumps(result)))
            for attempt in range(self.settings.ai_max_provider_attempts):
                feedback = (
                    "Previous answer failed grounding validation. Use only cited facts and no numbers in text."
                    if attempt
                    else None
                )
                try:
                    proposal = self.provider.answer(question, turn, outputs, registry.snapshot(), feedback)
                    input_tokens += proposal.input_tokens or 0
                    output_tokens += proposal.output_tokens or 0
                    grounded = validate_answer(proposal.payload, registry)
                    answer = grounded.model_dump(mode="json")
                    break
                except GroundingError as exc:
                    error_code = exc.code
                except ValueError:
                    error_code = "invalid_provider_answer"
            else:
                error_code = error_code or "invalid_provider_answer"
        except ToolError as exc:
            error_code = exc.code
        except Exception as exc:
            # Provider exceptions are deliberately not exposed or logged with prompt/key content.
            error_code = "provider_unavailable"
            logger.warning("ai_provider_failure run_id=%s type=%s", run_id, type(exc).__name__)
        if len(json.dumps(answer)) > self.settings.ai_max_response_length:
            answer = unavailable_answer()
            error_code = "response_too_large"
        with self.database.user_transaction(self.actor_id) as session:
            require_player(session, self.actor_id, self.player_id)
            if thread_id is not None:
                require_thread(session, self.actor_id, self.player_id, thread_id)
            run = session.get(AiRun, run_id)
            assert run is not None
            current = _analytics(session, self.player_id).fingerprint()
            if current != run.data_fingerprint:
                answer = unavailable_answer()
                error_code = "history_changed"
            run.status = "completed" if answer["status"] != "unavailable" else "unavailable"
            run.error_code = error_code
            run.response_json = answer
            run.evidence_snapshot = registry.snapshot()
            run.input_tokens = input_tokens or None
            run.output_tokens = output_tokens or None
            run.completed_at = datetime.now(UTC)
            if thread_id is not None:
                session.add(
                    ChatMessage(
                        thread_id=thread_id,
                        role="assistant",
                        content_json={"run_id": str(run.id)},
                        ai_run_id=run.id,
                        created_at=datetime.now(UTC),
                    )
                )
            session.flush()
            return _run_out(run, current, thread_id=thread_id)
