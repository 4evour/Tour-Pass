"""Tour Pass Multi-Agent System - Route Optimization Tools.

Enhanced with:
- 2-opt local search improvement on nearest neighbor results
- edges.json real travel time lookup
- Multiple travel mode support
"""

import json
import logging
import math
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    R = 6371  # Earth radius in km
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def estimate_travel_time(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    mode: str = "walk",
) -> int:
    """Estimate travel time between two points.

    Args:
        from_lat, from_lng: Starting coordinates.
        to_lat, to_lng: Ending coordinates.
        mode: Travel mode ("walk", "transit", "drive").

    Returns:
        Estimated travel time in minutes.
    """
    distance_km = _haversine_km(from_lat, from_lng, to_lat, to_lng)

    speeds = {"walk": 5, "transit": 25, "drive": 40}
    speed = speeds.get(mode, 5)
    time_hours = distance_km / speed

    return max(int(time_hours * 60), 5)  # Minimum 5 minutes


# ---------------------------------------------------------------------------
# edges.json real travel time cache
# ---------------------------------------------------------------------------

_edges_cache: dict[str, dict[str, dict]] = {}  # city -> {"from_id-to_id": edge_data}


def load_edges_cache(city: str, data_dir: str = "data") -> dict[str, dict]:
    """Load edges.json for a city into the cache.

    Returns the edge lookup dict for the city.
    """
    if city in _edges_cache:
        return _edges_cache[city]

    edges_path = Path(data_dir) / city / "edges.json"
    if not edges_path.exists():
        _edges_cache[city] = {}
        return {}

    try:
        with open(edges_path, "r", encoding="utf-8") as f:
            edges_list = json.load(f)

        lookup = {}
        for edge in edges_list:
            src = edge.get("source", "")
            dst = edge.get("target", "")
            if src and dst:
                key = f"{src}-{dst}"
                lookup[key] = edge

        _edges_cache[city] = lookup
        logger.info("Loaded %d edges for %s", len(lookup), city)
        return lookup
    except Exception as e:
        logger.warning("Failed to load edges for %s: %s", city, e)
        _edges_cache[city] = {}
        return {}


def get_real_travel_time(
    city: str,
    from_id: str,
    to_id: str,
    from_lat: float = 0,
    from_lng: float = 0,
    to_lat: float = 0,
    to_lng: float = 0,
    data_dir: str = "data",
) -> int:
    """Get travel time between two POIs, preferring edges.json data.

    Args:
        city: City name (directory name).
        from_id: Source POI ID.
        to_id: Target POI ID.
        from_lat, from_lng: Source coordinates (fallback).
        to_lat, to_lng: Target coordinates (fallback).
        data_dir: Data directory path.

    Returns:
        Travel time in minutes.
    """
    edges = load_edges_cache(city, data_dir)
    key = f"{from_id}-{to_id}"

    edge = edges.get(key)
    if edge:
        # edges.json has duration_minutes or distance_m
        duration = edge.get("duration_minutes")
        if duration and duration > 0:
            return int(duration)
        # Fallback: estimate from distance
        distance_m = edge.get("distance_m")
        if distance_m and distance_m > 0:
            return max(int(distance_m / 1000 / 5 * 60), 5)  # walk speed

    # Fallback: haversine estimate
    if from_lat and from_lng and to_lat and to_lng:
        return estimate_travel_time(from_lat, from_lng, to_lat, to_lng)

    return 30  # default


# ---------------------------------------------------------------------------
# 2-opt route improvement
# ---------------------------------------------------------------------------


def _build_distance_matrix(stops: list[dict]) -> list[list[float]]:
    """Build pairwise distance matrix for a list of stops."""
    n = len(stops)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = _haversine_km(
                stops[i].get("lat", 0), stops[i].get("lng", 0),
                stops[j].get("lat", 0), stops[j].get("lng", 0),
            )
            matrix[i][j] = d
            matrix[j][i] = d
    return matrix


def _route_distance(stops: list[dict], dist_matrix: list[list[float]]) -> float:
    """Calculate total route distance through ordered stops."""
    total = 0.0
    for i in range(len(stops) - 1):
        total += dist_matrix[i][i + 1]
    return total


def optimize_route_2opt(stops: list[dict]) -> list[dict]:
    """Improve route order using 2-opt local search.

    Takes the output of nearest neighbor and iteratively reverses
    sub-segments to reduce total distance.

    Args:
        stops: Ordered list of stop dicts with lat/lng.

    Returns:
        Improved ordered list of stops.
    """
    if len(stops) <= 2:
        return stops

    # Filter to stops with valid coordinates
    valid = [(i, s) for i, s in enumerate(stops) if s.get("lat") and s.get("lng")]
    if len(valid) <= 2:
        return stops

    valid_stops = [s for _, s in valid]
    n = len(valid_stops)

    dist_matrix = _build_distance_matrix(valid_stops)
    current_dist = _route_distance(valid_stops, dist_matrix)

    improved = True
    max_iterations = 50  # Prevent long loops
    iteration = 0

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1

        for i in range(1, n - 1):
            for j in range(i + 1, n):
                # Calculate distance change from reversing segment [i, j]
                # Old edges: (i-1, i) and (j, j+1)
                # New edges: (i-1, j) and (i, j+1)
                old_dist = dist_matrix[i - 1][i] + dist_matrix[j][min(j + 1, n - 1)]
                new_dist = dist_matrix[i - 1][j] + dist_matrix[i][min(j + 1, n - 1)]

                if new_dist < old_dist - 0.001:  # threshold to avoid floating point noise
                    # Reverse the segment
                    valid_stops[i: j + 1] = valid_stops[i: j + 1][::-1]
                    improved = True

        new_dist = _route_distance(valid_stops, dist_matrix)
        if new_dist < current_dist - 0.001:
            logger.info("2-opt improved route: %.1f km -> %.1f km", current_dist, new_dist)
            current_dist = new_dist
        else:
            break

    # Reconstruct full stops list (preserving invalid stops)
    result = []
    valid_idx = 0
    for i, s in enumerate(stops):
        if s.get("lat") and s.get("lng"):
            result.append(valid_stops[valid_idx])
            valid_idx += 1
        else:
            result.append(s)

    return result


# ---------------------------------------------------------------------------
# Main route optimization
# ---------------------------------------------------------------------------


def optimize_route(
    start_lat: float,
    start_lng: float,
    stops: list[dict],
    end_lat: Optional[float] = None,
    end_lng: Optional[float] = None,
    use_2opt: bool = True,
) -> list[dict]:
    """Optimize route order using nearest neighbor + optional 2-opt improvement.

    Args:
        start_lat, start_lng: Starting point coordinates.
        stops: List of stop dictionaries with lat/lng.
        end_lat, end_lng: Optional ending point (e.g., hotel).
        use_2opt: Whether to apply 2-opt improvement after nearest neighbor.

    Returns:
        Reordered list of stops.
    """
    if len(stops) <= 1:
        return stops

    # Filter stops with valid coordinates
    valid_stops = [s for s in stops if s.get("lat") and s.get("lng")]
    invalid_stops = [s for s in stops if not s.get("lat") or not s.get("lng")]

    if not valid_stops:
        return stops

    # Step 1: Nearest neighbor
    ordered = []
    remaining = valid_stops.copy()
    current_lat, current_lng = start_lat, start_lng

    while remaining:
        nearest = min(
            remaining,
            key=lambda s: _haversine_km(
                current_lat, current_lng, s["lat"], s["lng"]
            ),
        )
        ordered.append(nearest)
        remaining.remove(nearest)
        current_lat, current_lng = nearest["lat"], nearest["lng"]

    # Step 2: 2-opt improvement
    if use_2opt and len(ordered) > 2:
        ordered = optimize_route_2opt(ordered)

    # Add invalid stops at the end
    ordered.extend(invalid_stops)

    return ordered


def calculate_total_travel_time(stops: list[dict], mode: str = "walk") -> int:
    """Calculate total travel time for a route.

    Args:
        stops: Ordered list of stops with lat/lng.
        mode: Travel mode.

    Returns:
        Total travel time in minutes.
    """
    if len(stops) <= 1:
        return 0

    total_time = 0
    for i in range(len(stops) - 1):
        from_stop = stops[i]
        to_stop = stops[i + 1]

        if (
            from_stop.get("lat")
            and from_stop.get("lng")
            and to_stop.get("lat")
            and to_stop.get("lng")
        ):
            time = estimate_travel_time(
                from_stop["lat"],
                from_stop["lng"],
                to_stop["lat"],
                to_stop["lng"],
                mode,
            )
            total_time += time

    return total_time
