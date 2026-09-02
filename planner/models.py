"""Grounded Planner public contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DailyWindow(StrictModel):
    start: str = "09:00"
    end: str = "21:30"

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("time must use HH:MM")
        hour, minute = (int(part) for part in parts)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("time must use HH:MM")
        return f"{hour:02d}:{minute:02d}"


class HotelPreference(StrictModel):
    name: str = ""
    area: str = ""
    required_anchor: bool = True


class ConstraintProfile(StrictModel):
    reserve_lunch_minutes: int = Field(default=60, ge=0, le=120)
    lunch_start_minutes: int = Field(default=12 * 60, ge=0, le=24 * 60)
    prefer_low_walking: bool = False
    max_stops_per_day: int | None = Field(default=None, ge=1, le=8)
    freeform_requirements: list[str] = Field(default_factory=list)


class TripContext(StrictModel):
    request_id: str
    planning_run_id: str
    city: str
    date_start: date
    days: int = Field(ge=1, le=7)
    timezone: str = "Asia/Shanghai"
    daily_window: DailyWindow = Field(default_factory=DailyWindow)
    hotel: HotelPreference = Field(default_factory=HotelPreference)
    travelers: str = "solo"
    pace: Literal["relaxed", "balanced", "intense"] = "balanced"
    strategy: Literal["balanced", "culture", "culinary", "nature"] = "balanced"
    interests: list[str] = Field(default_factory=list)
    must_visit: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    budget_level: str | None = None
    transport_mode: Literal["driving", "walking", "transit"] = "driving"
    special_requests: str = ""
    constraints: ConstraintProfile = Field(default_factory=ConstraintProfile)
    assumptions: list[str] = Field(default_factory=list)


class PlaceQuery(StrictModel):
    query: str = Field(min_length=1, max_length=80)
    role: str = "attraction"
    preferred_period: Literal["morning", "afternoon", "evening", "any"] = "any"
    required: bool = False


class SkeletonDay(StrictModel):
    day: int = Field(ge=1, le=7)
    theme: str = Field(default="城市探索", max_length=80)
    area_sequence: list[str] = Field(default_factory=list, max_length=6)
    place_queries: list[PlaceQuery] = Field(default_factory=list, max_length=6)
    experience_notes: list[str] = Field(default_factory=list, max_length=6)


class PlanSkeleton(StrictModel):
    days: list[SkeletonDay]


class OpenWindow(StrictModel):
    start: str
    end: str


class PlaceEvidence(StrictModel):
    query: str
    entity_id: str
    local_id: str = ""
    source_id: str = ""
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    category: str = "attraction"
    role: str = "attraction"
    lat: float
    lng: float
    area: str = ""
    status: Literal["resolved", "ambiguous", "unresolved", "closed", "unknown"] = (
        "resolved"
    )
    open_status: Literal["verified", "unknown", "closed"] = "unknown"
    open_windows: list[OpenWindow] = Field(default_factory=list)
    visit_duration_minutes: int = Field(default=90, ge=15, le=480)
    popularity: float = Field(default=0, ge=0, le=10)
    tags: list[str] = Field(default_factory=list)
    provider: str
    retrieved_at: datetime
    valid_until: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    image_url: str = ""


class RouteEvidence(StrictModel):
    from_entity_id: str
    to_entity_id: str
    mode: Literal["driving", "walking", "transit"]
    duration_minutes: int = Field(gt=0)
    distance_meters: int = Field(ge=0)
    provider: str
    retrieved_at: datetime
    confidence: Literal["verified", "estimated"]
    cache_status: Literal["hit", "miss"] = "miss"


class WeatherDay(StrictModel):
    date: str
    condition: str = ""
    condition_night: str = ""
    temperature_high: int | None = None
    temperature_low: int | None = None
    humidity: int | None = None
    sunrise: str = ""
    sunset: str = ""
    uv_index: int = 0
    precip: float = 0
    suggestion: str = ""
    warnings: list[dict] = Field(default_factory=list)
    provider: Literal["qweather", "amap", "unavailable"] = "unavailable"


class PlannedStop(StrictModel):
    entity_id: str
    local_id: str = ""
    poi_name: str
    poi_type: str
    role: str
    area: str = ""
    lat: float
    lng: float
    slot: str
    start_minutes: int
    end_minutes: int
    visit_duration_minutes: int
    reason: str
    open_status: str
    evidence_provider: str
    image_url: str = ""
    travel_minutes_from_previous: int = 0
    distance_meters_from_previous: int = 0
    route_source: str = ""
    transport_hint: str = ""


class PlannedDay(StrictModel):
    day: int
    date: str
    theme: str
    start_anchor: str
    end_anchor: str
    stops: list[PlannedStop]
    route_segments: list[dict]
    total_travel_minutes: int
    total_visit_minutes: int
    summary: str
    weather: WeatherDay | None = None
    warnings: list[str] = Field(default_factory=list)


class ItineraryPlan(StrictModel):
    plan_id: str
    version: int = 1
    city: str
    planning_run_id: str
    hotel_anchor: PlaceEvidence
    days: list[PlannedDay]
    evidence_snapshot_id: str
    warnings: list[str] = Field(default_factory=list)


class ValidationIssue(StrictModel):
    code: str
    message: str
    repairable: bool = False
    day: int | None = None
    entity_id: str = ""


class ValidationReport(StrictModel):
    passed: bool
    hard_failures: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    soft_scores: dict[str, float] = Field(default_factory=dict)


class PlanningResult(StrictModel):
    success: bool
    planning_run_id: str
    itinerary: ItineraryPlan | None = None
    validation: ValidationReport
    trace: list[dict] = Field(default_factory=list)
    error: str | None = None
