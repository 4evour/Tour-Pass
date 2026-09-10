from __future__ import annotations

import asyncio
import math
import re
from datetime import date, timedelta
from typing import Any, Callable

from .providers.amap import AmapProvider
from .validation import _matches_key

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
    "公共交通": "public_transit",
}
_PERIOD_ORDER = {
    "breakfast": 0,
    "morning": 1,
    "lunch": 2,
    "afternoon": 3,
    "dinner": 4,
    "evening": 5,
}
_VISIT_DURATION = {
    "quick_stop": 60,
    "standard": 90,
    "half_day": 180,
    "full_day": 360,
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
    return _matches_key(_key(left), _key(right))


def _looks_like_transport_hub(value: Any) -> bool:
    name = _text(value)
    return bool(
        re.search(
            r"(?:机场(?:航站楼)?|航站楼|火车站|高铁站|动车站|客运站|"
            r"公交站|地铁站)(?:[（(].*?[）)])?$",
            name,
        )
        or re.fullmatch(r".{1,8}(?:南站|北站|东站|西站)", name)
        or (re.search(r"(?:动车|高铁|列车)", name) and re.search(r"(?:机场|站)", name))
    )


def _closed_on_date(opening_hours: Any, visit_date: date) -> bool:
    weekday = "一二三四五六日"[visit_date.weekday()]
    weekday_order = "一二三四五六日"
    current_mmdd = visit_date.month * 100 + visit_date.day
    for segment in re.split(r"[；;]", _text(opening_hours)):
        if not any(
            marker in segment for marker in ("全天不开放", "全天关闭", "全天闭园")
        ) and not re.search(r"每(?:周|星期).{0,3}闭园", segment):
            continue
        date_ranges = re.findall(
            r"(\d{1,2})/(\d{1,2})\s*[-至]\s*(\d{1,2})/(\d{1,2})",
            segment,
        )
        if date_ranges:
            in_range = False
            for start_month, start_day, end_month, end_day in date_ranges:
                start_mmdd = int(start_month) * 100 + int(start_day)
                end_mmdd = int(end_month) * 100 + int(end_day)
                if (
                    start_mmdd <= current_mmdd <= end_mmdd
                    if start_mmdd <= end_mmdd
                    else current_mmdd >= start_mmdd or current_mmdd <= end_mmdd
                ):
                    in_range = True
                    break
            if not in_range:
                continue
        applicable_days = {
            day_name.replace("天", "日")
            for day_name in re.findall(r"(?:周|星期)([一二三四五六日天])", segment)
        }
        for start_day, end_day in re.findall(
            r"(?:周|星期)([一二三四五六日天])\s*[-至]\s*"
            r"(?:(?:周|星期))?([一二三四五六日天])",
            segment,
        ):
            start_index = weekday_order.index(start_day.replace("天", "日"))
            end_index = weekday_order.index(end_day.replace("天", "日"))
            indexes = (
                range(start_index, end_index + 1)
                if start_index <= end_index
                else list(range(start_index, 7)) + list(range(0, end_index + 1))
            )
            applicable_days.update(weekday_order[index] for index in indexes)
        has_weekday_marker = bool(re.search(r"(?:周|星期|节假日)", segment))
        if applicable_days:
            if weekday in applicable_days:
                return True
            continue
        if has_weekday_marker:
            continue
        return True
    return False


def _default_stop(day: int, city: str) -> dict[str, Any]:
    return {
        "type": "free_time",
        "name": f"{city}第{day}日弹性探索",
        "search_query": None,
        "period": "afternoon",
        "visit_scale": "half_day",
        "reason": "保留弹性时间，按当天体力和现场情况调整。",
        "optional": True,
        "practical_tip": "出发前结合天气和营业状态选择附近活动。",
    }


def repair_skeleton(
    skeleton: dict[str, Any], context: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repaired = dict(skeleton)
    city = _text(context.get("destination"))

    def destination_name(item: dict[str, Any]) -> str:
        return _text(item.get("destination") or item.get("name"))

    def preferred_intercity_mode() -> str:
        preferences = " ".join(
            _text(item) for item in context.get("intercity_preferences") or []
        )
        for mode, markers in (
            ("flight", ("飞机", "航班", "航空")),
            ("rail", ("动车", "高铁", "火车", "铁路")),
            ("coach", ("大巴", "客车", "汽车")),
            ("ferry", ("轮渡", "渡轮", "船")),
            ("driving", ("自驾",)),
        ):
            if any(marker in preferences for marker in markers):
                return mode
        return "unknown"

    destination_requests = [
        dict(item)
        for item in context.get("destinations") or []
        if isinstance(item, dict) and destination_name(item)
    ]
    if not destination_requests:
        destination_requests = [{"destination": city}]
    requested_days = max(
        1,
        int(
            context.get("days")
            or len(
                [item for item in skeleton.get("days") or [] if isinstance(item, dict)]
            )
            or 3
        ),
    )
    allocated_destinations = [
        destination_name(item)
        for item in destination_requests
        for _ in range(max(0, int(item.get("days") or 0)))
    ]
    raw_days = [
        dict(item) for item in skeleton.get("days") or [] if isinstance(item, dict)
    ]
    repairs: list[dict[str, Any]] = []

    if len(raw_days) > requested_days:
        raw_days = raw_days[:requested_days]
        repairs.append({"reason": "trim_extra_days", "days": requested_days})
    while len(raw_days) < requested_days:
        day_number = len(raw_days) + 1
        destination = (
            allocated_destinations[day_number - 1]
            if day_number <= len(allocated_destinations)
            else destination_name(
                destination_requests[min(day_number - 1, len(destination_requests) - 1)]
            )
            if len(destination_requests) == requested_days
            else city
        )
        raw_days.append(
            {
                "day": day_number,
                "destination": destination,
                "theme": "弹性城市探索",
                "summary": "模型未返回该日完整安排，保留可调整时段。",
                "primary_area": destination,
                "overnight_area": destination,
                "secondary_areas": [],
                "intercity_leg": None,
                "stops": [_default_stop(day_number, destination)],
            }
        )
        repairs.append({"reason": "fill_missing_day", "day": day_number})

    seen: set[str] = set()
    for day_number, day in enumerate(raw_days, 1):
        day["day"] = day_number
        fallback_destination = (
            allocated_destinations[day_number - 1]
            if day_number <= len(allocated_destinations)
            else _text(destination_name(destination_requests[0]), city)
        )
        day["destination"] = _text(day.get("destination"), fallback_destination)
        day["overnight_area"] = _text(
            day.get("overnight_area"),
            _text(day.get("primary_area"), day["destination"]),
        )
        unique_stops: list[dict[str, Any]] = []
        for raw_stop in day.get("stops") or []:
            if not isinstance(raw_stop, dict):
                continue
            stop = dict(raw_stop)
            if _text(stop.get("period")) in {"breakfast", "lunch", "dinner"}:
                stop["type"] = "meal"
            required_by_user = any(
                _matches(stop.get("name"), must_visit)
                for must_visit in context.get("must_visits") or []
            )
            if (
                stop.get("type") == "visit"
                and _looks_like_transport_hub(stop.get("name"))
                and not required_by_user
            ):
                repairs.append(
                    {
                        "reason": "remove_transport_hub_stop",
                        "name": _text(stop.get("name")),
                    }
                )
                continue
            name_key = _key(stop.get("name"))
            if name_key and name_key in seen:
                repairs.append(
                    {"reason": "remove_duplicate_stop", "name": _text(stop.get("name"))}
                )
                continue
            if name_key:
                seen.add(name_key)
            stop["visit_scale"] = _text(stop.get("visit_scale"), "standard")
            default_duration = (
                45
                if stop.get("type") == "meal" and stop.get("period") == "breakfast"
                else 75
                if stop.get("type") == "meal"
                else _VISIT_DURATION.get(stop["visit_scale"], 90)
            )
            stop["duration_minutes"] = max(
                30, min(int(stop.get("duration_minutes") or default_duration), 540)
            )
            stop["_required_by_user"] = required_by_user
            stop["optional"] = (
                False
                if required_by_user or stop.get("type") == "meal"
                else bool(stop.get("optional", True))
            )
            unique_stops.append(stop)
        if not unique_stops:
            unique_stops.append(_default_stop(day_number, day["destination"]))
        while len(unique_stops) > 7:
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

    if len(allocated_destinations) >= len(raw_days):
        default_intercity_mode = preferred_intercity_mode()
        for day_index in range(1, len(raw_days)):
            previous_destination = allocated_destinations[day_index - 1]
            current_destination = allocated_destinations[day_index]
            if _matches(previous_destination, current_destination):
                continue
            day = raw_days[day_index]
            existing_leg = (
                dict(day.get("intercity_leg"))
                if isinstance(day.get("intercity_leg"), dict)
                else {}
            )
            repaired_leg = {
                **existing_leg,
                "from": _text(existing_leg.get("from"), previous_destination),
                "to": _text(existing_leg.get("to"), current_destination),
                "mode": _text(existing_leg.get("mode"), default_intercity_mode),
                "departure_hint": existing_leg.get("departure_hint"),
                "arrival_hint": existing_leg.get("arrival_hint"),
            }
            if repaired_leg != existing_leg:
                day["intercity_leg"] = repaired_leg
                repairs.append(
                    {
                        "reason": "repair_intercity_leg",
                        "day": day_index + 1,
                        "from": previous_destination,
                        "to": current_destination,
                    }
                )

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
        if len(stops) >= 7:
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

    default_day_start = _clock((context.get("daily_window") or {}).get("start"), 9 * 60)
    default_day_end = _clock((context.get("daily_window") or {}).get("end"), 20 * 60)
    arrival = context.get("arrival") if isinstance(context.get("arrival"), dict) else {}
    departure = (
        context.get("departure") if isinstance(context.get("departure"), dict) else {}
    )
    for day in raw_days:
        available_start = default_day_start
        available_end = default_day_end
        if day["day"] == 1 and arrival:
            arrival_time = _clock(arrival.get("time"), -1)
            available_start = max(
                available_start,
                arrival_time + 60
                if arrival_time >= 0
                else {
                    "morning": 10 * 60,
                    "afternoon": 14 * 60,
                    "evening": 18 * 60,
                    "late_night": 21 * 60,
                }.get(_text(arrival.get("period")), available_start),
            )
        if day["day"] == requested_days and departure:
            departure_time = _clock(departure.get("time"), -1)
            available_end = min(
                available_end,
                departure_time - 90
                if departure_time >= 0
                else {
                    "morning": 9 * 60 + 30,
                    "afternoon": 14 * 60,
                    "evening": 17 * 60 + 30,
                    "late_night": available_end,
                }.get(_text(departure.get("period")), available_end),
            )
        area = _text(day.get("primary_area"), _text(day.get("destination"), city))
        meal_specs = [
            (
                "breakfast",
                "早餐",
                45,
                available_start < 10 * 60 + 30,
                "在住宿附近简单吃早餐，优先选择出餐快、前往当天首站顺路的小店。",
            ),
            (
                "lunch",
                "午餐",
                75,
                available_start < 13 * 60 + 30 and available_end > 11 * 60 + 30,
                "在当天主要游览片区就近吃午餐，避免为了网红店跨区折返。",
            ),
            (
                "dinner",
                "晚餐",
                90,
                available_start < 19 * 60 + 30 and available_end > 17 * 60 + 30,
                "在当天最后一个游览片区吃晚餐，再按体力决定是否继续夜间活动。",
            ),
        ]
        stops = list(day.get("stops") or [])
        availability_by_period = {
            period: available for period, _, _, available, _ in meal_specs
        }
        filtered_stops = []
        for stop in stops:
            period = _text(stop.get("period"))
            if (
                stop.get("type") == "meal"
                and period in availability_by_period
                and not availability_by_period[period]
            ):
                repairs.append(
                    {
                        "reason": f"remove_unavailable_{period}",
                        "day": day["day"],
                        "name": _text(stop.get("name")),
                    }
                )
                continue
            filtered_stops.append(stop)
        stops = filtered_stops
        for period, label, duration, available, reason in meal_specs:
            if not available or any(
                stop.get("type") == "meal"
                and (stop.get("period") == period or label in _text(stop.get("name")))
                for stop in stops
            ):
                continue
            stops.append(
                {
                    "type": "meal",
                    "name": f"{area}{label}",
                    "search_query": None,
                    "period": period,
                    "visit_scale": "quick_stop",
                    "duration_minutes": duration,
                    "reason": reason,
                    "optional": False,
                    "_generic_meal": True,
                }
            )
            repairs.append({"reason": f"add_{period}", "day": day["day"]})
        stops.sort(key=lambda stop: _PERIOD_ORDER.get(_text(stop.get("period")), 9))
        while len(stops) > 7:
            removable = next(
                (
                    index
                    for index in range(len(stops) - 1, -1, -1)
                    if stops[index].get("optional")
                    and stops[index].get("type") != "meal"
                ),
                -1,
            )
            if removable < 0:
                break
            removed = stops.pop(removable)
            repairs.append(
                {"reason": "trim_optional_stop", "name": _text(removed.get("name"))}
            )
        day["stops"] = stops

    if _PACE.get(_text(context.get("pace"))) == "relaxed":
        major_markers = (
            "野生动物世界",
            "欢乐世界",
            "水上乐园",
            "飞鸟乐园",
            "主题乐园",
        )

        def required_major_stops(day: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                stop
                for stop in day.get("stops") or []
                if not stop.get("optional")
                and any(marker in _text(stop.get("name")) for marker in major_markers)
            ]

        for source_day in raw_days:
            for moved_stop in required_major_stops(source_day)[1:]:
                target_days = [
                    day
                    for day in raw_days
                    if day is not source_day and not required_major_stops(day)
                ]
                if not target_days:
                    break
                target_day = min(
                    target_days,
                    key=lambda day: (
                        sum(
                            not stop.get("optional") for stop in day.get("stops") or []
                        ),
                        len(day.get("stops") or []),
                    ),
                )
                source_stops = list(source_day.get("stops") or [])
                source_stops.remove(moved_stop)
                source_day["stops"] = source_stops
                moved_stop["period"] = "morning"
                target_day["stops"] = [
                    *list(target_day.get("stops") or []),
                    moved_stop,
                ]
                target_day["theme"] = f"{_text(moved_stop.get('name'))}主题日"
                repairs.append(
                    {
                        "reason": "spread_relaxed_major_stop",
                        "name": _text(moved_stop.get("name")),
                        "day": target_day.get("day"),
                    }
                )

        for day in raw_days:
            stops = list(day.get("stops") or [])
            has_required_major = bool(required_major_stops(day))
            if has_required_major:
                kept_stops = []
                for stop in stops:
                    optional_activity = (
                        stop.get("optional") and stop.get("type") == "visit"
                    )
                    if optional_activity:
                        repairs.append(
                            {
                                "reason": "trim_relaxed_major_stop",
                                "name": _text(stop.get("name")),
                            }
                        )
                    else:
                        kept_stops.append(stop)
                stops = kept_stops
            while len(stops) > 3:
                optional_index = next(
                    (
                        index
                        for index in range(len(stops) - 1, -1, -1)
                        if stops[index].get("optional")
                        and stops[index].get("type") != "meal"
                    ),
                    -1,
                )
                if optional_index < 0:
                    break
                removed = stops.pop(optional_index)
                repairs.append(
                    {
                        "reason": "trim_relaxed_stop",
                        "name": _text(removed.get("name")),
                    }
                )
            day["stops"] = stops

    destination_order = list(
        dict.fromkeys(_text(day.get("destination"), city) for day in raw_days)
    )
    raw_hotels = [
        dict(item) for item in repaired.get("hotels") or [] if isinstance(item, dict)
    ]
    legacy_hotel = (
        dict(repaired.get("hotel")) if isinstance(repaired.get("hotel"), dict) else {}
    )
    if legacy_hotel and not raw_hotels:
        raw_hotels.append(legacy_hotel)
    hotels: list[dict[str, Any]] = []
    for destination in destination_order:
        matched = next(
            (
                dict(item)
                for item in raw_hotels
                if _matches(item.get("destination"), destination)
            ),
            None,
        )
        if matched is None and len(destination_order) == 1 and raw_hotels:
            matched = dict(raw_hotels[0])
        area = _text(
            (matched or {}).get("area"),
            next(
                (
                    _text(day.get("overnight_area"))
                    for day in raw_days
                    if _matches(day.get("destination"), destination)
                    and _text(day.get("overnight_area"))
                ),
                destination,
            ),
        )
        matched = matched or {
            "name": f"{area}住宿区",
            "area": area,
            "search_query": f"{area}地铁站",
        }
        matched["destination"] = destination
        if destination == destination_order[0] and _text(context.get("hotel_area")):
            matched["name"] = _text(context.get("hotel_area"))
            matched["area"] = _text(context.get("hotel_area"))
            matched["search_query"] = _text(context.get("hotel_area"))
        hotels.append(matched)
    repaired["hotels"] = hotels
    repaired["hotel"] = hotels[0]

    repaired["days"] = raw_days
    return repaired, repairs


def _score_place(
    place: dict[str, Any],
    name: str,
    query: str,
    stop_type: str,
    area_hint: str = "",
) -> int:
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
            marker in place_type
            for marker in (
                "风景名胜",
                "科教文化服务",
                "公园广场",
                "体育休闲服务",
            )
        ):
            score += 30
        if any(
            marker in place_type
            for marker in ("餐饮服务", "住宿服务", "地名地址信息", "交通设施服务")
        ):
            score -= 60
    place_area = _key(place.get("area") or place.get("adname"))
    requested_area = _key(area_hint)
    if requested_area and place_area:
        if requested_area in place_area or place_area in requested_area:
            score += 45
        else:
            score -= 80
    return score


def _select_place(
    result: dict[str, Any] | None,
    *,
    name: str,
    query: str,
    stop_type: str,
    area_hint: str = "",
) -> dict[str, Any] | None:
    places = (result or {}).get("places") or []
    candidates = []
    for item in places:
        if not isinstance(item, dict):
            continue
        if any(
            marker in _text(item.get("name"))
            for marker in ("暂停开放", "暂停营业", "暂时关闭", "永久关闭")
        ):
            continue
        place_type = _text(item.get("type"))
        if stop_type == "hotel" and place_type and "住宿服务" not in place_type:
            continue
        if stop_type == "meal" and place_type and "餐饮服务" not in place_type:
            continue
        if stop_type == "visit" and "交通设施服务" in place_type:
            continue
        candidates.append(item)
    if not candidates:
        return None
    selected = max(
        candidates,
        key=lambda item: _score_place(
            item, name, query, stop_type, area_hint=area_hint
        ),
    )
    canonical = _key(selected.get("name"))
    requested_name = _key(name)
    requested_query = _key(query)
    lexically_relevant = any(
        requested
        and (canonical == requested or requested in canonical or canonical in requested)
        for requested in (requested_name, requested_query)
    )
    place_type = _text(selected.get("type"))
    if stop_type == "meal" and place_type and "餐饮服务" not in place_type:
        return None
    if stop_type == "visit" and "交通设施服务" in place_type:
        return None
    if stop_type in {"visit", "meal"} and not lexically_relevant:
        return None
    requested_area = _key(area_hint)
    selected_area = _key(selected.get("area") or selected.get("adname"))
    if (
        requested_area
        and selected_area
        and requested_area not in selected_area
        and selected_area not in requested_area
    ):
        return None
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
        self,
        amap: AmapProvider,
        weather: Any = None,
        max_provider_calls: int = 100,
        rail: Any = None,
    ) -> None:
        self.amap = amap
        self.weather = weather
        self.rail = rail
        self.max_provider_calls = max(1, max_provider_calls)

    async def _search(
        self,
        city: str,
        query: str,
        emit: EventEmitter,
    ) -> tuple[tuple[str, str], dict[str, Any] | None]:
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
            return (city, query), result
        except Exception as exc:
            error = str(exc)
            emit(
                {
                    "type": "tool_finished",
                    "tool": "search_places",
                    "error": error,
                    "tool_elapsed_ms": round(
                        (asyncio.get_running_loop().time() - started) * 1000
                    ),
                }
            )
            return (city, query), {"places": [], "provider_error": error}

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

    async def _rail(
        self,
        day_index: int,
        params: dict[str, Any],
        emit: EventEmitter,
    ) -> tuple[int, dict[str, Any] | None]:
        started = asyncio.get_running_loop().time()
        try:
            result = await self.rail.search_trains(**params)
            emit(
                {
                    "type": "tool_finished",
                    "tool": "rail_timetable",
                    "cache_hit": bool(result.get("cache_hit")),
                    "tool_elapsed_ms": round(
                        (asyncio.get_running_loop().time() - started) * 1000
                    ),
                    "response_hash": result.get("response_hash", ""),
                }
            )
            return day_index, result
        except Exception as exc:
            emit(
                {
                    "type": "tool_finished",
                    "tool": "rail_timetable",
                    "error": str(exc),
                    "tool_elapsed_ms": round(
                        (asyncio.get_running_loop().time() - started) * 1000
                    ),
                }
            )
            return day_index, None

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
        if context.get("days") in (None, ""):
            context["days"] = len(skeleton.get("days") or [])
        if context.get("nights") in (None, ""):
            context["nights"] = max(int(context.get("days") or 1) - 1, 0)
        if repairs:
            emit(
                {
                    "type": "plan_repair_applied",
                    "strategy": "skeleton",
                    "repairs": repairs,
                }
            )
        day_destinations = list(
            dict.fromkeys(
                _text(day.get("destination"), city)
                for day in skeleton.get("days") or []
                if isinstance(day, dict)
            )
        )
        provider_city = day_destinations[0] if len(day_destinations) == 1 else city
        region_area_hint = ""
        region_slots = 0
        resolve_search_city = getattr(self.amap, "resolve_search_city", None)
        if callable(resolve_search_city) and len(day_destinations) == 1:
            region_slots = 1
            emit(
                {
                    "type": "tool_started",
                    "tool": "resolve_region",
                    "arguments": {"destination": provider_city},
                }
            )
            started = asyncio.get_running_loop().time()
            try:
                region = await resolve_search_city(provider_city)
                provider_city = _text(region.get("search_city"), provider_city)
                if _text(region.get("level")) in {"district", "street"}:
                    region_area_hint = _text(region.get("name"))
                emit(
                    {
                        "type": "tool_finished",
                        "tool": "resolve_region",
                        "cache_hit": bool(region.get("cache_hit")),
                        "tool_elapsed_ms": round(
                            (asyncio.get_running_loop().time() - started) * 1000
                        ),
                        "response_hash": region.get("response_hash", ""),
                    }
                )
            except Exception as exc:
                emit(
                    {
                        "type": "tool_finished",
                        "tool": "resolve_region",
                        "error": str(exc),
                        "tool_elapsed_ms": round(
                            (asyncio.get_running_loop().time() - started) * 1000
                        ),
                    }
                )

        query_specs: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
        hotels = [
            hotel for hotel in skeleton.get("hotels") or [] if isinstance(hotel, dict)
        ]
        for hotel in hotels:
            hotel_query = _text(hotel.get("search_query"))
            hotel_city = _text(hotel.get("destination"), provider_city)
            if len(day_destinations) == 1:
                hotel_city = provider_city
            if hotel_query:
                query_specs.setdefault((hotel_city, hotel_query), []).append(
                    ("hotel", hotel)
                )
            if region_area_hint:
                hotel["_area_hint"] = region_area_hint
        for day in skeleton.get("days") or []:
            day_city = _text(day.get("destination"), provider_city)
            if len(day_destinations) == 1:
                day_city = provider_city
            primary_area = _text(day.get("primary_area"))
            area_hint = (
                primary_area
                if re.fullmatch(r"[\u4e00-\u9fff]{2,4}(?:区|县|市)", primary_area)
                else region_area_hint
                if len(day_destinations) == 1
                else ""
            )
            for stop in day.get("stops") or []:
                if (
                    not isinstance(stop, dict)
                    or stop.get("type") == "free_time"
                    or stop.get("_generic_meal")
                ):
                    continue
                stop["_area_hint"] = area_hint
                query = _text(stop.get("search_query") or stop.get("name"))
                if (
                    _text(stop.get("type")) == "meal"
                    and _text(stop.get("period")) == "breakfast"
                    and re.search(
                        r"(?:酒店|附近|就近|片区|古城).{0,8}早餐|早餐与前往",
                        query,
                    )
                ):
                    continue
                if _text(stop.get("type")) == "visit":
                    query = re.sub(r"(?:正门|[东南西北]门)$", "", query).strip()
                if query:
                    query_specs.setdefault((day_city, query), []).append(
                        (_text(stop.get("type")), stop)
                    )

        weather_specs: list[tuple[str, int]] = []
        if context.get("start_date") and self.weather is not None:
            for destination in day_destinations:
                destination_days = sum(
                    _matches(day.get("destination"), destination)
                    for day in skeleton.get("days") or []
                    if isinstance(day, dict)
                )
                weather_specs.append((destination, min(max(destination_days, 1), 7)))
                emit(
                    {
                        "type": "tool_started",
                        "tool": "weather",
                        "arguments": {"city": destination},
                    }
                )
        rail_specs: list[tuple[int, dict[str, Any]]] = []
        rail_available = bool(
            self.rail is not None and getattr(self.rail, "available", False)
        )
        if context.get("start_date") and rail_available:
            try:
                trip_start = date.fromisoformat(_text(context.get("start_date")))
            except ValueError:
                trip_start = None
            if trip_start is not None:
                for day_index, day in enumerate(skeleton.get("days") or []):
                    leg = (
                        day.get("intercity_leg")
                        if isinstance(day, dict)
                        and isinstance(day.get("intercity_leg"), dict)
                        else {}
                    )
                    if _text(leg.get("mode")) != "rail":
                        continue
                    origin = _text(leg.get("from"))
                    destination = _text(leg.get("to"))
                    if not origin or not destination:
                        continue
                    departure_hint = _text(leg.get("departure_hint"))
                    params = {
                        "travel_date": (
                            trip_start + timedelta(days=day_index)
                        ).isoformat(),
                        "from_station": origin,
                        "to_station": destination,
                        "preferred_departure": (
                            departure_hint
                            if re.fullmatch(r"\d{2}:\d{2}", departure_hint)
                            else None
                        ),
                        "limit": 3,
                    }
                    rail_specs.append((day_index, params))
                    emit(
                        {
                            "type": "tool_started",
                            "tool": "rail_timetable",
                            "arguments": {
                                "date": params["travel_date"],
                                "from": origin,
                                "to": destination,
                            },
                        }
                    )
        query_priority = sorted(
            query_specs,
            key=lambda query_key: (
                0
                if any(kind == "hotel" for kind, _ in query_specs[query_key])
                else 1
                if any(
                    not target.get("optional") for _, target in query_specs[query_key]
                )
                else 2,
            ),
        )
        enrichment_budget = max(
            0,
            self.max_provider_calls
            - len(weather_specs)
            - len(rail_specs)
            - region_slots,
        )
        route_reserve = min(4, enrichment_budget // 3)
        search_queries = query_priority[: max(0, enrichment_budget - route_reserve)]
        search_jobs = [
            self._search(search_city, query, emit)
            for search_city, query in search_queries
        ]
        weather_jobs = [
            self.weather.forecast(destination, days)
            for destination, days in weather_specs
        ]
        rail_jobs = [
            self._rail(day_index, params, emit) for day_index, params in rail_specs
        ]
        gathered = await asyncio.gather(
            *search_jobs,
            *weather_jobs,
            *rail_jobs,
            return_exceptions=True,
        )
        search_results = {
            query_key: result
            for item in gathered[: len(search_jobs)]
            if not isinstance(item, Exception)
            for query_key, result in [item]
        }
        weather_results: list[tuple[str, dict[str, Any]]] = []
        weather_start = len(search_jobs)
        weather_end = weather_start + len(weather_jobs)
        for (destination, _), result in zip(
            weather_specs, gathered[weather_start:weather_end]
        ):
            if isinstance(result, dict):
                weather_results.append((destination, result))
                emit(
                    {
                        "type": "tool_finished",
                        "tool": "weather",
                        "arguments": {"city": destination},
                        "cache_hit": bool(result.get("cache_hit")),
                        "response_hash": result.get("response_hash", ""),
                    }
                )
        rail_results = {
            day_index: result
            for item in gathered[weather_end:]
            if not isinstance(item, Exception)
            for day_index, result in [item]
            if isinstance(result, dict)
        }
        for day_index, result in rail_results.items():
            trains = [
                item for item in result.get("trains") or [] if isinstance(item, dict)
            ]
            if not trains:
                continue
            day = skeleton["days"][day_index]
            leg = day.get("intercity_leg")
            if not isinstance(leg, dict):
                continue
            leg["_train_option"] = {
                **trains[0],
                "provider": result.get("provider"),
                "fetched_at": result.get("fetched_at"),
                "response_hash": result.get("response_hash"),
                "stale": bool(result.get("stale")),
                "source_url": result.get("source_url"),
            }
            leg["_train_alternatives"] = trains[1:]
        weather_evidence = None
        if len(weather_results) == 1:
            weather_evidence = weather_results[0][1]
        elif weather_results:
            weather_days = [
                {**day, "destination": destination}
                for destination, result in weather_results
                for day in result.get("days") or []
                if isinstance(day, dict)
            ]
            providers = list(
                dict.fromkeys(
                    _text(result.get("provider"), "unknown")
                    for _, result in weather_results
                )
            )
            weather_evidence = {
                "mode": "forecast" if weather_days else "unavailable",
                "provider": providers[0] if len(providers) == 1 else "mixed",
                "available": bool(weather_days),
                "coverage": (
                    "partial"
                    if any(
                        sum(
                            _matches(day.get("destination"), destination)
                            for day in skeleton.get("days") or []
                            if isinstance(day, dict)
                        )
                        > 7
                        for destination, _ in weather_results
                    )
                    else "full"
                ),
                "days": weather_days,
                "destinations": [
                    {"destination": destination, **result}
                    for destination, result in weather_results
                ],
            }

        known_places: dict[str, dict[str, Any]] = {}
        unresolved: list[str] = []
        for query_key, specs in query_specs.items():
            query = query_key[1]
            result = search_results.get(query_key)
            for stop_type, target in specs:
                selected = _select_place(
                    result,
                    name=_text(target.get("name")),
                    query=query,
                    stop_type=stop_type,
                    area_hint=_text(target.get("_area_hint")),
                )
                if selected is None:
                    unresolved.append(_text(target.get("name")) or query)
                    target["_unresolved"] = True
                    continue
                selected = dict(selected)
                selected["source"] = "amap"
                selected["response_hash"] = (result or {}).get("response_hash")
                selected["fetched_at"] = (result or {}).get("fetched_at")
                selected["expires_at"] = (result or {}).get("expires_at")
                selected["stale"] = bool((result or {}).get("stale"))
                if stop_type in {"hotel", "meal"}:
                    required_category = (
                        "住宿服务" if stop_type == "hotel" else "餐饮服务"
                    )
                    target["_candidate_places"] = [
                        {
                            **dict(candidate),
                            "source": "amap",
                            "response_hash": (result or {}).get("response_hash"),
                            "fetched_at": (result or {}).get("fetched_at"),
                            "expires_at": (result or {}).get("expires_at"),
                            "stale": bool((result or {}).get("stale")),
                        }
                        for candidate in (result or {}).get("places") or []
                        if isinstance(candidate, dict)
                        and required_category in _text(candidate.get("type"))
                    ][:3]
                if (result or {}).get("stale"):
                    skeleton.setdefault("warnings", []).append(
                        "地图服务限流，部分地点使用历史缓存；出发前请重新核对。"
                    )
                place_id = _text(selected.get("id"))
                selected_name_key = _key(selected.get("name"))
                target_name_key = _key(target.get("name"))
                known_places[place_id] = selected
                if selected_name_key:
                    known_places[selected_name_key] = selected
                if target_name_key:
                    known_places[target_name_key] = selected
                target["_resolved_place"] = selected

        start_date = _text(context.get("start_date"))
        if start_date:
            try:
                first_date = date.fromisoformat(start_date)
            except ValueError:
                first_date = None
            if first_date is not None:
                for day_index, day in enumerate(skeleton.get("days") or []):
                    visit_date = first_date + timedelta(days=day_index)
                    for stop in day.get("stops") or []:
                        if not isinstance(stop, dict) or stop.get("type") != "visit":
                            continue
                        evidence = stop.get("_resolved_place") or {}
                        if not _closed_on_date(
                            evidence.get("opening_hours")
                            or evidence.get("business_hours")
                            or evidence.get("opentime2")
                            or evidence.get("opentime")
                            or (
                                (evidence.get("biz_ext") or {}).get("open_time")
                                if isinstance(evidence.get("biz_ext"), dict)
                                else None
                            ),
                            visit_date,
                        ):
                            continue
                        stop["_opening_risk"] = True
                        if stop.get("optional"):
                            stop["_opening_closed"] = True
                            skeleton.setdefault("warnings", []).append(
                                f"{visit_date.isoformat()} 当天不开放的可选地点"
                                f"“{_text(evidence.get('name'), _text(stop.get('name')))}”"
                                "已从行程移除。"
                            )

        mode = _route_mode(context)
        route_buckets: list[list[tuple[str, str, str, str]]] = [[], [], []]
        for day in skeleton.get("days") or []:
            day_city = _text(day.get("destination"), provider_city)
            if len(day_destinations) == 1:
                day_city = provider_city
            day_hotel = next(
                (
                    item
                    for item in hotels
                    if _matches(item.get("destination"), day.get("destination"))
                ),
                hotels[0],
            )
            physical = [
                stop
                for stop in day.get("stops") or []
                if isinstance(stop, dict)
                and stop.get("type") in {"visit", "meal"}
                and _text((stop.get("_resolved_place") or {}).get("location"))
                and not (stop.get("_unresolved") and stop.get("optional"))
                and not stop.get("_opening_closed")
            ]
            endpoints = [day_hotel, *physical, day_hotel]
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
                route_buckets[priority].append(
                    (day_city, left_location, right_location, mode)
                )
        route_specs = list(
            dict.fromkeys(route for bucket in route_buckets for route in bucket)
        )
        route_budget = max(
            0,
            self.max_provider_calls
            - len(search_jobs)
            - len(weather_specs)
            - len(rail_specs)
            - region_slots,
        )
        selected_routes = route_specs[:route_budget]
        route_pairs = await asyncio.gather(
            *(
                self._route(search_city, origin, destination, route_mode, emit)
                for search_city, origin, destination, route_mode in selected_routes
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
        hotels = [
            item for item in skeleton.get("hotels") or [] if isinstance(item, dict)
        ]
        if not hotels and isinstance(skeleton.get("hotel"), dict):
            hotels = [skeleton["hotel"]]
        if not hotels:
            hotels = [
                {
                    "destination": city,
                    "name": f"{city}住宿区",
                    "area": city,
                    "search_query": None,
                }
            ]
        arrival = (
            context.get("arrival") if isinstance(context.get("arrival"), dict) else {}
        )
        departure = (
            context.get("departure")
            if isinstance(context.get("departure"), dict)
            else {}
        )
        arrival_period_start = {
            "morning": 10 * 60,
            "afternoon": 14 * 60,
            "evening": 18 * 60,
            "late_night": 21 * 60,
        }
        departure_period_end = {
            "morning": 9 * 60 + 30,
            "afternoon": 14 * 60,
            "evening": 17 * 60 + 30,
            "late_night": maximum_end,
        }
        raw_days: list[dict[str, Any]] = []

        for day_index, day in enumerate(skeleton.get("days") or [], 1):
            day_destination = _text(day.get("destination"), city)
            hotel = next(
                (
                    item
                    for item in hotels
                    if _matches(item.get("destination"), day_destination)
                ),
                hotels[0],
            )
            hotel_area = _text(hotel.get("area"), day_destination)
            hotel_name = _text(hotel.get("name"), f"{hotel_area}住宿区")
            hotel_evidence = hotel.get("_resolved_place") or {}
            hotel_location = _text(hotel_evidence.get("location"))
            theme = _text(day.get("theme"), "城市探索")
            primary_area = _text(day.get("primary_area"), day_destination)
            intercity_leg = dict(day.get("intercity_leg") or {})
            train_option = (
                dict(intercity_leg.pop("_train_option"))
                if isinstance(intercity_leg.get("_train_option"), dict)
                else {}
            )
            train_alternatives = [
                dict(item)
                for item in intercity_leg.pop("_train_alternatives", [])
                if isinstance(item, dict)
            ]
            if train_option:
                preferred_price = (
                    train_option.get("price")
                    if isinstance(train_option.get("price"), dict)
                    else {}
                )
                intercity_leg.update(
                    {
                        "from": _text(
                            train_option.get("from_station"),
                            intercity_leg.get("from"),
                        ),
                        "to": _text(
                            train_option.get("to_station"), intercity_leg.get("to")
                        ),
                        "departure_hint": _text(train_option.get("departure_time")),
                        "arrival_hint": _text(train_option.get("arrival_time")),
                        "train_code": _text(train_option.get("train_code")),
                        "duration_minutes": int(
                            train_option.get("duration_minutes") or 0
                        ),
                        "price": preferred_price.get("amount"),
                        "seat_type": preferred_price.get("seat_type"),
                        "prices": list(train_option.get("prices") or []),
                        "provider": _text(train_option.get("provider"), "rail12306"),
                        "fetched_at": train_option.get("fetched_at"),
                        "evidence_hash": train_option.get("response_hash"),
                        "source_url": train_option.get("source_url"),
                        "status": (
                            "stale_schedule"
                            if train_option.get("stale")
                            else "verified_schedule"
                        ),
                        "alternatives": train_alternatives,
                    }
                )
                intercity_leg["summary"] = (
                    f"{intercity_leg['train_code']}次 "
                    f"{intercity_leg['from']}至{intercity_leg['to']}，"
                    f"{intercity_leg['departure_hint']}出发，"
                    f"{intercity_leg['arrival_hint']}到达"
                )
            day_start = default_start
            day_maximum_end = maximum_end
            if day_index == 1 and arrival:
                arrival_time = _clock(arrival.get("time"), -1)
                day_start = max(
                    day_start,
                    arrival_time + 60
                    if arrival_time >= 0
                    else arrival_period_start.get(
                        _text(arrival.get("period")), day_start
                    ),
                )
            if day_index == requested_days and departure:
                departure_time = _clock(departure.get("time"), -1)
                day_maximum_end = min(
                    day_maximum_end,
                    departure_time - 90
                    if departure_time >= 0
                    else departure_period_end.get(
                        _text(departure.get("period")), day_maximum_end
                    ),
                )
            if train_option:
                train_arrival = _clock(train_option.get("arrival_time"), -1)
                if train_arrival >= 0:
                    day_start = max(day_start, train_arrival + 60)
            if day_maximum_end <= day_start:
                day_start = max(0, day_maximum_end - 60)
            cursor = day_start
            area_counts: dict[str, int] = {}
            schedule: list[dict[str, Any]] = []
            transfers: list[dict[str, Any]] = []
            previous_name = hotel_name
            previous_location = hotel_location
            if train_option:
                previous_name = _text(train_option.get("to_station"), hotel_name)
                previous_location = ""
            day_stops = [
                stop for stop in day.get("stops") or [] if isinstance(stop, dict)
            ]
            day_stops.sort(
                key=lambda stop: _PERIOD_ORDER.get(_text(stop.get("period")), 5)
            )
            for stop_index, stop in enumerate(day_stops):
                stop_type = _text(stop.get("type"), "visit")
                if (
                    train_option
                    and stop_type == "meal"
                    and _text(stop.get("period")) == "breakfast"
                ):
                    continue
                generic_meal = stop_type == "meal" and (
                    stop.get("_unresolved") or stop.get("_generic_meal")
                )
                if stop.get("_opening_closed") or (
                    stop.get("_unresolved")
                    and stop.get("optional")
                    and not generic_meal
                ):
                    continue
                evidence = stop.get("_resolved_place") or {}
                location = _text(evidence.get("location"))
                if generic_meal:
                    period = _text(stop.get("period"))
                    meal_label = (
                        "早餐"
                        if period == "breakfast"
                        else "晚餐"
                        if period == "dinner"
                        else "午餐"
                        if period == "lunch"
                        else "用餐"
                    )
                    resolved_name = f"{primary_area}就近{meal_label}"
                else:
                    resolved_name = _text(evidence.get("name"), _text(stop.get("name")))
                evidence_area = _text(evidence.get("area"))
                if evidence_area:
                    area_counts[evidence_area] = area_counts.get(evidence_area, 0) + 1
                cursor_before_stop = cursor
                transfer_count_before_stop = len(transfers)
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
                    if (
                        route_minutes > 120
                        and schedule
                        and stop_type == "visit"
                        and not stop.get("_required_by_user")
                        and _text(stop.get("visit_scale"), "standard")
                        in {"quick_stop", "standard"}
                    ):
                        continue
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
                elif (
                    stop_type in {"visit", "meal"}
                    and not generic_meal
                    and previous_name != _text(stop.get("name"))
                ):
                    cursor += 20

                period = _text(stop.get("period"), "afternoon")
                suggested_start = _clock(stop.get("suggested_start"), -1)
                if suggested_start >= 0:
                    cursor = max(cursor, suggested_start)
                if stop_type == "meal" and period == "lunch":
                    cursor = max(cursor, 11 * 60)
                elif stop_type == "meal" and period == "dinner":
                    cursor = max(cursor, 17 * 60)
                suggested_end = _clock(stop.get("suggested_end"), -1)
                duration = (
                    suggested_end - cursor
                    if suggested_end - cursor >= 30
                    else max(30, min(int(stop.get("duration_minutes") or 90), 540))
                )
                if stop_type == "visit" and period == "morning":
                    later_stops = day_stops[stop_index + 1 :]
                    future_morning_visits = sum(
                        _text(item.get("type")) == "visit"
                        and _text(item.get("period")) == "morning"
                        for item in later_stops
                    )
                    if future_morning_visits and any(
                        _text(item.get("type")) == "meal"
                        and _text(item.get("period")) == "lunch"
                        for item in later_stops
                    ):
                        reserve_for_later = future_morning_visits * 50
                        duration = min(
                            duration,
                            max(30, 13 * 60 + 20 - cursor - reserve_for_later),
                        )
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
                        if (
                            latest_end - cursor < 30
                            and stop.get("optional")
                            and schedule
                        ):
                            cursor = cursor_before_stop
                            del transfers[transfer_count_before_stop:]
                            continue
                        duration = min(duration, max(30, latest_end - cursor))
                end = cursor + duration
                droppable_activity = stop_type not in {
                    "meal",
                    "free_time",
                } and not stop.get("_required_by_user")
                if (
                    end > day_maximum_end
                    and (stop.get("optional") or droppable_activity)
                    and schedule
                ):
                    cursor = cursor_before_stop
                    del transfers[transfer_count_before_stop:]
                    continue
                if cursor >= day_maximum_end:
                    cursor = cursor_before_stop
                    del transfers[transfer_count_before_stop:]
                    continue
                if end > day_maximum_end:
                    duration = day_maximum_end - cursor
                    end = day_maximum_end
                if end <= cursor:
                    continue
                reservation_note = _text(stop.get("reservation_note")) or None
                reservation_check = bool(reservation_note) or (
                    stop_type == "visit"
                    and not _looks_like_transport_hub(resolved_name)
                )
                schedule.append(
                    {
                        "period": period,
                        "type": stop_type,
                        "start": _hhmm(cursor),
                        "end": _hhmm(end),
                        "duration_minutes": duration,
                        "place_id": _text(evidence.get("id")) or None,
                        "name": resolved_name,
                        "area": evidence_area or None,
                        "address": _text(evidence.get("address")) or None,
                        "location": location or None,
                        "reason": _text(stop.get("reason"))
                        or (
                            f"在{evidence_area or primary_area}就近安排用餐，减少跨区折返。"
                            if stop_type == "meal"
                            else f"围绕“{theme}”主题安排，保持当天路线集中。"
                        ),
                        "opening_match": (
                            "risk" if stop.get("_opening_risk") else "unknown"
                        ),
                        "reservation": {
                            "required": None if reservation_check else False,
                            "status": (
                                "needs_verification"
                                if reservation_check
                                else "not_required"
                            ),
                            "note": reservation_note,
                        },
                        "source": (
                            "user"
                            if any(
                                _matches(stop.get("name"), item)
                                for item in context.get("must_visits") or []
                            )
                            else "model_judgment"
                        ),
                        "evidence_fetched_at": evidence.get("fetched_at"),
                        "evidence_stale": bool(evidence.get("stale")),
                        "optional": bool(stop.get("optional", True)),
                        "required_by_user": bool(stop.get("_required_by_user")),
                        "visit_scale": _text(stop.get("visit_scale"), "standard"),
                        "practical_tips": [
                            _text(stop.get("practical_tip"))
                            or (
                                "热门时段可能排队，建议提前取号或预约。"
                                if stop_type == "meal"
                                else "建议按当天开放、预约和人流情况调整停留时间。"
                            )
                        ],
                        "alternatives": (
                            [
                                {
                                    "name": _text(stop["alternative"].get("name")),
                                    "reason": _text(stop["alternative"].get("reason")),
                                    "source": "model_judgment",
                                    "evidence_refs": [],
                                }
                            ]
                            if isinstance(stop.get("alternative"), dict)
                            and _text(stop["alternative"].get("name"))
                            else []
                        )
                        + [
                            {
                                "name": _text(candidate.get("name")),
                                "place_id": _text(candidate.get("id")) or None,
                                "area": _text(
                                    candidate.get("business_area")
                                    or candidate.get("adname")
                                )
                                or None,
                                "address": _text(candidate.get("address")) or None,
                                "location": _text(candidate.get("location")) or None,
                                "source": "amap",
                                "evidence_hash": _text(candidate.get("response_hash"))
                                or None,
                                "evidence_fetched_at": candidate.get("fetched_at"),
                                "evidence_stale": bool(candidate.get("stale")),
                            }
                            for candidate in stop.get("_candidate_places") or []
                            if isinstance(candidate, dict)
                            and _text(candidate.get("id")) != _text(evidence.get("id"))
                        ][:2],
                    }
                )
                cursor = end
                if stop_type in {"visit", "meal"}:
                    previous_name = resolved_name
                    if location:
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
                return_buffer = (
                    10 if mode == "transit" else 5 if mode == "driving" else 0
                )
                latest_return_start = day_maximum_end - route_minutes - return_buffer
                if cursor > latest_return_start:
                    overrun = cursor - latest_return_start
                    while overrun > 0 and schedule:
                        last = schedule[-1]
                        last_duration = int(last.get("duration_minutes") or 0)
                        reducible = max(0, last_duration - 30)
                        if reducible:
                            reduction = min(reducible, overrun)
                            shortened_end = _clock(last.get("end"), cursor) - reduction
                            last["end"] = _hhmm(shortened_end)
                            last["duration_minutes"] = last_duration - reduction
                            cursor -= reduction
                            overrun -= reduction
                        elif last.get("source") == "model_judgment":
                            schedule.pop()
                            cursor = (
                                _clock(schedule[-1].get("end"), day_start)
                                if schedule
                                else day_start
                            )
                            previous_name = (
                                _text(schedule[-1].get("name"), hotel_name)
                                if schedule
                                else hotel_name
                            )
                            previous_location = (
                                _text(schedule[-1].get("location"), hotel_location)
                                if schedule
                                else hotel_location
                            )
                            overrun = max(0, cursor - latest_return_start)
                        else:
                            break
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
                cursor = transfer_end + return_buffer
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
            fallback_note = _text(day.get("fallback_note"))
            if train_option and current_date:
                fallback_note = (
                    f"已按{current_date}核验{intercity_leg.get('train_code')}次时刻"
                    "与参考票价，余票未接入；若首选班次不可用，"
                    "改选相邻时段并压缩抵达后的可选活动。"
                )
            raw_days.append(
                {
                    "day": day_index,
                    "date": current_date,
                    "weekday": weekday,
                    "destination": day_destination,
                    "theme": theme,
                    "summary": _text(day.get("summary"))
                    or f"围绕{primary_area}安排"
                    + "、".join(item["name"] for item in schedule)
                    + "，兼顾游览节奏与交通衔接。",
                    "start_time": _hhmm(day_start),
                    "end_time": _hhmm(min(cursor, day_maximum_end)),
                    "intercity_leg": intercity_leg,
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
                    "fallback": {
                        "notes": fallback_note,
                        "late_drop_order": [
                            item["name"]
                            for item in reversed(schedule)
                            if item.get("source") == "model_judgment"
                        ][:2],
                    },
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
                "以下地点未能绑定实时地图实体；可选项已移除"
                "（必要用餐休息或用户指定项除外），"
                + "、".join(dict.fromkeys(unresolved))
            )
        if not start_date:
            warnings.append("未提供出发日期，天气和按日期开放状态未核验。")
        title = _text(skeleton.get("title"), f"{city}{requested_days}日行程")
        overview = _text(skeleton.get("overview")) or "；".join(
            f"第{item['day']}天{item['theme']}" for item in raw_days
        )
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
        party = context.get("party") if isinstance(context.get("party"), dict) else {}
        hotel_outputs: list[dict[str, Any]] = []
        for hotel_index, hotel_item in enumerate(hotels):
            evidence = hotel_item.get("_resolved_place") or {}
            area = _text(
                hotel_item.get("area"), _text(hotel_item.get("destination"), city)
            )
            reason = _text(hotel_item.get("reason")) or (
                f"以{area}为住宿锚点，减少该站每日往返和换乘。"
            )
            hotel_outputs.append(
                {
                    "destination": _text(hotel_item.get("destination"), city),
                    "name": _text(hotel_item.get("name"), f"{area}住宿区"),
                    "place_id": _text(evidence.get("id")) or None,
                    "area": area,
                    "address": _text(evidence.get("address")) or None,
                    "location": _text(evidence.get("location")) or None,
                    "status": _text(hotel_item.get("status"), "recommended_area"),
                    "reason": reason,
                    "source": (
                        "user"
                        if hotel_index == 0 and context.get("hotel_area")
                        else "model_judgment"
                    ),
                    "evidence_fetched_at": evidence.get("fetched_at"),
                    "evidence_stale": bool(evidence.get("stale")),
                }
            )
        hotel_option_outputs: list[dict[str, Any]] = []
        for hotel_index, hotel_item in enumerate(hotels):
            selected_hotel = hotel_outputs[hotel_index]
            hotel_option_outputs.append(
                {
                    **selected_hotel,
                    "selected": True,
                    "room_type": None,
                    "bed_configuration": _text(
                        party.get("bed_requirement") or context.get("hotel_preferences")
                    )
                    or None,
                    "price_per_night": None,
                    "estimated_total": None,
                    "cancellation": None,
                    "evidence_hash": _text(
                        (hotel_item.get("_resolved_place") or {}).get("response_hash")
                    )
                    or None,
                    "evidence_fetched_at": evidence.get("fetched_at"),
                    "evidence_stale": bool(evidence.get("stale")),
                    "evidence_refs": [],
                }
            )
            selected_id = _text(selected_hotel.get("place_id"))
            for candidate in hotel_item.get("_candidate_places") or []:
                if not isinstance(candidate, dict):
                    continue
                candidate_id = _text(candidate.get("id"))
                if not candidate_id or candidate_id == selected_id:
                    continue
                hotel_option_outputs.append(
                    {
                        "destination": _text(hotel_item.get("destination"), city),
                        "name": _text(candidate.get("name")),
                        "place_id": candidate_id,
                        "area": _text(
                            candidate.get("business_area")
                            or candidate.get("adname")
                            or hotel_item.get("area")
                        ),
                        "address": _text(candidate.get("address")) or None,
                        "location": _text(candidate.get("location")) or None,
                        "status": "candidate",
                        "reason": "地图检索候选；房型、价格、库存和取消政策待核验。",
                        "source": "amap",
                        "selected": False,
                        "room_type": None,
                        "bed_configuration": _text(
                            party.get("bed_requirement")
                            or context.get("hotel_preferences")
                        )
                        or None,
                        "price_per_night": None,
                        "estimated_total": None,
                        "cancellation": None,
                        "evidence_hash": _text(candidate.get("response_hash")) or None,
                        "evidence_fetched_at": candidate.get("fetched_at"),
                        "evidence_stale": bool(candidate.get("stale")),
                        "evidence_refs": [],
                    }
                )
        primary_hotel = hotel_outputs[0]
        hotel_reason = primary_hotel["reason"]
        nights = int(context.get("nights") or max(requested_days - 1, 0))
        overnight_destinations = [
            _text(day.get("destination"), city) for day in raw_days[:nights]
        ]
        destinations = [
            {
                "name": destination,
                "days": sum(
                    _matches(day.get("destination"), destination) for day in raw_days
                ),
                "nights": sum(
                    _matches(name, destination) for name in overnight_destinations
                ),
                "areas": list(
                    dict.fromkeys(
                        _text(day.get("area_cluster", {}).get("primary_area"))
                        for day in raw_days
                        if _matches(day.get("destination"), destination)
                    )
                ),
            }
            for destination in dict.fromkeys(
                _text(day.get("destination"), city) for day in raw_days
            )
        ]
        intercity_options = [
            {
                "id": f"intercity-{day['day']}",
                "day": day["day"],
                "from": _text(day["intercity_leg"].get("from")),
                "to": _text(day["intercity_leg"].get("to")),
                "mode": _text(day["intercity_leg"].get("mode"), "unknown"),
                "departure_hint": _text(day["intercity_leg"].get("departure_hint"))
                or None,
                "arrival_hint": _text(day["intercity_leg"].get("arrival_hint")) or None,
                "status": _text(
                    day["intercity_leg"].get("status"), "planning_suggestion"
                ),
                "train_code": _text(day["intercity_leg"].get("train_code")) or None,
                "duration_minutes": day["intercity_leg"].get("duration_minutes"),
                "price": day["intercity_leg"].get("price"),
                "seat_type": day["intercity_leg"].get("seat_type"),
                "prices": list(day["intercity_leg"].get("prices") or []),
                "provider": day["intercity_leg"].get("provider"),
                "fetched_at": day["intercity_leg"].get("fetched_at"),
                "booking_url": day["intercity_leg"].get("source_url"),
                "source_url": day["intercity_leg"].get("source_url"),
                "evidence_hash": day["intercity_leg"].get("evidence_hash"),
                "alternatives": list(day["intercity_leg"].get("alternatives") or []),
                "evidence_refs": [],
            }
            for day in raw_days
            if day.get("intercity_leg")
        ]
        verified_rail = next(
            (
                item
                for item in intercity_options
                if item.get("mode") == "rail"
                and item.get("status") in {"verified_schedule", "stale_schedule"}
                and item.get("train_code")
            ),
            None,
        )
        transport_notes = [
            _text(item) for item in skeleton.get("transport_notes") or [] if _text(item)
        ]
        budget_notes = [
            _text(item) for item in skeleton.get("budget_notes") or [] if _text(item)
        ]
        if verified_rail:
            rail_date = _text(
                raw_days[int(verified_rail["day"]) - 1].get("date")
                if int(verified_rail["day"]) <= len(raw_days)
                else None
            )
            verified_summary = (
                f"{rail_date or '出行日'}已核验{verified_rail['train_code']}次："
                f"{verified_rail['departure_hint']}出发，"
                f"{verified_rail['arrival_hint']}到达，"
                f"{verified_rail.get('seat_type') or '参考席别'}"
                f"{'约¥' + str(verified_rail['price']) if verified_rail.get('price') is not None else '票价待售票页确认'}；"
                "时刻与参考票价来自12306，余票未接入。"
            )
            overview = re.sub(
                r"[^。]*(?:实际班次|实际车次|动车实际班次)[^。]*"
                r"(?:程序[^。]{0,40}(?:查询|补充)|交由程序)[^。]*。?",
                "",
                overview,
            ).strip()
            overview = f"{overview}{'。' if overview and not overview.endswith('。') else ''}{verified_summary}"
            transport_notes = [
                item
                for item in transport_notes
                if not (
                    re.search(r"(?:班次|车次|票价)", item)
                    and re.search(
                        r"(?:程序[^。]{0,40}(?:查询|补充)|交由程序|当前不虚构)",
                        item,
                    )
                )
            ]
            budget_notes = [
                item
                for item in budget_notes
                if not (
                    re.search(r"(?:动车|铁路|车次|票价)", item)
                    and re.search(r"(?:程序|尚未接入|未接入)", item)
                )
            ]
            budget_notes.append("铁路时刻与参考票价已核验，余票库存仍需在购票时确认。")
            transport_notes.append(verified_summary)
        dining_options = [
            {
                "id": f"meal-{day['day']}-{item_index}",
                "day": day["day"],
                "destination": day["destination"],
                "name": item["name"],
                "period": item["period"],
                "area": item.get("area"),
                "address": item.get("address"),
                "description": item.get("reason"),
                "status": (
                    "verified_place" if item.get("place_id") else "needs_verification"
                ),
                "price_per_person": None,
                "reservation_required": item.get("reservation", {}).get("required"),
                "alternatives": list(item.get("alternatives") or []),
                "evidence_refs": [],
            }
            for day in raw_days
            for item_index, item in enumerate(day["schedule"], 1)
            if item.get("type") == "meal"
        ]
        booking_tasks = [
            {
                "id": f"booking-{day['day']}-{item_index}",
                "category": "dining" if item.get("type") == "meal" else "attraction",
                "target_ref": item.get("place_id"),
                "target_name": item.get("name"),
                "day": day["day"],
                "status": (
                    "action_required"
                    if item.get("reservation", {}).get("required") is True
                    else "needs_verification"
                ),
                "action": _text(item.get("reservation", {}).get("note"))
                or (
                    "立即预约"
                    if item.get("reservation", {}).get("required") is True
                    else "出发前核对是否需要预约"
                ),
                "deadline": None,
                "booking_url": None,
                "delegation_supported": False,
                "evidence_refs": [],
            }
            for day in raw_days
            for item_index, item in enumerate(day["schedule"], 1)
            if (
                (
                    item.get("type") == "visit"
                    and not _looks_like_transport_hub(item.get("name"))
                )
                or item.get("reservation", {}).get("required") is True
            )
            and item.get("reservation", {}).get("required") is not False
        ]
        budget_range = (
            context.get("budget_range")
            if isinstance(context.get("budget_range"), dict)
            else {}
        )
        party_size = (
            int(party.get("adults") or 0)
            + len(party.get("children_ages") or [])
            + int(party.get("seniors") or 0)
        )
        budget_ceiling = budget_range.get("total_max")
        if budget_ceiling is None and budget_range.get("per_person") and party_size:
            budget_ceiling = int(budget_range["per_person"]) * party_size
        budget_categories = []
        if budget_ceiling is not None:
            model_categories = [
                item
                for item in skeleton.get("budget_allocation") or []
                if isinstance(item, dict)
                and _text(item.get("label"))
                and int(item.get("percentage") or 0) > 0
            ]
            if not model_categories:
                model_categories = [
                    {"label": "住宿", "percentage": 40, "reason": "预留住宿主体费用"},
                    {"label": "市内交通", "percentage": 10, "reason": "覆盖日常移动"},
                    {"label": "餐饮", "percentage": 25, "reason": "覆盖正餐与小吃"},
                    {"label": "门票与活动", "percentage": 15, "reason": "覆盖主要体验"},
                    {"label": "机动", "percentage": 10, "reason": "应对临时调整"},
                ]
            total_weight = sum(
                int(item.get("percentage") or 0) for item in model_categories
            )
            allocated = 0
            for index, item in enumerate(model_categories):
                amount = (
                    int(budget_ceiling) - allocated
                    if index == len(model_categories) - 1
                    else round(
                        int(budget_ceiling)
                        * int(item.get("percentage") or 0)
                        / total_weight
                    )
                )
                allocated += amount
                budget_categories.append(
                    {
                        "label": _text(item.get("label")),
                        "planning_cap": amount,
                        "actual_estimate": None,
                        "status": "model_allocation",
                        "reason": _text(item.get("reason")),
                    }
                )
        unknowns = [
            "住宿房型、实时价格和取消政策尚未接入酒店库存服务。",
            (
                "铁路余票库存尚未接入，时刻与参考票价仍需在购票时复核。"
                if verified_rail
                else "城际班次与票价尚未接入票务服务。"
            ),
            "餐厅人均消费和排队状态尚未接入本地生活服务。",
            "开放时间与预约规则只有地图数据，仍需出发前查官方渠道。",
        ]
        return {
            "schema_version": 2,
            "city": city,
            "title": title,
            "overview": overview,
            "duration": {"days": requested_days, "nights": nights},
            "date_range": {"start": start_date or None, "end": date_end},
            "arrival": dict(context.get("arrival") or {}),
            "departure": dict(context.get("departure") or {}),
            "destinations": destinations,
            "party": {
                "summary": _text(context.get("travelers"), "未指定"),
                "party_size": party_size or None,
                **party,
            },
            "trip_profile": {
                "days": requested_days,
                "nights": nights,
                "pace": _PACE.get(_text(context.get("pace")), "balanced"),
                "transport_preference": _TRANSPORT.get(
                    _text(context.get("transport")), "mixed"
                ),
                "travelers": _text(context.get("travelers"), "未指定"),
                "preferences": list(context.get("interests") or []),
                "dietary_requirements": list(context.get("dietary_requirements") or []),
                "mobility_needs": list(context.get("mobility_needs") or []),
                "budget": _text(context.get("budget")),
                "assumptions": ["未明确的票价、预约和营业状态需在出发前复核。"],
            },
            "hotel": primary_hotel,
            "hotels": hotel_outputs,
            "hotel_options": hotel_option_outputs,
            "transport_options": {
                "local": [],
                "local_strategy": {
                    "selected": _TRANSPORT.get(
                        _text(context.get("transport")), "mixed"
                    ),
                    "alternatives": [],
                    "notes": transport_notes,
                },
                "intercity": intercity_options,
            },
            "dining_options": dining_options,
            "booking_tasks": booking_tasks,
            "budget": {
                "currency": _text(budget_range.get("currency"), "CNY"),
                "party_size": party_size or None,
                "preference": _text(context.get("budget")) or None,
                "user_limit": {
                    "total_min": budget_range.get("total_min"),
                    "total_max": budget_range.get("total_max"),
                    "per_person": budget_range.get("per_person"),
                    "includes_major_transport": budget_range.get(
                        "includes_major_transport"
                    ),
                },
                "estimated_total": None,
                "estimated_per_person": None,
                "planning_ceiling": budget_ceiling,
                "categories": budget_categories,
                "included": [],
                "excluded": [],
                "assumptions": [
                    *budget_notes,
                    "预算分配是规划建议，不是实时价格报价。",
                    (
                        "住宿和餐饮实际费用未接入库存服务；"
                        "铁路时刻与参考票价已核验，余票未接入。"
                        if verified_rail
                        else "住宿、票价和餐饮实际费用未接入库存或票务服务。"
                    ),
                ],
                "price_checked_at": None,
                "coverage": "planning_envelope" if budget_categories else "unavailable",
                "confidence": "low",
            },
            "safety": {
                "destination_alerts": [
                    _text(item)
                    for item in skeleton.get("safety_notes") or []
                    if _text(item)
                ],
                "medical": [],
                "transport_risks": [],
                "food_safety": [],
                "altitude_notes": [],
                "emergency_contacts": [],
                "special_population_notes": [],
                "source_status": (
                    "model_judgment" if skeleton.get("safety_notes") else "unavailable"
                ),
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
                "route_overview": "；".join(
                    _text(item)
                    for item in skeleton.get("transport_notes") or []
                    if _text(item)
                )
                or "每日按当晚住宿锚点与相邻片区组织；跨城段需另行核对班次，以实时导航为准。"
            },
            "narrative": {
                "headline": title,
                "summary": overview,
                "highlights": [
                    _text(item)
                    for item in skeleton.get("highlights") or []
                    if _text(item)
                ]
                or [item["summary"] for item in raw_days],
                "tradeoffs": [
                    _text(item)
                    for item in skeleton.get("tradeoffs") or []
                    if _text(item)
                ]
                or [
                    "热门景点、餐厅和晚间项目可能需要预约或排队。",
                    "未指定日期时，开放安排与天气只能在出发前复核。",
                ],
                "weather_advice": None,
            },
            "evidence": [],
            "unknowns": unknowns,
            "warnings": list(dict.fromkeys(warnings))[:8],
        }
