"""AMap REST provider; raw responses are cached before normalization."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from ..cache import ProviderCache


class AmapProvider:
    def __init__(self, cache: ProviderCache | None = None) -> None:
        self.api_key = os.environ.get("AMAP_API_KEY") or os.environ.get(
            "AMAP_MAPS_API_KEY", ""
        )
        self.cache = cache or ProviderCache()
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self.min_interval = max(
            float(os.environ.get("AMAP_MIN_INTERVAL_SECONDS", "0.2")), 0.0
        )

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self, operation: str, path: str, params: dict[str, Any], ttl: int = 86400
    ) -> dict[str, Any]:
        cached = self.cache.get("amap", operation, params)
        if cached:
            return cached
        if not self.available:
            raise RuntimeError("AMAP_API_KEY is not configured")
        async with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            client = self._client or httpx.AsyncClient(timeout=15)
            self._client = client
            started = time.perf_counter()
            response = await client.get(
                f"https://restapi.amap.com{path}",
                params={"key": self.api_key, **params},
            )
            self._last_request = time.monotonic()
            if response.is_error:
                raise RuntimeError(
                    f"AMap {operation} failed with HTTP {response.status_code}"
                )
            body = response.json()
            latency = round((time.perf_counter() - started) * 1000)
            if str(body.get("status")) != "1":
                raise RuntimeError(
                    f"AMap {operation} failed: {body.get('info') or 'AMAP_ERROR'}"
                )
            return self.cache.put("amap", operation, params, body, ttl, latency)

    async def search_places(
        self, city: str, keywords: str, category: str = "", limit: int = 8
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "city": city,
            "keywords": keywords,
            "offset": min(max(limit, 1), 25),
            "page": 1,
            "extensions": "all",
            "citylimit": "true",
        }
        if category:
            params["types"] = category
        record = await self._request("place_search", "/v3/place/text", params)
        raw = record["response"].get("pois", [])
        places = [
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "type": item.get("type", ""),
                "address": item.get("address", ""),
                "area": item.get("adname") or item.get("business_area", ""),
                "location": item.get("location", ""),
                "alias": item.get("alias", ""),
                "rating": (item.get("biz_ext") or {}).get("rating", ""),
            }
            for item in raw[:limit]
        ]
        return {
            "places": places,
            "source": "amap",
            "cache_hit": record["cache_hit"],
            "response_hash": record["response_hash"],
        }

    async def place_detail(self, place_id: str) -> dict[str, Any]:
        record = await self._request(
            "place_detail",
            "/v3/place/detail",
            {"id": place_id, "extensions": "all"},
            ttl=7 * 86400,
        )
        places = record["response"].get("pois", [])
        return {
            "place": places[0] if places else None,
            "source": "amap",
            "cache_hit": record["cache_hit"],
            "response_hash": record["response_hash"],
        }

    async def weather(self, city: str) -> dict[str, Any]:
        record = await self._request(
            "weather_forecast",
            "/v3/weather/weatherInfo",
            {"city": city, "extensions": "all"},
            ttl=3 * 3600,
        )
        forecasts = record["response"].get("forecasts", [])
        casts = forecasts[0].get("casts", []) if forecasts else []
        return {
            "provider": "amap",
            "available": True,
            "city": city,
            "days": [
                {
                    "date": item.get("date", ""),
                    "condition": item.get("dayweather", ""),
                    "condition_night": item.get("nightweather", ""),
                    "high": item.get("daytemp"),
                    "low": item.get("nighttemp"),
                    "wind": item.get("daywind", ""),
                    "wind_power": item.get("daypower", ""),
                }
                for item in casts
            ],
            "cache_hit": record["cache_hit"],
            "response_hash": record["response_hash"],
        }

    async def route(
        self, city: str, origin: str, destination: str, mode: str = "driving"
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "strategy": 0,
        }
        if mode == "walking":
            path = "/v3/direction/walking"
        elif mode == "transit":
            path = "/v3/direction/transit/integrated"
            params.update({"city": city, "cityd": city, "nightflag": 0})
        else:
            path = "/v3/direction/driving"
        record = await self._request(f"route_{mode}", path, params, ttl=1800)
        route = record["response"].get("route", {})
        options = (
            route.get("transits", []) if mode == "transit" else route.get("paths", [])
        )
        first = options[0] if options else {}
        return {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "distance_meters": int(
                float(first.get("distance", route.get("distance", 0)) or 0)
            ),
            "duration_seconds": int(float(first.get("duration", 0) or 0)),
            "summary": first,
            "source": "amap",
            "cache_hit": record["cache_hit"],
            "response_hash": record["response_hash"],
        }
