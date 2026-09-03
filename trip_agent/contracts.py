"""Public request and response contracts for the standalone Trip Agent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=80)


class ChatResponse(BaseModel):
    session_id: str
    run_id: str
    reply: str
    plan: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class StoredMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class SessionSummary(BaseModel):
    session_id: str
    title: str
    city: str | None = None
    created_at: str
    updated_at: str
    latest_run_id: str | None = None


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary] = Field(default_factory=list)


class SessionDetailResponse(BaseModel):
    session: SessionSummary
    messages: list[StoredMessage] = Field(default_factory=list)
    latest: ChatResponse | None = None


class StreamProgress(BaseModel):
    type: Literal["progress"] = "progress"
    event: dict[str, Any]


class StreamResult(BaseModel):
    type: Literal["result"] = "result"
    result: ChatResponse


class StreamErrorDetail(BaseModel):
    code: Literal["planning_timeout", "planning_failed"]
    message: str


class StreamError(BaseModel):
    type: Literal["error"] = "error"
    error: StreamErrorDetail
