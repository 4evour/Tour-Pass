from __future__ import annotations

import os
from typing import Any

from .cache import ProviderCache
from .auth import AuthManager
from .context import MemoryPolicy
from .llm import OpenAICompatibleLLM
from .loop import TripAgent
from .observability import close_logging, configure_logging, log_event
from .providers.amap import AmapProvider
from .providers.rail import Rail12306Provider
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
        self.rail = Rail12306Provider(cache)
        self.weather = WeatherProvider(cache, amap=self.amap)
        self.llm = OpenAICompatibleLLM()
        self.request_timeout_seconds = max(
            15.0,
            min(
                float(os.environ.get("TRIP_AGENT_RUN_TIMEOUT_SECONDS", "180")),
                180.0,
            ),
        )
        memory_policy = MemoryPolicy(
            history_messages=int(
                os.environ.get("TRIP_AGENT_MEMORY_HISTORY_MESSAGES", "6")
            ),
            message_chars=int(
                os.environ.get("TRIP_AGENT_MEMORY_MESSAGE_CHARS", "4000")
            ),
            plan_days=int(os.environ.get("TRIP_AGENT_MEMORY_PLAN_DAYS", "30")),
            schedule_items_per_day=int(
                os.environ.get("TRIP_AGENT_MEMORY_ITEMS_PER_DAY", "8")
            ),
            evidence_places=int(
                os.environ.get("TRIP_AGENT_MEMORY_EVIDENCE_PLACES", "40")
            ),
            evidence_routes=int(
                os.environ.get("TRIP_AGENT_MEMORY_EVIDENCE_ROUTES", "40")
            ),
        )
        self.agent = TripAgent(
            llm=self.llm,
            store=self.store,
            amap=self.amap,
            weather=self.weather,
            rail=self.rail,
            memory_policy=memory_policy,
            max_provider_calls=int(
                os.environ.get("TRIP_AGENT_MAX_PROVIDER_CALLS", "18")
            ),
        )
        log_event(
            "runtime_started",
            model=self.llm.model,
            wire_api=self.llm.wire_api,
            reasoning_effort=self.llm.reasoning_effort,
            request_timeout_seconds=self.request_timeout_seconds,
            workflow="single_model_deterministic",
            max_model_calls=1,
            max_provider_calls=self.agent.max_provider_calls,
            reviewer_enabled=False,
            memory_policy=self.agent.memory_policy.as_dict(),
        )

    async def close(self) -> None:
        await self.amap.close()
        await self.rail.close()
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
            "rail": {
                "available": self.rail.available,
                "provider": "rail12306",
                "mode": "read_only_timetable",
            },
            "cache": self.cache.stats(),
            "store": self.store.stats(),
            "database": self.store.engine.url.get_backend_name(),
        }
