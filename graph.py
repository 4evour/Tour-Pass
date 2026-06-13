"""Tour Pass Multi-Agent System - Main Graph Construction.

Graph structure:

    START → node_intent → node_retrieve → ┬→ node_poi        ──┐
                                          ├→ node_hotel       ──┤
                                          ├→ node_weather     ──┼→ node_scheduler → node_reviewer
                                          └→ node_restaurant  ──┘         ↑                |
                                                                          |                |
                                                                          └────────────────┘
                                                                                (if not passed & cycle < MAX)
                                                                                      |
                                                                              node_ticket → END
"""

import logging

from langchain_core.language_models import BaseChatModel
from langgraph.constants import START, END
from langgraph.graph import StateGraph

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

logger = logging.getLogger(__name__)

# Maximum review cycles before forcing pass
MAX_REVIEW_CYCLES = 2


def build_tour_graph(
    llm: BaseChatModel,
    data_dir: str = "data",
) -> StateGraph:
    """Build the multi-agent tour planning graph.

    Only agents that actually need an LLM receive one (IntentAgent,
    WeatherAgent, ReviewerAgent).  All others are pure deterministic.
    """
    # --- Instantiate agents (LLM only where needed) ---
    intent_agent = IntentAgent(llm)
    retrieve_agent = RetrieveAgent()              # no LLM
    poi_agent = PoiAgent(data_dir)                 # no LLM
    hotel_agent = HotelAgent(data_dir)             # no LLM
    weather_agent = WeatherAgent(llm)              # LLM for suggestions
    restaurant_agent = RestaurantAgent(data_dir)   # no LLM
    scheduler_agent = SchedulerAgent()             # no LLM
    reviewer_agent = ReviewerAgent(llm)            # LLM for review
    ticket_agent = TicketAgent()                   # no LLM

    # --- Build graph ---
    builder = StateGraph(TourState)

    builder.add_node("node_intent", intent_agent)
    builder.add_node("node_retrieve", retrieve_agent)
    builder.add_node("node_poi", poi_agent)
    builder.add_node("node_hotel", hotel_agent)
    builder.add_node("node_weather", weather_agent)
    builder.add_node("node_restaurant", restaurant_agent)
    builder.add_node("node_scheduler", scheduler_agent)
    builder.add_node("node_reviewer", reviewer_agent)
    builder.add_node("node_ticket", ticket_agent)

    # Linear: intent → retrieve → fan-out
    builder.add_edge(START, "node_intent")
    builder.add_edge("node_intent", "node_retrieve")

    # Parallel data-gathering
    builder.add_edge("node_retrieve", "node_poi")
    builder.add_edge("node_retrieve", "node_hotel")
    builder.add_edge("node_retrieve", "node_weather")
    builder.add_edge("node_retrieve", "node_restaurant")

    # Converge on scheduler
    builder.add_edge("node_poi", "node_scheduler")
    builder.add_edge("node_hotel", "node_scheduler")
    builder.add_edge("node_weather", "node_scheduler")
    builder.add_edge("node_restaurant", "node_scheduler")

    # Scheduler → reviewer (always)
    builder.add_edge("node_scheduler", "node_reviewer")

    # Conditional: reviewer → ticket (pass) or scheduler (revise)
    def route_review(state: TourState) -> str:
        review = state.get("review_result")
        cycle = state.get("review_cycle", 0)

        # Reviewer crashed or never produced a result - force pass
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

    builder.add_edge("node_ticket", END)

    graph = builder.compile()
    logger.info("Tour planning graph built successfully")
    return graph


def create_initial_state(user_message: str) -> dict:
    """Create initial state from user message."""
    return {
        "user_message": user_message,
        "trip_intent": None,
        "city": "",
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
    }
