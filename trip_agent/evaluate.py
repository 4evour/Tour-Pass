from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from dotenv import load_dotenv

from .cache import ProviderCache
from .context import MemoryPolicy
from .llm import OpenAICompatibleLLM
from .loop import SKELETON_PROMPT, TripAgent
from .model_schema import itinerary_skeleton_output_format
from .observability import close_logging, configure_logging
from .providers.amap import AmapProvider
from .providers.rail import Rail12306Provider
from .providers.weather import WeatherProvider
from .store import TripStore

DEFAULT_REQUESTS = [
    {
        "id": "changsha-loop",
        "city": "长沙",
        "message": (
            "请规划长沙1天行程。住五一广场住宿区，必去岳麓山、橘子洲；"
            "09:00至20:00，节奏标准，优先公共交通和步行。"
            "所有地点必须核验，提供真实通勤并回到住宿区。"
        ),
        "trip": {
            "destination": "长沙",
            "days": 1,
            "date_range": {"start": None, "end": None},
            "hotel_area": "五一广场住宿区",
            "travellers": "",
            "pace": "balanced",
            "transport_preference": "public_transit",
            "budget": "",
            "must_visits": ["岳麓山", "橘子洲"],
            "notes": "所有地点必须核验，提供真实通勤并回到住宿区。",
            "interests": [],
            "daily_window": {"start": "09:00", "end": "20:00"},
        },
    },
    {
        "id": "qingdao-loop",
        "city": "青岛",
        "message": (
            "请规划青岛1天行程。住五四广场住宿区，必去栈桥、八大关；"
            "09:00至19:30，节奏轻松，少走回头路。"
            "所有地点必须核验，提供真实通勤并回到住宿区。"
        ),
        "trip": {
            "destination": "青岛",
            "days": 1,
            "date_range": {"start": None, "end": None},
            "hotel_area": "五四广场住宿区",
            "travellers": "",
            "pace": "relaxed",
            "transport_preference": "public_transit",
            "budget": "",
            "must_visits": ["栈桥", "八大关"],
            "notes": "少走回头路，所有地点必须核验并回到住宿区。",
            "interests": [],
            "daily_window": {"start": "09:00", "end": "19:30"},
        },
    },
    {
        "id": "chongqing-loop",
        "city": "重庆",
        "message": (
            "请规划重庆1天行程。住解放碑住宿区，必去李子坝、洪崖洞；"
            "10:00至21:00，节奏标准，尽量少步行。"
            "所有地点必须核验，提供真实通勤并回到住宿区。"
        ),
        "trip": {
            "destination": "重庆",
            "days": 1,
            "date_range": {"start": None, "end": None},
            "hotel_area": "解放碑住宿区",
            "travellers": "",
            "pace": "balanced",
            "transport_preference": "taxi",
            "budget": "",
            "must_visits": ["李子坝", "洪崖洞"],
            "notes": "尽量少步行，所有地点必须核验并回到住宿区。",
            "interests": [],
            "daily_window": {"start": "10:00", "end": "21:00"},
        },
    },
]


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_hash(path: str) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _request_signature(
    messages: list[dict[str, Any]], kwargs: dict[str, Any]
) -> dict[str, Any]:
    options = {
        key: value
        for key, value in kwargs.items()
        if key
        in {
            "output_format",
            "reasoning_effort",
            "tool_choice",
            "tools",
            "prompt_cache_key",
            "model",
        }
        and (key != "model" or value is not None)
    }
    return {"messages": _json_copy(messages), "options": _json_copy(options)}


class RecordingLLM:
    def __init__(self, inner: OpenAICompatibleLLM) -> None:
        self.inner = inner
        self.calls: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def ainvoke(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        signature = _request_signature(messages, kwargs)
        record: dict[str, Any] = {
            "index": len(self.calls) + 1,
            "purpose": "skeleton",
            "request_hash": _json_hash(signature),
            "request": signature,
        }
        self.calls.append(record)
        started_at = time.perf_counter()
        try:
            response = await self.inner.ainvoke(messages, **kwargs)
        except Exception as exc:
            record["elapsed_ms"] = round((time.perf_counter() - started_at) * 1000)
            record["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            raise
        record["elapsed_ms"] = round((time.perf_counter() - started_at) * 1000)
        record["response"] = {
            "content": response.content,
            "tool_calls": _json_copy(getattr(response, "tool_calls", [])),
            "metrics": _json_copy(getattr(response, "metrics", {})),
        }
        return response

    async def close(self) -> None:
        await self.inner.close()


class ReplayLLM:
    requires_decision_wrapper = False

    def __init__(
        self,
        calls: list[dict[str, Any]],
        model: str,
        reasoning_effort: str,
        final_reasoning_effort: str,
    ) -> None:
        self.calls = calls
        self.cursor = 0
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.final_reasoning_effort = final_reasoning_effort

    async def ainvoke(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        if self.cursor >= len(self.calls):
            raise RuntimeError("Replay LLM recording exhausted")
        record = self.calls[self.cursor]
        self.cursor += 1
        signature = _request_signature(messages, kwargs)
        actual_hash = _json_hash(signature)
        if actual_hash != record["request_hash"]:
            raise RuntimeError(
                f"Replay LLM request mismatch at call {self.cursor}: "
                f"{actual_hash} != {record['request_hash']}"
            )
        if record.get("error"):
            raise RuntimeError(record["error"]["message"])
        response = record["response"]
        return SimpleNamespace(
            content=response.get("content", ""),
            tool_calls=_json_copy(response.get("tool_calls", [])),
            metrics=_json_copy(response.get("metrics", {})),
        )

    async def close(self) -> None:
        return None


class RecordingProvider:
    def __init__(self, inner: Any, name: str) -> None:
        self.inner = inner
        self.name = name
        self.calls: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return bool(self.inner.available)

    @property
    def provider_name(self) -> str:
        return str(getattr(self.inner, "provider_name", self.name))

    async def _call(
        self,
        method: str,
        arguments: dict[str, Any],
        operation: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "index": len(self.calls) + 1,
            "provider": self.name,
            "method": method,
            "arguments": _json_copy(arguments),
            "request_hash": _json_hash({"method": method, "arguments": arguments}),
        }
        self.calls.append(record)
        started_at = time.perf_counter()
        try:
            result = await operation()
        except Exception as exc:
            record["elapsed_ms"] = round((time.perf_counter() - started_at) * 1000)
            record["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            raise
        record["elapsed_ms"] = round((time.perf_counter() - started_at) * 1000)
        record["result"] = _json_copy(result)
        return result

    async def close(self) -> None:
        await self.inner.close()


class RecordingAmap(RecordingProvider):
    def __init__(self, inner: AmapProvider) -> None:
        super().__init__(inner, "amap")

    def __getattr__(self, name: str) -> Any:
        if name == "resolve_search_city" and callable(getattr(self.inner, name, None)):
            return self._resolve_search_city
        raise AttributeError(name)

    async def _resolve_search_city(self, destination: str) -> dict[str, Any]:
        arguments = {"destination": destination}
        return await self._call(
            "resolve_search_city",
            arguments,
            lambda: self.inner.resolve_search_city(**arguments),
        )

    async def search_places(
        self,
        city: str,
        keywords: str,
        category: str = "",
        limit: int = 8,
    ) -> dict[str, Any]:
        arguments = {
            "city": city,
            "keywords": keywords,
            "category": category,
            "limit": limit,
        }
        return await self._call(
            "search_places",
            arguments,
            lambda: self.inner.search_places(**arguments),
        )

    async def place_detail(self, place_id: str) -> dict[str, Any]:
        arguments = {"place_id": place_id}
        return await self._call(
            "place_detail",
            arguments,
            lambda: self.inner.place_detail(**arguments),
        )

    async def route(
        self,
        city: str,
        origin: str,
        destination: str,
        mode: str = "driving",
    ) -> dict[str, Any]:
        arguments = {
            "city": city,
            "origin": origin,
            "destination": destination,
            "mode": mode,
        }
        return await self._call(
            "route",
            arguments,
            lambda: self.inner.route(**arguments),
        )

    async def weather(self, city: str) -> dict[str, Any]:
        arguments = {"city": city}
        return await self._call(
            "weather",
            arguments,
            lambda: self.inner.weather(**arguments),
        )


class RecordingWeather(RecordingProvider):
    def __init__(self, inner: WeatherProvider) -> None:
        super().__init__(inner, "weather")

    async def forecast(self, city: str, days: int = 3) -> dict[str, Any]:
        arguments = {"city": city, "days": days}
        return await self._call(
            "forecast",
            arguments,
            lambda: self.inner.forecast(**arguments),
        )


class RecordingRail(RecordingProvider):
    def __init__(self, inner: Rail12306Provider) -> None:
        super().__init__(inner, "rail")

    async def search_trains(
        self,
        *,
        travel_date: str,
        from_station: str,
        to_station: str,
        preferred_departure: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        arguments = {
            "travel_date": travel_date,
            "from_station": from_station,
            "to_station": to_station,
            "preferred_departure": preferred_departure,
            "limit": limit,
        }
        return await self._call(
            "search_trains",
            arguments,
            lambda: self.inner.search_trains(**arguments),
        )


class ReplayProvider:
    def __init__(self, calls: list[dict[str, Any]], name: str) -> None:
        self.calls = calls
        self.name = name
        self.cursor = 0

    @property
    def available(self) -> bool:
        return True

    @property
    def provider_name(self) -> str:
        return self.name

    async def _result(self, method: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.cursor >= len(self.calls):
            raise RuntimeError(f"Replay {self.name} recording exhausted")
        record = self.calls[self.cursor]
        self.cursor += 1
        actual_hash = _json_hash({"method": method, "arguments": arguments})
        if method != record["method"] or actual_hash != record["request_hash"]:
            raise RuntimeError(
                f"Replay {self.name} request mismatch at call {self.cursor}"
            )
        if record.get("error"):
            raise RuntimeError(record["error"]["message"])
        return _json_copy(record["result"])

    async def close(self) -> None:
        return None


class ReplayAmap(ReplayProvider):
    def __init__(self, calls: list[dict[str, Any]]) -> None:
        super().__init__(calls, "amap")

    def __getattr__(self, name: str) -> Any:
        # Old recordings did not exercise region resolution; retain that behavior.
        if name == "resolve_search_city" and any(
            call.get("method") == name for call in self.calls
        ):
            return self._resolve_search_city
        raise AttributeError(name)

    async def _resolve_search_city(self, destination: str) -> dict[str, Any]:
        return await self._result("resolve_search_city", {"destination": destination})

    async def search_places(
        self,
        city: str,
        keywords: str,
        category: str = "",
        limit: int = 8,
    ) -> dict[str, Any]:
        return await self._result(
            "search_places",
            {
                "city": city,
                "keywords": keywords,
                "category": category,
                "limit": limit,
            },
        )

    async def place_detail(self, place_id: str) -> dict[str, Any]:
        return await self._result("place_detail", {"place_id": place_id})

    async def route(
        self,
        city: str,
        origin: str,
        destination: str,
        mode: str = "driving",
    ) -> dict[str, Any]:
        return await self._result(
            "route",
            {
                "city": city,
                "origin": origin,
                "destination": destination,
                "mode": mode,
            },
        )

    async def weather(self, city: str) -> dict[str, Any]:
        return await self._result("weather", {"city": city})


class ReplayWeather(ReplayProvider):
    def __init__(self, calls: list[dict[str, Any]]) -> None:
        super().__init__(calls, "weather")

    async def forecast(self, city: str, days: int = 3) -> dict[str, Any]:
        return await self._result("forecast", {"city": city, "days": days})


class ReplayRail(ReplayProvider):
    def __init__(self, calls: list[dict[str, Any]]) -> None:
        super().__init__(calls, "rail")

    async def search_trains(
        self,
        *,
        travel_date: str,
        from_station: str,
        to_station: str,
        preferred_departure: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        return await self._result(
            "search_trains",
            {
                "travel_date": travel_date,
                "from_station": from_station,
                "to_station": to_station,
                "preferred_departure": preferred_departure,
                "limit": limit,
            },
        )


def _quality_metrics(plan: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {
            "schedule_item_count": 0,
            "verified_entity_count": 0,
            "entity_binding_rate": 0.0,
            "route_count": 0,
            "verified_route_count": 0,
            "route_evidence_rate": 0.0,
            "must_visit_count": 0,
            "must_visit_covered": 0,
            "must_visit_coverage_rate": 0.0,
            "opening_checked_count": 0,
            "opening_verification_rate": 0.0,
            "unresolved_schedule_item_count": 0,
            "unknown_walking_segments": 0,
            "guide_explanation_coverage": 0.0,
            "first_step_available": False,
        }

    def key(value: Any) -> str:
        return "".join(
            character
            for character in str(value or "").casefold()
            if character.isalnum()
        )

    days = [item for item in plan.get("days") or [] if isinstance(item, dict)]
    schedule = [
        item
        for day in days
        for item in day.get("schedule") or []
        if isinstance(item, dict)
    ]
    physical = [item for item in schedule if item.get("type") in {"visit", "meal"}]
    verified_entities = [
        item
        for item in physical
        if item.get("source") == "amap"
        and item.get("place_id")
        and item.get("location")
    ]
    unresolved = [
        item
        for item in physical
        if not (
            item.get("source") == "amap"
            and item.get("place_id")
            and item.get("location")
        )
    ]
    transfers = [
        transfer
        for day in days
        for transfer in day.get("transfers") or []
        if isinstance(transfer, dict)
    ]
    verified_routes = [
        item
        for item in transfers
        if item.get("source") == "amap"
        and item.get("evidence_refs")
        and int(item.get("duration_minutes") or 0) > 0
    ]
    context = plan.get("planning_context")
    context = context if isinstance(context, dict) else {}
    must_visits = [item for item in context.get("must_visits") or [] if str(item)]
    visit_names = [
        key(item.get("name")) for item in schedule if item.get("type") == "visit"
    ]
    must_visit_covered = sum(
        any(key(required) in name or name in key(required) for name in visit_names)
        for required in must_visits
    )
    opening_checked = [
        item for item in physical if item.get("opening_match") in {"matched", "risk"}
    ]
    mobility_summary = plan.get("mobility_summary")
    mobility_summary = mobility_summary if isinstance(mobility_summary, dict) else {}
    guide_ready = [
        item
        for item in physical
        if str(item.get("reason") or "").strip()
        and (
            item.get("practical_tips") or str(item.get("reason") or "").count("。") >= 1
        )
    ]
    first_day = days[0] if days else {}
    first_step_available = bool(
        next(
            (
                item
                for item in first_day.get("schedule") or []
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ),
            None,
        )
    )
    return {
        "schedule_item_count": len(physical),
        "verified_entity_count": len(verified_entities),
        "entity_binding_rate": round(len(verified_entities) / len(physical), 4)
        if physical
        else 0.0,
        "route_count": len(transfers),
        "verified_route_count": len(verified_routes),
        "route_evidence_rate": round(len(verified_routes) / len(transfers), 4)
        if transfers
        else 0.0,
        "must_visit_count": len(must_visits),
        "must_visit_covered": must_visit_covered,
        "must_visit_coverage_rate": round(must_visit_covered / len(must_visits), 4)
        if must_visits
        else 1.0,
        "opening_checked_count": len(opening_checked),
        "opening_verification_rate": round(len(opening_checked) / len(physical), 4)
        if physical
        else 0.0,
        "unresolved_schedule_item_count": len(unresolved),
        "unknown_walking_segments": int(
            mobility_summary.get("walking_distance_unknown") or 0
        ),
        "guide_explanation_coverage": round(len(guide_ready) / len(physical), 4)
        if physical
        else 0.0,
        "first_step_available": first_step_available,
    }


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def _trace_metrics(
    events: list[dict[str, Any]], recording: dict[str, Any]
) -> dict[str, Any]:
    """Summarize the deterministic trace without pretending it is a full DAG."""
    durations = [int(event.get("elapsed_ms") or 0) for event in events]
    provider_calls = [
        call for name in ("amap", "weather", "rail") for call in recording.get(name, [])
    ]
    provider_latencies = [int(call.get("elapsed_ms") or 0) for call in provider_calls]
    stage_pairs = {
        "model": ("model_started", "model_finished"),
        "validation": ("plan_validation_started", "plan_validation_finished"),
    }
    stage_elapsed: dict[str, int] = {}
    for name, (start_type, finish_type) in stage_pairs.items():
        start = next(
            (event for event in events if event.get("type") == start_type), None
        )
        finish = next(
            (event for event in events if event.get("type") == finish_type), None
        )
        if start and finish:
            stage_elapsed[name] = max(
                0,
                int(finish.get("elapsed_ms") or 0) - int(start.get("elapsed_ms") or 0),
            )
    return {
        "trace_wall_clock_ms": max(durations) if durations else 0,
        "stage_elapsed_ms": stage_elapsed,
        "provider_latency_p50_ms": _percentile(provider_latencies, 0.50),
        "provider_latency_p95_ms": _percentile(provider_latencies, 0.95),
        "provider_error_rate": round(
            sum(bool(call.get("error")) for call in provider_calls)
            / len(provider_calls),
            4,
        )
        if provider_calls
        else 0.0,
        "provider_cache_hit_rate": round(
            sum(
                bool((call.get("result") or {}).get("cache_hit"))
                for call in provider_calls
            )
            / len(provider_calls),
            4,
        )
        if provider_calls
        else 0.0,
        "event_type_counts": {
            event_type: sum(event.get("type") == event_type for event in events)
            for event_type in sorted(
                {event.get("type") for event in events if event.get("type")}
            )
        },
    }


def _summarize(
    response: Any,
    recording: dict[str, Any],
    elapsed_ms: int,
) -> dict[str, Any]:
    events = response.events
    validations = [
        event for event in events if event.get("type") == "plan_validation_finished"
    ]
    final_validation = validations[-1] if validations else {}
    hard_history = [event.get("hard_failure_codes", []) for event in validations]
    warnings = final_validation.get("warning_codes", [])
    llm_calls = recording["llm"]
    provider_calls = [
        call for name in ("amap", "weather", "rail") for call in recording.get(name, [])
    ]

    def usage_value(call: dict[str, Any], key: str) -> int:
        return int(
            (
                (call.get("response") or {}).get("metrics", {}).get("usage", {}) or {}
            ).get(key, 0)
            or 0
        )

    input_tokens = sum(usage_value(call, "input_tokens") for call in llm_calls)
    output_tokens = sum(usage_value(call, "output_tokens") for call in llm_calls)
    cached_input_tokens = sum(
        usage_value(call, "input_tokens_details.cached_tokens") for call in llm_calls
    )
    repair_events = [
        event for event in events if event.get("type") == "plan_repair_applied"
    ]
    repair_reasons: dict[str, int] = {}
    for event in repair_events:
        for repair in event.get("repairs") or []:
            if not isinstance(repair, dict):
                continue
            reason = str(repair.get("reason") or "unknown")
            repair_reasons[reason] = repair_reasons.get(reason, 0) + 1
    required_stop_repairs = repair_reasons.get("add_required_stop", 0)
    tool_started = [event for event in events if event.get("type") == "tool_started"]
    tool_finished = [event for event in events if event.get("type") == "tool_finished"]
    tool_errors = [event for event in tool_finished if event.get("error")]
    quality_metrics = _quality_metrics(response.plan)
    trace_metrics = _trace_metrics(events, recording)
    started_call_ids = [str(event.get("call_id") or "") for event in tool_started]
    finished_call_ids = [str(event.get("call_id") or "") for event in tool_finished]
    tool_call_lifecycle_complete = bool(
        tool_started
        and all(started_call_ids)
        and all(finished_call_ids)
        and len(started_call_ids) == len(finished_call_ids)
        and set(started_call_ids) == set(finished_call_ids)
    )
    event_indexes = [event.get("event_index") for event in events]
    event_trace_complete = bool(
        events
        and all(event.get("trace_id") == events[0].get("trace_id") for event in events)
        and event_indexes == list(range(1, len(events) + 1))
        and len({event.get("event_id") for event in events}) == len(events)
    )
    return {
        "success": response.plan is not None,
        "elapsed_ms": elapsed_ms,
        "reply": response.reply,
        "semantic_result_hash": _json_hash(
            {"reply": response.reply, "plan": response.plan}
        ),
        "planner_llm_calls": sum(call["purpose"] == "skeleton" for call in llm_calls),
        "llm_elapsed_ms": sum(int(call.get("elapsed_ms", 0)) for call in llm_calls),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "non_cached_input_tokens": max(0, input_tokens - cached_input_tokens),
        "provider_calls": len(provider_calls),
        "provider_elapsed_ms": sum(
            int(call.get("elapsed_ms", 0)) for call in provider_calls
        ),
        "provider_cache_hits": sum(
            bool((call.get("result") or {}).get("cache_hit")) for call in provider_calls
        ),
        "repair_count": sum(repair_reasons.values()),
        "repair_reasons": dict(sorted(repair_reasons.items())),
        "required_stop_repairs": required_stop_repairs,
        "tool_started": len(tool_started),
        "tool_finished": len(tool_finished),
        "tool_errors": len(tool_errors),
        "tool_cache_hits": sum(bool(event.get("cache_hit")) for event in tool_finished),
        "tool_pair_gap": len(tool_started) - len(tool_finished),
        "tool_call_lifecycle_complete": tool_call_lifecycle_complete,
        "event_trace_complete": event_trace_complete,
        **quality_metrics,
        **trace_metrics,
        "submit_attempts": len(validations),
        "hard_failure_history": hard_history,
        "final_hard_pass": bool(final_validation.get("passed")),
        "warning_codes": warnings,
        "completeness_score": (
            (response.plan or {}).get("completeness", {}).get("score")
            if response.plan
            else None
        ),
        "event_count": len(events),
        "event_sequence": [event.get("type") for event in events],
    }


def _aggregate(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [item for item in summaries if item["success"]]
    repair_reasons: dict[str, int] = {}
    for item in summaries:
        for reason, count in (item.get("repair_reasons") or {}).items():
            repair_reasons[reason] = repair_reasons.get(reason, 0) + int(count)

    def average_metric(name: str) -> float | None:
        values = [item.get(name) for item in successes if item.get(name) is not None]
        return round(sum(values) / len(values), 4) if values else None

    return {
        "run_count": len(summaries),
        "success_count": len(successes),
        "hard_pass_rate": (
            round(
                sum(item["final_hard_pass"] for item in summaries) / len(summaries), 4
            )
            if summaries
            else 0
        ),
        "total_elapsed_ms": sum(item["elapsed_ms"] for item in summaries),
        "total_planner_llm_calls": sum(item["planner_llm_calls"] for item in summaries),
        "total_input_tokens": sum(item["input_tokens"] for item in summaries),
        "total_output_tokens": sum(item["output_tokens"] for item in summaries),
        "total_cached_input_tokens": sum(
            item["cached_input_tokens"] for item in summaries
        ),
        "total_non_cached_input_tokens": sum(
            item["non_cached_input_tokens"] for item in summaries
        ),
        "total_provider_calls": sum(item["provider_calls"] for item in summaries),
        "total_repairs": sum(item.get("repair_count", 0) for item in summaries),
        "total_required_stop_repairs": sum(
            item.get("required_stop_repairs", 0) for item in summaries
        ),
        "repair_reasons": dict(sorted(repair_reasons.items())),
        "total_tool_started": sum(item.get("tool_started", 0) for item in summaries),
        "total_tool_finished": sum(item.get("tool_finished", 0) for item in summaries),
        "total_tool_errors": sum(item.get("tool_errors", 0) for item in summaries),
        "total_tool_cache_hits": sum(
            item.get("tool_cache_hits", 0) for item in summaries
        ),
        "tool_pair_gap": sum(item.get("tool_pair_gap", 0) for item in summaries),
        "tool_call_lifecycle_complete_rate": (
            round(
                sum(
                    bool(item.get("tool_call_lifecycle_complete")) for item in summaries
                )
                / len(summaries),
                4,
            )
            if summaries
            else 0
        ),
        "average_entity_binding_rate": average_metric("entity_binding_rate"),
        "average_route_evidence_rate": average_metric("route_evidence_rate"),
        "average_must_visit_coverage_rate": average_metric("must_visit_coverage_rate"),
        "average_opening_verification_rate": average_metric(
            "opening_verification_rate"
        ),
        "total_unresolved_schedule_items": sum(
            item.get("unresolved_schedule_item_count", 0) for item in summaries
        ),
        "total_unknown_walking_segments": sum(
            item.get("unknown_walking_segments", 0) for item in summaries
        ),
        "event_trace_complete_rate": (
            round(
                sum(bool(item.get("event_trace_complete")) for item in summaries)
                / len(summaries),
                4,
            )
            if summaries
            else 0
        ),
        "average_completeness_score": (
            round(
                sum(
                    item["completeness_score"]
                    for item in successes
                    if item["completeness_score"] is not None
                )
                / sum(item["completeness_score"] is not None for item in successes),
                2,
            )
            if any(item["completeness_score"] is not None for item in successes)
            else None
        ),
        "average_guide_explanation_coverage": average_metric(
            "guide_explanation_coverage"
        ),
        "first_step_available_rate": round(
            sum(bool(item.get("first_step_available")) for item in successes)
            / len(successes),
            4,
        )
        if successes
        else 0,
        "provider_latency_p50_ms": _percentile(
            [
                int(item["provider_latency_p50_ms"])
                for item in successes
                if item.get("provider_latency_p50_ms") is not None
            ],
            0.50,
        ),
        "provider_latency_p95_ms": _percentile(
            [
                int(item["provider_latency_p95_ms"])
                for item in successes
                if item.get("provider_latency_p95_ms") is not None
            ],
            0.95,
        ),
        "average_provider_error_rate": average_metric("provider_error_rate"),
        "failure_codes": sorted(
            {
                code
                for item in summaries
                for attempt in item["hard_failure_history"]
                for code in attempt
            }
        ),
        "warning_codes": sorted(
            {code for item in summaries for code in item["warning_codes"]}
        ),
    }


def _manifest(
    args: argparse.Namespace, requests: list[dict[str, Any]]
) -> dict[str, Any]:
    try:
        httpx_version = importlib.metadata.version("httpx")
    except importlib.metadata.PackageNotFoundError:
        httpx_version = "unknown"
    return {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "mode": "live",
        "source_hashes": {
            path: _file_hash(path)
            for path in (
                "trip_agent/context.py",
                "trip_agent/contracts.py",
                "trip_agent/evaluate.py",
                "trip_agent/llm.py",
                "trip_agent/loop.py",
                "trip_agent/model_schema.py",
                "trip_agent/plan_output.py",
                "trip_agent/validation.py",
                "trip_agent/workflow.py",
            )
        },
        "model": args.model,
        "wire_api": args.wire_api,
        "reasoning_effort": args.reasoning_effort,
        "workflow": "single_model_deterministic",
        "max_model_calls": 1,
        "reviewer_enabled": False,
        "max_provider_calls": max(
            1,
            min(
                int(os.environ.get("TRIP_AGENT_MAX_PROVIDER_CALLS", "100")),
                100,
            ),
        ),
        "memory_policy": MemoryPolicy(
            history_messages=args.memory_history_messages,
            message_chars=args.memory_message_chars,
            plan_days=args.memory_plan_days,
            schedule_items_per_day=args.memory_items_per_day,
            evidence_places=args.memory_evidence_places,
            evidence_routes=args.memory_evidence_routes,
        ).as_dict(),
        "request_count": len(requests),
        "prompt_hashes": {
            "skeleton": _json_hash(SKELETON_PROMPT),
        },
        "contract_hashes": {
            "skeleton_output": _json_hash(itinerary_skeleton_output_format()),
        },
        "versions": {"httpx": httpx_version},
        "provider_availability": {
            "amap": bool(
                os.environ.get("AMAP_API_KEY") or os.environ.get("AMAP_MAPS_API_KEY")
            ),
            "qweather": bool(
                os.environ.get("QWEATHER_KEY")
                or os.environ.get("QWEATHER_API_KEY")
                or os.environ.get("HEFENG_WEATHER_KEY")
            ),
            "rail": os.environ.get("TRIP_AGENT_RAIL_ENABLED", "true").lower()
            not in {"0", "false", "no"},
        },
    }


def _load_requests(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return _json_copy(DEFAULT_REQUESTS)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("requests 文件必须是非空 JSON 数组")
    for index, item in enumerate(payload):
        if not isinstance(item, dict) or (
            not str(item.get("message", "")).strip()
            and not isinstance(item.get("trip"), dict)
        ):
            raise ValueError(f"requests[{index}] 缺少 message 或 trip")
        item.setdefault("message", "")
        item.setdefault("id", f"request-{index + 1}")
        item.setdefault(
            "city",
            (item.get("trip") or {}).get("destination", "unknown"),
        )
    return payload


async def _live(args: argparse.Namespace) -> int:
    load_dotenv(args.env_file)
    requests = _load_requests(args.requests)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_root = Path(args.output) / stamp
    output_root.mkdir(parents=True, exist_ok=False)
    configure_logging(output_root / "planning.jsonl")
    manifest = _manifest(args, requests)
    _write_json(output_root / "manifest.json", manifest)
    _write_json(output_root / "requests.json", requests)
    summaries: list[dict[str, Any]] = []

    for index, request in enumerate(requests, 1):
        run_dir = output_root / "runs" / f"{index:02d}-{request['id']}"
        run_dir.mkdir(parents=True)
        cache = ProviderCache(output_root / "provider-cache.sqlite")
        amap_inner = AmapProvider(cache)
        rail_inner = Rail12306Provider(cache)
        weather_inner = WeatherProvider(cache, amap=amap_inner)
        amap = RecordingAmap(amap_inner)
        rail = RecordingRail(rail_inner)
        weather = RecordingWeather(weather_inner)
        llm_inner = OpenAICompatibleLLM()
        llm_inner.model = args.model
        llm_inner.wire_api = args.wire_api
        llm_inner.reasoning_effort = args.reasoning_effort
        llm = RecordingLLM(llm_inner)
        store = TripStore(f"sqlite:///{(output_root / 'trips.sqlite').as_posix()}")
        agent = TripAgent(
            llm=llm,
            amap=amap,
            weather=weather,
            rail=rail,
            store=store,
            memory_policy=MemoryPolicy(**manifest["memory_policy"]),
            max_provider_calls=manifest["max_provider_calls"],
        )
        started_at = time.perf_counter()
        try:
            response = await agent.run(
                str(request["message"]),
                session_id=f"eval-{stamp}-{request['id']}",
                structured_request=(
                    request.get("trip")
                    if isinstance(request.get("trip"), dict)
                    else None
                ),
            )
        finally:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000)
            await agent.close()
            await rail.close()
            await llm.close()
            store.close()
        recording = {
            "llm": llm.calls,
            "amap": amap.calls,
            "weather": weather.calls,
            "rail": rail.calls,
        }
        response_payload = {
            "session_id": response.session_id,
            "run_id": response.run_id,
            "reply": response.reply,
            "plan": response.plan,
        }
        summary = {
            "request_id": request["id"],
            "city": request.get("city"),
            **_summarize(response, recording, elapsed_ms),
        }
        summaries.append(summary)
        _write_json(run_dir / "request.json", request)
        _write_json(run_dir / "response.json", response_payload)
        _append_jsonl(run_dir / "events.jsonl", response.events)
        _write_json(run_dir / "recording.json", recording)
        _write_json(run_dir / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)

    aggregate = {
        "manifest": manifest,
        "aggregate": _aggregate(summaries),
        "runs": summaries,
    }
    _write_json(output_root / "evaluation-summary.json", aggregate)
    close_logging()
    print(
        json.dumps(
            {"output": str(output_root), **aggregate["aggregate"]}, ensure_ascii=False
        )
    )
    return 0 if aggregate["aggregate"]["success_count"] == len(requests) else 2


async def _replay(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    recording = json.loads((run_dir / "recording.json").read_text(encoding="utf-8"))
    expected = json.loads((run_dir / "response.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (run_dir.parents[1] / "manifest.json").read_text(encoding="utf-8")
    )
    llm = ReplayLLM(
        recording["llm"],
        manifest["model"],
        manifest.get("reasoning_effort", "medium"),
        manifest.get("reasoning_effort", "medium"),
    )
    amap = ReplayAmap(recording["amap"])
    weather = ReplayWeather(recording["weather"])
    rail = ReplayRail(recording["rail"]) if "rail" in recording else None
    memory_policy = MemoryPolicy(**manifest.get("memory_policy", {}))
    agent = TripAgent(
        llm=llm,
        amap=amap,
        weather=weather,
        rail=rail,
        memory_policy=memory_policy,
        max_provider_calls=int(manifest.get("max_provider_calls", 100)),
    )
    response = await agent.run(
        str(request["message"]),
        session_id=str(expected["session_id"]),
        structured_request=(
            request.get("trip") if isinstance(request.get("trip"), dict) else None
        ),
    )
    await agent.close()
    if rail is not None:
        await rail.close()
    await llm.close()
    actual_hash = _json_hash({"reply": response.reply, "plan": response.plan})
    expected_hash = _json_hash({"reply": expected["reply"], "plan": expected["plan"]})
    fully_consumed = {
        "llm": llm.cursor == len(llm.calls),
        "amap": amap.cursor == len(amap.calls),
        "weather": weather.cursor == len(weather.calls),
    }
    if rail is not None:
        fully_consumed["rail"] = rail.cursor == len(rail.calls)
    result = {
        "matched": actual_hash == expected_hash and all(fully_consumed.values()),
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "recordings_fully_consumed": fully_consumed,
    }
    _write_json(run_dir / "replay-result.json", result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["matched"] else 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run and deterministically replay the standalone Trip Agent."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    live = subparsers.add_parser("live")
    live.add_argument("--env-file", default=".env")
    live.add_argument("--requests")
    live.add_argument("--output", default="artifacts/trip-agent-eval")
    live.add_argument("--model", default="deepseek-flash")
    live.add_argument(
        "--wire-api",
        choices=["responses", "chat_completions"],
        default="chat_completions",
    )
    live.add_argument("--reasoning-effort", default="low")
    live.add_argument("--memory-history-messages", type=int, default=4)
    live.add_argument("--memory-message-chars", type=int, default=800)
    live.add_argument("--memory-plan-days", type=int, default=7)
    live.add_argument("--memory-items-per-day", type=int, default=8)
    live.add_argument("--memory-evidence-places", type=int, default=24)
    live.add_argument("--memory-evidence-routes", type=int, default=24)
    replay = subparsers.add_parser("replay")
    replay.add_argument("run_dir")
    return parser


def main() -> None:
    args = _parser().parse_args()
    command = _live(args) if args.command == "live" else _replay(args)
    raise SystemExit(asyncio.run(command))


if __name__ == "__main__":
    main()
