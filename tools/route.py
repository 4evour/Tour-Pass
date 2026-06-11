"""Tour Pass Multi-Agent System - Route Optimization Tools.

Simple route optimization using nearest neighbor heuristic.
"""

import math
from typing import Optional


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    R = 6371  # Earth radius in km
    
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


def estimate_travel_time(
    from_lat: float, from_lng: float,
    to_lat: float, to_lng: float,
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
    
    # Average speeds (km/h)
    speeds = {
        "walk": 5,
        "transit": 25,
        "drive": 40,
    }
    
    speed = speeds.get(mode, 5)
    time_hours = distance_km / speed
    
    return max(int(time_hours * 60), 5)  # Minimum 5 minutes


def optimize_route(
    start_lat: float, start_lng: float,
    stops: list[dict],
    end_lat: Optional[float] = None,
    end_lng: Optional[float] = None,
) -> list[dict]:
    """Optimize route order using nearest neighbor heuristic.
    
    Args:
        start_lat, start_lng: Starting point coordinates.
        stops: List of stop dictionaries with lat/lng.
        end_lat, end_lng: Optional ending point (e.g., hotel).
    
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
    
    # Nearest neighbor algorithm
    ordered = []
    remaining = valid_stops.copy()
    current_lat, current_lng = start_lat, start_lng
    
    while remaining:
        # Find nearest stop
        nearest = min(
            remaining,
            key=lambda s: _haversine_km(
                current_lat, current_lng,
                s["lat"], s["lng"]
            )
        )
        
        ordered.append(nearest)
        remaining.remove(nearest)
        current_lat, current_lng = nearest["lat"], nearest["lng"]
    
    # Add invalid stops at the end
    ordered.extend(invalid_stops)
    
    return ordered


def calculate_total_travel_time(
    stops: list[dict],
    mode: str = "walk",
) -> int:
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
        
        if from_stop.get("lat") and from_stop.get("lng") and to_stop.get("lat") and to_stop.get("lng"):
            time = estimate_travel_time(
                from_stop["lat"], from_stop["lng"],
                to_stop["lat"], to_stop["lng"],
                mode
            )
            total_time += time
    
    return total_time
