"""Restaurant Agent - Search and recommend restaurants using local data."""

import json
import logging
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

RESTAURANT_SYSTEM = """You are a restaurant recommendation expert.

Given the user's preferences and available restaurants, select the best dining options.

Output format (JSON):
```json
{
  "restaurants": [
    {
      "id": "restaurant_id",
      "name": "restaurant name",
      "meal_type": "lunch",
      "day": 1,
      "reason": "recommendation reason"
    }
  ]
}
```"""


class RestaurantAgent(BaseTourAgent):
    """Agent that searches and recommends restaurants."""
    
    def __init__(self, llm: BaseChatModel, data_dir: str = "data"):
        super().__init__(llm)
        self.data_dir = Path(data_dir)
    
    @property
    def name(self) -> str:
        return "RestaurantAgent"
    
    @property
    def description(self) -> str:
        return "Search and recommend restaurants"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", RESTAURANT_SYSTEM),
            ("human", "{context}"),
        ])
    
    def _get_city_dir(self, city: str) -> str:
        """Get directory name for city."""
        if (self.data_dir / city).exists():
            return city
        if city in CITY_DIR_MAP:
            return CITY_DIR_MAP[city]
        return city.lower()
    
    def _load_restaurants(self, city: str) -> list[dict]:
        """Load restaurants from local JSON file."""
        city_dir = self._get_city_dir(city)
        poi_file = self.data_dir / city_dir / "pois.json"
        
        if not poi_file.exists():
            return []
        try:
            with open(poi_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                restaurants = [p for p in data if p.get("type") == "restaurant"]
                logger.info("Loaded " + str(len(restaurants)) + " restaurants for " + city)
                return restaurants
        except Exception as e:
            logger.error("Failed to load restaurants: " + str(e))
            return []
    
    async def execute(self, state: TourState) -> dict:
        """Select restaurants for the trip."""
        intent = state.get("trip_intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)
        interests = intent.get("interests", [])
        
        if not city:
            return {"restaurants": []}
        
        restaurants = self._load_restaurants(city)
        if not restaurants:
            return {"restaurants": []}
        
        # Select top rated restaurants
        restaurants.sort(key=lambda x: x.get("rating", 0), reverse=True)
        
        # Assign to days
        enriched = []
        for i, r in enumerate(restaurants[:days * 2]):
            r_copy = r.copy()
            r_copy["meal_type"] = "lunch" if i % 2 == 0 else "dinner"
            r_copy["day"] = (i // 2) + 1
            r_copy["recommend_reason"] = "High rated restaurant"
            enriched.append(r_copy)
        
        logger.info("Recommended " + str(len(enriched)) + " restaurants")
        return {"restaurants": enriched}
