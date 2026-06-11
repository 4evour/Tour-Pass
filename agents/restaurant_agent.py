"""Restaurant Agent - Search and recommend restaurants using local data.

Future: Will integrate with Dianping and Douyin APIs.
"""

import json
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

RESTAURANT_SYSTEM = """You are a restaurant recommendation expert.

Given the user's preferences, trip schedule, and available restaurants, select the best dining options.

Consider:
1. Cuisine type matching user's interests
2. Location near planned attractions
3. Price level matching budget
4. Rating and reviews
5. Meal timing (lunch vs dinner)

Output format (JSON):
{
  "restaurants": [
    {
      "id": "restaurant_id",
      "name": "餐厅名称",
      "meal_type": "lunch",
      "day": 1,
      "reason": "推荐理由"
    }
  ]
}

meal_type options: "lunch", "dinner", "breakfast"
day: Which day of the trip (1-indexed)"""


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
    
    def _load_restaurants(self, city: str) -> list[dict]:
        """Load restaurants from local JSON file."""
        poi_file = self.data_dir / city / "pois.json"
        if not poi_file.exists():
            return []
        
        try:
            with open(poi_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                restaurants = [p for p in data if p.get("type") == "restaurant"]
                logger.info(f"Loaded {len(restaurants)} restaurants for {city}")
                return restaurants
        except Exception as e:
            logger.error(f"Failed to load restaurants: {e}")
            return []
    
    async def execute(self, state: TourState) -> dict:
        """Select restaurants for the trip."""
        intent = state.get("intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)
        interests = intent.get("interests", [])
        budget = intent.get("budget", "mid-range")
        daily_plans = state.get("daily_plans", [])
        
        if not city:
            return {"errors": state.get("errors", []) + ["No city specified"]}
        
        # Load restaurants
        restaurants = self._load_restaurants(city)
        
        if not restaurants:
            return {"restaurants": []}
        
        # Get areas from daily plans for location-based recommendation
        planned_areas = []
        for day in daily_plans:
            for stop in day.get("stops", []):
                if stop.get("area"):
                    planned_areas.append(stop["area"])
        
        context = f"""城市: {city}
旅行天数: {days}
用户兴趣: {', '.join(interests) if interests else '综合'}
预算级别: {budget}
计划区域: {', '.join(set(planned_areas)) if planned_areas else '未知'}

候选餐厅 ({len(restaurants)}家):
{chr(10).join([
    f"- {r['name']} (ID:{r['id']}, 区域:{r.get('area', '')}, "
    f"评分:{r.get('rating', 0)}, 人均:{r.get('avg_price', 0)}元, "
    f"标签:{','.join(r.get('tags', [])[:3])})"
    for r in restaurants[:30]
])}

请为每天推荐午餐和晚餐各1家餐厅。"""
        
        runnable = self.get_runnable()
        response = await runnable.ainvoke({"context": context})
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            recommended = result.get("restaurants", [])
            
            # Enrich with full restaurant data
            restaurant_map = {r["id"]: r for r in restaurants}
            enriched = []
            for rec in recommended:
                rid = rec.get("id", "")
                if rid in restaurant_map:
                    r = restaurant_map[rid].copy()
                    r["meal_type"] = rec.get("meal_type", "lunch")
                    r["day"] = rec.get("day", 1)
                    r["recommend_reason"] = rec.get("reason", "")
                    enriched.append(r)
            
            logger.info(f"Recommended {len(enriched)} restaurants")
            return {"restaurants": enriched}
        
        except Exception as e:
            logger.error(f"Failed to parse restaurant recommendations: {e}")
            # Fallback: return top rated restaurants
            restaurants.sort(key=lambda x: x.get("rating", 0), reverse=True)
            return {"restaurants": restaurants[:days * 2]}
