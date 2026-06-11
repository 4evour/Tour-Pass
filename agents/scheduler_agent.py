"""Scheduler Agent - Create day-by-day itinerary."""

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

SCHEDULER_SYSTEM = """You are a travel itinerary scheduler.

Given POIs, hotels, restaurants, and weather, create a detailed day-by-day itinerary.

RULES:
1. MUST include all must_visit places (marked with 【必去】)
2. Group nearby POIs together (geographic clustering)
3. Consider opening hours and visit duration
4. Include meal breaks (lunch ~12:00, dinner ~18:00)
5. Consider weather for outdoor activities
6. Balance activities to avoid exhaustion
7. Start and end each day at the hotel

Time slots:
- morning: 09:00-12:00
- lunch: 12:00-13:30
- afternoon: 13:30-17:30
- dinner: 18:00-19:30
- evening: 19:30-22:00

Output format (JSON):
{
  "daily_plans": [
    {
      "day": 1,
      "theme": "文化探索日",
      "stops": [
        {
          "slot": "morning",
          "poi_id": "xxx",
          "poi_name": "景点名称",
          "start_minutes": 540,
          "end_minutes": 660,
          "visit_duration_minutes": 120,
          "reason": "推荐理由"
        }
      ],
      "summary": "第1天: 上午参观XXX，下午游览XXX"
    }
  ]
}

start_minutes/end_minutes: Minutes from midnight (540 = 9:00, 720 = 12:00, etc.)"""


class SchedulerAgent(BaseTourAgent):
    """Agent that creates day-by-day itinerary."""
    
    @property
    def name(self) -> str:
        return "SchedulerAgent"
    
    @property
    def description(self) -> str:
        return "Create day-by-day itinerary"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", SCHEDULER_SYSTEM),
            ("human", "{context}"),
        ])
    
    async def execute(self, state: TourState) -> dict:
        """Create day-by-day itinerary."""
        intent = state.get("intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)
        pace = intent.get("pace", "balanced")
        must_visit = intent.get("must_visit", [])
        
        pois = state.get("pois", [])
        hotel = state.get("selected_hotel", {})
        restaurants = state.get("restaurants", [])
        weather = state.get("weather", [])
        
        if not pois:
            return {"errors": state.get("errors", []) + ["No POIs available"]}
        
        # Prepare POI list
        poi_list = "\n".join([
            f"- {p['name']} (ID:{p['id']}, 区域:{p.get('area', '')}, "
            f"游玩时长:{p.get('visit_duration_minutes', 60)}分钟, "
            f"标签:{','.join(p.get('tags', [])[:3])})"
            + (" 【必去】" if p.get("is_must_visit") or any(mv in p["name"] for mv in must_visit) else "")
            for p in pois
        ])
        
        # Prepare restaurant list
        rest_list = "\n".join([
            f"- {r['name']} (ID:{r['id']}, 区域:{r.get('area', '')}, "
            f"人均:{r.get('avg_price', 0)}元)"
            for r in restaurants[:10]
        ])
        
        # Prepare weather info
        weather_info = "\n".join([
            f"- 第{i+1}天 ({w.get('date', '')}): {w.get('condition', '')}, "
            f"{w.get('temperature_low', 0)}-{w.get('temperature_high', 0)}°C, "
            f"建议: {w.get('suggestion', '')}"
            for i, w in enumerate(weather)
        ])
        
        context = f"""城市: {city}
旅行天数: {days}
节奏: {pace}
酒店: {hotel.get('name', '未定')} ({hotel.get('area', '')})

天气预报:
{weather_info}

候选景点:
{poi_list}

候选餐厅:
{rest_list}

请规划{days}天的详细行程。"""
        
        runnable = self.get_runnable()
        response = await runnable.ainvoke({"context": context})
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            daily_plans = result.get("daily_plans", [])
            
            # Enrich with full POI data
            poi_map = {p["id"]: p for p in pois}
            for day in daily_plans:
                for stop in day.get("stops", []):
                    pid = stop.get("poi_id", "")
                    if pid in poi_map:
                        poi = poi_map[pid]
                        stop["poi_type"] = poi.get("type", "attraction")
                        stop["area"] = poi.get("area", "")
                        stop["lat"] = poi.get("lat", 0)
                        stop["lng"] = poi.get("lng", 0)
            
            logger.info(f"Created {len(daily_plans)} day plans")
            return {"daily_plans": daily_plans}
        
        except Exception as e:
            logger.error(f"Failed to parse schedule: {e}")
            return {"errors": state.get("errors", []) + [f"Schedule creation failed: {e}"]}
