from __future__ import annotations

import asyncio
import math
import re
from datetime import date, timedelta
from typing import Any, Callable

from .providers.amap import AmapProvider

EventEmitter = Callable[[dict[str, Any]], None]

_PACE = {
    "轻松": "relaxed",
    "标准": "balanced",
    "紧凑": "intensive",
    "relaxed": "relaxed",
    "balanced": "balanced",
    "intensive": "intensive",
}
_TRANSPORT = {
    "公共交通优先": "public_transit",
    "打车优先": "taxi",
    "步行优先": "walking",
    "自驾": "driving",
    "混合交通": "mixed",
    "public_transit": "public_transit",
    "taxi": "taxi",
    "walking": "walking",
    "driving": "driving",
    "mixed": "mixed",
}
_PERIOD_ORDER = {
    "morning": 0,
    "lunch": 1,
    "afternoon": 2,
    "dinner": 3,
    "evening": 4,
}


def _text(value: Any, fallback: str = "") -> str:
    return str(value or fallback).strip()


def _key(value: Any) -> str:
    return re.sub(r"[\s·（）()\-—]", "", _text(value)).casefold()


def _clock(value: Any, fallback: int) -> int:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", _text(value))
    if not match:
        return fallback
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return fallback
    return hour * 60 + minute


def _hhmm(minutes: int) -> str:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _matches(left: Any, right: Any) -> bool:
    left_key, right_key = _key(left), _key(right)
    return bool(
        left_key and right_key and (left_key in right_key or right_key in left_key)
    )


def _default_stop(day: int, city: str) -> dict[str, Any]:
    return {
        "type": "free_time",
        "name": f"{city}第{day}日弹性探索",
        "search_query": None,
        "period": "afternoon",
        "duration_minutes": 120,
        "reason": "保留弹性时间，按当天体力和现场情况调整。",
        "optional": True,
        "practical_tip": "出发前结合天气和营业状态选择附近活动。",
    }


def repair_skeleton(
    skeleton: dict[str, Any], context: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repaired = dict(skeleton)
    city = _text(context.get("destination"))
    requested_days = max(1, min(int(context.get("days") or 3), 7))
    raw_days = [
        dict(item) for item in skeleton.get("days") or [] if isinstance(item, dict)
    ]
    repairs: list[dict[str, Any]] = []

    if len(raw_days) > requested_days:
        raw_days = raw_days[:requested_days]
        repairs.append({"reason": "trim_extra_days", "days": requested_days})
    while len(raw_days) < requested_days:
        day_number = len(raw_days) + 1
        raw_days.append(
            {
                "day": day_number,
                "theme": "弹性城市探索",
                "summary": "模型未返回该日完整安排，保留可调整时段。",
                "primary_area": city,
                "secondary_areas": [],
                "stops": [_default_stop(day_number, city)],
            }
        )
        repairs.append({"reason": "fill_missing_day", "day": day_number})

    seen: set[str] = set()
    for day_number, day in enumerate(raw_days, 1):
        day["day"] = day_number
        unique_stops: list[dict[str, Any]] = []
        for raw_stop in day.get("stops") or []:
            if not isinstance(raw_stop, dict):
                continue
            stop = dict(raw_stop)
            name_key = _key(stop.get("name"))
            if name_key and name_key in seen:
                repairs.append(
                    {"reason": "remove_duplicate_stop", "name": _text(stop.get("name"))}
                )
                continue
            if name_key:
                seen.add(name_key)
            stop["duration_minutes"] = max(
                30, min(int(stop.get("duration_minutes") or 90), 240)
            )
            stop["optional"] = bool(stop.get("optional", True))
            unique_stops.append(stop)
        if not unique_stops:
            unique_stops.append(_default_stop(day_number, city))
        while len(unique_stops) > 4:
            optional_index = next(
                (
                    index
                    for index in range(len(unique_stops) - 1, -1, -1)
                    if unique_stops[index].get("optional")
                ),
                -1,
            )
            if optional_index < 0:
                break
            removed = unique_stops.pop(optional_index)
            repairs.append(
                {"reason": "trim_optional_stop", "name": _text(removed.get("name"))}
            )
        day["stops"] = unique_stops

    for must_visit in context.get("must_visits") or []:
        if any(
            _matches(must_visit, stop.get("name"))
            for day in raw_days
            for stop in day.get("stops") or []
        ):
            continue
        target = min(raw_days, key=lambda item: len(item.get("stops") or []))
        stops = list(target.get("stops") or [])
        required_stop = {
            "type": "visit",
            "name": _text(must_visit),
            "search_query": _text(must_visit),
            "period": "afternoon",
            "duration_minutes": 120,
            "reason": "用户明确指定的必去地点。",
            "optional": False,
            "practical_tip": "出发前确认开放和预约要求。",
        }
        if len(stops) >= 4:
            optional_index = next(
                (
                    index
                    for index in range(len(stops) - 1, -1, -1)
                    if stops[index].get("optional")
                ),
                -1,
            )
            if optional_index >= 0:
                stops[optional_index] = required_stop
            else:
                stops.append(required_stop)
        else:
            stops.append(required_stop)
        target["stops"] = stops
        repairs.append({"reason": "add_required_stop", "name": _text(must_visit)})

    day_start = _clock((context.get("daily_window") or {}).get("start"), 9 * 60)
    day_end = _clock((context.get("daily_window") or {}).get("end"), 20 * 60)
    if day_start <= 11 * 60 + 30 and day_end >= 13 * 60 + 30:
        for day in raw_days:
            stops = list(day.get("stops") or [])
            has_lunch = any(
                stop.get("type") == "meal"
                or stop.get("period") == "lunch"
                or "午餐" in _text(stop.get("name"))
                for stop in stops
            )
            if has_lunch:
                continue
            area = _text(day.get("primary_area"), city)
            lunch = {
                "type": "meal",
                "name": f"{area}午餐",
                "search_query": f"{area} 本地特色餐厅",
                "period": "lunch",
                "duration_minutes": 60,
                "reason": "在当天主要游览片区就近用餐，减少折返。",
                "optional": True,
                "practical_tip": "热门餐厅建议错峰或提前取号。",
            }
            insert_at = min(1, len(stops))
            if len(stops) >= 4:
                optional_index = next(
                    (
                        index
                        for index in range(len(stops) - 1, -1, -1)
                        if stops[index].get("optional")
                    ),
                    -1,
                )
                if optional_index >= 0:
                    stops.pop(optional_index)
            stops.insert(insert_at, lunch)
            day["stops"] = stops
            repairs.append({"reason": "add_lunch", "day": day["day"]})

    repaired["days"] = raw_days
    return repaired, repairs


def _score_place(place: dict[str, Any], name: str, query: str, stop_type: str) -> int:
    canonical = _key(place.get("name"))
    requested_name = _key(name)
    requested_query = _key(query)
    place_type = _text(place.get("type"))
    score = int(bool(place.get("id"))) * 5 + int(bool(place.get("location"))) * 10
    if canonical == requested_name or canonical == requested_query:
        score += 100
    elif requested_name and (
        requested_name in canonical or canonical in requested_name
    ):
        score += 65
    elif requested_query and (
        requested_query in canonical or canonical in requested_query
    ):
        score += 35
    is_food = "餐饮服务" in place_type
    if stop_type == "meal":
        score += 25 if is_food else -40
    elif stop_type == "hotel":
        if any(marker in place_type for marker in ("住宿服务", "交通设施服务")):
            score += 30
        elif "风景名胜" in place_type:
            score -= 40
    elif stop_type == "visit":
        if any(
            marker in place_type for marker in ("风景名胜", "科教文化服务", "公园广场")
        ):
            score += 30
        if any(
            marker in place_type
            for marker in ("餐饮服务", "住宿服务", "地名地址信息", "交通设施服务")
        ):
            score -= 60
    return score


def _select_place(
    result: dict[str, Any] | None, *, name: str, query: str, stop_type: str
) -> dict[str, Any] | None:
    places = (result or {}).get("places") or []
    candidates = [item for item in places if isinstance(item, dict)]
    if not candidates:
        return None
    selected = max(
        candidates, key=lambda item: _score_place(item, name, query, stop_type)
    )
    if not selected.get("id") or not selected.get("location"):
        return None
    return selected


def _route_mode(context: dict[str, Any]) -> str:
    transport = _text(context.get("transport"))
    if transport in {"自驾", "打车优先", "driving", "taxi"}:
        return "driving"
    if transport in {"步行优先", "walking"}:
        return "walking"
    return "transit"


def _estimate_route(origin: str, destination: str, mode: str) -> tuple[int, int]:
    try:
        origin_lon, origin_lat = (float(value) for value in origin.split(",", 1))
        destination_lon, destination_lat = (
            float(value) for value in destination.split(",", 1)
        )
    except (TypeError, ValueError):
        return 20, 0
    mean_latitude = math.radians((origin_lat + destination_lat) / 2)
    east_west = (
        math.radians(destination_lon - origin_lon) * math.cos(mean_latitude) * 6_371_000
    )
    north_south = math.radians(destination_lat - origin_lat) * 6_371_000
    distance = max(1, math.ceil(math.hypot(east_west, north_south) * 1.25))
    if mode == "walking":
        minutes = max(5, math.ceil(distance / 75))
    elif mode == "driving":
        minutes = max(10, 8 + math.ceil(distance / 350))
    else:
        minutes = max(12, 8 + math.ceil(distance / 220))
    return minutes, distance


class ItineraryAssembler:
    def __init__(
        self, amap: AmapProvider, weather: Any = None, max_provider_calls: int = 14
    ) -> None:
        self.amap = amap
        self.weather = weather
        self.max_provider_calls = max(1, max_provider_calls)

    async def _search(
        self,
        city: str,
        query: str,
        emit: EventEmitter,
    ) -> tuple[str, dict[str, Any] | None]:
        emit(
            {
                "type": "tool_started",
                "tool": "search_places",
                "arguments": {"city": city, "keywords": query},
            }
        )
        started = asyncio.get_running_loop().time()
        try:
            result = await self.amap.search_places(city, query, limit=5)
            emit(
                {
                    "type": "tool_finished",
                    "tool": "search_places",
                    "cache_hit": bool(result.get("cache_hit")),
                    "tool_elapsed_ms": round(
                        (asyncio.get_running_loop().time() - started) * 1000
                    ),
                    "response_hash": result.get("response_hash", ""),
                }
            )
            return query, result
        except Exception as exc:
            emit(
                {
                    "type": "tool_finished",
                    "tool": "search_places",
                    "error": str(exc),
                    "tool_elapsed_ms": round(
                        (asyncio.get_running_loop().time() - started) * 1000
                    ),
                }
            )
            return query, None

    async def _route(
        self,
        city: str,
        origin: str,
        destination: str,
        mode: str,
        emit: EventEmitter,
    ) -> tuple[tuple[str, str, str], dict[str, Any] | None]:
        key = (origin, destination, mode)
        emit(
            {
                "type": "tool_started",
                "tool": "route",
                "arguments": {"city": city, "mode": mode},
            }
        )
        started = asyncio.get_running_loop().time()
        try:
            result = await self.amap.route(city, origin, destination, mode)
            if int(result.get("duration_seconds") or 0) <= 0:
                result = None
            emit(
                {
                    "type": "tool_finished",
                    "tool": "route",
                    "cache_hit": bool((result or {}).get("cache_hit")),
                    "tool_elapsed_ms": round(
                        (asyncio.get_running_loop().time() - started) * 1000
                    ),
                    "response_hash": (result or {}).get("response_hash", ""),
                }
            )
            return key, result
        except Exception as exc:
            emit(
                {
                    "type": "tool_finished",
                    "tool": "route",
                    "error": str(exc),
                    "tool_elapsed_ms": round(
                        (asyncio.get_running_loop().time() - started) * 1000
                    ),
                }
            )
            return key, None

    async def assemble(
        self,
        context: dict[str, Any],
        skeleton: dict[str, Any],
        emit: EventEmitter,
    ) -> tuple[
        dict[str, Any],
        dict[str, dict[str, Any]],
        list[dict[str, Any]],
        dict[str, Any] | None,
    ]:
        city = _text(context.get("destination"))
        skeleton, repairs = repair_skeleton(skeleton, context)
        if repairs:
            emit(
                {
                    "type": "plan_repair_applied",
                    "strategy": "skeleton",
                    "repairs": repairs,
                }
            )

        query_specs: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        hotel = skeleton.get("hotel") if isinstance(skeleton.get("hotel"), dict) else {}
        hotel_query = _text(hotel.get("search_query"))
        if hotel_query:
            query_specs.setdefault(hotel_query, []).append(("hotel", hotel))
        for day in skeleton.get("days") or []:
            for stop in day.get("stops") or []:
                if not isinstance(stop, dict) or stop.get("type") == "free_time":
                    continue
                query = _text(stop.get("search_query") or stop.get("name"))
                if query:
                    query_specs.setdefault(query, []).append(
                        (_text(stop.get("type")), stop)
                    )

        weather_job = None
        weather_slots = 0
        if context.get("start_date") and self.weather is not None:
            weather_slots = 1
            emit({"type": "tool_started", "tool": "weather"})
            weather_job = self.weather.forecast(
                city, min(int(context.get("days") or 3), 7)
            )
        query_priority = sorted(
            query_specs,
            key=lambda query: (
                0
                if any(kind == "hotel" for kind, _ in query_specs[query])
                else 1
                if any(not target.get("optional") for _, target in query_specs[query])
                else 2,
            ),
        )
        search_queries = query_priority[
            : max(0, self.max_provider_calls - weather_slots)
        ]
        search_jobs = [self._search(city, query, emit) for query in search_queries]
        gathered = await asyncio.gather(
            *search_jobs,
            *([weather_job] if weather_job is not None else []),
            return_exceptions=True,
        )
        search_results = {
            query: result
            for item in gathered[: len(search_jobs)]
            if not isinstance(item, Exception)
            for query, result in [item]
        }
        weather_evidence = None
        if weather_job is not None and len(gathered) > len(search_jobs):
            weather_result = gathered[-1]
            if isinstance(weather_result, dict):
                weather_evidence = weather_result
                emit(
                    {
                        "type": "tool_finished",
                        "tool": "weather",
                        "cache_hit": bool(weather_result.get("cache_hit")),
                        "response_hash": weather_result.get("response_hash", ""),
                    }
                )

        known_places: dict[str, dict[str, Any]] = {}
        unresolved: list[str] = []
        for query, specs in query_specs.items():
            result = search_results.get(query)
            for stop_type, target in specs:
                selected = _select_place(
                    result,
                    name=_text(target.get("name")),
                    query=query,
                    stop_type=stop_type,
                )
                if selected is None:
                    unresolved.append(_text(target.get("name")) or query)
                    target["_unresolved"] = True
                    continue
                selected = dict(selected)
                selected["source"] = "amap"
                selected["response_hash"] = (result or {}).get("response_hash")
                place_id = _text(selected.get("id"))
                selected_name_key = _key(selected.get("name"))
                target_name_key = _key(target.get("name"))
                known_places[place_id] = selected
                if selected_name_key:
                    known_places[selected_name_key] = selected
                if target_name_key:
                    known_places[target_name_key] = selected
                target["_resolved_place"] = selected

        mode = _route_mode(context)
        route_buckets: list[list[tuple[str, str, str]]] = [[], [], []]
        for day in skeleton.get("days") or []:
            physical = [
                stop
                for stop in day.get("stops") or []
                if isinstance(stop, dict)
                and stop.get("type") in {"visit", "meal"}
                and not (stop.get("_unresolved") and stop.get("optional"))
            ]
            endpoints = [hotel, *physical, hotel]
            for edge_index, (left, right) in enumerate(zip(endpoints, endpoints[1:])):
                left_location = _text(
                    (left.get("_resolved_place") or {}).get("location")
                )
                right_location = _text(
                    (right.get("_resolved_place") or {}).get("location")
                )
                if (
                    not left_location
                    or not right_location
                    or left_location == right_location
                ):
                    continue
                priority = (
                    1
                    if edge_index == 0
                    else 2
                    if edge_index == len(endpoints) - 2
                    else 0
                )
                route_buckets[priority].append((left_location, right_location, mode))
        route_specs = list(
            dict.fromkeys(route for bucket in route_buckets for route in bucket)
        )
        route_budget = max(
            0, self.max_provider_calls - len(search_jobs) - weather_slots
        )
        selected_routes = route_specs[:route_budget]
        route_pairs = await asyncio.gather(
            *(
                self._route(city, origin, destination, route_mode, emit)
                for origin, destination, route_mode in selected_routes
            ),
            return_exceptions=True,
        )
        route_results = {
            key: result
            for item in route_pairs
            if not isinstance(item, Exception)
            for key, result in [item]
        }
        route_evidence = [
            result
            for result in route_results.values()
            if isinstance(result, dict) and int(result.get("duration_seconds") or 0) > 0
        ]

        skipped_provider_calls = (
            len(query_specs)
            - len(search_jobs)
            + len(route_specs)
            - len(selected_routes)
        )
        if skipped_provider_calls:
            skeleton.setdefault("warnings", []).append(
                "部分路线时间采用两点距离保守估算；出发前请以地图实时导航为准。"
            )
        raw_plan = self._build_plan(
            context,
            skeleton,
            route_results,
            weather_evidence,
            unresolved,
        )
        return raw_plan, known_places, route_evidence, weather_evidence

    def _build_plan(
        self,
        context: dict[str, Any],
        skeleton: dict[str, Any],
        route_results: dict[tuple[str, str, str], dict[str, Any] | None],
        weather_evidence: dict[str, Any] | None,
        unresolved: list[str],
    ) -> dict[str, Any]:
        city = _text(context.get("destination"))
        start_date = _text(context.get("start_date"))
        requested_days = int(context.get("days") or 3)
        window = context.get("daily_window") or {}
        default_start = _clock(window.get("start"), 9 * 60)
        maximum_end = _clock(window.get("end"), 20 * 60)
        mode = _route_mode(context)
        hotel = skeleton.get("hotel") if isinstance(skeleton.get("hotel"), dict) else {}
        hotel_area = _text(hotel.get("area"), _text(context.get("hotel_area"), city))
        hotel_name = (
            _text(context.get("hotel_area"))
            if context.get("hotel_area")
            else f"{hotel_area}住宿区"
        )
        if context.get("hotel_area"):
            hotel["area"] = _text(context.get("hotel_area"))
        hotel_evidence = hotel.get("_resolved_place") or {}
        hotel_location = _text(hotel_evidence.get("location"))
        raw_days: list[dict[str, Any]] = []

        for day_index, day in enumerate(skeleton.get("days") or [], 1):
            theme = _text(day.get("theme"), "城市探索")
            primary_area = _text(day.get("primary_area"), city)
            cursor = default_start
            area_counts: dict[str, int] = {}
            schedule: list[dict[str, Any]] = []
            transfers: list[dict[str, Any]] = []
            previous_name = hotel_name
            previous_location = hotel_location
            day_stops = [
                stop for stop in day.get("stops") or [] if isinstance(stop, dict)
            ]
            day_stops.sort(
                key=lambda stop: _PERIOD_ORDER.get(_text(stop.get("period")), 5)
            )
            for stop_index, stop in enumerate(day_stops):
                if stop.get("_unresolved") and stop.get("optional"):
                    continue
                stop_type = _text(stop.get("type"), "visit")
                evidence = stop.get("_resolved_place") or {}
                location = _text(evidence.get("location"))
                resolved_name = _text(evidence.get("name"), _text(stop.get("name")))
                evidence_area = _text(evidence.get("area"))
                if evidence_area:
                    area_counts[evidence_area] = area_counts.get(evidence_area, 0) + 1
                route = (
                    route_results.get((previous_location, location, mode))
                    if previous_location and location
                    else None
                )
                if previous_location and location and previous_location != location:
                    estimated_minutes, estimated_distance = _estimate_route(
                        previous_location, location, mode
                    )
                    route_minutes = (
                        max(
                            1,
                            math.ceil(
                                int((route or {}).get("duration_seconds") or 0) / 60
                            ),
                        )
                        if route
                        else 0
                    )
                    if route and route_minutes <= max(
                        estimated_minutes + 15, estimated_minutes * 2
                    ):
                        route_source = "amap"
                        route_distance = 0
                    else:
                        route = None
                        route_minutes = estimated_minutes
                        route_distance = estimated_distance
                        route_source = "estimate"
                    transfer_start = cursor
                    transfer_end = cursor + route_minutes
                    transfers.append(
                        {
                            "from_name": previous_name,
                            "to_name": resolved_name,
                            "from_location": previous_location,
                            "to_location": location,
                            "mode": mode,
                            "start": _hhmm(transfer_start),
                            "end": _hhmm(transfer_end),
                            "duration_minutes": route_minutes,
                            "distance_meters": route_distance,
                            "instructions": (
                                "已按实时路线结果预留通勤与换乘缓冲。"
                                if route
                                else "基于两点距离保守估算；出发前请用实时导航复核。"
                            ),
                            "source": route_source,
                            "evidence_hash": (route or {}).get("response_hash"),
                        }
                    )
                    cursor = transfer_end + (
                        10 if mode == "transit" else 5 if mode == "driving" else 0
                    )
                elif stop_type in {"visit", "meal"} and previous_name != _text(
                    stop.get("name")
                ):
                    cursor += 20

                period = _text(stop.get("period"), "afternoon")
                if stop_type == "meal" and period == "lunch":
                    cursor = max(cursor, 11 * 60 + 30)
                elif stop_type == "meal" and period == "dinner":
                    cursor = max(cursor, 17 * 60 + 30)
                duration = max(30, min(int(stop.get("duration_minutes") or 90), 240))
                if stop_type == "visit" and period == "morning":
                    duration = min(duration, 90)
                if (
                    stop_type == "visit"
                    and period == "morning"
                    and stop_index + 1 < len(day_stops)
                ):
                    next_stop = day_stops[stop_index + 1]
                    if (
                        _text(next_stop.get("type")) == "meal"
                        and _text(next_stop.get("period")) == "lunch"
                    ):
                        next_evidence = next_stop.get("_resolved_place") or {}
                        next_location = _text(next_evidence.get("location"))
                        transfer_to_lunch = (
                            _estimate_route(location, next_location, mode)[0]
                            if location and next_location and location != next_location
                            else 0
                        )
                        latest_end = (
                            13 * 60
                            + 20
                            - transfer_to_lunch
                            - (
                                10
                                if mode == "transit"
                                else 5
                                if mode == "driving"
                                else 0
                            )
                        )
                        duration = min(duration, max(30, latest_end - cursor))
                end = cursor + duration
                if end > maximum_end and stop.get("optional") and schedule:
                    continue
                if end > maximum_end:
                    duration = max(30, maximum_end - cursor)
                    end = cursor + duration
                if end <= cursor:
                    continue
                schedule.append(
                    {
                        "period": period,
                        "type": stop_type,
                        "start": _hhmm(cursor),
                        "end": _hhmm(end),
                        "name": resolved_name,
                        "reason": _text(stop.get("reason"))
                        or (
                            f"在{evidence_area or primary_area}就近安排用餐，减少跨区折返。"
                            if stop_type == "meal"
                            else f"围绕“{theme}”主题安排，保持当天路线集中。"
                        ),
                        "opening_match": "unknown",
                        "reservation": {
                            "required": None,
                            "status": "unknown",
                            "note": None,
                        },
                        "source": "user"
                        if any(
                            _matches(stop.get("name"), item)
                            for item in context.get("must_visits") or []
                        )
                        else "model_judgment",
                        "practical_tips": [
                            "热门时段可能排队，建议提前取号或预约。"
                            if stop_type == "meal"
                            else "建议按当天开放、预约和人流情况调整停留时间。"
                        ],
                    }
                )
                cursor = end
                if stop_type in {"visit", "meal"}:
                    previous_name = resolved_name
                    previous_location = location

            if (
                previous_location
                and hotel_location
                and previous_location != hotel_location
            ):
                route = route_results.get((previous_location, hotel_location, mode))
                estimated_minutes, estimated_distance = _estimate_route(
                    previous_location, hotel_location, mode
                )
                route_minutes = (
                    max(
                        1,
                        math.ceil(int((route or {}).get("duration_seconds") or 0) / 60),
                    )
                    if route
                    else 0
                )
                if route and route_minutes <= max(
                    estimated_minutes + 15, estimated_minutes * 2
                ):
                    route_source = "amap"
                    route_distance = 0
                else:
                    route = None
                    route_minutes = estimated_minutes
                    route_distance = estimated_distance
                    route_source = "estimate"
                transfer_end = cursor + route_minutes
                transfers.append(
                    {
                        "from_name": previous_name,
                        "to_name": hotel_name,
                        "from_location": previous_location,
                        "to_location": hotel_location,
                        "mode": mode,
                        "start": _hhmm(cursor),
                        "end": _hhmm(transfer_end),
                        "duration_minutes": route_minutes,
                        "distance_meters": route_distance,
                        "instructions": (
                            "已按实时路线结果预留返程与换乘缓冲。"
                            if route
                            else "基于两点距离保守估算返程；出发前请用实时导航复核。"
                        ),
                        "source": route_source,
                        "evidence_hash": (route or {}).get("response_hash"),
                    }
                )
                cursor = transfer_end + (
                    10 if mode == "transit" else 5 if mode == "driving" else 0
                )
            if area_counts:
                primary_area = max(area_counts, key=area_counts.get)

            current_date = None
            weekday = None
            if start_date:
                try:
                    parsed = date.fromisoformat(start_date) + timedelta(
                        days=day_index - 1
                    )
                    current_date = parsed.isoformat()
                    weekday = f"星期{'一二三四五六日'[parsed.weekday()]}"
                except ValueError:
                    pass
            raw_days.append(
                {
                    "day": day_index,
                    "date": current_date,
                    "weekday": weekday,
                    "theme": theme,
                    "summary": _text(day.get("summary"))
                    or f"围绕{primary_area}安排"
                    + "、".join(item["name"] for item in schedule)
                    + "，兼顾游览节奏与交通衔接。",
                    "start_time": _hhmm(default_start),
                    "end_time": _hhmm(min(cursor, maximum_end)),
                    "start_anchor": {
                        "name": hotel_name,
                        "type": "hotel"
                        if hotel.get("status") == "confirmed"
                        else "area",
                    },
                    "end_anchor": {
                        "name": hotel_name,
                        "type": "hotel"
                        if hotel.get("status") == "confirmed"
                        else "area",
                    },
                    "area_cluster": {
                        "primary_area": primary_area,
                        "secondary_areas": list(day.get("secondary_areas") or []),
                        "rationale": "按相邻片区组合，减少跨城折返。",
                    },
                    "schedule": schedule,
                    "transfers": transfers,
                    "risks": [],
                }
            )

        date_end = None
        if start_date:
            try:
                date_end = (
                    date.fromisoformat(start_date) + timedelta(days=requested_days - 1)
                ).isoformat()
            except ValueError:
                pass
        warnings = [
            _text(item) for item in skeleton.get("warnings") or [] if _text(item)
        ]
        if unresolved:
            warnings.append(
                "以下地点未能绑定实时地图实体；可选项已移除，必去项将阻止交付："
                + "、".join(dict.fromkeys(unresolved))
            )
        if not start_date:
            warnings.append("未提供出发日期，天气和按日期开放状态未核验。")
        title = _text(skeleton.get("title"), f"{city}{requested_days}日行程")
        overview = "；".join(f"第{item['day']}天{item['theme']}" for item in raw_days)
        candidate_areas: list[dict[str, Any]] = []
        seen_areas: set[str] = set()
        for item in raw_days:
            area = item["area_cluster"]["primary_area"]
            if area in seen_areas:
                continue
            seen_areas.add(area)
            stop_names = [stop["name"] for stop in item["schedule"]]
            candidate_areas.append(
                {
                    "name": area,
                    "highlights": stop_names,
                    "tradeoffs": ["具体步行与排队时间需按当天情况调整。"],
                    "fit_score": max(75, 95 - len(candidate_areas) * 5),
                    "selected": True,
                }
            )
        hotel_reason = _text(hotel.get("reason")) or (
            f"以{_text(hotel.get('area'), hotel_name)}为住宿锚点，"
            "兼顾三日片区之间的交通衔接。"
        )
        return {
            "city": city,
            "title": title,
            "overview": overview,
            "date_range": {"start": start_date or None, "end": date_end},
            "trip_profile": {
                "days": requested_days,
                "pace": _PACE.get(_text(context.get("pace")), "balanced"),
                "transport_preference": _TRANSPORT.get(
                    _text(context.get("transport")), "mixed"
                ),
                "travelers": _text(context.get("travelers"), "未指定"),
                "preferences": list(context.get("interests") or []),
                "assumptions": ["未明确的票价、预约和营业状态需在出发前复核。"],
            },
            "hotel": {
                "name": hotel_name,
                "place_id": _text(hotel_evidence.get("id")) or None,
                "area": _text(
                    hotel.get("area"), _text(context.get("hotel_area"), city)
                ),
                "status": _text(hotel.get("status"), "recommended_area"),
                "reason": hotel_reason,
                "source": "user" if context.get("hotel_area") else "model_judgment",
            },
            "candidate_comparison": {
                "areas": candidate_areas,
                "selected_areas": [
                    item.get("name") for item in candidate_areas if item.get("selected")
                ],
                "selection_reason": hotel_reason,
            },
            "days": raw_days,
            "map": {
                "route_overview": "每日按住宿锚点—同片区景点—住宿锚点组织；以实时导航结果为准。"
            },
            "narrative": {
                "headline": title,
                "summary": overview,
                "highlights": [item["summary"] for item in raw_days],
                "tradeoffs": [
                    "热门景点、餐厅和晚间项目可能需要预约或排队。",
                    "未指定日期时，开放安排与天气只能在出发前复核。",
                ],
                "weather_advice": None,
            },
            "warnings": list(dict.fromkeys(warnings))[:5],
        }
