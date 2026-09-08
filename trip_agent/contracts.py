"""Public request and response contracts for the standalone Trip Agent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TripDateRange(BaseModel):
    start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class DailyWindow(BaseModel):
    start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    end: str = Field(default="20:00", pattern=r"^\d{2}:\d{2}$")


class StructuredTripRequest(BaseModel):
    destination: str = Field(min_length=1, max_length=40)
    days: int = Field(default=3, ge=1, le=7)
    date_range: TripDateRange = Field(default_factory=TripDateRange)
    hotel_area: str = Field(default="", max_length=80)
    travellers: str = Field(default="", max_length=40)
    pace: Literal["relaxed", "balanced", "intensive"] = "balanced"
    transport_preference: Literal[
        "public_transit", "taxi", "walking", "driving", "mixed"
    ] = "mixed"
    budget: Literal["", "经济", "适中", "品质"] = ""
    must_visits: list[str] = Field(default_factory=list, max_length=12)
    notes: str = Field(default="", max_length=500)
    interests: list[str] = Field(default_factory=list, max_length=12)
    daily_window: DailyWindow = Field(default_factory=DailyWindow)

    @model_validator(mode="after")
    def validate_daily_window(self) -> "StructuredTripRequest":
        start_hour, start_minute = (
            int(value) for value in self.daily_window.start.split(":")
        )
        end_hour, end_minute = (
            int(value) for value in self.daily_window.end.split(":")
        )
        start = start_hour * 60 + start_minute
        end = end_hour * 60 + end_minute
        if (
            start_hour > 23
            or end_hour > 23
            or start_minute > 59
            or end_minute > 59
            or start >= end
        ):
            raise ValueError("每日游玩结束时间必须晚于开始时间")
        self.must_visits = list(
            dict.fromkeys(value.strip() for value in self.must_visits if value.strip())
        )
        self.interests = list(
            dict.fromkeys(value.strip() for value in self.interests if value.strip())
        )
        return self


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    trip: StructuredTripRequest | None = None
    session_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def require_input(self) -> "ChatRequest":
        self.message = self.message.strip()
        if not self.message and self.trip is None:
            raise ValueError("message 或 trip 至少提供一项")
        return self


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
