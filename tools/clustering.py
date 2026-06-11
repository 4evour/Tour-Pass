"""Tour Pass Multi-Agent System - Geographic Clustering Tools.

Adapted from legacy agent/clustering.py with enhancements.
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


def _infer_theme(pois: list[dict]) -> str:
    """Infer a theme for a cluster of POIs based on their tags."""
    tag_counts = defaultdict(int)
    
    for poi in pois:
        for tag in poi.get("tags", []):
            if tag not in {"城市游览", "景点", "风景名胜"}:
                tag_counts[tag] += 1
    
    if not tag_counts:
        return "综合游览"
    
    # Get top 2 tags
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:2]
    return "·".join(tag for tag, _ in top_tags)


def cluster_pois_for_days(
    scored_attractions: list[dict],
    restaurants: list[dict],
    num_days: int,
    intent: dict,
) -> list[DayCluster]:
    """Cluster POIs into day groups based on geographic proximity.
    
    Args:
        scored_attractions: List of scored attraction POIs.
        restaurants: List of restaurant POIs.
        num_days: Number of days.
        intent: User intent dictionary.
    
    Returns:
        List of DayCluster objects, one per day.
    """
    if not scored_attractions:
        return [DayCluster(day_num=i+1, theme="自由活动") for i in range(num_days)]
    
    # Initialize clusters
    clusters = [DayCluster(day_num=i+1, theme="") for i in range(num_days)]
    
    # Separate must-visit and regular attractions
    must_visit = [a for a in scored_attractions if a.get("is_must_visit")]
    regular = [a for a in scored_attractions if not a.get("is_must_visit")]
    
    # Distribute must-visit attractions evenly across days
    for i, attr in enumerate(must_visit):
        day_idx = i % num_days
        clusters[day_idx].attractions.append(attr)
    
    # Assign regular attractions to closest clusters
    for attr in regular:
        # Calculate current cluster centers
        for cluster in clusters:
            if cluster.attractions:
                cluster.center_lat, cluster.center_lng = _area_center(cluster.attractions)
        
        # Find closest cluster
        closest_idx = _find_closest_cluster(attr, clusters)
        
        # Balance: limit attractions per day based on pace
        pace = intent.get("pace", "balanced")
        max_per_day = {"relaxed": 4, "balanced": 6, "intense": 8}.get(pace, 6)
        
        if len(clusters[closest_idx].attractions) < max_per_day:
            clusters[closest_idx].attractions.append(attr)
        else:
            # Find cluster with fewest attractions
            min_cluster = min(clusters, key=lambda c: len(c.attractions))
            min_cluster.attractions.append(attr)
    
    # Assign restaurants to clusters based on location
    for cluster in clusters:
        if not cluster.center_lat or not cluster.center_lng:
            cluster.center_lat, cluster.center_lng = _area_center(cluster.attractions)
        
        # Find closest restaurants
        cluster_restaurants = []
        for rest in restaurants:
            rest_lat = rest.get("lat", 0)
            rest_lng = rest.get("lng", 0)
            
            if not rest_lat or not rest_lng:
                continue
            
            dist = _haversine_km(
                cluster.center_lat, cluster.center_lng,
                rest_lat, rest_lng
            )
            
            if dist < 5.0:  # Within 5km
                cluster_restaurants.append((dist, rest))
        
        # Sort by distance and take top 3
        cluster_restaurants.sort(key=lambda x: x[0])
        cluster.restaurants = [r for _, r in cluster_restaurants[:3]]
    
    # Infer themes
    for cluster in clusters:
        cluster.theme = _infer_theme(cluster.attractions)
    
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
