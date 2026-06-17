"""Ticket Agent - Provide ticket information from POI data.

Pure deterministic agent — no LLM required.
"""

import logging

from agents.base import BaseAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

PRICE_LEVEL_MAP = {
    0: "免费",
    1: "0-50元",
    2: "50-100元",
    3: "100-200元",
    4: "200-500元",
    5: "500元以上",
}


class TicketAgent(BaseAgent):
    """Provide ticket information for planned attractions."""

    @property
    def name(self) -> str:
        return "TicketAgent"

    @property
    def description(self) -> str:
        return "Provide ticket information from POI data"

    async def execute(self, state: TourState) -> dict:
        daily_plans = state.get("daily_plans", [])
        pois = state.get("pois", [])

        if not daily_plans:
            return {"tickets": []}

        # Build POI lookup
        poi_lookup = {p.get("name", ""): p for p in pois if p.get("name")}

        # Collect unique attractions from itinerary
        seen_ids: set[str] = set()
        attractions: list[dict] = []
        for day in daily_plans:
            for stop in day.get("stops", []):
                pid = stop.get("poi_id", "")
                if stop.get("poi_type") == "attraction" and pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    attractions.append(stop)

        if not attractions:
            return {"tickets": []}

        tickets: list[dict] = []
        for attr in attractions:
            poi_name = attr.get("poi_name", "")
            poi_data = poi_lookup.get(poi_name, {})

            price_level = poi_data.get("price_level", 0)
            price_estimate = PRICE_LEVEL_MAP.get(price_level, "未知")

            # Build booking tip
            tip = poi_data.get("recommendation", "") or poi_data.get("description", "")[:80]
            open_time = poi_data.get("open_time", "")
            close_time = poi_data.get("close_time", "")
            if open_time and close_time:
                tip += f" 开放时间: {open_time}-{close_time}"

            tickets.append({
                "poi_id": attr.get("poi_id", ""),
                "poi_name": poi_name,
                "ticket_type": "entrance",
                "price_estimate": price_estimate,
                "price_level": price_level,
                "booking_tip": tip.strip(),
            })

        logger.info("Got ticket info for %d attractions", len(tickets))
        return {
            "tickets": tickets,
            "sse_events": [{
                "type": "tickets_loaded",
                "content": f"已生成 {len(tickets)} 张门票信息",
            }],
        }
