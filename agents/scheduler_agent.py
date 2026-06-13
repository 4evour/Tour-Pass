"""Scheduler Agent - Create day-by-day itinerary with clustering and route optimization.

Consumes:
- city_guides from RetrieveAgent (injected into schedule context)
- review_feedback from ReviewerAgent (full structured feedback, not just
  missing_must_visit) on re-run cycles

Features:
- POI opening time awareness
- Weather-aware indoor/outdoor prioritisation
- Pace-aware gap times and stop limits
- City guide context enrichment
- POI knowledge-aware closed_days filtering
"""

import logging

from agents.base import BaseAgent
from agents.state import TourState
from tools import rag
from tools.clustering import cluster_pois_for_days
from tools.route import optimize_route, calculate_total_travel_time

logger = logging.getLogger(__name__)

# Pace configuration
PACE_CONFIG = {
    "relaxed":  {"max_stops": 4, "gap_minutes": 45, "start_time": 540, "end_time": 1080},
    "balanced": {"max_stops": 6, "gap_minutes": 30, "start_time": 540, "end_time": 1140},
    "intense":  {"max_stops": 8, "gap_minutes": 15, "start_time": 480, "end_time": 1200},
}

# Meal time windows
MEAL_WINDOWS = {
    "lunch":  {"start": 660, "end": 780, "default_start": 720, "duration": 60},
    "dinner": {"start": 1020, "end": 1140, "default_start": 1080, "duration": 75},
}

# Indoor tags for weather-aware scheduling
INDOOR_TAGS = {
    "博物馆", "室内", "展览", "美术馆", "科技馆", "水族馆",
    "商场", "购物中心", "书店", "剧院", "电影院",
}

# Weekday names for closed_days matching
_WEEKDAY_MAP = {
    0: "Monday", 1: "Tuesday", 2: "Wednesday",
    3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday",
}


class SchedulerAgent(BaseAgent):
    """Create optimised day-by-day itinerary."""

    @property
    def name(self) -> str:
        return "SchedulerAgent"

    @property
    def description(self) -> str:
        return "Create optimised day-by-day itinerary with clustering"

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _is_rainy(weather: list, day_idx: int) -> bool:
        if not weather or day_idx >= len(weather):
            return False
        condition = weather[day_idx].get("condition", "")
        return any(rain in condition for rain in ("雨", "rain", "Rain"))

    @staticmethod
    def _prioritize_by_weather(attractions: list, is_rainy: bool) -> list:
        if not is_rainy:
            return attractions
        indoor = [a for a in attractions if set(a.get("tags", [])) & INDOOR_TAGS]
        outdoor = [a for a in attractions if not (set(a.get("tags", [])) & INDOOR_TAGS)]
        logger.info("Rainy day: %d indoor, %d outdoor POIs", len(indoor), len(outdoor))
        return indoor + outdoor

    @staticmethod
    def _check_opening_time(attr: dict, arrival: int) -> tuple[int, int]:
        """Return (adjusted_start, adjusted_duration)."""
        duration = attr.get("visit_duration_minutes", 60)
        open_t = attr.get("open_minutes", 480)
        close_t = attr.get("close_minutes", 1080)
        if arrival < open_t:
            arrival = open_t
        end = min(arrival + duration, close_t)
        duration = max(end - arrival, 30)
        return arrival, duration

    @staticmethod
    def _find_meal_slot(stops: list, meal_type: str) -> dict:
        window = MEAL_WINDOWS.get(meal_type, MEAL_WINDOWS["lunch"])
        dur = window["duration"]
        preferred = window["default_start"]
        w_start, w_end = window["start"], window["end"]

        def _conflicts(start: int, end: int) -> bool:
            return any(start < s.get("end_minutes", 0) and end > s.get("start_minutes", 0) for s in stops)

        # Try preferred -> earlier
        for attempt in range(preferred, w_start - 30, -30):
            if not _conflicts(attempt, attempt + dur) and attempt >= w_start:
                return {"start": attempt, "end": attempt + dur}
        # Try later
        for attempt in range(preferred + 30, w_end, 30):
            if not _conflicts(attempt, attempt + dur) and attempt + dur <= w_end:
                return {"start": attempt, "end": attempt + dur}
        return None  # No non-conflicting slot

    @staticmethod
    def _insert_missing_must_visits(clusters: list, missing: list[str], all_pois: list) -> list:
        if not missing:
            return clusters
        missing_pois = []
        for mv in missing:
            for poi in all_pois:
                if mv in poi.get("name", ""):
                    missing_pois.append(poi)
                    break
        for poi in missing_pois:
            min_cluster = min(clusters, key=lambda c: len(c.attractions))
            existing = {a.get("name", "") for a in min_cluster.attractions}
            if poi.get("name", "") not in existing:
                min_cluster.attractions.insert(0, poi)
                logger.info("Inserted missing must_visit '%s' into day %d", poi.get("name"), min_cluster.day_num)
        return clusters

    @staticmethod
    def _remove_flagged_pois(clusters: list, flagged_names: list[str]) -> list:
        """Remove POIs flagged by reviewer (e.g. duplicates, invalid)."""
        if not flagged_names:
            return clusters
        flagged = set(flagged_names)
        for cluster in clusters:
            cluster.attractions = [
                a for a in cluster.attractions
                if a.get("name", "") not in flagged
            ]
        return clusters

    @staticmethod
    def _filter_closed_pois(attractions: list, day_idx: int, start_date=None) -> list:
        """Remove POIs that are closed on the given day of week."""
        if start_date:
            from datetime import timedelta
            target_date = start_date + timedelta(days=day_idx)
            weekday_name = _WEEKDAY_MAP.get(target_date.weekday(), "")
        else:
            weekday_name = ""

        if not weekday_name:
            return attractions

        filtered = []
        removed = 0
        for a in attractions:
            closed_days = a.get("closed_days", [])
            if weekday_name in closed_days:
                logger.info("Skipping '%s' on day %d (closed on %s)",
                            a.get("name", ""), day_idx + 1, weekday_name)
                removed += 1
            else:
                filtered.append(a)

        if removed:
            logger.info("Filtered %d closed POIs for day %d (%s)", removed, day_idx + 1, weekday_name)
        return filtered

    async def execute(self, state: TourState) -> dict:
        city = state.get("city", "")
        days = state.get("days", 3)
        pois = state.get("pois", [])
        hotels = state.get("hotels", [])
        restaurants = state.get("restaurants", [])
        weather = state.get("weather", [])
        city_guides = state.get("city_guides", [])
        review_feedback = state.get("review_feedback") or {}
        intent = state.get("trip_intent") or {}

        pace = intent.get("pace", "balanced")
        pace_cfg = PACE_CONFIG.get(pace, PACE_CONFIG["balanced"])
        hotel = state.get("selected_hotel") or (hotels[0] if hotels else None)

        # Extract review corrections
        missing_must_visit = review_feedback.get("missing_must_visit", [])
        flagged_names = [
            i.get("poi_name", "") for i in review_feedback.get("issues", [])
            if i.get("severity") in ("high", "critical") and i.get("poi_name")
        ]

        # Enrich POIs with closed_days from poi_knowledge
        poi_knowledge = rag.get_poi_knowledge(city)
        if poi_knowledge:
            for poi in pois:
                name = poi.get("name", "")
                for kid, kdata in poi_knowledge.items():
                    if kdata.get("name") == name:
                        if kdata.get("closed_days"):
                            poi["closed_days"] = kdata["closed_days"]
                        break
            logger.info("Enriched %d POIs with poi_knowledge metadata", len(pois))

        # Step 1: Cluster POIs
        clusters = cluster_pois_for_days(
            pois=pois, restaurants=restaurants, days=days,
            intent=intent,
        )

        # Apply review corrections
        if missing_must_visit:
            clusters = self._insert_missing_must_visits(clusters, missing_must_visit, pois)
        if flagged_names:
            clusters = self._remove_flagged_pois(clusters, flagged_names)

        # Step 2: Route optimisation
        hotel_lat = hotel.get("lat", 0) if hotel else 0
        hotel_lng = hotel.get("lng", 0) if hotel else 0
        for cluster in clusters:
            if cluster.attractions and hotel_lat and hotel_lng:
                cluster.attractions = optimize_route(
                    start_lat=hotel_lat, start_lng=hotel_lng,
                    stops=cluster.attractions,
                    end_lat=hotel_lat, end_lng=hotel_lng,
                )

        # Build city guide context string (actually USE the RAG data)
        guide_context = ""
        if city_guides:
            guide_snippets = city_guides[:5]  # top 5 snippets
            guide_context = "\n".join(guide_snippets)
            logger.info("Injecting %d city guide snippets into schedule", len(guide_snippets))

        # Step 3: Create schedule with time awareness
        daily_plans: list[dict] = []
        for day_idx, cluster in enumerate(clusters):
            is_rainy = self._is_rainy(weather, day_idx)
            if is_rainy:
                cluster.attractions = self._prioritize_by_weather(cluster.attractions, True)

            # Filter closed POIs for this day
            cluster.attractions = self._filter_closed_pois(cluster.attractions, day_idx)

            max_stops = pace_cfg["max_stops"]
            current_time = pace_cfg["start_time"]
            gap = pace_cfg["gap_minutes"]
            end_of_day = pace_cfg["end_time"]

            stops: list[dict] = []

            # Schedule attractions
            for attr in cluster.attractions[:max_stops]:
                if current_time >= end_of_day:
                    break
                adj_start, adj_dur = self._check_opening_time(attr, current_time)
                if adj_start >= end_of_day:
                    continue

                if adj_start < 660:
                    slot = "morning"
                elif adj_start < 780:
                    slot = "lunch"
                elif adj_start < 1080:
                    slot = "afternoon"
                else:
                    slot = "evening"

                stops.append({
                    "slot": slot,
                    "poi_id": attr.get("id", ""),
                    "poi_name": attr.get("name", ""),
                    "start_minutes": adj_start,
                    "end_minutes": adj_start + adj_dur,
                    "visit_duration_minutes": adj_dur,
                    "reason": attr.get("recommend_reason", attr.get("recommendation", "")),
                    "poi_type": attr.get("type", "attraction"),
                    "area": attr.get("area", ""),
                    "lat": attr.get("lat", 0),
                    "lng": attr.get("lng", 0),
                })
                current_time = adj_start + adj_dur + gap

            # Schedule restaurants
            for rest in cluster.restaurants[:2]:
                has_lunch = any(s.get("slot") == "lunch" for s in stops)
                meal_type = "dinner" if has_lunch else "lunch"
                meal_slot = self._find_meal_slot(stops, meal_type)
                if meal_slot is None:
                    continue
                stops.append({
                    "slot": meal_type,
                    "poi_id": rest.get("id", ""),
                    "poi_name": rest.get("name", ""),
                    "start_minutes": meal_slot["start"],
                    "end_minutes": meal_slot["end"],
                    "visit_duration_minutes": meal_slot["end"] - meal_slot["start"],
                    "reason": rest.get("recommend_reason", "Dining"),
                    "poi_type": "restaurant",
                    "area": rest.get("area", ""),
                    "lat": rest.get("lat", 0),
                    "lng": rest.get("lng", 0),
                })

            stops.sort(key=lambda x: x.get("start_minutes", 0))

            # Build day summary enriched with guide context
            summary_parts = [f"Day {cluster.day_num}: {cluster.theme}"]
            if guide_context:
                snippet = city_guides[day_idx % len(city_guides)] if city_guides else ""
                if snippet:
                    summary_parts.append(f"💡 {snippet[:120]}")

            daily_plans.append({
                "day": cluster.day_num,
                "theme": cluster.theme,
                "stops": stops,
                "summary": "\n".join(summary_parts),
                "total_travel_minutes": calculate_total_travel_time(stops),
                "is_rainy": is_rainy,
            })

        logger.info("Created %d day plans", len(daily_plans))
        return {"daily_plans": daily_plans}
