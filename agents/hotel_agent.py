"""Hotel Agent - Search and recommend hotels with location-aware scoring.

Pure deterministic agent — no LLM required.
"""

import logging
from pathlib import Path

from agents.base import BaseAgent
from agents.constants import resolve_city_dir, haversine_km, compute_center, load_pois_by_type
from agents.state import TourState

logger = logging.getLogger(__name__)


def score_hotel(hotel: dict, poi_center: tuple[float, float], budget: str | None) -> float:
    """Score a hotel based on location, rating, and budget fit."""
    score = 0.0
    rating = hotel.get("rating", 0) or 0
    score += rating * 10

    hotel_lat = hotel.get("lat", 0)
    hotel_lng = hotel.get("lng", 0)
    center_lat, center_lng = poi_center

    if hotel_lat and hotel_lng and center_lat and center_lng:
        dist = haversine_km(hotel_lat, hotel_lng, center_lat, center_lng)
        score += max(0, 30 - dist * 3)

    price = hotel.get("price_per_night", 0)
    budget_ranges = {
        "budget": (0, 200),
        "mid-range": (200, 500),
        "luxury": (500, 10000),
    }
    low, high = budget_ranges.get(budget or "mid-range", (0, 10000))
    if low <= price <= high:
        score += 20
    elif price < low:
        score += 15
    else:
        score += 5

    return score


class HotelAgent(BaseAgent):
    """Search and recommend hotels with location-aware scoring."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)

    @property
    def name(self) -> str:
        return "HotelAgent"

    @property
    def description(self) -> str:
        return "Search and recommend hotels with location-aware scoring"

    async def execute(self, state: TourState) -> dict:
        intent = state.get("trip_intent", {})
        city = intent.get("city", state.get("city", ""))
        budget = intent.get("budget", "mid-range")
        pois = state.get("pois", [])

        if not city:
            return {"selected_hotel": None, "errors": ["HotelAgent: no city specified"]}

        hotels = load_pois_by_type(self.data_dir, city, "hotel")
        if not hotels:
            return {"selected_hotel": None, "errors": [f"HotelAgent: no hotel data for {city}"]}

        poi_center = compute_center(pois)

        scored = sorted(
            [(score_hotel(h, poi_center, budget), h) for h in hotels],
            key=lambda x: x[0],
            reverse=True,
        )

        if scored:
            _, best = scored[0]
            logger.info("Selected hotel: %s (score=%.1f)", best.get("name"), scored[0][0])
            return {"selected_hotel": best}

        return {"selected_hotel": None}
