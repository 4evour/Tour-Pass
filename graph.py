"""Tour Pass Multi-Agent System - Main Graph Construction."""

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
    """Build the multi-agent tour planning graph."""
    
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
    
    # Add nodes with prefix to avoid state key conflicts
    builder.add_node("node_intent", intent_agent)
    builder.add_node("node_poi", poi_agent)
    builder.add_node("node_hotel", hotel_agent)
    builder.add_node("node_weather", weather_agent)
    builder.add_node("node_restaurant", restaurant_agent)
    builder.add_node("node_scheduler", scheduler_agent)
    builder.add_node("node_reviewer", reviewer_agent)
    builder.add_node("node_ticket", ticket_agent)
    
    # Define edges
    builder.add_edge(START, "node_intent")
    builder.add_edge("node_intent", "node_poi")
    builder.add_edge("node_intent", "node_hotel")
    builder.add_edge("node_intent", "node_weather")
    builder.add_edge("node_intent", "node_restaurant")
    builder.add_edge("node_poi", "node_scheduler")
    builder.add_edge("node_hotel", "node_scheduler")
    builder.add_edge("node_weather", "node_scheduler")
    builder.add_edge("node_restaurant", "node_scheduler")
    builder.add_edge("node_scheduler", "node_reviewer")
    
    # Conditional edge: reviewer -> ticket or scheduler
    def route_review(state: TourState) -> str:
        review = state.get("review_result", {})
        errors = state.get("errors", [])
        
        # Count how many times we've been through the review cycle
        review_count = sum(1 for e in errors if "Schedule creation failed" in e or "review" in e.lower())
        
        # If we've tried too many times, force pass
        if review_count >= 2:
            logger.warning("Review cycle limit reached, forcing pass")
            return "node_ticket"
        
        if review and review.get("passed"):
            return "node_ticket"
        return "node_scheduler"
    
    builder.add_conditional_edges(
        "node_reviewer",
        route_review,
        ["node_ticket", "node_scheduler"]
    )
    
    builder.add_edge("node_ticket", END)
    
    # Compile with increased recursion limit
    graph = builder.compile(checkpointer=checkpointer)
    logger.info("Tour planning graph built successfully")
    return graph


def create_initial_state(user_message: str) -> dict:
    """Create initial state from user message."""
    return {
        "messages": [HumanMessage(content=user_message)],
        "user_message": user_message,
        "trip_intent": None,
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
