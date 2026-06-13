"""Shared constants and utility functions for all agents."""

import math

# ---------------------------------------------------------------------------
# City name mappings
# ---------------------------------------------------------------------------

CITY_DIR_MAP: dict[str, str] = {
    "广州": "guangzhou",
    "北京": "beijing",
    "上海": "shanghai",
    "深圳": "shenzhen",
    "成都": "chengdu",
    "重庆": "chongqing",
    "杭州": "hangzhou",
    "武汉": "wuhan",
    "南京": "nanjing",
    "西安": "xian",
    "长沙": "changsha",
    "昆明": "kunming",
    "大理": "dali",
    "丽江": "lijiang",
    "三亚": "sanya",
    "桂林": "guilin",
    "厦门": "xiamen",
    "青岛": "qingdao",
    "哈尔滨": "harbin",
    "苏州": "suzhou",
    "张家界": "zhangjiajie",
}

# Reverse mapping: English -> Chinese
DIR_CITY_MAP: dict[str, str] = {v: k for k, v in CITY_DIR_MAP.items()}

# English city names that users might type
ENGLISH_CITY_MAP: dict[str, str] = {
    "guangzhou": "广州",
    "beijing": "北京",
    "shanghai": "上海",
    "shenzhen": "深圳",
    "chengdu": "成都",
    "chongqing": "重庆",
    "hangzhou": "杭州",
    "wuhan": "武汉",
    "nanjing": "南京",
    "xian": "西安",
    "changsha": "长沙",
    "kunming": "昆明",
    "dali": "大理",
    "lijiang": "丽江",
    "sanya": "三亚",
    "guilin": "桂林",
    "xiamen": "厦门",
    "qingdao": "青岛",
    "harbin": "哈尔滨",
    "suzhou": "苏州",
    "zhangjiajie": "张家界",
}

# All supported Chinese city names (for text matching)
KNOWN_CITIES: list[str] = list(CITY_DIR_MAP.keys())


# ---------------------------------------------------------------------------
# Geo utilities
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two (lat, lng) points in kilometres."""
    R = 6371.0
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def compute_center(points: list[dict]) -> tuple[float, float]:
    """Compute the geographic centre of a list of dicts with lat/lng keys."""
    valid = [p for p in points if p.get("lat") and p.get("lng")]
    if not valid:
        return 0.0, 0.0
    avg_lat = sum(p["lat"] for p in valid) / len(valid)
    avg_lng = sum(p["lng"] for p in valid) / len(valid)
    return avg_lat, avg_lng


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402


def resolve_city_dir(data_dir: Path, city: str) -> Path:
    """Return the data directory path for a given city name."""
    # Try Chinese name directly
    candidate = data_dir / city
    if candidate.exists():
        return candidate
    # Map Chinese -> English
    eng = CITY_DIR_MAP.get(city, city.lower())
    return data_dir / eng


def load_pois_by_type(data_dir: Path, city: str, poi_type: str) -> list[dict]:
    """Load POIs of a specific type from a city's pois.json."""
    import json
    import logging

    city_dir = resolve_city_dir(data_dir, city)
    poi_file = city_dir / "pois.json"
    if not poi_file.exists():
        return []
    try:
        with open(poi_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [p for p in data if p.get("type") == poi_type]
    except Exception as e:
        logging.getLogger(__name__).error("Failed to load POIs for %s: %s", city, e)
        return []
