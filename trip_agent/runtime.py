from __future__ import annotations

import os
from typing import Any

from .cache import ProviderCache
from .llm import OpenAICompatibleLLM
from .loop import TripAgent
from .providers.amap import AmapProvider
from .providers.weather import WeatherProvider


class TripRuntime:
    def __init__(self) -> None:
        cache = ProviderCache(
            os.environ.get("TRIP_AGENT_CACHE", "trip_agent/runtime-cache.sqlite")
        )
        self.cache = cache
        self.amap = AmapProvider(cache)
        self.weather = WeatherProvider(cache, amap=self.amap)
        self.llm = OpenAICompatibleLLM()
        self.request_timeout_seconds = max(
            15.0,
            min(
                float(os.environ.get("TRIP_AGENT_RUN_TIMEOUT_SECONDS", "300")),
                600.0,
            ),
        )
        self.agent = TripAgent(
            llm=self.llm,
            amap=self.amap,
            weather=self.weather,
            max_steps=int(os.environ.get("TRIP_AGENT_MAX_STEPS", "16")),
            max_tool_calls=int(os.environ.get("TRIP_AGENT_MAX_TOOLS", "20")),
        )

    async def close(self) -> None:
        await self.amap.close()
        await self.weather.close()
        await self.llm.close()

    def health(self) -> dict[str, Any]:
        return {
            "llm": self.llm.available,
            "amap": self.amap.available,
            "weather": {
                "available": self.weather.available,
                "provider": self.weather.provider_name,
            },
            "cache": self.cache.stats(),
        }
