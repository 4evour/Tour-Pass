"""XHS (小红书) Route Data Loader.

Loads crawled Xiaohongshu travel route data and provides:
- Raw route loading with in-memory caching
- Popular POI frequency extraction (for PoiAgent scoring boost)
- POI co-occurrence matrix extraction (for SchedulerAgent affinity)
"""

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level cache
_route_cache: dict[str, list[dict]] = {}

try:
    from agents.constants import CITY_DIR_MAP
except Exception:
    CITY_DIR_MAP = {}


def _normalize_city_dir(city: str) -> str:
    city_key = (city or "").strip()
    if not city_key:
        return ""
    return CITY_DIR_MAP.get(city_key, city_key.lower())


def _route_stop_names(route: dict) -> list[str]:
    names: list[str] = []
    for day_plan in route.get("itinerary", []):
        for stop in day_plan.get("stops", []):
            name = (stop.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def load_routes(city: str, data_dir: str = "data") -> list[dict]:
    """Load XHS routes for a city from ``data/{city}/xhs_routes.json``.

    Results are cached in memory.  Returns an empty list when the file
    does not exist or is invalid.
    """
    city_key = _normalize_city_dir(city)
    if city_key in _route_cache:
        return _route_cache[city_key]

    city_dir = Path(data_dir) / city_key
    route_file = city_dir / "xhs_routes.json"
    if not route_file.exists():
        logger.info("No XHS routes found for %s", city)
        _route_cache[city_key] = []
        return []

    try:
        with open(route_file, "r", encoding="utf-8") as f:
            routes = json.load(f)
        if not isinstance(routes, list):
            routes = []
        _route_cache[city_key] = routes
        logger.info("Loaded %d XHS routes for %s", len(routes), city_key)
        return routes
    except Exception as e:
        logger.warning("Failed to load XHS routes for %s: %s", city, e)
        _route_cache[city_key] = []
        return []


def extract_popular_pois(
    city: str,
    days: Optional[int] = None,
    data_dir: str = "data",
) -> dict[str, int]:
    """Count how often each POI name appears across all XHS routes.

    Parameters
    ----------
    city : str
        City key (e.g. ``"beijing"``).
    days : int, optional
        If provided, only consider routes whose ``days`` field matches
        (±1 day tolerance).  ``None`` means use all routes.
    data_dir : str
        Root data directory.

    Returns
    -------
    dict[str, int]
        Mapping of POI name → occurrence count.
    """
    routes = load_routes(city, data_dir)
    if not routes:
        return {}

    counter: Counter[str] = Counter()
    for route in routes:
        route_days = route.get("days", 0)
        if days is not None and abs(route_days - days) > 1:
            continue
        for day_plan in route.get("itinerary", []):
            for stop in day_plan.get("stops", []):
                name = (stop.get("name") or "").strip()
                if name:
                    counter[name] += 1

    logger.info(
        "XHS popular POIs for %s: %d unique names from %d routes",
        city, len(counter), len(routes),
    )
    return dict(counter)


def summarize_route(route: dict) -> dict:
    """Return a compact route summary for prompt context and evaluation."""
    stops = _route_stop_names(route)
    return {
        "source_title": route.get("source_title", ""),
        "source_url": route.get("source_url", ""),
        "days": route.get("days", 0),
        "travel_style": route.get("travel_style", ""),
        "route_summary": route.get("route_summary", ""),
        "tags": route.get("tags", [])[:8],
        "stops": stops[:20],
    }


def select_reference_routes(
    city: str,
    days: Optional[int] = None,
    interests: Optional[list[str]] = None,
    must_visit: Optional[list[str]] = None,
    top_k: int = 5,
    data_dir: str = "data",
) -> list[dict]:
    """Select high-signal XHS routes as scheduling context.

    Routes are used as references only. They provide POI overlap,
    same-day co-occurrence, and summary cues; generated itineraries
    should not copy them verbatim.
    """
    routes = load_routes(city, data_dir)
    if not routes:
        return []

    interests = [i.lower() for i in (interests or []) if i]
    must_visit = [m for m in (must_visit or []) if m]
    scored: list[tuple[float, dict]] = []

    for route in routes:
        route_days = int(route.get("days") or 0)
        score = 0.0
        if days:
            day_delta = abs(route_days - days)
            score += max(0, 30 - day_delta * 12)

        stop_names = _route_stop_names(route)
        route_text = " ".join([
            route.get("route_summary", ""),
            route.get("travel_style", ""),
            " ".join(route.get("tags", []) or []),
            " ".join(stop_names),
        ]).lower()

        for interest in interests:
            if interest and interest in route_text:
                score += 8

        for mv in must_visit:
            if any(mv in name or name in mv for name in stop_names):
                score += 18

        try:
            likes = int(str(route.get("source_likes", "0")).replace(",", ""))
        except ValueError:
            likes = 0
        if likes > 0:
            score += min(20, likes ** 0.5 / 4)

        if route.get("route_summary"):
            score += 5
        if stop_names:
            score += min(8, len(stop_names) / 2)

        scored.append((score, route))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = []
    for score, route in scored[:max(1, top_k)]:
        summary = summarize_route(route)
        summary["score"] = round(score, 2)
        selected.append(summary)
    return selected


def extract_cooccurrence(
    city: str,
    data_dir: str = "data",
) -> dict[tuple[str, str], int]:
    """Build a POI co-occurrence matrix from XHS routes.

    Two POIs *co-occur* when they appear in the **same day** of a route.
    The returned dict maps ``(name_a, name_b)`` (sorted alphabetically)
    to the number of routes where they share a day.

    Parameters
    ----------
    city : str
        City key.
    data_dir : str
        Root data directory.

    Returns
    -------
    dict[tuple[str, str], int]
        Co-occurrence counts.
    """
    routes = load_routes(city, data_dir)
    if not routes:
        return {}

    cooccur: Counter[tuple[str, str]] = Counter()
    for route in routes:
        for day_plan in route.get("itinerary", []):
            names = [
                (s.get("name") or "").strip()
                for s in day_plan.get("stops", [])
            ]
            names = [n for n in names if n]
            # All unique pairs within the same day
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    pair = tuple(sorted((names[i], names[j])))
                    cooccur[pair] += 1

    logger.info(
        "XHS co-occurrence for %s: %d pairs", city, len(cooccur),
    )
    return dict(cooccur)


def match_poi_name(poi_name: str, xhs_pois: dict[str, int]) -> int:
    """Fuzzy-match a POI name against XHS frequency data.

    Uses a *contains* strategy: if the POI name contains an XHS name
    or vice-versa, the match succeeds.  Returns the frequency count
    for the best match, or 0 if no match.
    """
    if not poi_name or not xhs_pois:
        return 0

    best = 0
    for xhs_name, freq in xhs_pois.items():
        if poi_name in xhs_name or xhs_name in poi_name:
            best = max(best, freq)
    return best
