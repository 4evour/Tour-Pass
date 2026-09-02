"""Public request and response contracts for the standalone Trip Agent."""

from __future__ import annotations

from typing import Any

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
