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
# Chinese city name to English directory name mapping
_CITY_DIR_MAP = {
    "北京": "beijing", "上海": "shanghai", "广州": "guangzhou", "深圳": "shenzhen",
    "成都": "chengdu", "重庆": "chongqing", "杭州": "hangzhou", "武汉": "wuhan",
    "南京": "nanjing", "西安": "xian", "长沙": "changsha", "昆明": "kunming",
    "大理": "dali", "丽江": "lijiang", "三亚": "sanya", "桂林": "guilin",
    "厦门": "xiamen", "青岛": "qingdao", "哈尔滨": "harbin", "苏州": "suzhou",
    "张家界": "zhangjiajie",
}


def _resolve_city_dir(city: str) -> str:
    """Resolve Chinese city name to English directory name."""
    if city in _CITY_DIR_MAP:
        return _CITY_DIR_MAP[city]
    # Try lowercase match
    lower = city.lower()
    for cn, en in _CITY_DIR_MAP.items():
        if lower == en:
            return en
    return city


def _load_pois_from_file(city: str, poi_type: str = "", keyword: str = "", limit: int = 50) -> list[PoiInfo]:
    """Load POIs directly from data/{city}/pois.json as fallback."""
    import os
    city_dir = _resolve_city_dir(city)
    pois_path = os.path.join("data", city_dir, "pois.json")
    if not os.path.exists(pois_path):
        logger.warning(f"No local POI data for {city}")
        return []
    try:
        with open(pois_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        pois = []
        for item in raw_data:
            ptype = item.get("type", "attraction")
            if poi_type and ptype != poi_type:
                continue
            pois.append(PoiInfo(
                id=item.get("id", ""),
                name=item.get("name", ""),
                type=ptype,
                lat=item.get("lat", 0.0),
                lng=item.get("lng", 0.0),
                area=item.get("area", ""),
                popularity=item.get("popularity", 0.0),
                description=item.get("description", ""),
                recommendation=item.get("recommendation", ""),
                tags=item.get("tags", []),
                meal_type=item.get("meal_type", "main"),
            ))
        # Sort by popularity descending
        pois.sort(key=lambda x: x.popularity, reverse=True)
        # Keyword filter
        if keyword:
            kw = keyword.lower()
            pois = [p for p in pois if kw in p.name.lower() or kw in p.area.lower()
                    or kw in p.description.lower()]
        logger.info(f"Loaded {len(pois)} POIs from local file for {city}")
        return pois[:limit]
    except Exception as e:
        logger.error(f"Failed to load local POIs for {city}: {e}")
        return []



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
        if pois:
            return pois
        # Backend returned empty data, try local JSON fallback
        logger.info(f"Backend returned 0 POIs for {city}, trying local JSON fallback")
    except Exception as e:
        logger.warning(f"search_pois backend failed: {e}, trying local JSON fallback")

    # Fallback: load directly from data/{city}/pois.json
    return _load_pois_from_file(city, poi_type, keyword, limit)


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
                price_level=item.get("price_level", 1),
                price_range=item.get("price_range", ""),
                star_rating=item.get("star_rating", 0),
                brand_category=item.get("brand_category", ""),
                description=item.get("description", ""),
                tags=item.get("tags", []),
            ))
        if hotels:
            return hotels
        logger.info(f"Backend returned 0 hotels for {city}, trying local JSON fallback")
    except Exception as e:
        logger.warning(f"search_hotels backend failed: {e}, trying local JSON fallback")

    # Fallback: load directly from data/{city}/pois.json
    return _load_hotels_from_file(city, limit)


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



def _load_hotels_from_file(city: str, limit: int = 20) -> list[HotelInfo]:
    """Load hotels directly from data/{city}/pois.json as fallback."""
    import os
    city_dir = _resolve_city_dir(city)
    pois_path = os.path.join("data", city_dir, "pois.json")
    if not os.path.exists(pois_path):
        return []
    try:
        with open(pois_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        hotels = []
        for item in raw_data:
            if item.get("type") != "hotel":
                continue
            hotels.append(HotelInfo(
                id=item.get("id", ""),
                name=item.get("name", ""),
                area=item.get("area", ""),
                lat=item.get("lat", 0.0),
                lng=item.get("lng", 0.0),
                popularity=item.get("popularity", 0.0),
                price_level=item.get("price_level", 1),
                price_range=item.get("price_range", ""),
                star_rating=item.get("star_rating", 0),
                brand_category=item.get("brand_category", ""),
                description=item.get("description", ""),
                tags=item.get("tags", []),
            ))
        hotels.sort(key=lambda x: x.popularity, reverse=True)
        logger.info(f"Loaded {len(hotels)} hotels from local file for {city}")
        return hotels[:limit]
    except Exception as e:
        logger.error(f"Failed to load local hotels for {city}: {e}")
        return []

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




