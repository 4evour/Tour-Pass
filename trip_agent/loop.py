from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from .context import (
    MemoryPolicy,
    build_planning_context,
    compact_plan_memory,
    compact_planning_context,
)
from .contracts import ChatResponse
from .model_schema import itinerary_skeleton_output_format
from .observability import log_event
from .plan_output import normalize_plan as normalize_complete_plan
from .providers.amap import AmapProvider
from .store import TripStore
from .validation import HardValidator
from .workflow import ItineraryAssembler

SKELETON_PROMPT = """你是 Tour Pass 的行程骨架规划器。只输出符合给定 JSON Schema 的结果，不调用工具，不输出思维过程。
输入末尾提供结构化旅行约束和可选的上一版行程摘要。必须严格满足目的地、天数、每日时段、同行人、节奏、交通、预算、兴趣、必去地点和用户备注；必去地点名称必须原样出现在 stops。
每天安排 3~4 个主要活动，按相邻片区组织，避免跨城折返；跨越 11:30~13:30 时必须包含午餐。均衡或紧凑节奏安排 4 项且必须是 3 个 visit 加 1 个 lunch，轻松节奏安排 2 个 visit 加 1 个 lunch；晚餐不单列为 stop。每个 stop 只能对应一个真实地点，不得把两个地点合并为一项，也不得同时选择相互包含或体验高度重复的景点。除最后一个相邻夜景项目外，同一天的景点和餐厅必须位于同一行政区或连续步行片区；三日行程的 primary_area 不得重复。同一天的餐厅必须位于当天游览动线附近，并优先选择有目的地代表性的知名老店，避免普通连锁或无代表性小店。meal 的 name 必须是具体真实餐厅或分店，禁止使用“某片区餐厅”等占位名称。按 morning、lunch、afternoon、evening 的实际执行顺序输出；目的地适合且用户时段允许时，多日行程至少一天以晚间游览活动收尾。为景点或餐厅填写准确、简短、适合地图检索的 search_query；free_time 的 search_query 必须为 null。
不要生成介绍文案、候选区比较、坐标、Provider ID、路线距离、路线时间、开放时间、票价或预约结论；介绍文案与外部事实由程序补齐。没有指定住宿时只推荐一个交通方便的住宿片区，并用该片区内明确地标或地铁站作为 search_query；指定住宿时必须保留用户原文。
修改既有行程时只改变用户要求的部分，并输出完整替代骨架；不得伪造不确定事实。
"""


class TripAgent:
    def __init__(
        self,
        llm: Any,
        amap: AmapProvider | None = None,
        weather: Any = None,
        store: TripStore | None = None,
        validator: HardValidator | None = None,
        memory_policy: MemoryPolicy | None = None,
        max_provider_calls: int = 14,
    ) -> None:
        self.llm = llm
        self.amap = amap or AmapProvider()
        self.weather = weather
        self.store = store
        self.validator = validator or HardValidator()
        self.memory_policy = memory_policy or MemoryPolicy()
        self.max_provider_calls = max(1, min(int(max_provider_calls), 40))
        self.sessions: dict[str, list[dict[str, str]]] = {}

    async def close(self) -> None:
        await self.amap.close()
        if self.weather is not None and hasattr(self.weather, "close"):
            await self.weather.close()

    @staticmethod
    def _place_key(value: Any) -> str:
        return re.sub(r"[\s·（）()—\-]", "", str(value or "")).casefold()

    @classmethod
    def _resolve_place_evidence(
        cls, stop: dict[str, Any], known_places: dict[str, dict[str, Any]]
    ) -> dict[str, Any] | None:
        place_id = str(stop.get("place_id") or stop.get("id") or "")
        exact = known_places.get(place_id) if place_id else None
        requested_key = cls._place_key(stop.get("name"))
        if exact is None and requested_key:
            exact = known_places.get(requested_key)
        if exact is not None:
            return exact
        requested = cls._place_key(stop.get("name"))
        if len(requested) < 2:
            return None
        for suffix in ("住宿区域", "住宿区", "酒店区域", "酒店"):
            if not requested.endswith(suffix):
                continue
            area_key = requested[: -len(suffix)]
            exact_area = known_places.get(area_key)
            if exact_area is not None:
                return exact_area
            area_matches: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
            for place in known_places.values():
                canonical = cls._place_key(place.get("name"))
                place_type = str(place.get("type") or "")
                if area_key not in canonical or not any(
                    marker in place_type
                    for marker in ("交通设施", "地铁站", "地名地址", "风景名胜")
                ):
                    continue
                key = str(place.get("id") or canonical)
                area_matches[key] = (
                    (
                        int(canonical in {area_key, f"{area_key}地铁站"}),
                        -abs(len(canonical) - len(area_key)),
                    ),
                    place,
                )
            if area_matches:
                ranked = sorted(
                    area_matches.values(), key=lambda item: item[0], reverse=True
                )
                if len(ranked) == 1 or ranked[0][0] > ranked[1][0]:
                    return ranked[0][1]
            requested = area_key
            break
        matches: dict[str, dict[str, Any]] = {}
        for place in known_places.values():
            canonical = cls._place_key(place.get("name"))
            if requested in canonical or canonical in requested:
                key = str(place.get("id") or canonical)
                matches[key] = place
        return next(iter(matches.values())) if len(matches) == 1 else None

    @classmethod
    def normalize_plan(
        cls,
        plan: dict[str, Any],
        known_places: dict[str, dict[str, Any]] | None = None,
        route_evidence: list[dict[str, Any]] | None = None,
        weather_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return normalize_complete_plan(
            plan,
            known_places or {},
            cls._resolve_place_evidence,
            route_evidence or [],
            weather_evidence,
        )

    async def run(
        self,
        message: str,
        session_id: str | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        owner: tuple[str, str] = ("guest", "local"),
        structured_request: dict[str, Any] | None = None,
    ) -> ChatResponse:
        session_id = session_id or uuid.uuid4().hex
        run_id = uuid.uuid4().hex
        if self.store is not None:
            prior_history = self.store.history(session_id, owner)
            previous_plan = self.store.latest_plan(session_id, owner)
        else:
            prior_history = self.sessions.setdefault(session_id, [])
            previous_plan = None
        planning_context = build_planning_context(
            previous_plan,
            message,
            prior_history,
            structured_request=structured_request,
        )
        started_at = time.perf_counter()
        events: list[dict[str, Any]] = []

        def emit_event(event: dict[str, Any]) -> None:
            enriched = {
                **event,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            }
            events.append(enriched)
            log_event(
                "planner_event",
                run_id=run_id,
                session_id=session_id,
                **{
                    key: value
                    for key, value in enriched.items()
                    if key not in {"run_id", "session_id"}
                },
            )
            if on_event is not None:
                on_event(enriched)

        emit_event({"type": "run_started", "run_id": run_id, "session_id": session_id})
        if previous_plan is not None:
            emit_event(
                {
                    "type": "session_restored",
                    "message_count": len(prior_history),
                    "previous_city": previous_plan.get("city"),
                    "previous_title": previous_plan.get("title"),
                }
            )

        plan: dict[str, Any] | None = None
        destination = str(planning_context.get("destination") or "").strip()
        if not destination:
            reply = "请先告诉我目的地城市。"
            emit_event({"type": "assistant_message", "content": reply})
        else:
            schema = itinerary_skeleton_output_format()
            cache_material = (
                SKELETON_PROMPT
                + json.dumps(schema, ensure_ascii=False, sort_keys=True)
                + str(getattr(self.llm, "model", ""))
            )
            prompt_cache_key = (
                "tour-pass-fast-v1-"
                + hashlib.sha256(cache_material.encode()).hexdigest()[:20]
            )
            request_payload = {
                "planning_context": compact_planning_context(planning_context),
                "previous_plan_digest": compact_plan_memory(
                    previous_plan, self.memory_policy
                ),
            }
            model_messages: list[dict[str, Any]] = [
                {"role": "system", "content": SKELETON_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        request_payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ]
            skeleton: dict[str, Any] | None = None
            model_metrics: dict[str, Any] = {}
            for attempt in range(2):
                emit_event(
                    {
                        "type": "model_started",
                        "phase": "skeleton",
                        "step": attempt + 1,
                        "detail": "生成轻量行程骨架",
                    }
                )
                response = await self.llm.ainvoke(
                    model_messages,
                    trace={
                        "run_id": run_id,
                        "session_id": session_id,
                        "stage": "skeleton",
                        "step": attempt + 1,
                    },
                    on_progress=emit_event,
                    reasoning_effort=getattr(self.llm, "reasoning_effort", "medium"),
                    output_format=schema,
                    prompt_cache_key=prompt_cache_key,
                )
                model_metrics = getattr(response, "metrics", {})
                try:
                    parsed = json.loads(response.content)
                    if not isinstance(parsed, dict):
                        raise ValueError("骨架输出必须是 JSON 对象")
                    skeleton = parsed
                except (json.JSONDecodeError, ValueError) as exc:
                    emit_event(
                        {
                            "type": "model_finished",
                            "phase": "skeleton",
                            "step": attempt + 1,
                            "error": "invalid_structured_output",
                            "message": str(exc),
                            "model_metrics": model_metrics,
                        }
                    )
                    if attempt == 0:
                        model_messages.append(
                            {
                                "role": "user",
                                "content": "上一响应不是可解析的结构化对象，请严格按 JSON Schema 重新输出。",
                            }
                        )
                        continue
                    raise RuntimeError("模型连续两次未返回有效行程骨架") from exc
                emit_event(
                    {
                        "type": "model_finished",
                        "phase": "skeleton",
                        "step": attempt + 1,
                        "tool_calls": [],
                        "model_metrics": model_metrics,
                    }
                )
                usage = model_metrics.get("usage") or {}
                emit_event(
                    {
                        "type": "prompt_cache",
                        "cached_tokens": int(
                            usage.get("input_tokens_details.cached_tokens") or 0
                        ),
                        "cache_write_tokens": int(
                            usage.get("input_tokens_details.cache_write_tokens") or 0
                        ),
                        "input_tokens": int(usage.get("input_tokens") or 0),
                    }
                )
                break

            if skeleton is None:
                raise RuntimeError("模型未生成行程骨架")

            assembler = ItineraryAssembler(
                self.amap, self.weather, self.max_provider_calls
            )
            (
                raw_plan,
                known_places,
                route_evidence,
                weather_evidence,
            ) = await assembler.assemble(planning_context, skeleton, emit_event)
            emit_event({"type": "plan_validation_started", "submit_attempt": 1})
            validation_started_at = time.perf_counter()
            candidate = self.normalize_plan(
                raw_plan,
                known_places=known_places,
                route_evidence=route_evidence,
                weather_evidence=weather_evidence,
            )
            candidate["planning_context"] = planning_context
            report = self.validator.validate(candidate, planning_context)
            report["submit_attempt"] = 1
            report["repairs_used"] = 0
            report["repairs_remaining"] = 0
            emit_event(
                {
                    "type": "plan_validation_finished",
                    "submit_attempt": 1,
                    "validation_elapsed_ms": round(
                        (time.perf_counter() - validation_started_at) * 1000
                    ),
                    "passed": report["passed"],
                    "hard_failure_codes": [
                        item["code"] for item in report["hard_failures"]
                    ],
                    "warning_codes": [item["code"] for item in report["warnings"]],
                    "validation_report": report,
                    "candidate_plan": candidate,
                }
            )
            if report["passed"]:
                candidate["validation"] = report
                candidate["review"] = {
                    "verdict": "not_run",
                    "summary": "快速模式默认不调用独立审查模型。",
                    "issues": [],
                    "shadow": True,
                }
                plan = candidate
                reply = (
                    f"{destination}{int(planning_context.get('days') or 3)}天行程已完成。"
                    "未完全核验的开放时间、预约或路线已在结果中标明。"
                )
                emit_event(
                    {
                        "type": "plan_ready",
                        "submit_attempt": 1,
                        "tool_count": sum(
                            event.get("type") == "tool_started" for event in events
                        ),
                        "completeness_score": plan["completeness"]["score"],
                    }
                )
            else:
                codes = "、".join(
                    dict.fromkeys(item["code"] for item in report["hard_failures"])
                )
                reply = f"行程存在无法自动修复的核心约束冲突：{codes}。"
                emit_event(
                    {
                        "type": "run_error",
                        "error": "hard_constraint_failed",
                        "hard_failure_codes": [
                            item["code"] for item in report["hard_failures"]
                        ],
                    }
                )

        if self.store is None:
            prior_history.extend(
                [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": reply},
                ]
            )
        else:
            emit_event({"type": "persistence_started", "has_plan": plan is not None})
            self.store.save_exchange(
                session_id=session_id,
                run_id=run_id,
                owner=owner,
                user_message=message,
                reply=reply,
                plan=plan,
                events=events,
            )
            emit_event({"type": "persistence_finished", "has_plan": plan is not None})
        emit_event(
            {"type": "run_finished", "run_id": run_id, "success": plan is not None}
        )
        if self.store is not None and plan is not None:
            self.store.update_events(run_id, events)
        return ChatResponse(
            session_id=session_id,
            run_id=run_id,
            reply=reply,
            plan=plan,
            events=events,
        )
