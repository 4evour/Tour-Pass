"""Ticket Agent - Search and book tickets for attractions."""

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

TICKET_SYSTEM = """You are a ticket booking assistant.

Given the planned itinerary, provide ticket information for attractions.

For each attraction, provide:
1. Ticket type (entrance, combo, vip)
2. Estimated price
3. Booking tips
4. Any discounts or special notes

Output format (JSON):
{
  "tickets": [
    {
      "poi_id": "xxx",
      "poi_name": "景点名称",
      "ticket_type": "entrance",
      "price": 100,
      "booking_url": null,
      "notes": "建议提前网上预订，可享受9折优惠"
    }
  ]
}"""


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
        
        # Prepare context
        attr_list = "\n".join([
            f"- {a['name']} (ID:{a['id']}, 区域:{a['area']})"
            for a in attractions
        ])
        
        context = f"""行程中的景点:
{attr_list}

请提供每个景点的门票信息。"""
        
        runnable = self.get_runnable()
        response = await runnable.ainvoke({"context": context})
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            tickets = result.get("tickets", [])
            
            logger.info(f"Got ticket info for {len(tickets)} attractions")
            return {"tickets": tickets}
        
        except Exception as e:
            logger.error(f"Failed to parse ticket info: {e}")
            # Fallback: generate basic ticket info
            fallback = [
                {
                    "poi_id": a["id"],
                    "poi_name": a["name"],
                    "ticket_type": "entrance",
                    "price": 0,
                    "booking_url": None,
                    "notes": "请查询官方票价",
                }
                for a in attractions
            ]
            return {"tickets": fallback}
