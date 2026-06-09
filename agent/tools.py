"""Tools for the TourPass Agent — all local-first, Amap as fallback."""
from __future__ import annotations
import json
import logging
from typing import Any

import httpx

from .config import CPP_BACKEND_URL, AMAP_API_KEY
from .models import PoiInfo, HotelInfo

logger = logging.getLogger(__name__)

# ── HTTP client (reused across calls) ─────────────────────────────────────────

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


# ── C++ backend tools (local, <100ms) ─────────────────────────────────────────

async def search_pois(
    city: str,
    poi_type: str = "",
    area: str = "",
    keyword: str = "",
    limit: int = 50,
) -> list[PoiInfo]:
    """Search local POI database via C++ backend."""
    client = await get_client()
    params: dict[str, Any] = {"city": city, "limit": limit}
    if poi_type:
        params["type"] = poi_type
    if area:
        params["area"] = area

    try:
        resp = await client.get(f"{CPP_BACKEND_URL}/poi/browse", params=params)
        resp.raise_for_status()
        data = resp.json()
        pois = []
        for item in data.get("data", []):
            pois.append(PoiInfo(
                id=item.get("id", ""),
                name=item.get("name", ""),
                type=item.get("type", "attraction"),
                lat=item.get("lat", 0.0),
                lng=item.get("lng", 0.0),
                area=item.get("area", ""),
                popularity=item.get("popularity", 0.0),
                description=item.get("description", ""),
                recommendation=item.get("recommendation", ""),
                tags=item.get("tags", []),
                meal_type=item.get("meal_type", "main"),
            ))
        # keyword filter (client-side since backend doesn't support it)
        if keyword:
            kw = keyword.lower()
            pois = [p for p in pois if kw in p.name.lower() or kw in p.area.lower()
                    or kw in p.description.lower()]
        return pois
    except Exception as e:
        logger.error(f"search_pois failed: {e}")
        return []


async def search_hotels(
    city: str,
    area: str = "",
    limit: int = 20,
) -> list[HotelInfo]:
    """Search local hotel database via C++ backend."""
    client = await get_client()
    params: dict[str, Any] = {"city": city, "type": "hotel", "limit": limit}
    if area:
        params["area"] = area

    try:
        resp = await client.get(f"{CPP_BACKEND_URL}/poi/browse", params=params)
        resp.raise_for_status()
        data = resp.json()
        hotels = []
        for item in data.get("data", []):
            hotels.append(HotelInfo(
                id=item.get("id", ""),
                name=item.get("name", ""),
                area=item.get("area", ""),
                lat=item.get("lat", 0.0),
                lng=item.get("lng", 0.0),
                popularity=item.get("popularity", 0.0),
                description=item.get("description", ""),
                tags=item.get("tags", []),
            ))
        return hotels
    except Exception as e:
        logger.error(f"search_hotels failed: {e}")
        return []


async def get_poi_areas(city: str) -> list[dict]:
    """Get all areas with POI counts for a city."""
    client = await get_client()
    try:
        resp = await client.get(f"{CPP_BACKEND_URL}/poi/areas", params={"city": city})
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        logger.error(f"get_poi_areas failed: {e}")
        return []


async def get_travel_time(
    city: str,
    from_id: str,
    to_id: str,
) -> int:
    """Get travel minutes between two POIs from local commute graph.
    Returns minutes, or -1 if no edge found."""
    client = await get_client()
    try:
        resp = await client.get(
            f"{CPP_BACKEND_URL}/api/travel-time",
            params={"city": city, "from": from_id, "to": to_id},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("travelMinutes", -1)
    except Exception as e:
        logger.warning(f"get_travel_time failed ({from_id}->{to_id}): {e}")
        return -1


async def optimize_route(
    city: str,
    poi_ids: list[str],
    hotel_id: str = "",
    start_minutes: int = 540,
    end_minutes: int = 1260,
    pace: str = "标准",
) -> dict:
    """Call C++ Beam Search to optimize a day's route via dedicated API."""
    client = await get_client()
    # Convert minutes to time strings for C++ backend
    def _min_to_time(m):
        return f"{m // 60:02d}:{m % 60:02d}"

    payload = {
        "city": city,
        "must_visit": poi_ids,
        "days": 1,
        "start_time": _min_to_time(start_minutes),
        "end_time": _min_to_time(end_minutes),
        "pace": pace,
        "candidate_count": 1,
        "strategy": "balanced",
    }
    if hotel_id:
        payload["hotel_location"] = hotel_id

    try:
        resp = await client.post(
            f"{CPP_BACKEND_URL}/api/optimize-route",
            json=payload,
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"optimize_route via /api/optimize-route failed: {e}, trying /trip/plan")
        try:
            resp = await client.post(
                f"{CPP_BACKEND_URL}/trip/plan",
                json=payload,
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e2:
            logger.error(f"optimize_route fallback also failed: {e2}")
            return {}


async def get_city_guide(city: str) -> dict:
    """Get pre-generated city guide from C++ backend or local file."""
    client = await get_client()
    try:
        resp = await client.get(
            f"{CPP_BACKEND_URL}/city-guide",
            params={"city": city},
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    # Fallback: read local file
    import os
    guide_path = os.path.join("data", city, "city_guide.json")
    if os.path.exists(guide_path):
        with open(guide_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ── Amap supplementary tools (only when local data is insufficient) ───────────

async def amap_search_nearby(
    lat: float,
    lng: float,
    keyword: str = "",
    poi_type: str = "风景名胜",
    radius: int = 3000,
) -> list[dict]:
    """Search POIs near a location via Amap API. Used only as fallback."""
    if not AMAP_API_KEY:
        return []
    client = await get_client()
    try:
        resp = await client.get(
            "https://restapi.amap.com/v5/place/around",
            params={
                "key": AMAP_API_KEY,
                "location": f"{lng},{lat}",
                "keywords": keyword,
                "types": poi_type,
                "radius": radius,
                "page_size": 10,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("pois", [])
    except Exception as e:
        logger.error(f"amap_search_nearby failed: {e}")
        return []


async def get_weather(city: str) -> dict:
    """Get weather info. Uses Amap if key available, otherwise returns empty."""
    if not AMAP_API_KEY:
        return {}
    client = await get_client()
    try:
        # First get city adcode
        resp = await client.get(
            "https://restapi.amap.com/v3/config/district",
            params={"key": AMAP_API_KEY, "keywords": city, "subdistrict": 0},
        )
        resp.raise_for_status()
        districts = resp.json().get("districts", [])
        if not districts:
            return {}
        adcode = districts[0].get("adcode", "")
        if not adcode:
            return {}

        # Then get weather
        resp = await client.get(
            "https://restapi.amap.com/v3/weather/weatherInfo",
            params={"key": AMAP_API_KEY, "city": adcode},
        )
        resp.raise_for_status()
        lives = resp.json().get("lives", [])
        if lives:
            return lives[0]
        return {}
    except Exception as e:
        logger.error(f"get_weather failed: {e}")
        return {}



