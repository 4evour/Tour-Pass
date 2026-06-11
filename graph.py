"""Tour Pass Multi-Agent System - Main Graph Construction.

This module builds the LangGraph workflow that orchestrates all agents.
"""

import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from agents.state import TourState
from agents.intent_agent import IntentAgent
from agents.poi_agent import PoiAgent
from agents.hotel_agent import HotelAgent
from agents.weather_agent import WeatherAgent
from agents.restaurant_agent import RestaurantAgent
from agents.scheduler_agent import SchedulerAgent
from agents.reviewer_agent import ReviewerAgent
from agents.ticket_agent import TicketAgent

logger = logging.getLogger(__name__)


def build_tour_graph(
    llm: BaseChatModel,
    data_dir: str = "data",
    checkpointer: Optional[MemorySaver] = None,
) -> StateGraph:
    """Build the multi-agent tour planning graph.
    
    Workflow:
    1. IntentAgent: Parse user intent
    2. PoiAgent + HotelAgent + WeatherAgent + RestaurantAgent: Parallel data gathering
    3. SchedulerAgent: Create itinerary
    4. ReviewerAgent: Validate constraints (loop back if failed)
    5. TicketAgent: Provide ticket info
    
    Args:
        llm: Language model for all agents.
        data_dir: Directory containing city data files.
        checkpointer: Optional checkpoint saver for state persistence.
    
    Returns:
        Compiled StateGraph.
    """
    
    # Initialize agents
    intent_agent = IntentAgent(llm)
    poi_agent = PoiAgent(llm, data_dir)
    hotel_agent = HotelAgent(llm, data_dir)
    weather_agent = WeatherAgent(llm)
    restaurant_agent = RestaurantAgent(llm, data_dir)
    scheduler_agent = SchedulerAgent(llm)
    reviewer_agent = ReviewerAgent(llm)
    ticket_agent = TicketAgent(llm)
    
    # Build graph
    builder = StateGraph(TourState)
    
    # Add nodes
    builder.add_node("intent", intent_agent)
    builder.add_node("poi", poi_agent)
    builder.add_node("hotel", hotel_agent)
    builder.add_node("weather", weather_agent)
    builder.add_node("restaurant", restaurant_agent)
    builder.add_node("scheduler", scheduler_agent)
    builder.add_node("reviewer", reviewer_agent)
    builder.add_node("ticket", ticket_agent)
    
    # Define edges
    # 1. Start -> Intent
    builder.add_edge(START, "intent")
    
    # 2. Intent -> Parallel data gathering
    builder.add_edge("intent", "poi")
    builder.add_edge("intent", "hotel")
    builder.add_edge("intent", "weather")
    builder.add_edge("intent", "restaurant")
    
    # 3. Data gathering -> Scheduler (all must complete)
    builder.add_edge("poi", "scheduler")
    builder.add_edge("hotel", "scheduler")
    builder.add_edge("weather", "scheduler")
    builder.add_edge("restaurant", "scheduler")
    
    # 4. Scheduler -> Reviewer
    builder.add_edge("scheduler", "reviewer")
    
    # 5. Reviewer -> conditional (pass -> ticket, fail -> scheduler)
    def route_review(state: TourState) -> str:
        review = state.get("review_result", {})
        if review and review.get("passed"):
            return "ticket"
        return "scheduler"
    
    builder.add_conditional_edges(
        "reviewer",
        route_review,
        ["ticket", "scheduler"]
    )
    
    # 6. Ticket -> End
    builder.add_edge("ticket", END)
    
    # Compile
    graph = builder.compile(checkpointer=checkpointer)
    
    logger.info("Tour planning graph built successfully")
    return graph


def create_initial_state(user_message: str) -> dict:
    """Create initial state from user message.
    
    Args:
        user_message: User's natural language request.
    
    Returns:
        Initial state dictionary.
    """
    return {
        "messages": [HumanMessage(content=user_message)],
        "user_message": user_message,
        "intent": None,
        "city": "",
        "days": 3,
        "pois": [],
        "hotels": [],
        "restaurants": [],
        "weather": [],
        "daily_plans": [],
        "selected_hotel": None,
        "review_result": None,
        "tickets": [],
        "errors": [],
        "dialog_state": [],
    }
