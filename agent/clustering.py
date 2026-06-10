"""Geographic clustering for daily itinerary planning.

Groups POIs by area and creates day plans that minimize travel
by keeping same-area attractions together.
"""
from __future__ import annotations
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .models import PoiInfo, TripIntent
from .scorer import ScoredPoi, rank_pois


@dataclass
class DayCluster:
    """A cluster of POIs assigned to one day."""
    day_num: int
    primary_area: str
    attractions: list[PoiInfo] = field(default_factory=list)
    restaurants: list[PoiInfo] = field(default_factory=list)
    nightlife: list[PoiInfo] = field(default_factory=list)
    theme: str = ""


def _area_center(pois: list[PoiInfo]) -> tuple[float, float]:
    """Compute centroid of a group of POIs."""
    if not pois:
        return (0.0, 0.0)
    lat = sum(p.lat for p in pois) / len(pois)
    lng = sum(p.lng for p in pois) / len(pois)
    return (lat, lng)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance between two points in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def cluster_pois_for_days(
    scored_attractions: list[ScoredPoi],
    restaurants: list[PoiInfo],
    nightlife: list[PoiInfo],
    num_days: int,
    intent: TripIntent,
) -> list[DayCluster]:
    """Distribute POIs across days using area-based clustering.

    Strategy:
    1. Group top-scored attractions by area
    2. Assign each day a primary area (greedy: biggest cluster first)
    3. Fill each day with its area's attractions + nearby restaurants
    4. Must-visit POIs are pre-assigned to their best-fit day
    """
    if num_days <= 0:
        num_days = 1

    # Separate must-visit from others
    must_visit_names = set(intent.must_visit)
    must_pois: list[ScoredPoi] = []
    optional_pois: list[ScoredPoi] = []

    for sp in scored_attractions:
        is_must = any(mv in sp.poi.name or mv == sp.poi.id for mv in must_visit_names)
        if is_must:
            must_pois.append(sp)
        else:
            optional_pois.append(sp)

    # Group optional attractions by area
    area_groups: dict[str, list[ScoredPoi]] = defaultdict(list)
    for sp in optional_pois:
        area = sp.poi.area or "其他"
        area_groups[area].append(sp)

    # Sort areas by total score (descending)
    area_scores = {
        area: sum(s.total_score for s in pois)
        for area, pois in area_groups.items()
    }
    sorted_areas = sorted(area_scores.keys(), key=lambda a: area_scores[a], reverse=True)

    # Limit to top attractions (don't give LLM too many)
    # Pick top N per day based on pace
    pace_limits = {"休闲": 5, "标准": 7, "紧凑": 9}
    max_per_day = pace_limits.get(intent.pace, 7)
    total_needed = max_per_day * num_days

    # Initialize day clusters
    clusters: list[DayCluster] = []
    for d in range(num_days):
        clusters.append(DayCluster(
            day_num=d + 1,
            primary_area="",
        ))

    # Assign must-visit POIs to days (spread across days)
    for i, sp in enumerate(must_pois):
        day_idx = i % num_days
        clusters[day_idx].attractions.append(sp.poi)

    # Assign optional attractions using area-based round-robin
    # Each day gets a "theme area" rotation
    day_idx = 0
    assigned_count = {d: len(clusters[d].attractions) for d in range(num_days)}

    for area in sorted_areas:
        area_pois = sorted(area_groups[area], key=lambda s: s.total_score, reverse=True)
        for sp in area_pois:
            if assigned_count[day_idx] >= max_per_day:
                # Find day with fewest attractions
                day_idx = min(range(num_days), key=lambda d: assigned_count[d])
            if assigned_count[day_idx] >= max_per_day:
                continue  # All days full

            clusters[day_idx].attractions.append(sp.poi)
            assigned_count[day_idx] += 1

            # Set primary area if not set
            if not clusters[day_idx].primary_area:
                clusters[day_idx].primary_area = sp.poi.area

            # Move to next day for variety (but stay in same area for a few)
            if assigned_count[day_idx] >= 2:
                day_idx = (day_idx + 1) % num_days

    # Assign restaurants to days (prefer same area as day's attractions)
    rest_by_area: dict[str, list[PoiInfo]] = defaultdict(list)
    for r in restaurants:
        rest_by_area[r.area or "其他"].append(r)

    for cluster in clusters:
        day_areas = set(a.area for a in cluster.attractions if a.area)
        # Pick restaurants from same area
        day_rests: list[PoiInfo] = []
        for area in day_areas:
            day_rests.extend(rest_by_area.get(area, [])[:2])

        # If not enough, add from nearby
        if len(day_rests) < 2:
            for area, rests in rest_by_area.items():
                if area not in day_areas:
                    day_rests.extend(rests[:1])
                    break

        cluster.restaurants = day_rests[:3]

        # Add nightlife
        if nightlife:
            cluster.nightlife = [nightlife[cluster.day_num % len(nightlife)]]

        # Set theme based on attractions
        cluster.theme = _infer_theme(cluster.attractions, intent)

    return clusters


def _infer_theme(attractions: list[PoiInfo], intent: TripIntent) -> str:
    """Infer a day theme from the attractions."""
    if not attractions:
        return "休闲探索"

    areas = set(a.area for a in attractions if a.area)
    all_tags = set()
    for a in attractions:
        all_tags.update(a.tags)

    if any("历史" in t or "文化" in t or "世界遗产" in t for t in all_tags):
        return f"历史文化之旅（{'、'.join(list(areas)[:2])}）"
    if any("美食" in t or "小吃" in t for t in all_tags):
        return f"美食探店之旅（{'、'.join(list(areas)[:2])}）"
    if any("自然" in t or "公园" in t or "山水" in t for t in all_tags):
        return f"自然风光之旅（{'、'.join(list(areas)[:2])}）"
    if any("购物" in t or "商圈" in t for t in all_tags):
        return f"城市探索之旅（{'、'.join(list(areas)[:2])}）"

    return f"{'、'.join(list(areas)[:2])}深度游"