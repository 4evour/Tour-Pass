"""Public request and response contracts for the standalone Trip Agent."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TripDateRange(BaseModel):
    start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class DailyWindow(BaseModel):
    start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    end: str = Field(default="20:00", pattern=r"^\d{2}:\d{2}$")


class TripEndpoint(BaseModel):
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    period: Literal["", "morning", "afternoon", "evening", "late_night"] = ""
    city: str = Field(default="", max_length=40)
    station: str = Field(default="", max_length=80)


class DestinationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    days: int | None = Field(default=None, ge=1)
    nights: int | None = Field(default=None, ge=0)
    must_visits: list[str] = Field(default_factory=list, max_length=30)
    notes: str = Field(default="", max_length=1000)


class PartyRequest(BaseModel):
    adults: int = Field(default=1, ge=0, le=30)
    children_ages: list[int] = Field(default_factory=list, max_length=20)
    seniors: int = Field(default=0, ge=0, le=20)
    rooms: int | None = Field(default=None, ge=1, le=20)
    bed_requirement: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def require_traveller(self) -> "PartyRequest":
        if self.adults + len(self.children_ages) + self.seniors < 1:
            raise ValueError("同行人数至少为 1")
        if any(age < 0 or age > 17 for age in self.children_ages):
            raise ValueError("儿童年龄必须在 0 至 17 岁之间")
        return self


class BudgetRange(BaseModel):
    total_min: int | None = Field(default=None, ge=0)
    total_max: int | None = Field(default=None, ge=0)
    per_person: int | None = Field(default=None, ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    includes_major_transport: bool | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "BudgetRange":
        if (
            self.total_min is not None
            and self.total_max is not None
            and self.total_min > self.total_max
        ):
            raise ValueError("预算下限不能高于预算上限")
        return self


class StructuredTripRequest(BaseModel):
    destination: str = Field(min_length=1, max_length=160)
    destinations: list[DestinationRequest] = Field(default_factory=list)
    days: int | None = Field(default=None, ge=1)
    nights: int | None = Field(default=None, ge=0)
    date_range: TripDateRange = Field(default_factory=TripDateRange)
    arrival: TripEndpoint | None = None
    departure: TripEndpoint | None = None
    hotel_area: str = Field(default="", max_length=160)
    hotel_preferences: str = Field(default="", max_length=1000)
    travellers: str = Field(default="", max_length=160)
    party: PartyRequest | None = None
    pace: Literal["relaxed", "balanced", "intensive"] = "balanced"
    transport_preference: Literal[
        "public_transit", "taxi", "walking", "driving", "mixed"
    ] = "mixed"
    intercity_preferences: list[str] = Field(default_factory=list)
    budget: Literal["", "经济", "适中", "品质"] = ""
    budget_range: BudgetRange | None = None
    must_visits: list[str] = Field(default_factory=list, max_length=60)
    notes: str = Field(default="", max_length=4000)
    interests: list[str] = Field(default_factory=list, max_length=30)
    dietary_requirements: list[str] = Field(default_factory=list, max_length=20)
    mobility_needs: list[str] = Field(default_factory=list, max_length=20)
    booking_preferences: str = Field(default="", max_length=1000)
    daily_window: DailyWindow = Field(default_factory=DailyWindow)

    @model_validator(mode="after")
    def validate_trip(self) -> "StructuredTripRequest":
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
        if self.date_range.start and self.date_range.end:
            start_date = date.fromisoformat(self.date_range.start)
            end_date = date.fromisoformat(self.date_range.end)
            if end_date < start_date:
                raise ValueError("返程日期不能早于出发日期")
            range_days = (end_date - start_date).days + 1
            if self.days is not None and range_days != self.days:
                raise ValueError("日期范围包含的自然日必须等于总游玩天数")
            if self.days is None:
                self.days = range_days
        for label, endpoint in (("抵达", self.arrival), ("返程", self.departure)):
            if endpoint and endpoint.time:
                hour, minute = (int(value) for value in endpoint.time.split(":"))
                if hour > 23 or minute > 59:
                    raise ValueError(f"{label}时间无效")
            if (
                endpoint
                and endpoint.date
                and self.date_range.start
                and endpoint.date < self.date_range.start
            ):
                raise ValueError(f"{label}日期不能早于行程开始日期")
            if (
                endpoint
                and endpoint.date
                and self.date_range.end
                and endpoint.date > self.date_range.end
            ):
                raise ValueError(f"{label}日期不能晚于行程结束日期")
        if self.days is not None and self.nights is None:
            self.nights = self.days - 1
        if self.destinations:
            specified_days = [item.days for item in self.destinations]
            if any(value is None for value in specified_days) and any(
                value is not None for value in specified_days
            ):
                raise ValueError("各目的地天数必须全部填写或全部留空")
            names = [item.name for item in self.destinations]
            self.destination = "、".join(dict.fromkeys(names))
            stated_days = sum(item.days or 0 for item in self.destinations)
            if self.days is None and stated_days:
                self.days = stated_days
                self.nights = self.days - 1 if self.nights is None else self.nights
            elif stated_days and stated_days != self.days:
                raise ValueError("各目的地天数之和必须等于总游玩天数")
        for field_name in (
            "must_visits",
            "interests",
            "intercity_preferences",
            "dietary_requirements",
            "mobility_needs",
        ):
            values = getattr(self, field_name)
            setattr(
                self,
                field_name,
                list(dict.fromkeys(value.strip() for value in values if value.strip())),
            )
        return self


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=12000)
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
    code: Literal["planning_timeout", "planning_service_unavailable", "planning_failed"]
    message: str


class StreamError(BaseModel):
    type: Literal["error"] = "error"
    error: StreamErrorDetail
