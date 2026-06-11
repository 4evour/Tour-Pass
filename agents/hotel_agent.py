"""Hotel Agent - Search and recommend hotels with location-aware scoring."""

import json
import logging
import math
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

# City name to directory mapping
CITY_DIR_MAP = {
    "广州": "guangzhou",
    "北京": "beijing",
    "上海": "shanghai",
    "深圳": "shenzhen",
    "成都": "chengdu",
    "重庆": "chongqing",
    "杭州": "hangzhou",
    "武汉": "wuhan",
    "南京": "nanjing",
    "西安": "xian",
    "长沙": "changsha",
    "昆明": "kunming",
    "大理": "dali",
    "丽江": "lijiang",
    "三亚": "sanya",
    "桂林": "guilin",
    "厦门": "xiamen",
    "青岛": "qingdao",
    "哈尔滨": "harbin",
    "苏州": "suzhou",
    "张家界": "zhangjiajie",
}

HOTEL_SYSTEM = """You are a hotel recommendation expert.

Given the user's intent, POI locations, and available hotels, select the best hotel.

Output format (JSON):
```json
{
  "selected_hotel": {
    "id": "hotel_id",
    "name": "hotel name",
    "reason": "recommendation reason"
  }
}
```"""


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    R = 6371
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def score_hotel(hotel: dict, poi_center: tuple, budget: str) -> float:
    """Score a hotel based on location and budget."""
    score = 0.0
    rating = hotel.get("rating", 0)
    score += rating * 10
    
    hotel_lat = hotel.get("lat", 0)
    hotel_lng = hotel.get("lng", 0)
    center_lat, center_lng = poi_center
    
    if hotel_lat and hotel_lng and center_lat and center_lng:
        distance = _haversine_km(hotel_lat, hotel_lng, center_lat, center_lng)
        location_score = max(0, 30 - distance * 3)
        score += location_score
    
    price = hotel.get("price_per_night", 0)
    budget_ranges = {"budget": (0, 200), "mid-range": (200, 500), "luxury": (500, 10000)}
    low, high = budget_ranges.get(budget, (0, 10000))
    if low <= price <= high:
        score += 20
    elif price < low:
        score += 15
    else:
        score += 5
    
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
    
    def _get_city_dir(self, city: str) -> str:
        """Get directory name for city."""
        if (self.data_dir / city).exists():
            return city
        if city in CITY_DIR_MAP:
            return CITY_DIR_MAP[city]
        return city.lower()
    
    def _load_hotels(self, city: str) -> list[dict]:
        """Load hotels from local JSON file."""
        city_dir = self._get_city_dir(city)
        poi_file = self.data_dir / city_dir / "pois.json"
        
        if not poi_file.exists():
            return []
        try:
            with open(poi_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                hotels = [p for p in data if p.get("type") == "hotel"]
                logger.info("Loaded " + str(len(hotels)) + " hotels for " + city)
                return hotels
        except Exception as e:
            logger.error("Failed to load hotels: " + str(e))
            return []
    
    async def execute(self, state: TourState) -> dict:
        """Select the best hotel with location-aware scoring."""
        intent = state.get("trip_intent", {})
        city = intent.get("city", state.get("city", ""))
        budget = intent.get("budget", "mid-range")
        pois = state.get("pois", [])
        
        if not city:
            return {"selected_hotel": None}
        
        hotels = self._load_hotels(city)
        if not hotels:
            return {"selected_hotel": None}
        
        # Calculate POI center
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
            s = score_hotel(hotel, (avg_lat, avg_lng), budget)
            scored_hotels.append((s, hotel))
        
        scored_hotels.sort(key=lambda x: x[0], reverse=True)
        
        # Select best hotel
        if scored_hotels:
            _, best_hotel = scored_hotels[0]
            return {"selected_hotel": best_hotel}
        
        return {"selected_hotel": None}
