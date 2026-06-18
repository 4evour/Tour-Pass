"""Scheduler Agent - Create day-by-day itinerary with clustering and route optimization.

Consumes:
- city_guides from RetrieveAgent (injected into schedule context)
- review_feedback from ReviewerAgent (full structured feedback, not just
  missing_must_visit) on re-run cycles
- available_pois from PoiAgent (full POI list for must-visit rescue)

Features:
- POI opening time awareness
- Weather-aware indoor/outdoor prioritisation
- Pace-aware gap times and stop limits
- City guide context enrichment
- POI knowledge-aware closed_days filtering
- Must-visit 4-layer guarantee chain (layers 3 & 4 in this agent)
- C++ Beam Search route optimization via optimize_route_smart
- Fine-grained SSE event emission
"""

import logging

from agents.base import BaseAgent
from agents.state import TourState
from agents.config import USE_CPP_ROUTE_OPTIMIZER
from agents.constants import haversine_km
from tools import rag
from tools.clustering import cluster_pois_for_days, _is_must_visit
from tools.route import optimize_route_smart, calculate_total_travel_time

logger = logging.getLogger(__name__)

# Pace configuration
PACE_CONFIG = {
    "relaxed":  {"max_stops": 2, "gap_minutes": 60, "start_time": 600, "end_time": 1020},
    "balanced": {"max_stops": 3, "gap_minutes": 30, "start_time": 540, "end_time": 1140},
    "intense":  {"max_stops": 4, "gap_minutes": 15, "start_time": 480, "end_time": 1260},
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
    def _meal_types_for_pace(pace: str, intent: dict) -> list[str]:
        interests = set(intent.get("interests", []))
        food_focused = bool(interests & {"food", "culinary", "美食"}) or intent.get("strategy") == "culinary"
        if pace == "relaxed" and not food_focused:
            return ["lunch"]
        return ["lunch", "dinner"]

    @staticmethod
    def _avoid_reserved_meals(start: int, duration: int, meal_types: list[str]) -> int:
        """Move attraction starts out of reserved meal slots."""
        adjusted = start
        changed = True
        while changed:
            changed = False
            for meal_type in meal_types:
                window = MEAL_WINDOWS.get(meal_type)
                if not window:
                    continue
                reserved_start = window["default_start"]
                reserved_end = reserved_start + window["duration"]
                if adjusted < reserved_end and adjusted + duration > reserved_start:
                    adjusted = reserved_end
                    changed = True
        return adjusted

    @staticmethod
    def _anchored_start_for_pace(pace: str, attr_idx: int, current_time: int) -> int:
        if pace != "intense":
            return current_time
        anchors = [480, 600, 840, 1170]
        if attr_idx < len(anchors):
            return max(current_time, anchors[attr_idx])
        return current_time

    @staticmethod
    def _slot_for_time(start_minutes: int) -> str:
        if start_minutes < 660:
            return "morning"
        if start_minutes < 780:
            return "lunch"
        if start_minutes < 1080:
            return "afternoon"
        return "evening"

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

    @staticmethod
    def _inject_missing_must_visit(
        stops: list[dict],
        must_visit_ids: set[str],
        cluster_attractions: list[dict],
    ) -> list[dict]:
        """Layer 3: Per-day must_visit post-injection.

        After building the stops list for a day, check whether any
        must_visit attraction assigned to this cluster is missing.
        If so, force-inject it into the schedule.
        """
        if not must_visit_ids:
            return stops

        included_ids = {s.get("poi_id", "") for s in stops}
        missing_ids = must_visit_ids - included_ids
        if not missing_ids:
            return stops

        for attr in cluster_attractions:
            aid = attr.get("id", "")
            if aid not in missing_ids:
                continue
            slot = "上午" if not any(s.get("slot") == "上午" for s in stops) else "下午"
            injected = {
                "slot": slot,
                "poi_id": aid,
                "poi_name": attr.get("name", ""),
                "start_minutes": 540 if slot == "上午" else 840,
                "end_minutes": (540 if slot == "上午" else 840)
                + attr.get("visit_duration_minutes", 60),
                "visit_duration_minutes": attr.get("visit_duration_minutes", 60),
                "reason": f"用户必去: {attr.get('name', '')}",
                "poi_type": attr.get("type", "attraction"),
                "area": attr.get("area", ""),
                "lat": attr.get("lat", 0),
                "lng": attr.get("lng", 0),
            }
            stops.insert(0, injected)
            logger.info("Layer-3: force-injected must_visit '%s'", attr.get("name"))
        return stops

    @staticmethod
    def _xhs_affinity_swap(
        clusters: list,
        cooccur: dict[tuple[str, str], int],
        must_visit_names: list[str] | None = None,
        max_move_distance_km: float = 25.0,
        min_source_attractions: int = 1,
        min_cooccur: int = 3,
    ) -> list:
        """Swap attractions between clusters to maximise XHS co-occurrence.

        For each pair of clusters, check whether moving an attraction from
        cluster A to cluster B (or vice-versa) increases the total number
        of high-affinity pairs kept together.  Only performs moves that
        strictly improve affinity (greedy, single pass).
        """
        must_visit_names = must_visit_names or []
        high_pairs = {pair for pair, cnt in cooccur.items() if cnt >= min_cooccur}
        if not high_pairs:
            return clusters

        def _names(cluster):
            return {a.get("name", "") for a in cluster.attractions}

        def _affinity(cluster):
            ns = _names(cluster)
            return sum(1 for a, b in high_pairs if a in ns and b in ns)

        def _center(attractions: list[dict]) -> tuple[float, float]:
            lats = [a.get("lat", 0) for a in attractions if a.get("lat")]
            lngs = [a.get("lng", 0) for a in attractions if a.get("lng")]
            if not lats or not lngs:
                return 0.0, 0.0
            return sum(lats) / len(lats), sum(lngs) / len(lngs)

        def _fits_target_area(attr: dict, target_cluster) -> bool:
            if not max_move_distance_km or not target_cluster.attractions:
                return True
            attr_lat = attr.get("lat", 0)
            attr_lng = attr.get("lng", 0)
            center_lat, center_lng = _center(target_cluster.attractions)
            if not attr_lat or not attr_lng or not center_lat or not center_lng:
                return True
            return haversine_km(attr_lat, attr_lng, center_lat, center_lng) <= max_move_distance_km

        improved = True
        max_iters = 3  # prevent infinite loops
        iters = 0
        while improved and iters < max_iters:
            improved = False
            iters += 1
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    ci, cj = clusters[i], clusters[j]
                    before = _affinity(ci) + _affinity(cj)
                    # Try moving each attraction from ci → cj
                    best_gain = 0
                    best_move = None  # (attr_idx, from_i, to_j)
                    if len(ci.attractions) > min_source_attractions:
                        for ai, attr in enumerate(ci.attractions):
                            if _is_must_visit(attr, must_visit_names):
                                continue
                            if not _fits_target_area(attr, cj):
                                continue
                            # Simulate move
                            ci.attractions.pop(ai)
                            cj.attractions.append(attr)
                            after = _affinity(ci) + _affinity(cj)
                            gain = after - before
                            # Revert
                            cj.attractions.pop()
                            ci.attractions.insert(ai, attr)
                            if gain > best_gain:
                                best_gain = gain
                                best_move = (ai, i, j)

                    if best_move and best_gain > 0:
                        ai, fi, ti = best_move
                        attr = clusters[fi].attractions.pop(ai)
                        clusters[ti].attractions.append(attr)
                        logger.info(
                            "XHS affinity: moved '%s' day %d → day %d (gain +%d)",
                            attr.get("name"), fi + 1, ti + 1, best_gain,
                        )
                        improved = True
                    # Also try cj → ci
                    best_gain = 0
                    best_move = None
                    if len(cj.attractions) > min_source_attractions:
                        for aj, attr in enumerate(cj.attractions):
                            if _is_must_visit(attr, must_visit_names):
                                continue
                            if not _fits_target_area(attr, ci):
                                continue
                            cj.attractions.pop(aj)
                            ci.attractions.append(attr)
                            after = _affinity(ci) + _affinity(cj)
                            gain = after - before
                            ci.attractions.pop()
                            cj.attractions.insert(aj, attr)
                            if gain > best_gain:
                                best_gain = gain
                                best_move = (aj, j, i)

                    if best_move and best_gain > 0:
                        aj, fi, ti = best_move
                        attr = clusters[fi].attractions.pop(aj)
                        clusters[ti].attractions.append(attr)
                        logger.info(
                            "XHS affinity: moved '%s' day %d → day %d (gain +%d)",
                            attr.get("name"), fi + 1, ti + 1, best_gain,
                        )
                        improved = True
        return clusters

    async def execute(self, state: TourState) -> dict:
        city = state.get("city", "")
        days = state.get("days", 3)
        pois = state.get("pois", [])
        hotels = state.get("hotels", [])
        restaurants = state.get("restaurants", [])
        weather = state.get("weather", [])
        city_guides = state.get("city_guides", [])
        xhs_reference_routes = state.get("xhs_reference_routes") or []
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

        # Full POI list for Layer-2 must_visit rescue
        available_pois = state.get("available_pois", [])
        # Nightlife POIs (may have been loaded by RestaurantAgent or PoiAgent)
        nightlife = [p for p in available_pois if p.get("type") == "nightlife"]

        # Step 1: Cluster POIs (Layer 2 must_visit rescue via all_available_pois)
        clusters = cluster_pois_for_days(
            scored_attractions=pois,
            restaurants=restaurants,
            num_days=days,
            intent=intent,
            all_available_pois=available_pois,
            nightlife=nightlife,
        )

        # Apply review corrections
        if missing_must_visit:
            clusters = self._insert_missing_must_visits(clusters, missing_must_visit, pois)
        if flagged_names:
            clusters = self._remove_flagged_pois(clusters, flagged_names)

        # Step 1.5: XHS co-occurrence affinity adjustment
        # If two POIs frequently appear together in real XHS itineraries,
        # try to keep them on the same day by swapping across clusters.
        xhs_routes = state.get("xhs_routes") or []
        if xhs_routes:
            try:
                from tools.xhs_loader import extract_cooccurrence
                cooccur = extract_cooccurrence(city)
                if cooccur:
                    clusters = self._xhs_affinity_swap(
                        clusters,
                        cooccur,
                        must_visit_names=intent.get("must_visit", []),
                        max_move_distance_km=12.0,
                        min_source_attractions={"relaxed": 2, "balanced": 3, "intense": 4}.get(pace, 3),
                    )
                    logger.info("Applied XHS co-occurrence affinity to %d clusters", len(clusters))
            except Exception as e:
                logger.warning("XHS affinity swap failed: %s", e)

        # Step 2: Route optimisation (C++ Beam Search with Python 2-opt fallback)
        city_dir = state.get("city", "")
        hotel_lat = hotel.get("lat", 0) if hotel else 0
        hotel_lng = hotel.get("lng", 0) if hotel else 0
        hotel_id = hotel.get("id", "") if hotel else ""

        for cluster in clusters:
            if cluster.attractions and hotel_lat and hotel_lng:
                cluster.attractions = await optimize_route_smart(
                    city=city_dir,
                    stops=cluster.attractions,
                    hotel_id=hotel_id,
                    start_lat=hotel_lat,
                    start_lng=hotel_lng,
                    start_minutes=pace_cfg["start_time"],
                    end_minutes=pace_cfg["end_time"],
                    pace=pace,
                    strategy=intent.get("strategy", "balanced"),
                    use_cpp=USE_CPP_ROUTE_OPTIMIZER,
                )

        # Build city guide context string (actually USE the RAG data)
        guide_context = ""
        if city_guides:
            guide_snippets = city_guides[:5]  # top 5 snippets
            guide_context = "\n".join(guide_snippets)
            logger.info("Injecting %d city guide snippets into schedule", len(guide_snippets))
        if xhs_reference_routes:
            logger.info("Injecting %d XHS reference routes into schedule", len(xhs_reference_routes))

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
            meal_types = self._meal_types_for_pace(pace, intent)

            # Schedule attractions
            for attr_idx, attr in enumerate(cluster.attractions[:max_stops]):
                if current_time >= end_of_day:
                    break
                preferred_start = self._anchored_start_for_pace(pace, attr_idx, current_time)
                preferred_start = self._avoid_reserved_meals(
                    preferred_start,
                    attr.get("visit_duration_minutes", 60),
                    meal_types,
                )
                adj_start, adj_dur = self._check_opening_time(attr, preferred_start)
                adj_start = self._avoid_reserved_meals(adj_start, adj_dur, meal_types)
                if adj_start >= end_of_day:
                    continue

                slot = self._slot_for_time(adj_start)

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
            meal_candidates = [
                r for r in cluster.restaurants
                if r.get("type", "restaurant") == "restaurant"
            ] or cluster.restaurants
            used_restaurant_ids: set[str] = set()
            for meal_type in meal_types:
                rest = None
                for candidate in meal_candidates:
                    rid = candidate.get("id") or candidate.get("name", "")
                    if rid not in used_restaurant_ids:
                        rest = candidate
                        used_restaurant_ids.add(rid)
                        break
                if rest is None:
                    continue
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

            # ── Layer 3: per-day must_visit post-injection ────────────────────
            must_visit_names = intent.get("must_visit", [])
            if must_visit_names:
                mv_ids = set()
                for mv in must_visit_names:
                    for a in cluster.attractions:
                        if mv in a.get("name", "") or mv == a.get("id"):
                            mv_ids.add(a.get("id", ""))
                stops = self._inject_missing_must_visit(stops, mv_ids, cluster.attractions)

            stops.sort(key=lambda x: x.get("start_minutes", 0))

            # Build day summary enriched with guide context
            summary_parts = [f"Day {cluster.day_num}: {cluster.theme}"]
            if guide_context:
                snippet = city_guides[day_idx % len(city_guides)] if city_guides else ""
                if snippet:
                    summary_parts.append(f"💡 {snippet[:120]}")
            if xhs_reference_routes:
                ref = xhs_reference_routes[day_idx % len(xhs_reference_routes)]
                ref_stops = " -> ".join(ref.get("stops", [])[:6])
                if ref_stops:
                    summary_parts.append(f"真实路线参考: {ref_stops}")

            daily_plans.append({
                "day": cluster.day_num,
                "theme": cluster.theme,
                "stops": stops,
                "summary": "\n".join(summary_parts),
                "total_travel_minutes": calculate_total_travel_time(stops),
                "is_rainy": is_rainy,
            })

        # ── Layer 4: Global must_visit post-verification ────────────────────
        # Traverse all daily_plans, check that every intent.must_visit keyword
        # appears in at least one stop.  Inject any remaining gaps into the
        # lightest day (migrated from agent/graph.py:503-544).
        must_visit_coverage: list[dict] = []
        must_visit_names = intent.get("must_visit", [])
        sse_events: list[dict] = []

        if must_visit_names:
            all_planned_names: set[str] = set()
            for dp in daily_plans:
                for s in dp.get("stops", []):
                    all_planned_names.add(s.get("poi_name", ""))

            still_missing: list[str] = []
            for mv in must_visit_names:
                if not any(mv in name for name in all_planned_names):
                    still_missing.append(mv)

            if still_missing:
                logger.warning("Layer-4 global verification: missing %s", still_missing)
                for mv in still_missing:
                    # Find POI in available_pois
                    target = None
                    for p in available_pois:
                        if mv in p.get("name", "") or mv == p.get("id"):
                            target = p
                            break
                    if not target:
                        logger.error("Layer-4: cannot rescue '%s' — not in available_pois", mv)
                        continue

                    # Inject into lightest day
                    lightest = min(daily_plans, key=lambda d: len(d.get("stops", [])))
                    slot = "下午" if len(lightest.get("stops", [])) >= 3 else "上午"
                    injected_stop = {
                        "slot": slot,
                        "poi_id": target.get("id", ""),
                        "poi_name": target.get("name", ""),
                        "start_minutes": 840 if slot == "下午" else 540,
                        "end_minutes": (840 if slot == "下午" else 540)
                        + target.get("visit_duration_minutes", 60),
                        "visit_duration_minutes": target.get("visit_duration_minutes", 60),
                        "reason": f"用户必去（全局补救）: {target.get('name', '')}",
                        "poi_type": target.get("type", "attraction"),
                        "area": target.get("area", ""),
                        "lat": target.get("lat", 0),
                        "lng": target.get("lng", 0),
                    }
                    lightest.setdefault("stops", []).append(injected_stop)
                    logger.info(
                        "Layer-4: rescued '%s' into day %d",
                        target.get("name"), lightest.get("day"),
                    )
                    sse_events.append({
                        "type": "must_visit_injected",
                        "content": f"已强制安排行程: {mv}",
                    })

            # Build coverage report
            final_planned: set[str] = set()
            for dp in daily_plans:
                for s in dp.get("stops", []):
                    final_planned.add(s.get("poi_name", ""))
            for mv in must_visit_names:
                matched = ""
                included = False
                for name in final_planned:
                    if mv in name:
                        included = True
                        matched = name
                        break
                must_visit_coverage.append({
                    "name": mv, "included": included, "matched_poi": matched,
                })

            covered = sum(1 for c in must_visit_coverage if c["included"])
            logger.info(
                "Must-visit coverage: %d/%d", covered, len(must_visit_coverage),
            )

        # Emit day_planned SSE events
        for dp in daily_plans:
            sse_events.append({
                "type": "day_planned",
                "content": f"第 {dp.get('day', '?')} 天规划完成：{len(dp.get('stops', []))} 个行程",
            })

        logger.info("Created %d day plans", len(daily_plans))
        return {
            "daily_plans": daily_plans,
            "must_visit_coverage": must_visit_coverage,
            "sse_events": sse_events,
        }
