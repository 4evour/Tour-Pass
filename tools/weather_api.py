"""Real weather API integration (QWeather / 和风天气).

Provides three data-fetching functions:
- fetch_weather: daily forecast with rich fields (sunrise/sunset, UV, precip, etc.)
- fetch_weather_indices: travel/UV/clothing/sports/cold-risk indices
- fetch_weather_warnings: active severe weather alerts

Configuration defaults come from agents.config, but key/host values are
resolved at call time so tests and reloads can update environment aliases.
"""
import logging
import os
from typing import Optional

import httpx

from agents import config as agent_config

logger = logging.getLogger(__name__)

# City name → QWeather location ID mapping (all 21 supported cities + extras)
_CITY_LOCATION_MAP = {
    "北京": "101010100", "上海": "101020100", "广州": "101280101",
    "深圳": "101280601", "成都": "101270101", "重庆": "101040100",
    "杭州": "101210101", "武汉": "101200101", "南京": "101190101",
    "西安": "101110101", "长沙": "101250101", "昆明": "101290101",
    "大理": "101290201", "丽江": "101291401", "三亚": "101310201",
    "桂林": "101300501", "厦门": "101230201", "青岛": "101120201",
    "哈尔滨": "101050101", "苏州": "101190401", "张家界": "101251101",
    "郑州": "101180101", "合肥": "101220101", "济南": "101120101",
    "福州": "101230101", "贵阳": "101260101", "南宁": "101300101",
    "兰州": "101160101", "太原": "101100101", "石家庄": "101090101",
}

# Weather indices type IDs most relevant for travel planning
# type=6: Travel Index (旅游指数)
# type=5: UV Index (紫外线指数)
# type=3: Clothing Index (穿衣指数)
# type=1: Sports Index (运动指数)
# type=9: Cold Risk Index (感冒指数)
_TRAVEL_INDICES_TYPES = "1,3,5,6,9"

# Mapping from indices type ID to a friendly key name
_INDICES_TYPE_MAP = {
    "1": "sports_index",
    "3": "clothing_index",
    "5": "uv_index_detail",
    "6": "travel_index",
    "9": "cold_risk_index",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """Check if weather API is configured."""
    return bool(_qweather_key())


def get_config_status() -> dict:
    """Return non-secret weather provider configuration status."""
    return {
        "provider": "qweather",
        "available": is_available(),
        "key_configured": bool(_qweather_key()),
    }


def _get_location_id(city: str) -> Optional[str]:
    """Get QWeather location ID for a city."""
    return _CITY_LOCATION_MAP.get(city)


def _qweather_key() -> str:
    """Resolve QWeather key from current env, then config defaults."""
    return (
        os.environ.get("QWEATHER_KEY")
        or os.environ.get("QWEATHER_API_KEY")
        or os.environ.get("HEFENG_WEATHER_KEY")
        or getattr(agent_config, "QWEATHER_KEY", "")
        or ""
    )


def _qweather_host() -> str:
    """Resolve QWeather API host from current env, then config defaults."""
    return (
        os.environ.get("QWEATHER_API_HOST")
        or getattr(agent_config, "QWEATHER_API_HOST", "")
        or "devapi.qweather.com"
    )


def _qweather_url(path: str) -> str:
    return f"https://{_qweather_host()}{path}"


def _safe_int(value, default: int = 0) -> int:
    """Safely convert a value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 1. Daily Forecast (rich fields)
# ---------------------------------------------------------------------------

async def fetch_weather(city: str, days: int = 3) -> list[dict]:
    """Fetch real weather forecast for a city.

    Returns list of daily forecasts with rich fields, or empty list on failure.
    Each forecast dict contains:
        date, temperature_high, temperature_low, condition, condition_night,
        humidity, wind_speed, wind_dir, wind_scale,
        sunrise, sunset, uv_index, precip, vis, pressure, cloud
    """
    if not is_available():
        logger.info("QWeather API key not configured, skipping real weather")
        return []

    api_key = _qweather_key()
    location_id = _get_location_id(city)
    if not location_id:
        logger.warning("No QWeather location ID for city: %s", city)
        return []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _qweather_url("/v7/weather/3d"),
                params={"location": location_id, "key": api_key},
            )
            data = resp.json()

            if data.get("code") != "200":
                logger.warning("QWeather API error: %s", data.get("code") or data.get("error", {}).get("title", "unknown"))
                return []

            forecasts = []
            for daily in data.get("daily", [])[:days]:
                forecasts.append({
                    # Core fields (backward compatible)
                    "date": daily.get("fxDate", ""),
                    "temperature_high": _safe_int(daily.get("tempMax"), 25),
                    "temperature_low": _safe_int(daily.get("tempMin"), 15),
                    "condition": daily.get("textDay", "多云"),
                    "condition_night": daily.get("textNight", ""),
                    "humidity": _safe_int(daily.get("humidity"), 50),
                    "wind_speed": _safe_int(daily.get("windSpeedDay"), 10),
                    # NEW: Extended fields
                    "wind_dir": daily.get("windDirDay", ""),
                    "wind_scale": daily.get("windScaleDay", ""),
                    "sunrise": daily.get("sunrise", ""),
                    "sunset": daily.get("sunset", ""),
                    "uv_index": _safe_int(daily.get("uvIndex"), 0),
                    "precip": _safe_float(daily.get("precip"), 0.0),
                    "vis": _safe_int(daily.get("vis"), 25),
                    "pressure": _safe_int(daily.get("pressure"), 1013),
                    "cloud": _safe_int(daily.get("cloud"), 0),
                    # Filled by WeatherAgent
                    "suggestion": "",
                })

            logger.info("Fetched %d-day forecast for %s", len(forecasts), city)
            return forecasts

    except ImportError:
        logger.warning("httpx not installed, cannot fetch weather")
        return []
    except Exception as e:
        logger.warning("Weather API request failed for %s: %s", city, e)
        return []


# ---------------------------------------------------------------------------
# 2. Weather Indices (旅游指数 / 紫外线 / 穿衣 / 运动 / 感冒)
# ---------------------------------------------------------------------------

async def fetch_weather_indices(city: str, days: int = 3) -> dict[str, dict[str, dict]]:
    """Fetch weather life indices for a city.

    Returns a nested dict: {date_str: {index_key: {level, category, text}}}
    where index_key is one of: travel_index, clothing_index, uv_index_detail,
    sports_index, cold_risk_index.

    Returns empty dict on failure.
    """
    if not is_available():
        return {}

    api_key = _qweather_key()
    location_id = _get_location_id(city)
    if not location_id:
        return {}

    try:
        days_param = "3d" if days >= 3 else "1d"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _qweather_url(f"/v7/indices/{days_param}"),
                params={
                    "location": location_id,
                    "key": api_key,
                    "type": _TRAVEL_INDICES_TYPES,
                },
            )
            data = resp.json()

            if data.get("code") != "200":
                logger.warning("QWeather indices API error: %s", data.get("code") or data.get("error", {}).get("title", "unknown"))
                return {}

            # Group by date
            result: dict[str, dict[str, dict]] = {}
            for item in data.get("daily", []):
                date = item.get("date", "")
                type_id = item.get("type", "")
                index_key = _INDICES_TYPE_MAP.get(type_id, "")
                if not date or not index_key:
                    continue

                result.setdefault(date, {})[index_key] = {
                    "level": item.get("level", ""),
                    "category": item.get("category", ""),
                    "text": item.get("text", ""),
                }

            logger.info(
                "Fetched weather indices for %s: %d dates",
                city, len(result),
            )
            return result

    except Exception as e:
        logger.warning("Weather indices request failed for %s: %s", city, e)
        return {}


# ---------------------------------------------------------------------------
# 3. Weather Warnings (灾害预警)
# ---------------------------------------------------------------------------

async def fetch_weather_warnings(city: str) -> list[dict]:
    """Fetch active severe weather warnings for a city.

    Returns a list of warning dicts, each containing:
        title, level, type_name, pub_time, text
    Returns empty list on failure or no active warnings.
    """
    if not is_available():
        return []

    api_key = _qweather_key()
    location_id = _get_location_id(city)
    if not location_id:
        return []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _qweather_url("/v7/warning/now"),
                params={"location": location_id, "key": api_key},
            )
            data = resp.json()

            if data.get("code") != "200":
                logger.warning("QWeather warning API error: %s", data.get("code") or data.get("error", {}).get("title", "unknown"))
                return []

            warnings = []
            for w in data.get("warning", []):
                warnings.append({
                    "title": w.get("title", ""),
                    "level": w.get("level", ""),
                    "type_name": w.get("typeName", ""),
                    "pub_time": w.get("pubTime", ""),
                    "text": (w.get("text", "") or "")[:200],  # Truncate long texts
                })

            if warnings:
                logger.info(
                    "Fetched %d active weather warning(s) for %s",
                    len(warnings), city,
                )
            return warnings

    except Exception as e:
        logger.warning("Weather warnings request failed for %s: %s", city, e)
        return []
