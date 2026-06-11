"""Tour Pass Multi-Agent System - Shared State Definition.

This module defines the shared state that flows between all agents
in the LangGraph workflow.
"""

from typing import TypedDict, Annotated, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


# ──────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────

class TripIntent(BaseModel):
    """Parsed user intent from natural language."""
    city: str = Field(description="Destination city")
    days: int = Field(default=3, description="Number of travel days")
    pace: Literal["relaxed", "balanced", "intense"] = Field(
        default="balanced", description="Travel pace"
    )
    travelers: str = Field(default="solo", description="Traveler type")
    interests: list[str] = Field(default_factory=list, description="Interest tags")
    must_visit: list[str] = Field(default_factory=list, description="Must-visit places")
    avoid: list[str] = Field(default_factory=list, description="Places to avoid")
    budget: Optional[str] = Field(default=None, description="Budget level")
    special_requests: Optional[str] = Field(default=None, description="Special requests")


class PoiInfo(BaseModel):
    """Point of Interest information."""
    id: str
    name: str
    type: Literal["attraction", "restaurant", "hotel", "nightlife", "transit"]
    area: str = ""
    lat: float = 0.0
    lng: float = 0.0
    popularity: float = 0.0
    visit_duration_minutes: int = 60
    tags: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    price_level: int = 1
    open_hours: Optional[str] = None
    recommendation: Optional[str] = None


class HotelInfo(BaseModel):
    """Hotel information."""
    id: str
    name: str
    area: str = ""
    lat: float = 0.0
    lng: float = 0.0
    price_per_night: float = 0.0
    rating: float = 0.0
    tags: list[str] = Field(default_factory=list)
    amenities: list[str] = Field(default_factory=list)


class RestaurantInfo(BaseModel):
    """Restaurant information (from Dianping/Douyin)."""
    id: str
    name: str
    area: str = ""
    lat: float = 0.0
    lng: float = 0.0
    cuisine: str = ""  # Cuisine type (e.g., Sichuan, Cantonese, Japanese)
    avg_price: float = 0.0  # Average price per person
    rating: float = 0.0  # Rating (Dianping score)
    douyin_deal: Optional[dict] = None  # Douyin group deal info
    tags: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    open_hours: Optional[str] = None


class WeatherInfo(BaseModel):
    """Weather forecast information."""
    city: str
    date: str
    temperature_high: float
    temperature_low: float
    condition: str  # Sunny, Cloudy, Rainy, etc.
    humidity: float = 0.0
    wind_speed: float = 0.0
    suggestion: str = ""  # Clothing/activity suggestions


class StopInfo(BaseModel):
    """A stop in the itinerary."""
    slot: Literal["morning", "afternoon", "evening", "lunch", "dinner"]
    poi_id: str
    poi_name: str
    poi_type: str = "attraction"
    area: str = ""
    lat: float = 0.0
    lng: float = 0.0
    start_minutes: int = 0  # Minutes from midnight
    end_minutes: int = 0
    visit_duration_minutes: int = 60
    reason: str = ""
    recommendation: Optional[str] = None


class DayPlan(BaseModel):
    """Plan for a single day."""
    day: int
    stops: list[StopInfo] = Field(default_factory=list)
    total_travel_minutes: int = 0
    total_visit_minutes: int = 0
    summary: str = ""
    theme: str = ""


class ReviewResult(BaseModel):
    """Result from the reviewer agent."""
    passed: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    missing_must_visit: list[str] = Field(default_factory=list)


class TicketInfo(BaseModel):
    """Ticket/reservation information."""
    poi_id: str
    poi_name: str
    ticket_type: str = ""  # e.g., "entrance", "combo", "vip"
    price: float = 0.0
    booking_url: Optional[str] = None
    notes: Optional[str] = None


# ──────────────────────────────────────────────
# Dialog Stack Management
# ──────────────────────────────────────────────

def update_dialog_stack(left: list[str], right: Optional[str]) -> list[str]:
    """Update the dialog state stack.
    
    Args:
        left: Current state stack.
        right: New state to push, or 'pop' to remove top, or None to keep.
    
    Returns:
        Updated state stack.
    """
    if right is None:
        return left
    if right == "pop":
        return left[:-1]
    return left + [right]


# ──────────────────────────────────────────────
# Shared State
# ──────────────────────────────────────────────

class TourState(TypedDict):
    """Shared state for the entire tour planning workflow."""
    # Message history
    messages: Annotated[list[AnyMessage], add_messages]
    
    # User input
    user_message: str
    
    # Parsed intent
    intent: Optional[TripIntent]
    
    # City info
    city: str
    days: int
    
    # Data collected by agents
    pois: list[dict]  # Candidate POIs
    hotels: list[dict]  # Candidate hotels
    restaurants: list[dict]  # Candidate restaurants
    weather: list[dict]  # Weather forecast for each day
    
    # Planning results
    daily_plans: list[dict]  # Day-by-day itinerary
    selected_hotel: Optional[dict]
    
    # Review
    review_result: Optional[dict]
    
    # Tickets
    tickets: list[dict]
    
    # Error tracking
    errors: list[str]
    
    # Dialog state stack (for agent routing)
    dialog_state: Annotated[
        list[
            Literal[
                "intent",
                "poi",
                "hotel",
                "weather",
                "restaurant",
                "scheduler",
                "reviewer",
                "ticket",
            ]
        ],
        update_dialog_stack,
    ]
