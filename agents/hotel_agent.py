"""Hotel Agent - Search and recommend hotels with location-aware scoring.

This agent considers:
1. Proximity to planned attractions
2. Price level matching budget
3. Rating and reviews
4. Amenities
"""

import json
import logging
import math
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

HOTEL_SYSTEM = """You are a hotel recommendation expert.

Given the user's intent, POI locations, and available hotels, select the best hotel.

Consider:
1. **Location**: Hotel should be central to the planned attractions
2. **Budget**: Match user's budget level
3. **Rating**: Prioritize higher-rated hotels
4. **Amenities**: Consider user's needs

Output format (JSON):
{
  "selected_hotel": {
    "id": "hotel_id",
    "name": "酒店名称",
    "reason": "推荐理由"
  },
  "alternatives": [
    {"id": "hotel_id", "name": "酒店名称", "reason": "推荐理由"}
  ]
}"""


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    R = 6371  # Earth radius in km
    
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


def score_hotel(hotel: dict, poi_center: tuple[float, float], budget: str) -> float:
    """Score a hotel based on location and budget."""
    score = 0.0
    
    # Rating score (0-50)
    rating = hotel.get("rating", 0)
    score += rating * 10
    
    # Location score (0-30) - closer to POI center is better
    hotel_lat = hotel.get("lat", 0)
    hotel_lng = hotel.get("lng", 0)
    center_lat, center_lng = poi_center
    
    if hotel_lat and hotel_lng and center_lat and center_lng:
        distance = _haversine_km(hotel_lat, hotel_lng, center_lat, center_lng)
        # Closer is better, max 30 points for < 1km, 0 points for > 10km
        location_score = max(0, 30 - distance * 3)
        score += location_score
    
    # Budget match (0-20)
    price = hotel.get("price_per_night", 0)
    budget_ranges = {
        "budget": (0, 200),
        "mid-range": (200, 500),
        "luxury": (500, 10000),
    }
    
    low, high = budget_ranges.get(budget, (0, 10000))
    if low <= price <= high:
        score += 20
    elif price < low:
        score += 15  # Under budget is okay
    else:
        score += 5  # Over budget is penalized
    
    return score


class HotelAgent(BaseTourAgent):
    """Agent that searches and recommends hotels with location awareness."""
    
    def __init__(self, llm: BaseChatModel, data_dir: str = "data"):
        super().__init__(llm)
        self.data_dir = Path(data_dir)
    
    @property
    def name(self) -> str:
        return "HotelAgent"
    
    @property
    def description(self) -> str:
        return "Search and recommend hotels with location-aware scoring"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", HOTEL_SYSTEM),
            ("human", "{context}"),
        ])
    
    def _load_hotels(self, city: str) -> list[dict]:
        """Load hotels from local JSON file."""
        poi_file = self.data_dir / city / "pois.json"
        if not poi_file.exists():
            return []
        
        try:
            with open(poi_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                hotels = [p for p in data if p.get("type") == "hotel"]
                logger.info(f"Loaded {len(hotels)} hotels for {city}")
                return hotels
        except Exception as e:
            logger.error(f"Failed to load hotels: {e}")
            return []
    
    async def execute(self, state: TourState) -> dict:
        """Select the best hotel with location-aware scoring."""
        intent = state.get("intent", {})
        city = intent.get("city", state.get("city", ""))
        budget = intent.get("budget", "mid-range")
        pois = state.get("pois", [])
        
        if not city:
            return {"errors": state.get("errors", []) + ["No city specified"]}
        
        # Load hotels
        hotels = self._load_hotels(city)
        
        if not hotels:
            return {"errors": state.get("errors", []) + [f"No hotel data for {city}"]}
        
        # Calculate POI center for location-based recommendation
        if pois:
            valid_pois = [p for p in pois if p.get("lat") and p.get("lng")]
            if valid_pois:
                avg_lat = sum(p["lat"] for p in valid_pois) / len(valid_pois)
                avg_lng = sum(p["lng"] for p in valid_pois) / len(valid_pois)
            else:
                avg_lat, avg_lng = 0, 0
        else:
            avg_lat, avg_lng = 0, 0
        
        # Score hotels
        scored_hotels = []
        for hotel in hotels:
            score = score_hotel(hotel, (avg_lat, avg_lng), budget)
            scored_hotels.append((score, hotel))
        
        # Sort by score
        scored_hotels.sort(key=lambda x: x[0], reverse=True)
        
        # Prepare context for LLM
        hotel_list = "\n".join([
            f"- {h['name']} (ID:{h['id']}, 区域:{h.get('area', '')}, "
            f"评分:{h.get('rating', 0)}, 价格:{h.get('price_per_night', 0)}元/晚, "
            f"综合分数:{score:.1f})"
            for score, h in scored_hotels[:10]
        ])
        
        context = f"""城市: {city}
预算级别: {budget}
景点中心位置: ({avg_lat:.4f}, {avg_lng:.4f})

候选酒店 (已按位置和评分排序):
{hotel_list}

请推荐最适合的酒店。"""
        
        runnable = self.get_runnable()
        response = await runnable.ainvoke({"context": context})
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            selected = result.get("selected_hotel", {})
            
            # Find full hotel data
            hotel_map = {h["id"]: h for h in hotels}
            selected_id = selected.get("id", "")
            
            if selected_id in hotel_map:
                hotel = hotel_map[selected_id].copy()
                hotel["recommend_reason"] = selected.get("reason", "")
                return {"selected_hotel": hotel}
            
            # Fallback: highest scored hotel
            if scored_hotels:
                _, best_hotel = scored_hotels[0]
                return {"selected_hotel": best_hotel}
            
            return {"selected_hotel": hotels[0] if hotels else None}
        
        except Exception as e:
            logger.error(f"Failed to parse hotel recommendation: {e}")
            # Fallback: highest scored hotel
            if scored_hotels:
                _, best_hotel = scored_hotels[0]
                return {"selected_hotel": best_hotel}
            
            return {"selected_hotel": hotels[0] if hotels else None}
