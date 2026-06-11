"""Ticket Agent - Search and book tickets for attractions."""

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

TICKET_SYSTEM = """You are a ticket booking assistant. Provide ticket information for attractions.

Output JSON with tickets array. Each ticket should have: poi_id, poi_name, ticket_type, price, notes."""


class TicketAgent(BaseTourAgent):
    """Agent that provides ticket information."""
    
    @property
    def name(self) -> str:
        return "TicketAgent"
    
    @property
    def description(self) -> str:
        return "Search and provide ticket information"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", TICKET_SYSTEM),
            ("human", "{context}"),
        ])
    
    async def execute(self, state: TourState) -> dict:
        """Provide ticket information for planned attractions."""
        daily_plans = state.get("daily_plans", [])
        
        if not daily_plans:
            return {"tickets": []}
        
        # Collect all attractions from itinerary
        attractions = []
        for day in daily_plans:
            for stop in day.get("stops", []):
                if stop.get("poi_type") == "attraction":
                    attractions.append({
                        "id": stop.get("poi_id", ""),
                        "name": stop.get("poi_name", ""),
                        "area": stop.get("area", ""),
                    })
        
        if not attractions:
            return {"tickets": []}
        
        # Generate basic ticket info
        tickets = []
        for attr in attractions:
            tickets.append({
                "poi_id": attr["id"],
                "poi_name": attr["name"],
                "ticket_type": "entrance",
                "price": 0,
                "notes": "Please check official website for pricing",
            })
        
        logger.info("Got ticket info for " + str(len(tickets)) + " attractions")
        return {"tickets": tickets}
