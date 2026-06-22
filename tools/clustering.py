"""Tour Pass Multi-Agent System - Geographic Clustering Tools.

Merged from:
- agent/clustering.py  — must-visit rescue from full POI list, nightlife
                          assignment, area-based theme inference
- tools/clustering.py  — cross-day restaurant deduplication, distance-based
                          scoring, RestaurantAgent _score integration
"""

import math
import logging
import re
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)

_SCENIC_SUFFIXES = (
    "风景名胜区", "国家森林公园", "森林公园", "湿地公园",
    "旅游度假区", "旅游区", "游客中心", "观景平台",
    "风景区", "景区", "公园", "广场", "岛",
)
_SAME_SCENIC_DISTANCE_KM = 0.35
_NEW_AREA_SEED_DISTANCE_KM = 12.0
_MAX_CLUSTER_APPEND_DISTANCE_KM = {
    "relaxed": 18.0,
    "balanced": 25.0,
    "intense": 35.0,
}
_MAX_RESTAURANT_DISTANCE_KM = {
    "relaxed": 8.0,
    "balanced": 12.0,
    "intense": 18.0,
}


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


def _canonical_scenic_name(name: str) -> str:
    """Return a stable key for parent scenic areas and near-duplicate POIs."""
    raw = (name or "").strip()
    if not raw:
        return ""

    base = re.split(r"[-—(（]", raw, 1)[0].strip()
    base = re.sub(r"\s+", "", base)

    changed = True
    while changed:
        changed = False
        for suffix in _SCENIC_SUFFIXES:
            if len(base) > len(suffix) + 1 and base.endswith(suffix):
                base = base[:-len(suffix)]
                changed = True
                break

    return base or raw


def _same_scenic_place(left: dict, right: dict) -> bool:
    left_id = left.get("id", "")
    right_id = right.get("id", "")
    if left_id and right_id and left_id == right_id:
        return True

    left_key = _canonical_scenic_name(left.get("name", ""))
    right_key = _canonical_scenic_name(right.get("name", ""))
    if not left_key or left_key != right_key:
        return False

    left_lat, left_lng = left.get("lat", 0), left.get("lng", 0)
    right_lat, right_lng = right.get("lat", 0), right.get("lng", 0)
    if left_lat and left_lng and right_lat and right_lng:
        return _haversine_km(left_lat, left_lng, right_lat, right_lng) <= _SAME_SCENIC_DISTANCE_KM

    return left.get("name", "") == right.get("name", "")


def _dedupe_attractions_by_place(attractions: list[dict], must_visit: list[str]) -> list[dict]:
    """Keep one attraction per physical scenic place, preserving first useful slot."""
    deduped: list[dict] = []

    def rank(poi: dict) -> tuple[int, int, float, float, int]:
        name = poi.get("name", "")
        exact = any(mv and name == mv for mv in must_visit)
        contains = any(mv and mv in name for mv in must_visit)
        return (
            1 if exact else 0,
            1 if poi.get("is_must_visit") or contains else 0,
            float(poi.get("_score", 0) or 0),
            float(poi.get("popularity", 0) or 0),
            -len(name),
        )

    for attr in attractions:
        duplicate_idx = None
        for idx, existing in enumerate(deduped):
            if _same_scenic_place(attr, existing):
                duplicate_idx = idx
                break

        if duplicate_idx is None:
            deduped.append(attr)
            continue

        if rank(attr) > rank(deduped[duplicate_idx]):
            deduped[duplicate_idx] = attr

    return deduped


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


def _find_best_underfilled_cluster(poi: dict, clusters: list[DayCluster]) -> DayCluster:
    """Choose the closest underfilled cluster; seed empty days only when needed."""
    empty_clusters = [c for c in clusters if not c.attractions]
    with_centers = []
    for cluster in clusters:
        if not cluster.center_lat or not cluster.center_lng:
            cluster.center_lat, cluster.center_lng = _area_center(cluster.attractions)
        if cluster.center_lat and cluster.center_lng:
            with_centers.append(cluster)

    if with_centers:
        poi_lat = poi.get("lat", 0)
        poi_lng = poi.get("lng", 0)
        if poi_lat and poi_lng:
            closest = min(
                with_centers,
                key=lambda c: _haversine_km(poi_lat, poi_lng, c.center_lat, c.center_lng),
            )
            closest_dist = _haversine_km(
                poi_lat, poi_lng,
                closest.center_lat, closest.center_lng,
            )
            if empty_clusters and closest_dist > _NEW_AREA_SEED_DISTANCE_KM:
                return min(empty_clusters, key=lambda c: c.day_num)
            return closest

    return min(clusters, key=lambda c: len(c.attractions))


def _distance_to_cluster(poi: dict, cluster: DayCluster) -> float:
    if not cluster.center_lat or not cluster.center_lng:
        cluster.center_lat, cluster.center_lng = _area_center(cluster.attractions)
    poi_lat = poi.get("lat", 0)
    poi_lng = poi.get("lng", 0)
    if not poi_lat or not poi_lng or not cluster.center_lat or not cluster.center_lng:
        return 0.0
    return _haversine_km(poi_lat, poi_lng, cluster.center_lat, cluster.center_lng)


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


def _target_restaurant_count(intent: dict) -> int:
    interests = set(intent.get("interests", []))
    food_focused = bool(interests & {"food", "culinary", "美食"}) or intent.get("strategy") == "culinary"
    return 2 if food_focused else 1


def _restaurant_identity(rest: dict) -> str:
    return rest.get("id") or rest.get("name", "")


def _score_restaurant_for_cluster(cluster: DayCluster, rest: dict) -> tuple[float, float]:
    agent_score = float(rest.get("_score", 0) or 0)
    rest_lat = rest.get("lat", 0)
    rest_lng = rest.get("lng", 0)
    if not cluster.center_lat or not cluster.center_lng or not rest_lat or not rest_lng:
        return agent_score - 1000, float("inf")

    dist = _haversine_km(
        cluster.center_lat, cluster.center_lng,
        rest_lat, rest_lng,
    )
    distance_penalty = dist * (10 if dist < 5.0 else 4)
    far_penalty = 0 if dist < 5.0 else 25
    return agent_score - distance_penalty - far_penalty, dist


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
    scored_attractions = _dedupe_attractions_by_place(scored_attractions, must_visit_names)

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

        must_pois = _dedupe_attractions_by_place(must_pois, must_visit_names)
        regular = [
            attr for attr in regular
            if not any(_same_scenic_place(attr, must_poi) for must_poi in must_pois)
        ]

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
    max_append_distance = _MAX_CLUSTER_APPEND_DISTANCE_KM.get(pace, 25.0)
    max_restaurant_distance = _MAX_RESTAURANT_DISTANCE_KM.get(pace, 12.0)
    target_min_per_day = min(max_per_day, max(1, len(scored_attractions) // num_days))
    skipped_far_keys: set[str] = set()

    for attr in regular:
        attr_key = attr.get("id") or attr.get("name", "")
        for cluster in clusters:
            if cluster.attractions:
                cluster.center_lat, cluster.center_lng = _area_center(cluster.attractions)

        underfilled = [c for c in clusters if len(c.attractions) < target_min_per_day]
        if underfilled:
            best_cluster = _find_best_underfilled_cluster(attr, underfilled)
            if best_cluster.attractions and _distance_to_cluster(attr, best_cluster) > max_append_distance:
                logger.info(
                    "Skipped far POI '%s' for day %d (distance > %.1fkm)",
                    attr.get("name", ""), best_cluster.day_num, max_append_distance,
                )
                if attr_key:
                    skipped_far_keys.add(attr_key)
                continue
            best_cluster.attractions.append(attr)
            continue

        closest_idx = _find_closest_cluster(attr, clusters)
        if (
            len(clusters[closest_idx].attractions) < max_per_day
            and _distance_to_cluster(attr, clusters[closest_idx]) <= max_append_distance
        ):
            clusters[closest_idx].attractions.append(attr)
        else:
            min_cluster = min(clusters, key=lambda c: len(c.attractions))
            if min_cluster.attractions and _distance_to_cluster(attr, min_cluster) > max_append_distance:
                logger.info(
                    "Skipped far POI '%s' for fallback day %d (distance > %.1fkm)",
                    attr.get("name", ""), min_cluster.day_num, max_append_distance,
                )
                if attr_key:
                    skipped_far_keys.add(attr_key)
                continue
            if len(min_cluster.attractions) < max_per_day:
                min_cluster.attractions.append(attr)
    
    # Assign restaurants to clusters with cross-day deduplication
    target_restaurants = _target_restaurant_count(intent)
    assigned_restaurant_ids: set[str] = set()

    for cluster in clusters:
        if not cluster.center_lat or not cluster.center_lng:
            cluster.center_lat, cluster.center_lng = _area_center(cluster.attractions)

        close_restaurants = []
        fallback_restaurants = []
        for rest in restaurants:
            rest_id = _restaurant_identity(rest)
            if rest_id in assigned_restaurant_ids:
                continue  # Skip already-assigned restaurant

            combined, dist = _score_restaurant_for_cluster(cluster, rest)
            if dist > max_restaurant_distance:
                logger.info(
                    "Skipped far restaurant '%s' for day %d (distance %.1fkm > %.1fkm)",
                    rest.get("name", ""), cluster.day_num, dist, max_restaurant_distance,
                )
                continue
            target = close_restaurants if dist < 5.0 else fallback_restaurants
            target.append((combined, dist, rest))

        close_restaurants.sort(key=lambda x: x[0], reverse=True)
        fallback_restaurants.sort(key=lambda x: x[0], reverse=True)
        selected = close_restaurants[:target_restaurants]
        if len(selected) < target_restaurants:
            selected.extend(fallback_restaurants[:target_restaurants - len(selected)])

        if len(selected) < target_restaurants:
            reusable = []
            selected_ids = {_restaurant_identity(r) for _, _, r in selected}
            for rest in restaurants:
                rest_id = _restaurant_identity(rest)
                if rest_id in selected_ids:
                    continue
                combined, dist = _score_restaurant_for_cluster(cluster, rest)
                if dist > max_restaurant_distance:
                    continue
                reusable.append((combined - 50, dist, rest))
            reusable.sort(key=lambda x: x[0], reverse=True)
            selected.extend(reusable[:target_restaurants - len(selected)])

        cluster.restaurants = [r for _, _, r in selected]

        # Track assigned restaurant IDs to prevent cross-day duplicates
        for r in cluster.restaurants:
            rid = _restaurant_identity(r)
            if rid:
                assigned_restaurant_ids.add(rid)
    
    # ── Nightlife rotation ───────────────────────────────────────────────────
    nightlife = nightlife or []
    for cluster in clusters:
        if nightlife:
            nl = nightlife[(cluster.day_num - 1) % len(nightlife)]
            _, dist = _score_restaurant_for_cluster(cluster, nl)
            if dist <= max_restaurant_distance:
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
                attr_key = attr.get("id") or attr.get("name", "")
                if attr_key in skipped_far_keys:
                    continue
                if not any(attr in c.attractions for c in clusters):
                    cluster.attractions.append(attr)
                    break
    
    logger.info(f"Created {num_days} day clusters")
    for cluster in clusters:
        logger.info(f"  Day {cluster.day_num} ({cluster.theme}): {len(cluster.attractions)} attractions, {len(cluster.restaurants)} restaurants")
    
    return clusters
