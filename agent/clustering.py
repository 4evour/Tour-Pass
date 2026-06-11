"""Geographic clustering for daily itinerary planning.

Groups POIs by area and creates day plans that minimize travel
by keeping same-area attractions together.
"""
from __future__ import annotations
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .models import PoiInfo, TripIntent
from .scorer import ScoredPoi, rank_pois, _is_must_visit

logger = logging.getLogger(__name__)


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


def _find_closest_cluster(
    poi: PoiInfo, clusters: list[DayCluster]
) -> int:
    """Find the day cluster whose attractions centroid is closest to the given POI."""
    best_idx = 0
    best_dist = float("inf")
    for i, cluster in enumerate(clusters):
        if not cluster.attractions:
            continue
        lat, lng = _area_center(cluster.attractions)
        dist = _haversine_km(poi.lat, poi.lng, lat, lng)
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


def cluster_pois_for_days(
    scored_attractions: list[ScoredPoi],
    restaurants: list[PoiInfo],
    nightlife: list[PoiInfo],
    num_days: int,
    intent: TripIntent,
    all_available_pois: Optional[list[PoiInfo]] = None,
) -> list[DayCluster]:
    """Distribute POIs across days using area-based clustering.

    Strategy:
    1. Group top-scored attractions by area
    2. Assign each day a primary area (greedy: biggest cluster first)
    3. Fill each day with its area's attractions + nearby restaurants
    4. Must-visit POIs are pre-assigned to their best-fit day

    Args:
        all_available_pois: Full POI list for rescuing must-visit POIs
            that weren't in scored_attractions (e.g. missed by search/filter).
    """
    if num_days <= 0:
        num_days = 1

    # Separate must-visit from others
    must_visit_names = set(intent.must_visit)
    must_pois: list[ScoredPoi] = []
    optional_pois: list[ScoredPoi] = []

    for sp in scored_attractions:
        if _is_must_visit(sp.poi, intent.must_visit):
            must_pois.append(sp)
        else:
            optional_pois.append(sp)

    # Rescue: check if any must_visit keyword is not matched in scored_attractions
    # If so, try to find the POI in all_available_pois and inject it
    if must_visit_names and all_available_pois:
        matched_keywords = set()
        for sp in must_pois:
            for mv in must_visit_names:
                if mv in sp.poi.name or mv == sp.poi.id:
                    matched_keywords.add(mv)

        missing_keywords = must_visit_names - matched_keywords
        for mv in missing_keywords:
            # Search in full POI list
            candidates = [
                p for p in all_available_pois
                if (mv in p.name or mv == p.id) and p.type not in ("hotel", "transit")
            ]
            if candidates:
                # Pick best match (shortest name containing keyword, highest popularity)
                candidates.sort(key=lambda p: (p.name != mv, len(p.name), -p.popularity))
                rescued_poi = candidates[0]
                fake_scored = ScoredPoi(
                    poi=rescued_poi, total_score=99999,
                    reason=f"必去景点补救: {mv}",
                )
                must_pois.append(fake_scored)
                logger.info(f"Rescued must_visit '{mv}' -> '{rescued_poi.name}' from full POI list")
            else:
                logger.warning(f"Must_visit '{mv}' not found in any available POI data")

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

    # Initialize day clusters
    clusters: list[DayCluster] = []
    for d in range(num_days):
        clusters.append(DayCluster(
            day_num=d + 1,
            primary_area="",
        ))

    # Assign must-visit POIs to days — distribute evenly first, then by proximity
    assigned_must_days: set[int] = set()
    for i, sp in enumerate(must_pois):
        if i < num_days:
            # First N must-visits go to different days (round-robin)
            day_idx = i % num_days
        else:
            # Remaining must-visits: find day with fewest must-visits
            min_must = min(
                range(num_days),
                key=lambda d: sum(1 for a in clusters[d].attractions if _is_must_visit(a, intent.must_visit))
            )
            day_idx = _find_closest_cluster(sp.poi, clusters) if clusters[0].attractions else min_must
            # If that day already has this must_visit, try the fewest-must day
            if any(sp.poi.id == a.id for a in clusters[day_idx].attractions):
                day_idx = min_must
        clusters[day_idx].attractions.append(sp.poi)
        assigned_must_days.add(day_idx)

    # Assign optional attractions using area-based round-robin
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

        # Add nightlife — use (day_num - 1) for 0-based indexing to rotate properly
        if nightlife:
            cluster.nightlife = [nightlife[(cluster.day_num - 1) % len(nightlife)]]

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
