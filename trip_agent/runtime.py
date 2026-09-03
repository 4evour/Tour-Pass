from __future__ import annotations

import os
from typing import Any

from .cache import ProviderCache
from .auth import AuthManager
from .llm import OpenAICompatibleLLM
from .loop import TripAgent
from .observability import close_logging, configure_logging, log_event
from .providers.amap import AmapProvider
from .providers.weather import WeatherProvider
from .store import TripStore


class TripRuntime:
    def __init__(self) -> None:
        self.logger = configure_logging(
            os.environ.get("TRIP_AGENT_LOG", "trip_agent/logs/planning.jsonl")
        )
        self.store = TripStore(
            os.environ.get("DATABASE_URL") or os.environ.get("TRIP_AGENT_STORE")
        )
        self.auth = AuthManager(self.store._sessions)
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
                float(os.environ.get("TRIP_AGENT_RUN_TIMEOUT_SECONDS", "600")),
                600.0,
            ),
        )
        self.agent = TripAgent(
            llm=self.llm,
            store=self.store,
            amap=self.amap,
            weather=self.weather,
            max_steps=int(os.environ.get("TRIP_AGENT_MAX_STEPS", "16")),
            max_tool_calls=int(os.environ.get("TRIP_AGENT_MAX_TOOLS", "20")),
        )
        log_event(
            "runtime_started",
            model=self.llm.model,
            wire_api=self.llm.wire_api,
            reasoning_effort=self.llm.reasoning_effort,
            final_reasoning_effort=self.llm.final_reasoning_effort,
            request_timeout_seconds=self.request_timeout_seconds,
        )

    async def close(self) -> None:
        await self.amap.close()
        await self.weather.close()
        await self.llm.close()
        self.store.close()
        log_event("runtime_stopped")
        close_logging()

    def health(self) -> dict[str, Any]:
        return {
            "llm": self.llm.available,
            "amap": self.amap.available,
            "weather": {
                "available": self.weather.available,
                "provider": self.weather.provider_name,
            },
            "cache": self.cache.stats(),
            "store": self.store.stats(),
            "database": self.store.engine.url.get_backend_name(),
        }
