"""Shared high-de AMap Web API client with request-level QPS control."""

from __future__ import annotations

import asyncio
import os
from time import monotonic
from typing import Any

import httpx

from planner.errors import EvidenceError


class AmapClient:
    def __init__(
        self, api_key: str | None = None, client: httpx.AsyncClient | None = None
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else os.environ.get("AMAP_API_KEY", "")
        )
        self._client = client
        self._owns_client = client is None
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._request_cache: dict[tuple[str, tuple[tuple[str, str], ...]], dict] = {}
        self.min_interval_seconds = max(
            float(os.environ.get("AMAP_MIN_INTERVAL_SECONDS", "1.05")), 0.0
        )

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def begin_request(self) -> None:
        self._request_cache.clear()

    async def close(self) -> None:
        if self._owns_client and self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def request(self, path: str, params: dict[str, Any]) -> dict:
        if not self.api_key:
            raise EvidenceError("AMap API key is not configured")
        clean_params = {
            key: str(value) for key, value in params.items() if value not in (None, "")
        }
        cache_key = (path, tuple(sorted(clean_params.items())))
        if cache_key in self._request_cache:
            return self._request_cache[cache_key]

        async with self._lock:
            wait_seconds = self.min_interval_seconds - (
                monotonic() - self._last_request
            )
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            client = await self._get_client()
            for attempt in range(3):
                response = await client.get(
                    f"https://restapi.amap.com{path}",
                    params={"key": self.api_key, **clean_params},
                )
                response.raise_for_status()
                data = response.json()
                self._last_request = monotonic()
                if str(data.get("status")) == "1":
                    self._request_cache[cache_key] = data
                    return data
                info = str(data.get("info") or "AMAP_ERROR")
                if (
                    info in {"CUQPS_HAS_EXCEEDED_THE_LIMIT", "DAILY_QUERY_OVER_LIMIT"}
                    and attempt < 2
                ):
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                raise EvidenceError(f"AMap request failed: {info}")
        raise EvidenceError("AMap request failed")

    async def search_text(
        self, city: str, keywords: str, page_size: int = 10
    ) -> list[dict]:
        data = await self.request(
            "/v3/place/text",
            {
                "city": city,
                "keywords": keywords,
                "offset": min(max(page_size, 1), 25),
                "page": 1,
                "extensions": "all",
                "citylimit": "true",
            },
        )
        return data.get("pois", []) if isinstance(data.get("pois"), list) else []

    async def place_detail(self, source_id: str) -> dict | None:
        if not source_id:
            return None
        data = await self.request(
            "/v3/place/detail", {"id": source_id, "extensions": "all"}
        )
        pois = data.get("pois", [])
        return pois[0] if isinstance(pois, list) and pois else None

    async def route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        mode: str,
        city: str,
    ) -> dict:
        origin_text = f"{origin[1]},{origin[0]}"
        destination_text = f"{destination[1]},{destination[0]}"
        if mode == "walking":
            return await self.request(
                "/v3/direction/walking",
                {"origin": origin_text, "destination": destination_text},
            )
        if mode == "transit":
            return await self.request(
                "/v3/direction/transit/integrated",
                {
                    "origin": origin_text,
                    "destination": destination_text,
                    "city": city,
                    "cityd": city,
                    "strategy": 0,
                    "nightflag": 0,
                },
            )
        return await self.request(
            "/v3/direction/driving",
            {
                "origin": origin_text,
                "destination": destination_text,
                "strategy": 0,
                "extensions": "base",
            },
        )

    async def weather(self, city: str) -> list[dict]:
        district = await self.request(
            "/v3/config/district", {"keywords": city, "subdistrict": 0}
        )
        districts = district.get("districts", [])
        if not districts:
            return []
        adcode = districts[0].get("adcode", "")
        if not adcode:
            return []
        data = await self.request(
            "/v3/weather/weatherInfo", {"city": adcode, "extensions": "all"}
        )
        forecasts = data.get("forecasts", [])
        if not forecasts:
            return []
        casts = forecasts[0].get("casts", [])
        return casts if isinstance(casts, list) else []
