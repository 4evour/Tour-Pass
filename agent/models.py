"""Pydantic data models matching C++ TourPass structures."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── User intent parsed from natural language ──────────────────────────────────

class TripIntent(BaseModel):
    """Structured intent extracted from user's natural language request."""
    city: str = Field(description="目标城市")
    days: int = Field(default=3, ge=1, le=30, description="旅行天数")
    pace: str = Field(default="标准", description="节奏: 休闲/标准/紧凑")
    budget: str = Field(default="中等", description="预算: 低/中等/高")
    travelers: str = Field(default="", description="出行人群: 老人/亲子/情侣/朋友/独自")
    interests: list[str] = Field(default_factory=list, description="兴趣偏好")
    must_visit: list[str] = Field(default_factory=list, description="必去景点名称")
    avoid: list[str] = Field(default_factory=list, description="要避开的景点/类型")
    hotel_preference: str = Field(default="", description="酒店偏好描述")
    hotel_area: str = Field(default="", description="希望住在哪个区域")
    special_requests: str = Field(default="", description="其他特殊要求")
    strategy: str = Field(default="balanced", description="策略: balanced/cultural/culinary/nature")


# ── POI and Hotel data (from C++ backend) ─────────────────────────────────────

class PoiInfo(BaseModel):
    id: str
    name: str
    type: str  # attraction, restaurant, hotel, nightlife, transit
    lat: float = 0.0
    lng: float = 0.0
    area: str = ""
    popularity: float = 0.0
    description: str = ""
    recommendation: str = ""
    tags: list[str] = Field(default_factory=list)
    meal_type: str = "main"
    open_minutes: int = 0
    close_minutes: int = 1440
    visit_duration_minutes: int = 60
    price_level: int = 1


class HotelInfo(BaseModel):
    id: str
    name: str
    area: str = ""
    lat: float = 0.0
    lng: float = 0.0
    popularity: float = 0.0
    price_level: int = 1
    description: str = ""
    tags: list[str] = Field(default_factory=list)


# ── Itinerary output ──────────────────────────────────────────────────────────

class StopInfo(BaseModel):
    slot: str = ""
    poi_id: str = ""
    poi_name: str = ""
    poi_type: str = ""
    meal_type: str = ""
    area: str = ""
    lat: float = 0.0
    lng: float = 0.0
    start_minutes: int = 0
    end_minutes: int = 0
    visit_duration_minutes: int = 0
    travel_minutes_from_previous: int = 0
    reason: str = Field(default="", description="推荐理由")
    recommendation: str = ""


class DayPlan(BaseModel):
    day: int
    stops: list[StopInfo] = Field(default_factory=list)
    total_travel_minutes: int = 0
    total_visit_minutes: int = 0
    summary: str = ""


class ItineraryResult(BaseModel):
    city: str
    days: list[DayPlan] = Field(default_factory=list)
    hotel: Optional[HotelInfo] = None
    total_score: float = 0.0
    variant_name: str = "推荐方案"
    strategy: str = "balanced"
    alternatives: list[str] = Field(default_factory=list)
    travel_tips: list[str] = Field(default_factory=list)
    summary: str = ""


# ── Agent state for LangGraph ─────────────────────────────────────────────────

class AgentState(BaseModel):
    """Mutable state passed through the LangGraph nodes."""
    user_message: str = ""
    intent: Optional[TripIntent] = None
    city_guides: list[str] = Field(default_factory=list)
    available_pois: list[PoiInfo] = Field(default_factory=list)
    available_hotels: list[HotelInfo] = Field(default_factory=list)
    selected_hotel: Optional[HotelInfo] = None
    daily_plans: list[DayPlan] = Field(default_factory=list)
    result: Optional[ItineraryResult] = None
    errors: list[str] = Field(default_factory=list)
    llm_call_count: int = 0
    stream_events: list[dict] = Field(default_factory=list)


# ── API request/response ──────────────────────────────────────────────────────

class PlanRequest(BaseModel):
    message: str = Field(description="用户自然语言需求")
    context: Optional[dict] = Field(default=None, description="前端编辑器当前状态(可选)")


class ChatRequest(BaseModel):
    message: str = Field(description="用户消息")
    itinerary: Optional[dict] = Field(default=None, description="当前完整行程")
    history: list[dict] = Field(default_factory=list, description="对话历史")


class HotItineraryItem(BaseModel):
    id: str
    city: str
    days: int
    preference: str
    itinerary: ItineraryResult
    created_at: str = ""
    hit_count: int = 0
