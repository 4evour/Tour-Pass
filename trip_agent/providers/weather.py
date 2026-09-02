from __future__ import annotations

import os
import time
from typing import Any

import httpx

from ..cache import ProviderCache

CITY_CODES = {
    "长沙": "101250101",
    "青岛": "101120201",
    "重庆": "101040100",
    "成都": "101270101",
    "杭州": "101210101",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280101",
    "深圳": "101280601",
}


class QWeatherProvider:
    def __init__(self, cache: ProviderCache | None = None) -> None:
        self.key = (
            os.environ.get("QWEATHER_KEY")
            or os.environ.get("QWEATHER_API_KEY")
            or os.environ.get("HEFENG_WEATHER_KEY", "")
        )
        self.host = os.environ.get("QWEATHER_API_HOST", "devapi.qweather.com")
        self.cache = cache or ProviderCache()
        self.client: httpx.AsyncClient | None = None

    @property
    def available(self) -> bool:
        return bool(self.key)

    async def close(self) -> None:
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    async def forecast(self, city: str, days: int = 3) -> dict[str, Any]:
        location = CITY_CODES.get(city)
        if not self.available or not location:
            return {"provider": "qweather", "available": False, "days": []}
        request = {"location": location, "days": min(max(days, 1), 7)}
        cached = self.cache.get("qweather", "forecast", request)
        if cached:
            return {
                "provider": "qweather",
                "available": True,
                "cache_hit": True,
                "response_hash": cached["response_hash"],
                "days": cached["response"].get("days", []),
            }
        self.client = self.client or httpx.AsyncClient(timeout=15)
        started = time.perf_counter()
        response = await self.client.get(
            f"https://{self.host}/v7/weather/{'7d' if days > 3 else '3d'}",
            params={"location": location, "key": self.key},
        )
        if response.is_error:
            raise RuntimeError(
                f"QWeather forecast failed with HTTP {response.status_code}"
            )
        body = response.json()
        if body.get("code") != "200":
            raise RuntimeError(
                f"QWeather forecast failed: {body.get('code', 'unknown')}"
            )
        normalized = {
            "days": [
                {
                    "date": item.get("fxDate", ""),
                    "condition": item.get("textDay", ""),
                    "condition_night": item.get("textNight", ""),
                    "high": item.get("tempMax"),
                    "low": item.get("tempMin"),
                    "precip": item.get("precip"),
                    "sunrise": item.get("sunrise", ""),
                    "sunset": item.get("sunset", ""),
                    "uv_index": item.get("uvIndex", ""),
                }
                for item in body.get("daily", [])[:days]
            ]
        }
        record = self.cache.put(
            "qweather",
            "forecast",
            request,
            normalized,
            3 * 3600,
            round((time.perf_counter() - started) * 1000),
        )
        return {
            "provider": "qweather",
            "available": True,
            "cache_hit": record["cache_hit"],
            "response_hash": record["response_hash"],
            **normalized,
        }


class WeatherProvider:
    def __init__(self, cache: ProviderCache | None = None, amap: Any = None) -> None:
        self.qweather = QWeatherProvider(cache)
        self.amap = amap

    @property
    def available(self) -> bool:
        return self.qweather.available or bool(
            self.amap is not None and self.amap.available
        )

    @property
    def provider_name(self) -> str:
        if self.qweather.available:
            return "qweather"
        if self.amap is not None and self.amap.available:
            return "amap"
        return "unavailable"

    async def close(self) -> None:
        await self.qweather.close()

    async def forecast(self, city: str, days: int = 3) -> dict[str, Any]:
        try:
            result = await self.qweather.forecast(city, days)
        except Exception as exc:
            if self.amap is None:
                raise
            result = {
                "provider": "qweather",
                "available": False,
                "fallback_reason": type(exc).__name__,
                "days": [],
            }
        if result.get("available"):
            return result
        if self.amap is None:
            return result
        fallback = await self.amap.weather(city)
        fallback["days"] = fallback.get("days", [])[:days]
        if result.get("fallback_reason"):
            fallback["fallback_from"] = "qweather"
            fallback["fallback_reason"] = result["fallback_reason"]
        return fallback
