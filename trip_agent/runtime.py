from __future__ import annotations

import os
from typing import Any

from .cache import ProviderCache
from .auth import AuthManager
from .context import MemoryPolicy
from .llm import OpenAICompatibleLLM
from .loop import TripAgent
from .reviewer import ItineraryReviewer
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
        reviewer = ItineraryReviewer(
            self.llm,
            shadow=os.environ.get("TRIP_AGENT_REVIEWER_SHADOW", "true").strip().lower()
            not in {"0", "false", "no"},
        )
        self.request_timeout_seconds = max(
            15.0,
            min(
                float(os.environ.get("TRIP_AGENT_RUN_TIMEOUT_SECONDS", "600")),
                600.0,
            ),
        )
        memory_policy = MemoryPolicy(
            history_messages=int(
                os.environ.get("TRIP_AGENT_MEMORY_HISTORY_MESSAGES", "4")
            ),
            message_chars=int(os.environ.get("TRIP_AGENT_MEMORY_MESSAGE_CHARS", "800")),
            plan_days=int(os.environ.get("TRIP_AGENT_MEMORY_PLAN_DAYS", "7")),
            schedule_items_per_day=int(
                os.environ.get("TRIP_AGENT_MEMORY_ITEMS_PER_DAY", "8")
            ),
            evidence_places=int(
                os.environ.get("TRIP_AGENT_MEMORY_EVIDENCE_PLACES", "24")
            ),
            evidence_routes=int(
                os.environ.get("TRIP_AGENT_MEMORY_EVIDENCE_ROUTES", "24")
            ),
        )
        self.agent = TripAgent(
            llm=self.llm,
            store=self.store,
            amap=self.amap,
            weather=self.weather,
            reviewer=(
                reviewer
                if os.environ.get("TRIP_AGENT_REVIEWER_ENABLED", "true").strip().lower()
                not in {"0", "false", "no"}
                else None
            ),
            max_steps=int(os.environ.get("TRIP_AGENT_MAX_STEPS", "24")),
            max_tool_calls=int(os.environ.get("TRIP_AGENT_MAX_TOOLS", "48")),
            max_submit_attempts=int(
                os.environ.get("TRIP_AGENT_MAX_SUBMIT_ATTEMPTS", "4")
            ),
            memory_policy=memory_policy,
        )
        log_event(
            "runtime_started",
            model=self.llm.model,
            wire_api=self.llm.wire_api,
            reasoning_effort=self.llm.reasoning_effort,
            final_reasoning_effort=self.llm.final_reasoning_effort,
            request_timeout_seconds=self.request_timeout_seconds,
            reviewer_enabled=self.agent.reviewer is not None,
            reviewer_shadow=reviewer.shadow,
            max_steps=self.agent.max_steps,
            max_tool_calls=self.agent.max_tool_calls,
            max_submit_attempts=self.agent.max_submit_attempts,
            memory_policy=self.agent.memory_policy.as_dict(),
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
