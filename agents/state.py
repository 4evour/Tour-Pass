"""Tour Pass Multi-Agent System - Shared State Definition."""

from typing import TypedDict, Annotated, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


class TripIntent(BaseModel):
    """Parsed user intent from natural language."""
    city: str = Field(description="Destination city")
    days: int = Field(default=3, description="Number of travel days")
    pace: Literal["relaxed", "balanced", "intense"] = Field(default="balanced", description="Travel pace")
    travelers: str = Field(default="solo", description="Traveler type")
    interests: list[str] = Field(default_factory=list, description="Interest tags")
    must_visit: list[str] = Field(default_factory=list, description="Must-visit places")
    avoid: list[str] = Field(default_factory=list, description="Places to avoid")
    budget: Optional[str] = Field(default=None, description="Budget level")
    special_requests: Optional[str] = Field(default=None, description="Special requests")


def update_dialog_stack(left: list[str], right: Optional[str]) -> list[str]:
    """Update the dialog state stack."""
    if right is None:
        return left
    if right == "pop":
        return left[:-1]
    return left + [right]


def reduce_list(left: list, right: list) -> list:
    """Combine two lists."""
    if not right:
        return left
    if not left:
        return right
    return left + right


class TourState(TypedDict):
    """Shared state for the entire tour planning workflow."""
    messages: Annotated[list[AnyMessage], add_messages]
    user_message: str
    trip_intent: Optional[dict]
    city: str
    days: int
    pois: list[dict]
    hotels: list[dict]
    restaurants: list[dict]
    weather: list[dict]
    daily_plans: list[dict]
    selected_hotel: Optional[dict]
    review_result: Optional[dict]
    tickets: list[dict]
    errors: Annotated[list[str], reduce_list]
    dialog_state: Annotated[
        list[
            Literal[
                "step_intent",
                "step_poi",
                "step_hotel",
                "step_weather",
                "step_restaurant",
                "step_scheduler",
                "step_reviewer",
                "step_ticket",
            ]
        ],
        update_dialog_stack,
    ]
