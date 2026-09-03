from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from .contracts import ChatResponse
from .observability import log_event
from .plan_output import normalize_plan as normalize_complete_plan
from .prompts import PLAN_OUTPUT_GUIDE
from .providers.amap import AmapProvider
from .store import TripStore

SYSTEM_PROMPT = (
    """你是 Tour Pass 的资深旅行规划顾问。你的首要目标是交付内容完整、可直接执行、阅读体验良好的行程，而不是尽快结束。
你可以主动调用高德地点搜索、地点详情、路线和天气工具。先在脑中形成 2~3 个区域组合，再查询最终会采用的地点。需要 2 个以上独立查询时必须使用 batch；典型流程是“天气与核心地点 -> 补充地点 -> 所有相邻交通段与酒店闭环 -> 完整 plan”，不要为每个工具单独往返模型。
地点、地址、坐标、开放时间、路线距离、路线耗时和天气只能来自工具；体验取舍、节奏和叙事可以由你判断，但必须标记为 model_judgment。
用户说“去广州/广州三天”时，广州就是目的地，绝不能再追问从哪座城市出发。只有目的地城市完全缺失时才追问；日期、酒店、预算、出发地等非关键缺失信息一律采用合理默认或写 unknown，并记录到 assumptions，不得为此中断规划。
如果上下文包含“当前已保存行程”，用户是在修改已有方案：必须保留用户未要求改变的城市、天数、酒店和日程，只调整明确提出的部分，并输出修改后的完整替代行程。
action 只能是 tool、ask、plan。调用工具时把工具名放在 tool 字段；交付时使用 action=plan。
每次只输出一个 JSON 对象。不要输出 Markdown、解释文字或思维过程。
一次请求最多执行 20 个高价值底层工具调用，batch 内每项计一次。优先分配为：天气 1 次；按区域或核心地点搜索 6~8 次；剩余预算查询每个相邻活动之间以及酒店首尾的 route。最多使用四轮 batch；地点证据齐备后必须把剩余预算优先用于路线，不要反复搜索同类地点。
工具预算限制的是查询次数，不限制最终内容。即使少量事实 unknown，也必须补齐时间轴、住宿锚点、候选比较、风险、叙事和自检后交付。
"""
    + PLAN_OUTPUT_GUIDE
)

TOOL_DECISION_PROMPT = """你正在为 Tour Pass 收集一份可执行行程所需的外部证据，此阶段禁止输出 plan。
仅输出一个 JSON 对象：
- 需要一个查询：{"action":"tool","tool":"工具名","arguments":{...}}
- 需要多个独立查询：{"action":"tool","tool":"batch","arguments":{"calls":[{"tool":"工具名","arguments":{...}}]}}
- 只有目的地城市完全缺失时才输出 {"action":"ask","reply":"问题"}
batch 每次放 2~5 项。先查天气和最终候选地点，再用地点坐标查询相邻活动及住宿锚点路线；已有地点不要重复搜索。不要输出 Markdown、解释、plan 或未定义字段。
"""


def extract_json(text: str) -> dict[str, Any]:
    text = str(text).strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("模型没有返回 JSON")
    result = json.loads(match.group(0))
    if not isinstance(result, dict):
        raise ValueError("模型返回格式不是对象")
    return result


class TripAgent:
    def __init__(
        self,
        llm: Any,
        amap: AmapProvider | None = None,
        weather: Any = None,
        store: TripStore | None = None,
        max_steps: int = 16,
        max_tool_calls: int = 20,
    ) -> None:
        self.llm = llm
        self.amap = amap or AmapProvider()
        self.weather = weather
        self.store = store
        self.max_steps = max(1, min(max_steps, 24))
        self.max_tool_calls = max(1, min(max_tool_calls, 30))
        self.sessions: dict[str, list[dict[str, str]]] = {}

    async def close(self) -> None:
        await self.amap.close()
        if self.weather is not None and hasattr(self.weather, "close"):
            await self.weather.close()

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "search_places",
                "description": "搜索城市地点候选",
                "parameters": {"city": "城市", "keywords": "关键词", "limit": "数量"},
            },
            {
                "name": "place_detail",
                "description": "查询高德地点详情",
                "parameters": {"place_id": "高德 POI ID"},
            },
            {
                "name": "route",
                "description": "查询两点路线",
                "parameters": {
                    "city": "城市",
                    "origin": "经度,纬度",
                    "destination": "经度,纬度",
                    "mode": "driving|walking|transit",
                },
            },
            {
                "name": "weather",
                "description": "查询城市天气",
                "parameters": {"city": "城市", "days": "天数"},
            },
            {
                "name": "batch",
                "description": "并行执行 2~5 个相互独立的地点、详情、路线或天气查询，优先用它减少模型往返",
                "parameters": {
                    "calls": [
                        {
                            "tool": "search_places|place_detail|route|weather",
                            "arguments": "对应工具参数",
                        }
                    ]
                },
            },
        ]

    async def ask_model(
        self,
        history: list[dict[str, str]],
        *,
        allow_plan: bool = True,
        planning_status: str = "",
        route_only: bool = False,
        trace: dict[str, Any] | None = None,
        on_model_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        prompt = SYSTEM_PROMPT if allow_plan else TOOL_DECISION_PROMPT
        tools = self.tool_definitions()
        if route_only:
            tools = [tool for tool in tools if tool["name"] in {"route", "batch"}]
            prompt += "\n地点证据已经足够。此阶段只能查询 route；batch.calls 中每一项也必须是 route。禁止继续搜索地点或查询详情。"
        base_messages = [
            {
                "role": "system",
                "content": prompt
                + (f"\n当前证据：{planning_status}" if planning_status else "")
                + "\n工具："
                + json.dumps(tools, ensure_ascii=False),
            },
            *history,
        ]
        repair_instruction = (
            "重新生成完整闭合的单行 JSON，总长度不超过 12000 字符：每天仅保留 2~4 个核心时间轴项目，每天最多 2 条风险，每项建议最多 1 条；省略 map.points、map.center 和 quality（系统自动生成），其余契约字段保留但压缩措辞。不要沿用先前输出，只输出新的 JSON 对象。"
            if allow_plan
            else "重新决策，只输出一个完整的 tool、batch 或 ask JSON 对象；禁止输出 plan、Markdown、解释或多个对象。"
        )
        last_error: ValueError | json.JSONDecodeError | None = None
        for attempt in range(3):
            messages = list(base_messages)
            if attempt:
                messages.append({"role": "user", "content": repair_instruction})
                if on_model_event is not None:
                    on_model_event(
                        {
                            "type": "model_retry",
                            "attempt": attempt + 1,
                            "reason": type(last_error).__name__,
                        }
                    )
            response = await self.llm.ainvoke(
                messages,
                trace={**(trace or {}), "json_attempt": attempt + 1},
                on_progress=on_model_event,
                reasoning_effort=(
                    getattr(self.llm, "final_reasoning_effort", "medium")
                    if allow_plan
                    else None
                ),
            )
            content = (
                response.content if hasattr(response, "content") else str(response)
            )
            try:
                return extract_json(content)
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ValueError("模型没有返回 JSON")

    @staticmethod
    def _required(arguments: dict[str, Any], key: str) -> str:
        value = str(arguments.get(key, "")).strip()
        if not value:
            raise ValueError(f"工具参数 {key} 不能为空")
        return value

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "batch":
            calls = arguments.get("calls")
            if not isinstance(calls, list) or not 2 <= len(calls) <= 5:
                raise ValueError("batch.calls 必须包含 2~5 个工具调用")

            async def invoke(call: Any) -> dict[str, Any]:
                if not isinstance(call, dict):
                    return {"tool": "", "arguments": {}, "error": "调用不是对象"}
                tool = str(call.get("tool", ""))
                args = call.get("arguments")
                if tool == "batch" or not isinstance(args, dict):
                    return {
                        "tool": tool,
                        "arguments": {},
                        "error": "batch 不允许嵌套且 arguments 必须是对象",
                    }
                try:
                    result = await self.call_tool(tool, args)
                    return {"tool": tool, "arguments": args, "result": result}
                except Exception as exc:
                    return {"tool": tool, "arguments": args, "error": str(exc)}

            results = await asyncio.gather(*(invoke(call) for call in calls))
            successful = [
                item["result"]
                for item in results
                if isinstance(item.get("result"), dict)
            ]
            return {
                "results": results,
                "cache_hit": bool(successful)
                and all(item.get("cache_hit", False) for item in successful),
            }
        if name == "search_places":
            return await self.amap.search_places(
                self._required(arguments, "city"),
                self._required(arguments, "keywords"),
                limit=min(max(int(arguments.get("limit", 8) or 8), 1), 10),
            )
        if name == "place_detail":
            return await self.amap.place_detail(self._required(arguments, "place_id"))
        if name == "route":
            mode = str(arguments.get("mode", "driving"))
            if mode not in {"driving", "walking", "transit"}:
                raise ValueError(f"不支持的路线方式：{mode}")
            return await self.amap.route(
                self._required(arguments, "city"),
                self._required(arguments, "origin"),
                self._required(arguments, "destination"),
                mode,
            )
        if name == "weather":
            if self.weather is None:
                raise RuntimeError("天气 Provider 未配置")
            return await self.weather.forecast(
                self._required(arguments, "city"),
                min(max(int(arguments.get("days", 3) or 3), 1), 7),
            )
        raise ValueError(f"未知工具：{name}")

    @staticmethod
    def _place_key(value: Any) -> str:
        return re.sub(r"[\s·（）()\-]", "", str(value or "")).casefold()

    @classmethod
    def _resolve_place_evidence(
        cls, stop: dict[str, Any], known_places: dict[str, dict[str, Any]]
    ) -> dict[str, Any] | None:
        place_id = str(stop.get("place_id") or stop.get("id") or "")
        exact = known_places.get(place_id) or known_places.get(
            cls._place_key(stop.get("name"))
        )
        if exact is not None:
            return exact
        requested = cls._place_key(stop.get("name"))
        if len(requested) < 2:
            return None
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

    @staticmethod
    def _history_window(
        history: list[dict[str, str]], request_start: int
    ) -> list[dict[str, str]]:
        prior = history[max(0, request_start - 6) : request_start]
        current = history[request_start:]
        return [*prior, *current]

    @staticmethod
    def _requested_days(message: str) -> int:
        match = re.search(r"([1-7])\s*天", message)
        if match:
            return int(match.group(1))
        chinese_days = {
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
        }
        match = re.search(r"([一二两三四五六七])天", message)
        return chinese_days.get(match.group(1), 3) if match else 3

    async def run(
        self,
        message: str,
        session_id: str | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        owner: tuple[str, str] = ("guest", "local"),
    ) -> ChatResponse:
        session_id = session_id or uuid.uuid4().hex
        run_id = uuid.uuid4().hex
        if self.store is not None:
            history = self.store.history(session_id, owner)
            previous_plan = self.store.latest_plan(session_id, owner)
        else:
            history = self.sessions.setdefault(session_id, [])
            previous_plan = None
        if previous_plan is not None:
            history.append(
                {
                    "role": "user",
                    "content": "当前已保存行程如下。请把本轮用户要求视为对它的修改，并在重新核验受影响事实后输出完整替代行程："
                    + json.dumps(
                        previous_plan,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )
        history.append({"role": "user", "content": message})
        request_start = len(history) - 1
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
                **{
                    "run_id": run_id,
                    "session_id": session_id,
                    **enriched,
                },
            )
            if on_event is not None:
                on_event(enriched)

        emit_event({"type": "run_started", "run_id": run_id, "session_id": session_id})
        if previous_plan is not None:
            emit_event(
                {
                    "type": "session_restored",
                    "message_count": len(history) - 2,
                    "previous_city": previous_plan.get("city"),
                    "previous_title": previous_plan.get("title"),
                }
            )
        tool_count = 0
        reply = ""
        plan = None
        known_places: dict[str, dict[str, Any]] = {}
        route_evidence: list[dict[str, Any]] = []
        weather_evidence: dict[str, Any] | None = None
        successful_tool_calls: set[str] = set()

        def tool_call_key(tool: str, arguments: dict[str, Any]) -> str:
            return f"{tool}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"

        def ingest_evidence(tool: str, result: dict[str, Any]) -> None:
            nonlocal weather_evidence
            if tool == "search_places":
                for place in result.get("places", []):
                    if not isinstance(place, dict):
                        continue
                    place_id = str(place.get("id", ""))
                    if place_id:
                        known_places[place_id] = place
                    known_places[self._place_key(place.get("name"))] = place
            elif tool == "place_detail":
                place = result.get("place")
                if isinstance(place, dict):
                    place_id = str(place.get("id", ""))
                    if place_id:
                        known_places[place_id] = place
                    known_places[self._place_key(place.get("name"))] = place
            elif tool == "route":
                response_hash = str(result.get("response_hash", "")).strip()
                if (
                    result.get("source") != "amap"
                    or int(result.get("distance_meters", 0) or 0) <= 0
                    or int(result.get("duration_seconds", 0) or 0) <= 0
                    or (
                        response_hash
                        and any(
                            item.get("response_hash") == response_hash
                            for item in route_evidence
                        )
                    )
                ):
                    return
                route_evidence.append(
                    {
                        key: result.get(key)
                        for key in (
                            "origin",
                            "destination",
                            "mode",
                            "distance_meters",
                            "duration_seconds",
                            "source",
                            "response_hash",
                        )
                    }
                )
            elif tool == "weather":
                weather_evidence = result

        stored_days = (
            previous_plan.get("days") if isinstance(previous_plan, dict) else None
        )
        requested_days = (
            len(stored_days)
            if isinstance(stored_days, list) and stored_days
            else self._requested_days(message)
        )
        target_places = max(3, requested_days * 2)
        target_routes = min(
            requested_days * 3,
            max(2, self.max_tool_calls - target_places - 1),
        )

        tool_names = {item["name"] for item in self.tool_definitions()}
        for step in range(self.max_steps):
            model_history = self._history_window(history, request_start)
            unique_place_count = len(
                {
                    text
                    for place in known_places.values()
                    if (text := str(place.get("id", "")).strip())
                }
            )
            route_only = (
                unique_place_count >= target_places
                and len(route_evidence) < target_routes
            )
            allow_plan = (
                tool_count >= self.max_tool_calls
                or self.max_tool_calls - tool_count < 2
                or step >= self.max_steps - 2
                or (
                    unique_place_count >= target_places
                    and len(route_evidence) >= target_routes
                )
            )
            planning_status = (
                f"已核验地点 {unique_place_count}/{target_places}，"
                f"已核验路线 {len(route_evidence)}/{target_routes}，"
                f"底层工具已用 {tool_count}/{self.max_tool_calls}。"
            )
            if tool_count >= self.max_tool_calls:
                model_history.append(
                    {
                        "role": "user",
                        "content": "工具预算已用完。现在只能输出 action=plan 交付已核验地点，或 action=ask 追问；禁止继续调用工具。",
                    }
                )
            model_phase = (
                "route_planning"
                if route_only
                else "final_planning"
                if allow_plan
                else "evidence_planning"
            )
            emit_event(
                {
                    "type": "model_started",
                    "phase": model_phase,
                    "step": step + 1,
                    "detail": planning_status,
                }
            )
            decision = await self.ask_model(
                model_history,
                allow_plan=allow_plan,
                planning_status=planning_status,
                route_only=route_only,
                trace={
                    "run_id": run_id,
                    "session_id": session_id,
                    "stage": model_phase,
                    "step": step + 1,
                },
                on_model_event=emit_event,
            )
            action = str(decision.get("action", "")).strip().lower()
            if action in tool_names:
                decision["tool"] = action
                action = "tool"
            elif not action and str(decision.get("tool", "")) in tool_names:
                action = "tool"
            elif action in {"final", "finish", "done"} and isinstance(
                decision.get("plan"), dict
            ):
                action = "plan"
            elif not action and isinstance(decision.get("plan"), dict):
                action = "plan"
            emit_event(
                {
                    "type": "model_finished",
                    "phase": model_phase,
                    "step": step + 1,
                    "action": action,
                    "tool": str(decision.get("tool", "")),
                }
            )
            if action == "plan" and not allow_plan:
                history.append(
                    {
                        "role": "user",
                        "content": "证据尚不足，plan 已拒绝。请继续调用 batch，优先补足真实路线。",
                    }
                )
                emit_event(
                    {
                        "type": "decision_rejected",
                        "action": "plan",
                        "fields": ["insufficient_evidence"],
                        "step": step + 1,
                    }
                )
                continue
            if action == "ask":
                reply = str(decision.get("reply") or "还需要一个信息才能继续规划。")
                emit_event(
                    {"type": "assistant_message", "content": reply, "step": step + 1}
                )
                break
            if action == "tool":
                name = str(decision.get("tool", ""))
                args = (
                    decision.get("arguments")
                    if isinstance(decision.get("arguments"), dict)
                    else {}
                )
                if (
                    name == "batch"
                    and not args
                    and isinstance(decision.get("calls"), list)
                ):
                    args = {"calls": decision["calls"]}
                if route_only:
                    invalid_route_call = name not in {"route", "batch"} or (
                        name == "batch"
                        and (
                            not isinstance(args.get("calls"), list)
                            or any(
                                not isinstance(call, dict)
                                or call.get("tool") != "route"
                                for call in args["calls"]
                            )
                        )
                    )
                    if invalid_route_call:
                        emit_event(
                            {
                                "type": "tool_rejected",
                                "tool": name,
                                "error": "route_evidence_required",
                                "step": step + 1,
                            }
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": "地点已足够，该调用已拒绝。现在只允许 route 或只包含 route 的 batch。",
                            }
                        )
                        continue
                if name == "batch" and isinstance(args.get("calls"), list):
                    fresh_calls = []
                    for call in args["calls"]:
                        if not isinstance(call, dict) or not isinstance(
                            call.get("arguments"), dict
                        ):
                            fresh_calls.append(call)
                            continue
                        if (
                            tool_call_key(str(call.get("tool", "")), call["arguments"])
                            not in successful_tool_calls
                        ):
                            fresh_calls.append(call)
                    if not fresh_calls:
                        emit_event(
                            {
                                "type": "tool_rejected",
                                "tool": name,
                                "error": "duplicate_tool_call",
                                "step": step + 1,
                            }
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": "该 batch 与已成功查询的请求重复，未执行也不计预算。请查询尚未覆盖的路线。",
                            }
                        )
                        continue
                    if len(fresh_calls) == 1 and isinstance(fresh_calls[0], dict):
                        only_call = fresh_calls[0]
                        name = str(only_call.get("tool", ""))
                        args = (
                            only_call.get("arguments")
                            if isinstance(only_call.get("arguments"), dict)
                            else {}
                        )
                    else:
                        args = {"calls": fresh_calls}
                elif tool_call_key(name, args) in successful_tool_calls:
                    emit_event(
                        {
                            "type": "tool_rejected",
                            "tool": name,
                            "error": "duplicate_tool_call",
                            "step": step + 1,
                        }
                    )
                    history.append(
                        {
                            "role": "user",
                            "content": "该工具请求已成功执行，重复调用未执行也不计预算。请查询尚未覆盖的路线。",
                        }
                    )
                    continue
                batch_calls = args.get("calls") if name == "batch" else None
                tool_cost = (
                    len(batch_calls)
                    if isinstance(batch_calls, list) and batch_calls
                    else 1
                )
                if tool_count + tool_cost > self.max_tool_calls:
                    emit_event(
                        {
                            "type": "tool_rejected",
                            "tool": name,
                            "error": "tool_budget_exceeded",
                            "step": step + 1,
                        }
                    )
                    history.append(
                        {
                            "role": "user",
                            "content": "该工具调用已拒绝：剩余工具预算不足。请缩小 batch，或直接输出 plan。",
                        }
                    )
                    continue
                tool_count += tool_cost
                tool_started_at = time.perf_counter()
                emit_event(
                    {
                        "type": "tool_started",
                        "tool": name,
                        "arguments": args,
                        "step": step + 1,
                    }
                )
                try:
                    result = await self.call_tool(name, args)
                    if name == "batch":
                        for item in result.get("results", []):
                            nested_result = item.get("result")
                            nested_args = item.get("arguments")
                            nested_tool = str(item.get("tool", ""))
                            if isinstance(nested_result, dict) and isinstance(
                                nested_args, dict
                            ):
                                successful_tool_calls.add(
                                    tool_call_key(nested_tool, nested_args)
                                )
                                ingest_evidence(nested_tool, nested_result)
                    else:
                        successful_tool_calls.add(tool_call_key(name, args))
                        ingest_evidence(name, result)
                    compact = json.dumps(
                        result, ensure_ascii=False, separators=(",", ":")
                    )[:12000]
                    history.extend(
                        [
                            {
                                "role": "assistant",
                                "content": json.dumps(
                                    {"tool": name, "arguments": args},
                                    ensure_ascii=False,
                                ),
                            },
                            {"role": "user", "content": f"工具 {name} 返回：{compact}"},
                        ]
                    )
                    emit_event(
                        {
                            "type": "tool_finished",
                            "tool": name,
                            "cache_hit": result.get("cache_hit", False),
                            "response_hash": result.get("response_hash", ""),
                            "tool_elapsed_ms": round(
                                (time.perf_counter() - tool_started_at) * 1000
                            ),
                            "step": step + 1,
                        }
                    )
                except Exception as exc:
                    history.append(
                        {"role": "user", "content": f"工具 {name} 失败：{exc}"}
                    )
                    emit_event(
                        {
                            "type": "tool_finished",
                            "tool": name,
                            "error": str(exc),
                            "tool_elapsed_ms": round(
                                (time.perf_counter() - tool_started_at) * 1000
                            ),
                            "step": step + 1,
                        }
                    )
                continue
            if action == "plan":
                validation_started_at = time.perf_counter()
                emit_event(
                    {
                        "type": "plan_validation_started",
                        "step": step + 1,
                    }
                )
                try:
                    plan = self.normalize_plan(
                        decision.get("plan") or {},
                        known_places=known_places,
                        route_evidence=route_evidence,
                        weather_evidence=weather_evidence,
                    )
                    emit_event(
                        {
                            "type": "plan_validation_finished",
                            "step": step + 1,
                            "validation_elapsed_ms": round(
                                (time.perf_counter() - validation_started_at) * 1000
                            ),
                        }
                    )
                except ValueError as exc:
                    history.append(
                        {
                            "role": "user",
                            "content": f"最终结构无法解析：{exc}。请按完整 schema 修正后重新输出。",
                        }
                    )
                    emit_event(
                        {
                            "type": "plan_rejected",
                            "error": str(exc),
                            "step": step + 1,
                        }
                    )
                    continue
                reply = str(decision.get("reply") or "行程已经整理完成。")
                emit_event(
                    {
                        "type": "plan_ready",
                        "step": step + 1,
                        "tool_count": tool_count,
                        "completeness_score": plan["completeness"]["score"],
                    }
                )
                break
            emit_event(
                {
                    "type": "decision_rejected",
                    "action": action,
                    "fields": sorted(decision),
                    "step": step + 1,
                }
            )
            history.append(
                {
                    "role": "user",
                    "content": "action 只能是 tool、ask 或 plan。请修正后继续。",
                }
            )
        if plan is None and not reply:
            reply = "这次查询步骤已达到上限。请缩小范围，或补充城市和游玩天数后再试。"
            emit_event({"type": "run_error", "error": "step_budget_exceeded"})
        history.append({"role": "assistant", "content": reply})
        if self.store is not None:
            emit_event(
                {
                    "type": "persistence_started",
                    "has_plan": plan is not None,
                }
            )
            self.store.save_exchange(
                session_id=session_id,
                run_id=run_id,
                owner=owner,
                user_message=message,
                reply=reply,
                plan=plan,
                events=events,
            )
            emit_event(
                {
                    "type": "persistence_finished",
                    "has_plan": plan is not None,
                }
            )
        emit_event(
            {"type": "run_finished", "run_id": run_id, "success": plan is not None}
        )
        if self.store is not None and plan is not None:
            self.store.update_events(run_id, events)
        return ChatResponse(
            session_id=session_id, run_id=run_id, reply=reply, plan=plan, events=events
        )
