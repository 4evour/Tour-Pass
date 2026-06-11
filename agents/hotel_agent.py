"""Hotel Agent - Search and recommend hotels."""

import json
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

HOTEL_SYSTEM = """You are a hotel recommendation expert.

Given the user's intent, POI locations, and available hotels, select the best hotel.

Consider:
1. Location: Hotel should be central to the planned attractions
2. Budget: Match user's budget level
3. Rating: Prioritize higher-rated hotels
4. Amenities: Consider user's needs

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


class HotelAgent(BaseTourAgent):
    """Agent that searches and recommends hotels."""
    
    def __init__(self, llm: BaseChatModel, data_dir: str = "data"):
        super().__init__(llm)
        self.data_dir = Path(data_dir)
    
    @property
    def name(self) -> str:
        return "HotelAgent"
    
    @property
    def description(self) -> str:
        return "Search and recommend hotels"
    
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
        """Select the best hotel."""
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
            avg_lat = sum(p.get("lat", 0) for p in pois if p.get("lat")) / len([p for p in pois if p.get("lat")]) or 0
            avg_lng = sum(p.get("lng", 0) for p in pois if p.get("lng")) / len([p for p in pois if p.get("lng")]) or 0
        else:
            avg_lat, avg_lng = 0, 0
        
        # Prepare context
        hotel_list = "\n".join([
            f"- {h['name']} (ID:{h['id']}, 区域:{h.get('area', '')}, "
            f"评分:{h.get('rating', 0)}, 价格:{h.get('price_per_night', 0)}元/晚)"
            for h in hotels[:20]
        ])
        
        context = f"""城市: {city}
预算级别: {budget}
景点中心位置: ({avg_lat}, {avg_lng})

候选酒店:
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
            
            # Fallback: highest rated hotel
            hotels.sort(key=lambda x: x.get("rating", 0), reverse=True)
            return {"selected_hotel": hotels[0] if hotels else None}
        
        except Exception as e:
            logger.error(f"Failed to parse hotel recommendation: {e}")
            hotels.sort(key=lambda x: x.get("rating", 0), reverse=True)
            return {"selected_hotel": hotels[0] if hotels else None}
