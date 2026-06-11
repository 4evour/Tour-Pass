"""Scheduler Agent - Create day-by-day itinerary with clustering and route optimization."""

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

Create a detailed schedule for each day. Output JSON with daily_plans array.

Each day plan should have: day, theme, stops array, summary.
Each stop should have: slot (morning/lunch/afternoon/dinner/evening), poi_id, poi_name, start_minutes, end_minutes, visit_duration_minutes, reason.

Time in minutes from midnight: 540=9:00, 720=12:00, 810=13:30, 1050=17:30, 1080=18:00, 1170=19:30."""


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
        intent = state.get("trip_intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)
        pace = intent.get("pace", "balanced")
        must_visit = intent.get("must_visit", [])
        
        pois = state.get("pois", [])
        hotel = state.get("selected_hotel", {})
        restaurants = state.get("restaurants", [])
        weather = state.get("weather", [])
        
        if not pois:
            return {"daily_plans": []}
        
        # Step 1: Geographic clustering
        logger.info("Step 1: Clustering POIs by geography...")
        
        attractions = [p for p in pois if p.get("type") in ("attraction", "nightlife")]
        rest_list = [r for r in restaurants] if restaurants else []
        
        clusters = cluster_pois_for_days(
            scored_attractions=attractions,
            restaurants=rest_list,
            num_days=days,
            intent=intent,
        )
        
        # Step 2: Route optimization
        logger.info("Step 2: Optimizing routes...")
        
        hotel_lat = hotel.get("lat", 0) if hotel else 0
        hotel_lng = hotel.get("lng", 0) if hotel else 0
        
        optimized_clusters = []
        for cluster in clusters:
            if cluster.attractions:
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
        
        # Step 3: Create schedule
        logger.info("Step 3: Creating detailed schedule...")
        
        # Build schedule directly without LLM
        daily_plans = []
        for cluster in optimized_clusters:
            stops = []
            current_time = 540  # 9:00 AM
            
            # Add attractions
            for i, attr in enumerate(cluster.attractions[:4]):
                visit_duration = attr.get("visit_duration_minutes", 60)
                
                if i == 0:
                    slot = "morning"
                elif i == 1:
                    slot = "afternoon"
                    current_time = 810  # 1:30 PM
                elif i == 2:
                    slot = "afternoon"
                    current_time = 960  # 4:00 PM
                else:
                    slot = "evening"
                    current_time = 1140  # 7:00 PM
                
                stops.append({
                    "slot": slot,
                    "poi_id": attr.get("id", ""),
                    "poi_name": attr.get("name", ""),
                    "start_minutes": current_time,
                    "end_minutes": current_time + visit_duration,
                    "visit_duration_minutes": visit_duration,
                    "reason": attr.get("recommend_reason", ""),
                    "poi_type": attr.get("type", "attraction"),
                    "area": attr.get("area", ""),
                    "lat": attr.get("lat", 0),
                    "lng": attr.get("lng", 0),
                })
                
                current_time += visit_duration + 30  # Add travel time
            
            # Add restaurants
            for rest in cluster.restaurants[:2]:
                meal_type = "lunch" if len(stops) < 2 else "dinner"
                meal_time = 720 if meal_type == "lunch" else 1080
                
                stops.append({
                    "slot": meal_type,
                    "poi_id": rest.get("id", ""),
                    "poi_name": rest.get("name", ""),
                    "start_minutes": meal_time,
                    "end_minutes": meal_time + 90,
                    "visit_duration_minutes": 90,
                    "reason": "Dining",
                    "poi_type": "restaurant",
                    "area": rest.get("area", ""),
                    "lat": rest.get("lat", 0),
                    "lng": rest.get("lng", 0),
                })
            
            # Sort by start time
            stops.sort(key=lambda x: x.get("start_minutes", 0))
            
            daily_plans.append({
                "day": cluster.day_num,
                "theme": cluster.theme,
                "stops": stops,
                "summary": "Day " + str(cluster.day_num) + ": " + cluster.theme,
                "total_travel_minutes": calculate_total_travel_time(stops),
            })
        
        logger.info("Created " + str(len(daily_plans)) + " day plans")
        return {"daily_plans": daily_plans}
