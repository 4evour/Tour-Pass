"""Tour Pass Multi-Agent System - Shared State Definition.

Extended with fields from the legacy single-agent pipeline (agent/models.py)
to support must-visit guarantees, hotel budget filtering, SSE streaming,
LLM call governance, and itinerary summary/coverage reporting.
"""

from typing import TypedDict, Annotated, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


class TripIntent(BaseModel):
    """Parsed user intent from natural language.

    Extended with hotel budget/area/strategy fields migrated from
    agent/models.py TripIntent so that HotelAgent can perform
    budget and brand filtering.
    """
    city: str = Field(description="Destination city")
    days: int = Field(default=3, description="Number of travel days")
    pace: Literal["relaxed", "balanced", "intense"] = Field(
        default="balanced", description="Travel pace",
    )
    travelers: str = Field(default="solo", description="Traveler type")
    interests: list[str] = Field(default_factory=list, description="Interest tags")
    must_visit: list[str] = Field(default_factory=list, description="Must-visit places")
    avoid: list[str] = Field(default_factory=list, description="Places to avoid")
    budget: Optional[str] = Field(default=None, description="Budget level: budget|mid-range|luxury")
    special_requests: Optional[str] = Field(default=None, description="Special requests")

    # ── Fields migrated from agent/models.py ────────────────────────────────
    hotel_preference: str = Field(default="", description="Hotel preference description")
    hotel_area: str = Field(default="", description="Preferred hotel area/district")
    hotel_budget_min: int = Field(
        default=0, description="Min nightly hotel budget (CNY); 0 = no limit",
    )
    hotel_budget_max: int = Field(
        default=0, description="Max nightly hotel budget (CNY); 0 = no limit",
    )
    strategy: str = Field(
        default="balanced",
        description="Planning strategy: balanced|culture|culinary|nature",
    )

    # ── Validators ──────────────────────────────────────────────────────────
    @field_validator("must_visit", "avoid", "interests", mode="before")
    @classmethod
    def coerce_str_to_list(cls, v):
        """LLM may return an empty string instead of an empty list."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [v.strip()]
        return v

    @field_validator("days", "hotel_budget_min", "hotel_budget_max", mode="before")
    @classmethod
    def coerce_int_fields(cls, v):
        """LLM may return string numbers; coerce them."""
        if isinstance(v, str):
            import re
            m = re.search(r"\d+", v)
            return int(m.group()) if m else 0
        return v


class ReviewFeedback(BaseModel):
    """Structured review feedback passed from Reviewer to Scheduler."""
    passed: bool = True
    issues: list[dict] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    missing_must_visit: list[str] = Field(default_factory=list)
    severity: str = "none"


# ── Reducer helpers ──────────────────────────────────────────────────────────

def update_dialog_stack(left: list[str], right: Optional[str]) -> list[str]:
    """Update the dialog state stack."""
    if right is None:
        return left
    if right == "pop":
        return left[:-1]
    return left + [right]


def reduce_list(left: list, right: list) -> list:
    """Combine two lists (used for sse_events accumulation)."""
    if not right:
        return left
    if not left:
        return right
    return left + right


def replace_list(left: list, right: list) -> list:
    """Replace left with right (for errors that should reset each cycle)."""
    return right if right else left


def replace_int(left: int, right: int) -> int:
    """Replace left int with right (used for llm_call_count)."""
    return right if right else left


def accumulate_int(left: int, right: int) -> int:
    """Accumulate int values (used for cumulative_error_count)."""
    return left + (right or 0)


def replace_str(left: str, right: str) -> str:
    """Replace left string with right (used for summary)."""
    return right if right else left


# ── Shared workflow state ─────────────────────────────────────────────────────

class TourState(TypedDict):
    """Shared state for the entire tour planning workflow.

    Extended fields (migrated from single-agent pipeline):
    - available_pois: full POI list for must-visit rescue in clustering
    - llm_call_count: guard against excessive LLM usage per request
    - must_visit_coverage: per-attraction coverage report after planning
    - summary: LLM-generated itinerary summary text
    - sse_events: fine-grained SSE events accumulated by each agent
    """
    messages: Annotated[list[AnyMessage], add_messages]
    user_message: str
    trip_intent: Optional[dict]
    city: str
    days: int
    pois: list[dict]
    hotels: list[dict]
    restaurants: list[dict]
    weather: list[dict]
    city_guides: list[str]
    daily_plans: list[dict]
    selected_hotel: Optional[dict]
    review_result: Optional[dict]
    review_feedback: Optional[dict]
    review_cycle: int
    tickets: list[dict]
    errors: Annotated[list[str], replace_list]
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
                "step_summary",
            ]
        ],
        update_dialog_stack,
    ]

    # ── Extended fields migrated from single-agent pipeline ──────────────────
    # Full POI list retained for must-visit rescue during clustering
    available_pois: list[dict]
    # LLM call counter — capped by MAX_LLM_CALLS_PER_REQUEST
    llm_call_count: Annotated[int, replace_int]
    # Per-attraction must-visit coverage report (produced by SchedulerAgent)
    must_visit_coverage: list[dict]
    # LLM-generated itinerary summary (produced by SummaryAgent)
    summary: Annotated[str, replace_str]
    # Cumulative non-critical error counter — only increases, never resets
    cumulative_error_count: Annotated[int, accumulate_int]
    # Fine-grained SSE events appended by each agent during execution
    sse_events: Annotated[list[dict], reduce_list]
    # Data root used by agents for POIs, route edges, and generated image files
    data_dir: str

    # ── XHS (小红书) route data fields ────────────────────────────────────
    # Raw XHS route data loaded from data/{city}/xhs_routes.json
    xhs_routes: list[dict]
    # POI name → occurrence frequency across XHS routes
    xhs_popular_pois: dict[str, int]
    # Selected high-signal XHS route summaries for scheduling context
    xhs_reference_routes: list[dict]
