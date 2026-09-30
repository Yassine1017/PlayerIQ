"""Stable public AI Analyst API shapes."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.ai.tools import Fact


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ThreadCreate(StrictModel):
    title: str | None = Field(default=None, max_length=120)


class ThreadOut(StrictModel):
    id: UUID
    player_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ThreadPage(StrictModel):
    items: list[ThreadOut]
    next_cursor: str | None


class SendMessage(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    request_id: UUID


class GenerateAnalysis(StrictModel):
    request_id: UUID


class AnswerSentence(StrictModel):
    text: str
    fact_ids: list[str]
    session_ids: list[UUID]


class AnalystAnswer(StrictModel):
    status: Literal["answered", "insufficient_data", "unavailable"]
    sentences: list[AnswerSentence]


class AnalystResponse(StrictModel):
    run_id: UUID
    player_id: UUID
    thread_id: UUID | None
    session_id: UUID | None
    answer: AnalystAnswer
    facts: list[Fact]
    results: list[dict[str, Any]]
    generated_at: datetime | None
    model: str
    provider: str
    prompt_version: str
    analytics_rule_version: str
    history_fingerprint: str
    stale: bool
    error_code: str | None = None


class MessageOut(StrictModel):
    id: UUID
    role: Literal["user", "assistant"]
    question: str | None
    analysis: AnalystResponse | None
    created_at: datetime


class MessagePage(StrictModel):
    items: list[MessageOut]
    next_cursor: str | None
