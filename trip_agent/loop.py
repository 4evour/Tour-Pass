from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from .context import (
    MemoryPolicy,
    build_planning_context,
    compact_conversation_history,
    compact_plan_memory,
    compact_planning_context,
    compact_repair_memory,
)
from .contracts import ChatResponse
from .model_schema import planner_tools
from .observability import log_event
from .plan_output import normalize_plan as normalize_complete_plan
from .providers.amap import AmapProvider
from .store import TripStore
from .validation import HardValidator

SYSTEM_PROMPT = """你是 Tour Pass 的主旅行规划 Agent。你负责地点选择、分日、顺序、时间安排、节奏和体验取舍；程序负责事实来源和最终交付否决。
必须通过原生工具完成工作，不得在普通文本中伪造工具调用或直接交付行程。优先批量调用相互独立的 search_places、place_detail、route 和 weather；地点、地址、坐标、开放时间、路线距离、路线耗时和天气只能来自工具。
证据收集阶段结束后，Runtime 才会提供 submit_itinerary；其严格 JSON Schema 是唯一结构契约。提交必须包含完整替代行程，每天按时间升序安排 2~4 个主要活动，并为住宿锚点和相邻实体提供已查询的路线证据。跨越午餐时段时显式安排午餐或用餐休息；公共交通段除工具耗时外至少留 10 分钟执行缓冲。
若用户只给出住宿区域，先搜索该区域内可定位的广场、地铁站或明确地标作为路线坐标锚点，hotel.name 仍使用“某某住宿区”、hotel.area 保留用户原文，hotel.place_id 填锚点 POI ID，status="recommended_area"；只有用户明确指定具体酒店时才可用 status="confirmed"。
没有固定开放时间、全天开放或 Provider 无法确认时写 opening_match=\"unknown\" 并给用户简短提示；不得虚构开放时段。预约要求未知时 required=null、status=\"unknown\"。已知开放时间与到访时段冲突时写 risk。用户未提供具体日期时，date_range.start、date_range.end、day.date 和 day.weekday 必须为 null；天气日期只能作为参考，不得擅自变成行程日期。
上下文包含 previous_plan_digest 时，本轮是修改已保存方案：保留用户未要求改变的部分，重新核验受影响事实，提交完整替代行程。摘要可能按 memory_limits 截断，不得据此删除未展示内容。
不要泄露思维过程，不要自行生成 Provider ID、坐标、路线数字或证据 hash。结构化时间轴、交通段、风险和最终叙述必须互相一致，不能声称未被证据支持的事实。
"""


class TripAgent:
    def __init__(
        self,
        llm: Any,
        amap: AmapProvider | None = None,
        weather: Any = None,
        store: TripStore | None = None,
        reviewer: Any = None,
        validator: HardValidator | None = None,
        max_steps: int = 24,
        max_tool_calls: int = 48,
        max_submit_attempts: int = 4,
        memory_policy: MemoryPolicy | None = None,
    ) -> None:
        self.llm = llm
        self.amap = amap or AmapProvider()
        self.weather = weather
        self.store = store
        self.reviewer = reviewer
        self.validator = validator or HardValidator()
        self.max_steps = max(1, min(max_steps, 32))
        self.max_tool_calls = max(1, min(max_tool_calls, 96))
        self.max_submit_attempts = max(1, min(max_submit_attempts, 6))
        self.memory_policy = memory_policy or MemoryPolicy()
        self.sessions: dict[str, list[dict[str, str]]] = {}

    async def close(self) -> None:
        await self.amap.close()
        if self.weather is not None and hasattr(self.weather, "close"):
            await self.weather.close()

    @staticmethod
    def _required(arguments: dict[str, Any], key: str) -> str:
        value = str(arguments.get(key, "")).strip()
        if not value:
            raise ValueError(f"工具参数 {key} 不能为空")
        return value

    @classmethod
    def _model_tool_result(cls, tool: str, result: dict[str, Any]) -> dict[str, Any]:
        metadata = {
            key: result.get(key)
            for key in ("source", "cache_hit", "response_hash")
            if key in result
        }
        if tool == "route":
            return {
                key: result.get(key)
                for key in (
                    "origin",
                    "destination",
                    "mode",
                    "distance_meters",
                    "duration_seconds",
                    "source",
                    "cache_hit",
                    "response_hash",
                )
                if key in result
            }
        if tool == "place_detail":
            place = result.get("place")
            if not isinstance(place, dict):
                return {**metadata, "place": None}
            compact_place = {
                key: place.get(key)
                for key in (
                    "id",
                    "name",
                    "type",
                    "address",
                    "adname",
                    "business_area",
                    "location",
                    "alias",
                    "business_hours",
                    "opentime",
                    "opentime2",
                )
                if place.get(key) not in (None, "", [], {})
            }
            biz_ext = place.get("biz_ext")
            if isinstance(biz_ext, dict):
                compact_biz_ext = {
                    key: biz_ext.get(key)
                    for key in ("rating", "cost", "open_time", "open_time2")
                    if biz_ext.get(key) not in (None, "", [], {})
                }
                if compact_biz_ext:
                    compact_place["biz_ext"] = compact_biz_ext
            return {**metadata, "place": compact_place}
        if tool == "search_places":
            return {**metadata, "places": result.get("places", [])}
        if tool == "weather":
            return {
                key: result.get(key)
                for key in (
                    "provider",
                    "available",
                    "city",
                    "days",
                    "fallback_from",
                    "fallback_reason",
                    "cache_hit",
                    "response_hash",
                )
                if key in result
            }
        return dict(result)

    @staticmethod
    def _evidence_snapshot(
        known_places: dict[str, dict[str, Any]],
        route_evidence: list[dict[str, Any]],
        weather_evidence: dict[str, Any] | None,
        *,
        policy: MemoryPolicy,
        focus_plan: dict[str, Any] | None = None,
        planning_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        focus_ids: set[str] = set()
        focus_names: set[str] = set()
        focus_route_hashes: set[str] = set()

        def add_place(value: Any) -> None:
            if not isinstance(value, dict):
                return
            place_id = str(value.get("place_id") or value.get("id") or "").strip()
            name = TripAgent._place_key(value.get("name"))
            if place_id:
                focus_ids.add(place_id)
            if name:
                focus_names.add(name)

        if isinstance(focus_plan, dict):
            add_place(focus_plan.get("hotel"))
            for day in focus_plan.get("days") or []:
                if not isinstance(day, dict):
                    continue
                add_place(day.get("start_anchor"))
                add_place(day.get("end_anchor"))
                for item in day.get("schedule") or []:
                    add_place(item)
                for transfer in day.get("transfers") or []:
                    if isinstance(transfer, dict) and transfer.get("evidence_hash"):
                        focus_route_hashes.add(str(transfer["evidence_hash"]))
        if isinstance(planning_context, dict):
            for value in planning_context.get("must_visits") or []:
                key = TripAgent._place_key(value)
                if key:
                    focus_names.add(key)
            hotel_area = TripAgent._place_key(planning_context.get("hotel_area"))
            if hotel_area:
                focus_names.add(hotel_area)

        places: dict[str, dict[str, Any]] = {}
        for place in known_places.values():
            place_id = str(place.get("id") or "").strip()
            if not place_id:
                continue
            compact = {
                key: place.get(key)
                for key in (
                    "id",
                    "name",
                    "type",
                    "address",
                    "area",
                    "adname",
                    "business_area",
                    "location",
                    "alias",
                    "business_hours",
                    "opentime",
                    "opentime2",
                    "biz_ext",
                    "source",
                    "response_hash",
                )
                if place.get(key) not in (None, "", [], {})
            }
            previous = places.get(place_id)
            if previous is None or len(compact) > len(previous):
                places[place_id] = compact

        def place_priority(place: dict[str, Any]) -> tuple[int, int]:
            place_id = str(place.get("id") or "")
            name = TripAgent._place_key(place.get("name"))
            focused = place_id in focus_ids or any(
                term in name or name in term for term in focus_names if name
            )
            return (int(focused), len(place))

        selected_places = sorted(
            places.values(),
            key=place_priority,
            reverse=True,
        )[: policy.evidence_places]

        routes_by_segment: dict[tuple[str, str, str], dict[str, Any]] = {}
        for route in route_evidence:
            if not isinstance(route, dict):
                continue
            key = (
                str(route.get("origin") or ""),
                str(route.get("destination") or ""),
                str(route.get("mode") or ""),
            )
            routes_by_segment[key] = route
        selected_routes = sorted(
            routes_by_segment.values(),
            key=lambda route: int(
                str(route.get("response_hash") or "") in focus_route_hashes
            ),
            reverse=True,
        )[: policy.evidence_routes]
        return {
            "places": selected_places,
            "routes": selected_routes,
            "weather": weather_evidence,
            "memory_limits": {
                "source_places": len(places),
                "included_places": len(selected_places),
                "source_routes": len(routes_by_segment),
                "included_routes": len(selected_routes),
            },
        }

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
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

    @classmethod
    def _resolve_route_point(
        cls,
        value: Any,
        known_places: dict[str, dict[str, Any]],
    ) -> str:
        raw = str(value or "").strip()
        coordinate = re.search(
            r"(?<!\d)(-?\d{2,3}(?:\.\d+)?)[,\s]+(-?\d{1,2}(?:\.\d+)?)(?!\d)",
            raw,
        )
        if coordinate:
            longitude = float(coordinate.group(1))
            latitude = float(coordinate.group(2))
            if -180 <= longitude <= 180 and -90 <= latitude <= 90:
                return f"{coordinate.group(1)},{coordinate.group(2)}"
        evidence = cls._resolve_place_evidence(
            {"place_id": raw, "name": raw},
            known_places,
        )
        location = str((evidence or {}).get("location") or "").strip()
        if location:
            return location
        raise ValueError(
            f"路线端点“{raw}”无法映射到已查询地点；请传坐标、POI ID 或已查询的准确名称。"
        )

    @classmethod
    def _resolve_route_arguments(
        cls,
        arguments: dict[str, Any],
        known_places: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        resolved = dict(arguments)
        resolved["origin"] = cls._resolve_route_point(
            arguments.get("origin"),
            known_places,
        )
        resolved["destination"] = cls._resolve_route_point(
            arguments.get("destination"),
            known_places,
        )
        return resolved

    @staticmethod
    def _clock_minutes(value: Any) -> int | None:
        match = re.fullmatch(r"(\d{1,2}):([0-5]\d)", str(value or "").strip())
        if match is None:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23:
            return None
        return hour * 60 + minute

    @classmethod
    def _repair_route_timeline(cls, plan: dict[str, Any]) -> list[dict[str, Any]]:
        repairs: list[dict[str, Any]] = []
        for day_index, day in enumerate(plan.get("days") or []):
            if not isinstance(day, dict):
                continue
            schedule = [
                item for item in day.get("schedule") or [] if isinstance(item, dict)
            ]
            physical = [
                (index, item)
                for index, item in enumerate(schedule)
                if item.get("type") in {"visit", "meal"}
            ]
            transfers = [
                item for item in day.get("transfers") or [] if isinstance(item, dict)
            ]
            day_start = cls._clock_minutes(day.get("start_time"))
            day_end = cls._clock_minutes(day.get("end_time"))
            for physical_index, (schedule_index, destination) in enumerate(physical):
                origin = (
                    day.get("start_anchor") or {}
                    if physical_index == 0
                    else physical[physical_index - 1][1]
                )
                origin_end = (
                    day_start
                    if physical_index == 0
                    else cls._clock_minutes(origin.get("end"))
                )
                destination_start = cls._clock_minutes(destination.get("start"))
                destination_end = cls._clock_minutes(destination.get("end"))
                if None in (origin_end, destination_start, destination_end):
                    continue
                transfer = next(
                    (
                        item
                        for item in transfers
                        if item.get("from_name") == origin.get("name")
                        and item.get("to_name") == destination.get("name")
                    ),
                    None,
                )
                if transfer is None:
                    continue
                route_minutes = int(transfer.get("duration_minutes") or 0)
                mode = str(transfer.get("mode") or "")
                buffer_minutes = (
                    10 if mode == "transit" else 5 if mode in {"driving", "taxi"} else 0
                )
                required_start = origin_end + route_minutes + buffer_minutes
                if destination_start >= required_start:
                    continue
                shifted_end = destination_end + required_start - destination_start
                later_starts = [
                    minute
                    for item in schedule[schedule_index + 1 :]
                    if (minute := cls._clock_minutes(item.get("start"))) is not None
                ]
                boundary = min(later_starts or [day_end or 24 * 60])
                if shifted_end > boundary or (
                    day_end is not None and shifted_end > day_end
                ):
                    continue
                destination["start"] = (
                    f"{required_start // 60:02d}:{required_start % 60:02d}"
                )
                destination["end"] = f"{shifted_end // 60:02d}:{shifted_end % 60:02d}"
                transfer["start"] = f"{origin_end // 60:02d}:{origin_end % 60:02d}"
                transfer_end = origin_end + route_minutes
                transfer["end"] = f"{transfer_end // 60:02d}:{transfer_end % 60:02d}"
                repairs.append(
                    {
                        "path": f"$.days[{day_index}].schedule[{schedule_index}]",
                        "reason": "route_execution_buffer",
                        "start": destination["start"],
                        "end": destination["end"],
                    }
                )
        return repairs

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
            prior_history = self.store.history(session_id, owner)
            previous_plan = self.store.latest_plan(session_id, owner)
        else:
            prior_history = self.sessions.setdefault(session_id, [])
            previous_plan = None
        planning_context = build_planning_context(previous_plan, message, prior_history)
        started_at = time.perf_counter()
        events: list[dict[str, Any]] = []

        def emit_event(event: dict[str, Any]) -> None:
            enriched = {
                **event,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            }
            events.append(enriched)
            log_fields = {"run_id": run_id, "session_id": session_id, **enriched}
            log_event("planner_event", **log_fields)
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

        previous_plan_memory = compact_plan_memory(previous_plan, self.memory_policy)
        context_payload = {
            "planning_context": compact_planning_context(planning_context),
            "previous_plan_digest": previous_plan_memory,
        }
        base_history: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *compact_conversation_history(prior_history, self.memory_policy),
            {
                "role": "system",
                "content": "当前结构化会话状态："
                + json.dumps(
                    context_payload, ensure_ascii=False, separators=(",", ":")
                ),
            },
            {"role": "user", "content": message},
        ]
        model_history = list(base_history)
        tool_count = 0
        submit_attempts = 0
        reply = ""
        plan: dict[str, Any] | None = None
        known_places: dict[str, dict[str, Any]] = {}
        route_evidence: list[dict[str, Any]] = []
        weather_evidence: dict[str, Any] | None = None
        successful_tool_calls: dict[str, dict[str, Any]] = {}
        tool_call_locks: dict[str, asyncio.Lock] = {}
        submitted_plan_hashes: set[str] = set()
        repair_context: dict[str, Any] | None = None

        def compact_history(*, include_repair: bool = True) -> list[dict[str, Any]]:
            history = list(base_history)
            focus_plan = (
                repair_context.get("candidate_plan")
                if isinstance(repair_context, dict)
                else previous_plan_memory
            )
            snapshot = self._evidence_snapshot(
                known_places,
                route_evidence,
                weather_evidence,
                policy=self.memory_policy,
                focus_plan=focus_plan,
                planning_context=planning_context,
            )
            if snapshot["places"] or snapshot["routes"] or snapshot["weather"]:
                history.append(
                    {
                        "role": "system",
                        "content": "当前已核验证据："
                        + json.dumps(
                            snapshot, ensure_ascii=False, separators=(",", ":")
                        ),
                    }
                )
            repair_memory = compact_repair_memory(repair_context, self.memory_policy)
            if include_repair and repair_memory is not None:
                history.append(
                    {
                        "role": "system",
                        "content": "当前待修复候选："
                        + json.dumps(
                            repair_memory, ensure_ascii=False, separators=(",", ":")
                        ),
                    }
                )
            return history

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

        def output_item(call_id: str, result: dict[str, Any]) -> dict[str, Any]:
            return {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result, ensure_ascii=False, separators=(",", ":"))[
                    :16000
                ],
            }

        async def execute_external_unlocked(
            call: dict[str, Any],
            arguments: dict[str, Any],
        ) -> tuple[dict[str, Any], dict[str, Any] | None]:
            nonlocal tool_count
            name = call["name"]
            call_id = call["call_id"]
            if name == "route":
                try:
                    arguments = self._resolve_route_arguments(
                        arguments,
                        known_places,
                    )
                except ValueError as exc:
                    emit_event(
                        {
                            "type": "tool_rejected",
                            "tool": name,
                            "error": "unresolved_route_endpoint",
                            "message": str(exc),
                        }
                    )
                    return output_item(
                        call_id,
                        {
                            "ok": False,
                            "error": {
                                "code": "unresolved_route_endpoint",
                                "message": str(exc),
                            },
                        },
                    ), None
            key = tool_call_key(name, arguments)
            if key in successful_tool_calls:
                compact_result = successful_tool_calls[key]
                emit_event(
                    {
                        "type": "tool_finished",
                        "tool": name,
                        "reused": True,
                        "cache_hit": True,
                        "model_context_chars": len(
                            json.dumps(compact_result, ensure_ascii=False)
                        ),
                        "model_result": compact_result,
                    }
                )
                return output_item(
                    call_id,
                    {"ok": True, "reused": True, "result": compact_result},
                ), None
            if tool_count >= self.max_tool_calls:
                emit_event(
                    {
                        "type": "tool_rejected",
                        "tool": name,
                        "error": "tool_budget_exceeded",
                    }
                )
                return output_item(
                    call_id,
                    {
                        "ok": False,
                        "error": {
                            "code": "tool_budget_exceeded",
                            "message": "外部工具预算已用完，请使用现有证据提交行程。",
                        },
                    },
                ), None
            tool_count += 1
            tool_started_at = time.perf_counter()
            emit_event(
                {
                    "type": "tool_started",
                    "tool": name,
                    "arguments": arguments,
                    "tool_count": tool_count,
                }
            )
            try:
                raw_result = await self.call_tool(name, arguments)
                ingest_evidence(name, raw_result)
                compact_result = self._model_tool_result(name, raw_result)
                successful_tool_calls[key] = compact_result
                emit_event(
                    {
                        "type": "tool_finished",
                        "tool": name,
                        "cache_hit": raw_result.get("cache_hit", False),
                        "response_hash": raw_result.get("response_hash", ""),
                        "tool_elapsed_ms": round(
                            (time.perf_counter() - tool_started_at) * 1000
                        ),
                        "raw_result_chars": len(
                            json.dumps(raw_result, ensure_ascii=False)
                        ),
                        "model_context_chars": len(
                            json.dumps(compact_result, ensure_ascii=False)
                        ),
                        "model_result": compact_result,
                    }
                )
                return output_item(
                    call_id, {"ok": True, "result": compact_result}
                ), raw_result
            except Exception as exc:
                emit_event(
                    {
                        "type": "tool_finished",
                        "tool": name,
                        "error": str(exc),
                        "tool_elapsed_ms": round(
                            (time.perf_counter() - tool_started_at) * 1000
                        ),
                    }
                )
                return output_item(
                    call_id,
                    {
                        "ok": False,
                        "error": {
                            "code": "tool_execution_failed",
                            "message": str(exc),
                        },
                    },
                ), None

        async def execute_external(
            call: dict[str, Any],
            arguments: dict[str, Any],
        ) -> tuple[dict[str, Any], dict[str, Any] | None]:
            key = tool_call_key(call["name"], arguments)
            lock = tool_call_locks.setdefault(key, asyncio.Lock())
            async with lock:
                return await execute_external_unlocked(call, arguments)

        terminal = False
        for step in range(self.max_steps):
            submit_enabled = step >= 2 or submit_attempts > 0
            reasoning_effort = (
                getattr(self.llm, "final_reasoning_effort", "medium")
                if submit_enabled
                else getattr(self.llm, "reasoning_effort", "low")
            )
            emit_event(
                {
                    "type": "model_started",
                    "phase": "agent_loop",
                    "step": step + 1,
                    "detail": (
                        f"外部工具 {tool_count}/{self.max_tool_calls}，"
                        f"提交 {submit_attempts}/{self.max_submit_attempts}"
                    ),
                }
            )
            response = await self.llm.ainvoke(
                model_history,
                trace={
                    "run_id": run_id,
                    "session_id": session_id,
                    "stage": "agent_loop",
                    "step": step + 1,
                },
                on_progress=emit_event,
                reasoning_effort=reasoning_effort,
                tools=planner_tools(allow_submit=submit_enabled),
                tool_choice="required",
            )
            calls = [
                call
                for call in getattr(response, "tool_calls", [])
                if isinstance(call, dict)
            ]
            emit_event(
                {
                    "type": "model_finished",
                    "phase": "agent_loop",
                    "step": step + 1,
                    "tool_calls": [call.get("name") for call in calls],
                    "model_metrics": getattr(response, "metrics", {}),
                }
            )
            if not calls:
                model_history = compact_history()
                model_history.append(
                    {
                        "role": "user",
                        "content": "普通文本不能结束规划。请选择工具；需要追问时调用 ask_user，完成时调用 submit_itinerary。",
                    }
                )
                emit_event(
                    {
                        "type": "decision_rejected",
                        "action": "text",
                        "error": "terminal_tool_required",
                        "step": step + 1,
                    }
                )
                continue
            model_history = compact_history(
                include_repair=not any(
                    call.get("name") == "submit_itinerary" for call in calls
                )
            )

            parsed_calls: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
            for call in calls:
                try:
                    arguments = json.loads(call.get("arguments") or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError("arguments 必须是对象")
                except (ValueError, json.JSONDecodeError) as exc:
                    arguments = None
                    model_history.append(
                        {
                            "type": "function_call",
                            "call_id": call.get("call_id"),
                            "name": call.get("name"),
                            "arguments": call.get("arguments") or "{}",
                        }
                    )
                    model_history.append(
                        output_item(
                            str(call.get("call_id") or ""),
                            {
                                "ok": False,
                                "error": {
                                    "code": "invalid_tool_arguments",
                                    "message": str(exc),
                                },
                            },
                        )
                    )
                parsed_calls.append((call, arguments))

            emit_event(
                {
                    "type": "model_tool_calls",
                    "step": step + 1,
                    "calls": [
                        {
                            "call_id": call.get("call_id"),
                            "name": call.get("name"),
                            "arguments": arguments,
                        }
                        for call, arguments in parsed_calls
                    ],
                }
            )
            terminal_calls = [
                call
                for call, arguments in parsed_calls
                if arguments is not None
                and call.get("name") in {"ask_user", "submit_itinerary"}
            ]
            if terminal_calls and len(parsed_calls) != 1:
                for call, arguments in parsed_calls:
                    if arguments is None:
                        continue
                    model_history.append(
                        {
                            "type": "function_call",
                            "call_id": call["call_id"],
                            "name": call["name"],
                            "arguments": call["arguments"],
                        }
                    )
                    model_history.append(
                        output_item(
                            call["call_id"],
                            {
                                "ok": False,
                                "error": {
                                    "code": "terminal_tool_must_be_exclusive",
                                    "message": "ask_user 和 submit_itinerary 必须单独调用。",
                                },
                            },
                        )
                    )
                continue

            valid_calls = [
                (call, arguments)
                for call, arguments in parsed_calls
                if arguments is not None
            ]
            for call, _ in valid_calls:
                model_history.append(
                    {
                        "type": "function_call",
                        "call_id": call["call_id"],
                        "name": call["name"],
                        "arguments": call["arguments"],
                    }
                )

            if terminal_calls:
                call, arguments = valid_calls[0]
                if call["name"] == "ask_user":
                    reply = str(arguments.get("question") or "请补充一个关键信息。")
                    model_history.append(
                        output_item(call["call_id"], {"ok": True, "terminal": True})
                    )
                    emit_event({"type": "assistant_message", "content": reply})
                    terminal = True
                    break

                submit_attempts += 1
                emit_event(
                    {
                        "type": "plan_validation_started",
                        "submit_attempt": submit_attempts,
                    }
                )
                validation_started_at = time.perf_counter()
                try:
                    candidate = self.normalize_plan(
                        arguments.get("plan") or {},
                        known_places=known_places,
                        route_evidence=route_evidence,
                        weather_evidence=weather_evidence,
                    )
                    timeline_repairs = self._repair_route_timeline(candidate)
                    if timeline_repairs:
                        emit_event(
                            {
                                "type": "plan_repair_applied",
                                "strategy": "route_timeline",
                                "repairs": timeline_repairs,
                            }
                        )
                    candidate["planning_context"] = planning_context
                    report = self.validator.validate(candidate, planning_context)
                except ValueError as exc:
                    report = {
                        "passed": False,
                        "validator_version": self.validator.version,
                        "plan_hash": "",
                        "failure_fingerprint": "",
                        "hard_failures": [
                            {
                                "code": "PLAN_NORMALIZATION_FAILED",
                                "severity": "hard",
                                "path": "$.plan",
                                "message": str(exc),
                                "actual": None,
                                "expected": "完整可解析行程",
                                "evidence_refs": [],
                                "allowed_actions": ["repair_plan_structure"],
                            }
                        ],
                        "warnings": [],
                    }
                    candidate = None

                repeated_plan = bool(
                    report.get("plan_hash")
                    and report["plan_hash"] in submitted_plan_hashes
                )
                if report.get("plan_hash"):
                    submitted_plan_hashes.add(report["plan_hash"])
                if repeated_plan and not report.get("passed"):
                    report["hard_failures"] = [
                        {
                            "code": "UNCHANGED_RESUBMISSION",
                            "severity": "hard",
                            "path": "$.plan",
                            "message": "计划内容没有变化，不能重复提交。",
                            "actual": report["plan_hash"],
                            "expected": "根据上一轮错误修改后的新计划",
                            "evidence_refs": [],
                            "allowed_actions": ["apply_validation_repairs"],
                        },
                        *report["hard_failures"],
                    ]
                report["submit_attempt"] = submit_attempts
                report["repairs_used"] = max(0, submit_attempts - 1)
                report["repairs_remaining"] = max(
                    0, self.max_submit_attempts - submit_attempts
                )
                emit_event(
                    {
                        "type": "plan_validation_finished",
                        "submit_attempt": submit_attempts,
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
                if report["passed"] and candidate is not None:
                    review = {
                        "verdict": "not_run",
                        "summary": "独立审查未启用",
                        "issues": [],
                        "shadow": True,
                    }
                    if self.reviewer is not None:
                        review_started_at = time.perf_counter()
                        emit_event({"type": "review_started"})
                        try:
                            review = await self.reviewer.review(
                                planning_context=planning_context,
                                plan=candidate,
                                validation_report=report,
                                trace={"run_id": run_id, "session_id": session_id},
                                on_model_event=emit_event,
                            )
                        except Exception as exc:
                            review = {
                                "verdict": "unavailable",
                                "summary": "独立审查暂不可用，硬校验结果不受影响。",
                                "issues": [],
                                "shadow": True,
                                "error_type": type(exc).__name__,
                            }
                        emit_event(
                            {
                                "type": "review_finished",
                                "verdict": review.get("verdict"),
                                "review_elapsed_ms": round(
                                    (time.perf_counter() - review_started_at) * 1000
                                ),
                                "shadow": review.get("shadow", True),
                                "issue_count": len(review.get("issues") or []),
                                "review_report": review,
                            }
                        )
                    if review.get("verdict") == "revise":
                        issues = review.get("issues") or []
                        completeness = candidate.get("completeness") or {}
                        completeness["score"] = max(
                            0,
                            min(
                                int(completeness.get("score") or 0),
                                100 - min(len(issues), 5) * 8,
                            ),
                        )
                        completeness["total"] = int(completeness.get("total") or 0) + 1
                        completeness.setdefault("checks", []).append(
                            {
                                "name": "独立质量审查",
                                "status": "warning",
                                "detail": f"发现 {len(issues)} 项需关注的质量问题",
                            }
                        )
                    if (
                        review.get("verdict") == "revise"
                        and not review.get("shadow", True)
                        and submit_attempts < self.max_submit_attempts
                    ):
                        report["passed"] = False
                        report["review_issues"] = review.get("issues", [])
                        repair_context = {
                            "candidate_plan": arguments.get("plan") or {},
                            "validation_report": {
                                "hard_failures": report.get("hard_failures", []),
                                "review_issues": report["review_issues"],
                                "repairs_remaining": report["repairs_remaining"],
                            },
                        }
                        model_history = compact_history()
                        continue
                    candidate["validation"] = report
                    candidate["review"] = review
                    plan = candidate
                    reply = str(arguments.get("reply") or "行程已经整理完成。")
                    model_history.append(
                        output_item(
                            call["call_id"],
                            {
                                "accepted": True,
                                "terminal": True,
                                "plan_hash": report["plan_hash"],
                                "warnings": report["warnings"],
                            },
                        )
                    )
                    emit_event(
                        {
                            "type": "plan_ready",
                            "submit_attempt": submit_attempts,
                            "tool_count": tool_count,
                            "completeness_score": plan["completeness"]["score"],
                        }
                    )
                    terminal = True
                    break

                repair_context = {
                    "candidate_plan": arguments.get("plan") or {},
                    "validation_report": {
                        "hard_failures": report.get("hard_failures", []),
                        "warnings": report.get("warnings", []),
                        "repairs_remaining": report["repairs_remaining"],
                    },
                }
                model_history = compact_history()
                emit_event(
                    {
                        "type": "plan_rejected",
                        "submit_attempt": submit_attempts,
                        "repairs_remaining": report["repairs_remaining"],
                    }
                )
                if submit_attempts >= self.max_submit_attempts:
                    codes = "、".join(
                        dict.fromkeys(item["code"] for item in report["hard_failures"])
                    )
                    reply = f"行程未通过可信校验，已停止交付。未解决问题：{codes}。"
                    emit_event(
                        {
                            "type": "run_error",
                            "error": "repair_budget_exhausted",
                            "hard_failure_codes": [
                                item["code"] for item in report["hard_failures"]
                            ],
                        }
                    )
                    terminal = True
                    break
                continue

            external_calls = [
                (call, arguments)
                for call, arguments in valid_calls
                if call["name"] in {"search_places", "place_detail", "route", "weather"}
            ]
            unknown_calls = [
                (call, arguments)
                for call, arguments in valid_calls
                if call["name"]
                not in {
                    "search_places",
                    "place_detail",
                    "route",
                    "weather",
                    "ask_user",
                    "submit_itinerary",
                }
            ]
            results = await asyncio.gather(
                *(
                    execute_external(call, arguments)
                    for call, arguments in external_calls
                )
            )
            model_history.extend(item for item, _ in results)
            for call, _ in unknown_calls:
                model_history.append(
                    output_item(
                        call["call_id"],
                        {
                            "ok": False,
                            "error": {
                                "code": "unknown_tool",
                                "message": f"未知工具：{call['name']}",
                            },
                        },
                    )
                )

        if not terminal and plan is None:
            reply = "这次规划已达到运行上限，未生成通过可信校验的行程。"
            emit_event({"type": "run_error", "error": "step_budget_exceeded"})
        if not reply:
            reply = "行程没有完成。"
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
