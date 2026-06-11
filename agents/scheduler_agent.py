"""Scheduler Agent - Create day-by-day itinerary with clustering and route optimization.

This agent uses:
1. Geographic clustering (from legacy clustering.py)
2. Route optimization (nearest neighbor heuristic)
3. LLM-based scheduling with constraints
"""

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState
from tools.clustering import cluster_pois_for_days
from tools.route import optimize_route, calculate_total_travel_time

logger = logging.getLogger(__name__)

SCHEDULER_SYSTEM = """You are a travel itinerary scheduler.

You receive clustered POIs organized by day. Your job is to:
1. Create a detailed schedule for each day
2. Assign time slots (morning, lunch, afternoon, dinner, evening)
3. Consider opening hours and visit duration
4. Include meal breaks
5. Ensure the schedule is realistic and not too rushed

RULES:
- MUST include all must_visit places (marked with 【必去】)
- Start each day around 9:00 AM
- Include lunch break around 12:00-13:00
- Include dinner around 18:00-19:00
- End each day by 21:00-22:00
- Allow travel time between stops (30-60 min)

Time slots:
- morning: 09:00-12:00 (180-720 minutes from midnight)
- lunch: 12:00-13:30 (720-810)
- afternoon: 13:30-17:30 (810-1050)
- dinner: 18:00-19:30 (1080-1170)
- evening: 19:30-22:00 (1170-1320)

Output format (JSON):
{
  "daily_plans": [
    {
      "day": 1,
      "theme": "主题",
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
      "summary": "行程摘要"
    }
  ]
}"""


class SchedulerAgent(BaseTourAgent):
    """Agent that creates optimized day-by-day itinerary."""
    
    @property
    def name(self) -> str:
        return "SchedulerAgent"
    
    @property
    def description(self) -> str:
        return "Create optimized day-by-day itinerary with clustering"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", SCHEDULER_SYSTEM),
            ("human", "{context}"),
        ])
    
    async def execute(self, state: TourState) -> dict:
        """Create optimized day-by-day itinerary."""
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
        
        # Step 1: Geographic clustering
        logger.info("Step 1: Clustering POIs by geography...")
        
        # Separate attractions and restaurants
        attractions = [p for p in pois if p.get("type") in ("attraction", "nightlife")]
        rest_list = [r for r in restaurants] if restaurants else []
        
        clusters = cluster_pois_for_days(
            scored_attractions=attractions,
            restaurants=rest_list,
            num_days=days,
            intent=intent,
        )
        
        # Step 2: Route optimization for each cluster
        logger.info("Step 2: Optimizing routes...")
        
        hotel_lat = hotel.get("lat", 0) if hotel else 0
        hotel_lng = hotel.get("lng", 0) if hotel else 0
        
        optimized_clusters = []
        for cluster in clusters:
            if cluster.attractions:
                # Optimize route starting from hotel
                if hotel_lat and hotel_lng:
                    optimized = optimize_route(
                        start_lat=hotel_lat,
                        start_lng=hotel_lng,
                        stops=cluster.attractions,
                        end_lat=hotel_lat,
                        end_lng=hotel_lng,
                    )
                    cluster.attractions = optimized
            
            optimized_clusters.append(cluster)
        
        # Step 3: Prepare context for LLM scheduling
        logger.info("Step 3: Creating detailed schedule...")
        
        cluster_descriptions = []
        for cluster in optimized_clusters:
            attr_list = "\n".join([
                f"  - {a['name']} (ID:{a['id']}, 区域:{a.get('area', '')}, "
                f"游玩时长:{a.get('visit_duration_minutes', 60)}分钟)"
                + (" 【必去】" if a.get("is_must_visit") or any(mv in a["name"] for mv in must_visit) else "")
                for a in cluster.attractions
            ])
            
            rest_list = "\n".join([
                f"  - {r['name']} (ID:{r['id']}, 人均:{r.get('avg_price', 0)}元)"
                for r in cluster.restaurants[:2]
            ])
            
            cluster_descriptions.append(f"""第{cluster.day_num}天 - {cluster.theme}
景点:
{attr_list}
餐厅:
{rest_list}""")
        
        # Weather info
        weather_info = ""
        if weather:
            weather_info = "\n天气预报:\n" + "\n".join([
                f"  第{i+1}天: {w.get('condition', '')}, {w.get('suggestion', '')}"
                for i, w in enumerate(weather)
            ])
        
        context = f"""城市: {city}
旅行天数: {days}
节奏: {pace}
酒店: {hotel.get('name', '未定')} ({hotel.get('area', '')})
{weather_info}

按地理位置聚类的景点:
{chr(10).join(cluster_descriptions)}

请为每天创建详细行程。"""
        
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
            
            # Calculate travel times
            for day in daily_plans:
                stops = day.get("stops", [])
                travel_time = calculate_total_travel_time(stops)
                day["total_travel_minutes"] = travel_time
            
            logger.info(f"Created {len(daily_plans)} day plans with clustering and route optimization")
            return {"daily_plans": daily_plans}
        
        except Exception as e:
            logger.error(f"Failed to parse schedule: {e}")
            return {"errors": state.get("errors", []) + [f"Schedule creation failed: {e}"]}
