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

SKELETON_PROMPT = """你是 Tour Pass 的资深亲切导游，也是一位擅长安排路线的旅行规划师。一次性输出符合 JSON Schema 的完整旅行方案；不调用工具，不输出思维过程。你的文字要像出发前一位熟悉当地、带过很多游客的导游在做行前说明：先告诉用户怎么走、看什么、怎么安排体力，再解释为什么这样安排。语气自然、耐心、具体，不夸张营销，也不堆砌典故。

先按以下优先级做规划：用户明确的硬约束（目的地、天数、抵返窗口、必去/不去） > 明确的安全与行动负荷 > 明确的同行人和饮食要求 > 路线顺序与交通偏好 > 兴趣、预算和文案风格。输入包含结构化约束、原始需求和上一版摘要；最新要求优先于旧要求，用户明确要求优先于你的推断。没有明确偏好时，不要把选择题抛回给用户：直接给一版大多数第一次到访者会满意的主方案。

输出契约必须严格遵守：`days` 始终是数组；stop 的 `type` 只能是 `visit`、`meal`、`free_time`；`period` 只能是 schema 中的六个枚举值；每个用户明确的必去地点单独生成一个 `visit`，其 `name` 和 `search_query` 保留用户使用的可检索名称；不要用 `attraction`、`sightseeing`、`restaurant` 等同义词替代枚举值。不要增加 schema 外字段，不要把早餐、午餐、晚餐或休息项写成景点。

地点和证据边界：你只负责选择规划意图和候选名称，不负责声称地点、坐标、路线、开放时间、票价、库存、预约或天气已经核验。没有把握时使用片区就近用餐或住宿区域，不编造店名、分店、Provider ID、坐标和精确交通数据；`search_query` 应短、可检索、与地点身份一致，必去地点不要改写成“附近景区”或泛化描述。

行动负荷必须改变方案：出现膝盖不适、老人、少走路、无障碍等要求时，优先减少换乘和接驳，安排可以坐下的休息，控制连续游览时长；不要仅在 safety_notes 里重复要求。模型不知道真实步行距离时，保留低步行意图和备选方式，由程序查询后决定是否满足。

输入包含结构化约束、原始需求和上一版摘要。先整体判断路线、片区、体力与体验，再生成完整结果。抵返时间、同行人年龄与行动能力、房型、预算、饮食、节奏、必去/不去和预约偏好都必须落实。
用户明确给出天数、目的地或路线时严格遵守；未明确时，由你根据目的地体量、交通、节奏、预算和往返条件自行决定合理的天数与目的地，并在 overview 或 tradeoffs 中解释依据。多目的地按用户指定顺序，或在用户未指定时按地理和交通合理性排序；换城日填写 intercity_leg，主动为进出站、入住和休息留余量。未提供出行日期或抵返时刻时不得自行虚构，intercity_leg 的时刻填 null，由程序查询；hotels 覆盖每个过夜目的地，未指定具体酒店时推荐交通方便的住宿片区或地铁站。
你负责判断每天的主题、景点组合、先后顺序、三餐、路线与取舍。没有必去清单、兴趣或预算等额外偏好时，优先选择城市最具代表性的热门景点、经典街区和当地首次到访体验，再用地理顺路性做排序；热门不等于把一天塞满。默认一版主方案，不罗列大量平行选择。每个完整游玩日通常安排 2~4 个核心活动，抵达日、返程日、换城日和大型项目主动减量。活动只使用 breakfast、morning、lunch、afternoon、dinner、evening 这些自然时段，不生成景点的分钟级到达、离开或停留时间；只有用户明确给出的航班、列车等固定班次可以保留精确时刻。完整游玩日安排早餐、午餐和晚餐，餐厅没有把握时写清楚所在片区、推荐菜品和就近用餐的默认建议，不得虚构分店。
day.summary 用一至两句自然语言做当天的导游 briefing：说清今天的主线、先后顺序、体力节奏、吃饭和休息位置，以及为什么主动舍弃某些项目。每个景点 stop 的 reason 用一至两句具体讲解：先说这里最值得看或体验什么，再说建议怎么逛、看多久或适合什么状态；有稳定且必要的背景知识时，用一句通俗话解释，不编造年代、票价、传说、排名或精确数据。餐饮 stop 说明推荐尝什么、在哪个片区就近解决；free_time 说明这段时间用来休息、补给还是看现场状态调整。文字要像导游在带路，避免“代表性景观”“感受文化”“丰富体验”等空话。search_query 保持简短，free_time 的 search_query 必须为 null。
不要生成坐标、Provider ID、精确路线距离、实时票价、库存、“已经预约”或未经输入支持的抵返时刻。开放时间、天气、路线耗时、铁路班次和票价由程序补充；模型不确定时直接说明取舍，不要用假事实填满字段。budget_notes、safety_notes 和 transport_notes 只给与目的地、同行人和路线真正相关的条件式建议，不得冒充官方预警。
修改既有行程时只改变用户要求的部分，但仍一次输出完整替代方案。
"""


class TripAgent:
    def __init__(
        self,
        llm: Any,
        amap: AmapProvider | None = None,
        weather: Any = None,
        rail: Any = None,
        store: TripStore | None = None,
        validator: HardValidator | None = None,
        memory_policy: MemoryPolicy | None = None,
        max_provider_calls: int = 18,
    ) -> None:
        self.llm = llm
        self.amap = amap or AmapProvider()
        self.weather = weather
        self.rail = rail
        self.store = store
        self.validator = validator or HardValidator()
        self.memory_policy = memory_policy or MemoryPolicy()
        self.max_provider_calls = max(1, min(int(max_provider_calls), 100))
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
        model: str | None = None,
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
        event_index = 0
        previous_event_id: str | None = None

        def emit_event(event: dict[str, Any]) -> None:
            nonlocal event_index, previous_event_id
            event_index += 1
            event_id = f"{run_id}:{event_index}"
            enriched = {
                **event,
                "trace_id": run_id,
                "event_id": event_id,
                "event_index": event_index,
                "parent_event_id": previous_event_id,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            }
            previous_event_id = event_id
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
            requested_days = planning_context.get("days")
            schema = itinerary_skeleton_output_format(
                int(requested_days) if requested_days else None
            )
            cache_material = (
                SKELETON_PROMPT
                + json.dumps(schema, ensure_ascii=False, sort_keys=True)
                + str(model or getattr(self.llm, "model", ""))
            )
            prompt_cache_key = (
                "tour-pass-complete-v5-"
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
            emit_event(
                {
                    "type": "model_started",
                    "phase": "complete_plan",
                    "step": 1,
                    "detail": "一次生成完整旅行方案",
                }
            )
            response = await self.llm.ainvoke(
                model_messages,
                trace={
                    "run_id": run_id,
                    "session_id": session_id,
                    "stage": "complete_plan",
                    "step": 1,
                },
                on_progress=emit_event,
                reasoning_effort=getattr(self.llm, "reasoning_effort", "medium"),
                output_format=schema,
                prompt_cache_key=prompt_cache_key,
                model=model,
            )
            model_metrics = getattr(response, "metrics", {})
            try:
                parsed = json.loads(response.content)
                if not isinstance(parsed, dict):
                    raise ValueError("完整方案输出必须是 JSON 对象")
                skeleton = parsed
            except (json.JSONDecodeError, ValueError) as exc:
                emit_event(
                    {
                        "type": "model_finished",
                        "phase": "complete_plan",
                        "step": 1,
                        "error": "invalid_structured_output",
                        "message": str(exc),
                        "model_metrics": model_metrics,
                    }
                )
                raise RuntimeError("模型未返回有效的完整旅行方案") from exc
            emit_event(
                {
                    "type": "model_finished",
                    "phase": "complete_plan",
                    "step": 1,
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
            if skeleton is None:
                raise RuntimeError("模型未生成完整旅行方案")

            assembler = ItineraryAssembler(
                self.amap,
                self.weather,
                self.max_provider_calls,
                rail=self.rail,
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
