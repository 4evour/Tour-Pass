"""Real weather API integration (QWeather / 和风天气)."""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

QWEATHER_KEY = (
    os.getenv("QWEATHER_KEY")
    or os.getenv("QWEATHER_API_KEY")
    or os.getenv("HEFENG_WEATHER_KEY")
    or ""
)
QWEATHER_GEO_URL = "https://geoapi.qweather.com/v2/city/lookup"
QWEATHER_WEATHER_URL = "https://devapi.qweather.com/v7/weather/3d"

# City name to QWeather location ID mapping (major cities)
_CITY_LOCATION_MAP = {
    "北京": "101010100", "上海": "101020100", "广州": "101280101",
    "深圳": "101280601", "成都": "101270101", "重庆": "101040100",
    "杭州": "101210101", "武汉": "101200101", "南京": "101190101",
    "西安": "101110101", "长沙": "101250101", "昆明": "101290101",
    "大理": "101290201", "丽江": "101290101", "三亚": "101310201",
    "桂林": "101300501", "厦门": "101230201", "青岛": "101120201",
    "哈尔滨": "101050101", "苏州": "101190401", "张家界": "101251101",
    "郑州": "101180101", "合肥": "101220101", "济南": "101120101",
    "福州": "101230101", "贵阳": "101260101", "南宁": "101300101",
    "兰州": "101160101", "太原": "101100101", "石家庄": "101090101",
}


def is_available() -> bool:
    """Check if weather API is configured."""
    return bool(QWEATHER_KEY)


def get_config_status() -> dict:
    """Return non-secret weather provider configuration status."""
    return {
        "provider": "qweather",
        "available": is_available(),
        "key_env": (
            "QWEATHER_KEY" if os.getenv("QWEATHER_KEY")
            else "QWEATHER_API_KEY" if os.getenv("QWEATHER_API_KEY")
            else "HEFENG_WEATHER_KEY" if os.getenv("HEFENG_WEATHER_KEY")
            else ""
        ),
    }


def _get_location_id(city: str) -> Optional[str]:
    """Get QWeather location ID for a city."""
    return _CITY_LOCATION_MAP.get(city)


async def fetch_weather(city: str, days: int = 3) -> list[dict]:
    """Fetch real weather forecast for a city.

    Returns list of daily forecasts, or empty list on failure.
    Each forecast: {date, temperature_high, temperature_low, condition,
                    humidity, wind_speed}
    """
    if not is_available():
        logger.info("QWeather API key not configured, skipping real weather")
        return []

    location_id = _get_location_id(city)
    if not location_id:
        logger.warning("No QWeather location ID for city: %s", city)
        return []

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                QWEATHER_WEATHER_URL,
                params={"location": location_id, "key": QWEATHER_KEY},
            )
            data = resp.json()

            if data.get("code") != "200":
                logger.warning("QWeather API error: %s", data.get("code"))
                return []

            forecasts = []
            for daily in data.get("daily", [])[:days]:
                forecasts.append({
                    "date": daily.get("fxDate", ""),
                    "temperature_high": int(daily.get("tempMax", 25)),
                    "temperature_low": int(daily.get("tempMin", 15)),
                    "condition": daily.get("textDay", "多云"),
                    "humidity": int(daily.get("humidity", 50)),
                    "wind_speed": int(daily.get("windSpeedDay", 10)),
                    "suggestion": "",  # To be filled by LLM
                })

            logger.info("Fetched %d day forecast for %s", len(forecasts), city)
            return forecasts

    except ImportError:
        logger.warning("httpx not installed, cannot fetch weather")
        return []
    except Exception as e:
        logger.warning("Weather API request failed: %s", e)
        return []
