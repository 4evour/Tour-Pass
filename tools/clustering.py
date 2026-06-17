"""Tour Pass Multi-Agent System - Geographic Clustering Tools.

Merged from:
- agent/clustering.py  — must-visit rescue from full POI list, nightlife
                          assignment, area-based theme inference
- tools/clustering.py  — cross-day restaurant deduplication, distance-based
                          scoring, RestaurantAgent _score integration
"""

import math
import logging
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class DayCluster:
    """A cluster of POIs for a single day."""
    day_num: int
    theme: str
    attractions: list[dict] = field(default_factory=list)
    restaurants: list[dict] = field(default_factory=list)
    center_lat: float = 0.0
    center_lng: float = 0.0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    R = 6371  # Earth radius in km
    
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


def _area_center(pois: list[dict]) -> tuple[float, float]:
    """Calculate the geographic center of a list of POIs."""
    lats = [p.get("lat", 0) for p in pois if p.get("lat")]
    lngs = [p.get("lng", 0) for p in pois if p.get("lng")]
    
    if not lats or not lngs:
        return 0.0, 0.0
    
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def _find_closest_cluster(
    poi: dict,
    clusters: list[DayCluster],
) -> int:
    """Find the index of the closest cluster to a POI."""
    poi_lat = poi.get("lat", 0)
    poi_lng = poi.get("lng", 0)
    
    if not poi_lat or not poi_lng:
        return 0  # Default to first cluster
    
    min_dist = float("inf")
    closest_idx = 0
    
    for i, cluster in enumerate(clusters):
        if not cluster.center_lat or not cluster.center_lng:
            continue
        
        dist = _haversine_km(poi_lat, poi_lng, cluster.center_lat, cluster.center_lng)
        if dist < min_dist:
            min_dist = dist
            closest_idx = i
    
    return closest_idx


def _infer_theme(pois: list[dict], intent: dict | None = None) -> str:
    """Infer a theme for a cluster of POIs.

    Migrated from agent/clustering.py — includes area names and strategy-aware
    labels when intent is provided.
    """
    if not pois:
        return "休闲探索"

    areas = {p.get("area", "") for p in pois if p.get("area")}
    all_tags: set[str] = set()
    for p in pois:
        all_tags.update(p.get("tags", []))

    if any("历史" in t or "文化" in t or "世界遗产" in t for t in all_tags):
        return f"历史文化之旅（{'、'.join(list(areas)[:2])}）"
    if any("美食" in t or "小吃" in t for t in all_tags):
        return f"美食探店之旅（{'、'.join(list(areas)[:2])}）"
    if any("自然" in t or "公园" in t or "山水" in t for t in all_tags):
        return f"自然风光之旅（{'、'.join(list(areas)[:2])}）"
    if any("购物" in t or "商圈" in t for t in all_tags):
        return f"城市探索之旅（{'、'.join(list(areas)[:2])}）"

    # Fallback: tag-count based
    tag_counts: dict[str, int] = defaultdict(int)
    for poi in pois:
        for tag in poi.get("tags", []):
            if tag not in {"城市游览", "景点", "风景名胜"}:
                tag_counts[tag] += 1
    if tag_counts:
        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:2]
        label = "·".join(tag for tag, _ in top_tags)
        return f"{label}（{'、'.join(list(areas)[:2])}）" if areas else label

    return f"{'、'.join(list(areas)[:2])}深度游" if areas else "综合游览"


def _is_must_visit(poi: dict, must_visit: list[str]) -> bool:
    """Check if a POI matches any must_visit keyword."""
    name = poi.get("name", "")
    pid = poi.get("id", "")
    for mv in must_visit:
        if mv in name or mv == pid:
            return True
    return False


def cluster_pois_for_days(
    scored_attractions: list[dict],
    restaurants: list[dict],
    num_days: int,
    intent: dict,
    all_available_pois: list[dict] | None = None,
    nightlife: list[dict] | None = None,
) -> list[DayCluster]:
    """Cluster POIs into day groups based on geographic proximity.

    Extended with:
    - **all_available_pois** rescue: if a must_visit keyword was not matched
      inside *scored_attractions* (e.g. truncated by top_k), search the full
      POI list and inject it with a high synthetic score.
    - **nightlife** rotation: assign one nightlife POI per day.
    - **closest-cluster** must_visit assignment for overflow (not just round-robin).

    Args:
        scored_attractions: Scored attraction dicts (output of rank_pois).
        restaurants: Restaurant dicts (output of RestaurantAgent).
        num_days: Number of travel days.
        intent: User intent dict.
        all_available_pois: Full POI list for must_visit rescue.
        nightlife: Nightlife POI list.

    Returns:
        List of DayCluster, one per day.
    """
    if num_days <= 0:
        num_days = 1
    if not scored_attractions:
        return [DayCluster(day_num=i + 1, theme="自由活动") for i in range(num_days)]

    must_visit_names = intent.get("must_visit", [])

    # ── Separate must_visit and regular attractions ──────────────────────────
    must_pois = [a for a in scored_attractions if _is_must_visit(a, must_visit_names)]
    regular = [a for a in scored_attractions if not _is_must_visit(a, must_visit_names)]

    # ── Layer 2: must_visit rescue from all_available_pois ───────────────────
    # If a must_visit keyword was not matched in scored_attractions, try to
    # find the POI in the full list and inject it (migrated from
    # agent/clustering.py:99-126).
    if must_visit_names and all_available_pois:
        must_visit_set = set(must_visit_names)
        matched_keywords: set[str] = set()
        for poi in must_pois:
            for mv in must_visit_names:
                if mv in poi.get("name", "") or mv == poi.get("id"):
                    matched_keywords.add(mv)

        for mv in must_visit_set - matched_keywords:
            candidates = [
                p for p in all_available_pois
                if (mv in p.get("name", "") or mv == p.get("id"))
                and p.get("type") not in ("hotel", "transit")
            ]
            if candidates:
                candidates.sort(
                    key=lambda p: (
                        p.get("name", "") != mv,
                        len(p.get("name", "")),
                        -(p.get("popularity", 0) or 0),
                    ),
                )
                rescued = candidates[0].copy()
                rescued["_score"] = 99999
                rescued["is_must_visit"] = True
                must_pois.append(rescued)
                logger.info(
                    "Rescued must_visit '%s' -> '%s' from full POI list",
                    mv, rescued.get("name"),
                )
            else:
                logger.warning("must_visit '%s' not found in any available POI", mv)

    # ── Initialise clusters ──────────────────────────────────────────────────
    clusters = [DayCluster(day_num=i + 1, theme="") for i in range(num_days)]

    # ── Assign must_visit attractions ────────────────────────────────────────
    # First N go to different days (round-robin); overflow uses closest cluster
    # or the day with fewest must-visits.
    for i, attr in enumerate(must_pois):
        if i < num_days:
            day_idx = i % num_days
        else:
            min_must_day = min(
                range(num_days),
                key=lambda d: sum(
                    1 for a in clusters[d].attractions
                    if _is_must_visit(a, must_visit_names)
                ),
            )
            day_idx = (
                _find_closest_cluster(attr, clusters)
                if clusters[0].attractions
                else min_must_day
            )
            if any(a.get("id") == attr.get("id") for a in clusters[day_idx].attractions):
                day_idx = min_must_day
        clusters[day_idx].attractions.append(attr)
    
    # ── Assign regular attractions ───────────────────────────────────────────
    pace = intent.get("pace", "balanced")
    max_per_day = {"relaxed": 4, "balanced": 6, "intense": 8}.get(pace, 6)

    for attr in regular:
        for cluster in clusters:
            if cluster.attractions:
                cluster.center_lat, cluster.center_lng = _area_center(cluster.attractions)

        closest_idx = _find_closest_cluster(attr, clusters)
        if len(clusters[closest_idx].attractions) < max_per_day:
            clusters[closest_idx].attractions.append(attr)
        else:
            min_cluster = min(clusters, key=lambda c: len(c.attractions))
            min_cluster.attractions.append(attr)
    
    # Assign restaurants to clusters with cross-day deduplication
    assigned_restaurant_ids: set[str] = set()

    for cluster in clusters:
        if not cluster.center_lat or not cluster.center_lng:
            cluster.center_lat, cluster.center_lng = _area_center(cluster.attractions)

        # Find closest restaurants not yet assigned to other days
        cluster_restaurants = []
        for rest in restaurants:
            rest_id = rest.get("id", rest.get("name", ""))
            if rest_id in assigned_restaurant_ids:
                continue  # Skip already-assigned restaurant

            rest_lat = rest.get("lat", 0)
            rest_lng = rest.get("lng", 0)
            if not rest_lat or not rest_lng:
                continue

            dist = _haversine_km(
                cluster.center_lat, cluster.center_lng,
                rest_lat, rest_lng,
            )

            if dist < 5.0:  # Within 5km
                # Bonus for score from RestaurantAgent
                agent_score = rest.get("_score", 0)
                # Combine: lower distance = better, higher score = better
                combined = agent_score - dist * 10
                cluster_restaurants.append((combined, dist, rest))

        # Sort by combined score (best first), take top 3
        cluster_restaurants.sort(key=lambda x: x[0], reverse=True)
        cluster.restaurants = [r for _, _, r in cluster_restaurants[:3]]

        # Track assigned restaurant IDs to prevent cross-day duplicates
        for r in cluster.restaurants:
            rid = r.get("id", r.get("name", ""))
            if rid:
                assigned_restaurant_ids.add(rid)
    
    # ── Nightlife rotation ───────────────────────────────────────────────────
    nightlife = nightlife or []
    for cluster in clusters:
        if nightlife:
            nl = nightlife[(cluster.day_num - 1) % len(nightlife)]
            cluster.restaurants.append(nl)

    # ── Infer themes (with area-aware labels) ────────────────────────────────
    for cluster in clusters:
        cluster.theme = _infer_theme(cluster.attractions, intent)
    
    # Fill empty clusters
    for i, cluster in enumerate(clusters):
        if not cluster.attractions:
            cluster.theme = "自由活动日"
            # Try to assign some unassigned attractions
            for attr in regular:
                if not any(attr in c.attractions for c in clusters):
                    cluster.attractions.append(attr)
                    break
    
    logger.info(f"Created {num_days} day clusters")
    for cluster in clusters:
        logger.info(f"  Day {cluster.day_num} ({cluster.theme}): {len(cluster.attractions)} attractions, {len(cluster.restaurants)} restaurants")
    
    return clusters
