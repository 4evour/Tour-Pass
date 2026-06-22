"""Tour Pass Multi-Agent System - Main Graph Construction.

Graph structure:

    START → node_intent → node_retrieve → node_data_gather → node_scheduler → node_reviewer
                                                ↑                                      |
                                   (poi,hotel,weather,restaurant)                      |
                                           parallel                                    |
                                                                          ┌────────────┘
                                                                          ▼ (if not passed & cycle < MAX)
                                                                     node_scheduler
                                                                          │ (passed or max cycles)
                                                                    node_ticket → node_summary → END
"""

import asyncio
import logging

from langchain_core.language_models import BaseChatModel
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

from agents.state import TourState
from agents.intent_agent import IntentAgent
from agents.retrieve_agent import RetrieveAgent
from agents.poi_agent import PoiAgent
from agents.hotel_agent import HotelAgent
from agents.weather_agent import WeatherAgent
from agents.restaurant_agent import RestaurantAgent
from agents.scheduler_agent import SchedulerAgent
from agents.reviewer_agent import ReviewerAgent
from agents.ticket_agent import TicketAgent
from agents.summary_agent import SummaryAgent

logger = logging.getLogger(__name__)

# Maximum review cycles before forcing pass
MAX_REVIEW_CYCLES = 2

# If more than this many non-critical agent errors accumulate, force-pass
# the review to prevent infinite revision loops on degraded state.
_MAX_TOLERABLE_ERRORS = 3


def _build_parallel_data_gather(
    poi_agent: PoiAgent,
    hotel_agent: HotelAgent,
    weather_agent: WeatherAgent,
    restaurant_agent: RestaurantAgent,
):
    """Build a two-phase data-gather node.

    Phase 1: Run PoiAgent first (critical, fast, deterministic).
    Phase 2: Run Hotel, Weather, Restaurant agents in parallel, with
    PoiAgent results (pois, available_pois) injected into the state they
    see — this fixes the data race where HotelAgent was reading empty pois.

    Returns merged state updates. Critical agent failures propagate;
    non-critical failures are collected as errors.
    """

    async def node_data_gather(state: TourState) -> dict:
        """Execute data-gathering agents in two phases."""
        logger.info("[DataGather] Phase 1: running PoiAgent first...")

        # ── Phase 1: POI (critical, must succeed) ────────────────────────
        try:
            poi_result = await poi_agent(state)
        except Exception as e:
            logger.critical("[DataGather] CRITICAL PoiAgent failed — aborting")
            raise

        if isinstance(poi_result, dict):
            # Inject POI results into a mutable state copy for Phase 2
            enriched_state = dict(state)
            for key, value in poi_result.items():
                if key not in ("errors", "sse_events"):
                    enriched_state[key] = value
        else:
            enriched_state = state

        # ── Phase 2: Hotel + Weather + Restaurant in parallel ───────────
        logger.info("[DataGather] Phase 2: running Hotel/Weather/Restaurant in parallel...")
        results = await asyncio.gather(
            hotel_agent(enriched_state),
            weather_agent(enriched_state),
            restaurant_agent(enriched_state),
            return_exceptions=True,
        )

        # Merge all results into a single state update
        merged: dict = {}
        errors: list[str] = []
        sse_events: list[dict] = []

        # First, merge POI result
        if isinstance(poi_result, dict):
            for key, value in poi_result.items():
                if key == "errors":
                    errors.extend(value)
                elif key == "sse_events":
                    sse_events.extend(value)
                else:
                    merged[key] = value

        agent_names = ["HotelAgent", "WeatherAgent", "RestaurantAgent"]
        for name, result in zip(agent_names, results):
            if isinstance(result, Exception):
                error_msg = f"{name}: {result}"
                logger.error("[DataGather] %s failed: %s", name, result)
                errors.append(error_msg)
                sse_events.append({
                    "type": "warning",
                    "content": f"⚠ {name} 执行失败，部分功能可能受限",
                })
            elif isinstance(result, dict):
                for key, value in result.items():
                    if key == "errors":
                        errors.extend(value)
                    elif key == "sse_events":
                        sse_events.extend(value)
                    else:
                        merged[key] = value
            else:
                logger.warning("[DataGather] Unexpected result type from %s: %s", name, type(result))

        if errors:
            merged["errors"] = errors
            merged["cumulative_error_count"] = len(errors)
        if sse_events:
            merged["sse_events"] = sse_events

        logger.info(
            "[DataGather] Completed: %d pois, %d hotels, %d weather, %d restaurants, %d errors",
            len(merged.get("pois", [])),
            1 if merged.get("selected_hotel") else 0,
            len(merged.get("weather", [])),
            len(merged.get("restaurants", [])),
            len(errors),
        )
        return merged

    return node_data_gather


def build_tour_graph(
    llm: BaseChatModel,
    data_dir: str = "data",
) -> StateGraph:
    """Build the multi-agent tour planning graph.

    Uses a parallel data-gathering node to run PoiAgent, HotelAgent,
    WeatherAgent, and RestaurantAgent concurrently via asyncio.gather,
    reducing total latency by 3-5 seconds compared to sequential execution.

    Critical agents (IntentAgent, PoiAgent, SchedulerAgent) raise
    ``RuntimeError`` on failure, which LangGraph surfaces to the API.
    Non-critical agents (Weather, Ticket, Summary) retry once and degrade.
    """
    # --- Instantiate agents (LLM only where needed) ---
    intent_agent = IntentAgent(llm)
    retrieve_agent = RetrieveAgent()              # no LLM
    poi_agent = PoiAgent(data_dir)                 # no LLM
    hotel_agent = HotelAgent(llm, data_dir)        # LLM for final selection
    weather_agent = WeatherAgent(llm)              # LLM for suggestions
    restaurant_agent = RestaurantAgent(data_dir)   # no LLM
    scheduler_agent = SchedulerAgent()             # no LLM
    reviewer_agent = ReviewerAgent(llm)            # LLM for review
    ticket_agent = TicketAgent()                   # no LLM
    summary_agent = SummaryAgent(llm)               # LLM for summary

    # Build the parallel data-gather node
    data_gather_node = _build_parallel_data_gather(
        poi_agent, hotel_agent, weather_agent, restaurant_agent,
    )

    # --- Build graph ---
    builder = StateGraph(TourState)

    builder.add_node("node_intent", intent_agent)
    builder.add_node("node_retrieve", retrieve_agent)
    builder.add_node("node_data_gather", data_gather_node)  # parallel fan-out
    builder.add_node("node_scheduler", scheduler_agent)
    builder.add_node("node_reviewer", reviewer_agent)
    builder.add_node("node_ticket", ticket_agent)
    builder.add_node("node_summary", summary_agent)

    # Linear: intent → retrieve → parallel data gather → scheduler
    builder.add_edge(START, "node_intent")
    builder.add_edge("node_intent", "node_retrieve")
    builder.add_edge("node_retrieve", "node_data_gather")
    builder.add_edge("node_data_gather", "node_scheduler")

    # Scheduler → reviewer (always)
    builder.add_edge("node_scheduler", "node_reviewer")

    # Conditional: reviewer → ticket (pass) or scheduler (revise)
    def route_review(state: TourState) -> str:
        review = state.get("review_result")
        cycle = state.get("review_cycle", 0)
        cum_errors = state.get("cumulative_error_count", 0)

        # Too many accumulated non-critical errors — force pass to prevent
        # infinite revision loops on a degraded state.
        if cum_errors >= _MAX_TOLERABLE_ERRORS:
            logger.warning(
                "Too many errors (%d >= %d), forcing pass to avoid "
                "infinite revision",
                cum_errors, _MAX_TOLERABLE_ERRORS,
            )
            return "node_ticket"

        # Reviewer crashed or never produced a result — force pass
        if review is None:
            logger.warning("No review_result (reviewer crashed?), forcing pass")
            return "node_ticket"

        if cycle >= MAX_REVIEW_CYCLES:
            logger.warning("Review cycle limit reached (%d), forcing pass", cycle)
            return "node_ticket"

        if review.get("passed"):
            return "node_ticket"

        logger.info("Review not passed (severity=%s, issues=%d), revising...",
                     review.get("severity"), len(review.get("issues", [])))
        return "node_scheduler"

    builder.add_conditional_edges(
        "node_reviewer",
        route_review,
        ["node_ticket", "node_scheduler"],
    )

    builder.add_edge("node_ticket", "node_summary")
    builder.add_edge("node_summary", END)

    graph = builder.compile(checkpointer=MemorySaver())
    logger.info("Tour planning graph built successfully (parallel data gather + MemorySaver checkpointer)")
    return graph


def create_initial_state(user_message: str, data_dir: str = "data") -> dict:
    """Create initial state from user message."""
    return {
        "user_message": user_message,
        "trip_intent": None,
        "city": "",
        "data_dir": data_dir,
        "days": 3,
        "pois": [],
        "hotels": [],
        "restaurants": [],
        "weather": [],
        "city_guides": [],
        "daily_plans": [],
        "selected_hotel": None,
        "review_result": None,
        "review_feedback": None,
        "review_cycle": 0,
        "tickets": [],
        "errors": [],
        "cumulative_error_count": 0,
        # Extended fields (migrated from single-agent pipeline)
        "available_pois": [],
        "llm_call_count": 0,
        "must_visit_coverage": [],
        "summary": "",
        "sse_events": [],
        # XHS route data (loaded by RetrieveAgent)
        "xhs_routes": [],
        "xhs_popular_pois": {},
        "xhs_reference_routes": [],
    }


def create_initial_state_from_intent(intent_dict: dict, data_dir: str = "data") -> dict:
    """Create initial state from pre-parsed structured intent.

    When the frontend sends a structured request (form-based), we skip
    the IntentAgent's regex/LLM parsing entirely by pre-populating
    ``trip_intent``. IntentAgent will see it and return {} immediately.
    """
    state = create_initial_state(
        user_message=_build_message_from_intent(intent_dict),
        data_dir=data_dir,
    )
    state["trip_intent"] = intent_dict
    state["city"] = intent_dict.get("city", "")
    state["days"] = intent_dict.get("days", 3)
    return state


def _build_message_from_intent(intent: dict) -> str:
    """Build a human-readable message from structured intent for logging."""
    parts = [f"去{intent.get('city', '')}玩{intent.get('days', 3)}天"]
    pace_map = {"relaxed": "轻松", "balanced": "适中", "intense": "紧凑"}
    if intent.get("pace") and intent["pace"] != "balanced":
        parts.append(f"节奏{pace_map.get(intent['pace'], '')}")
    strategy_map = {"culture": "文化深度", "culinary": "美食探索", "nature": "自然风光"}
    if intent.get("strategy") and intent["strategy"] != "balanced":
        parts.append(strategy_map.get(intent["strategy"], ""))
    if intent.get("must_visit"):
        parts.append(f"必去{'、'.join(intent['must_visit'][:5])}")
    if intent.get("travelers") and intent["travelers"] != "solo":
        travelers_map = {"couple": "情侣", "family": "家庭", "friends": "朋友", "elderly": "带长辈"}
        parts.append(travelers_map.get(intent["travelers"], intent["travelers"]))
    if intent.get("budget"):
        budget_map = {"budget": "经济", "mid-range": "中等", "luxury": "高端"}
        parts.append(f"预算{budget_map.get(intent['budget'], '')}")
    if intent.get("special_requests"):
        parts.append(intent["special_requests"])
    return "，".join(parts)
