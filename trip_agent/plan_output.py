from __future__ import annotations

import re
from typing import Any, Callable


def text(value: Any, default: str = "") -> str:
    return default if value is None else str(value).strip()


def integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_anchor(value: Any, fallback: str) -> dict[str, Any]:
    anchor = mapping(value)
    return {
        "name": text(anchor.get("name"), fallback),
        "type": text(anchor.get("type"), "area"),
        "location": None,
    }


def normalize_reservation(value: Any) -> dict[str, Any]:
    reservation = mapping(value)
    return {
        "required": bool(reservation.get("required", False)),
        "status": text(reservation.get("status"), "unknown"),
        "note": text(reservation.get("note")) or None,
    }


def normalize_hotel(value: Any) -> dict[str, Any]:
    hotel = mapping(value)
    requested_source = text(hotel.get("source"), "model_judgment")
    source = "user" if requested_source == "user" else "model_judgment"
    status = text(hotel.get("status"), "unknown")
    if source != "user" and status == "confirmed":
        status = "recommended_area"
    return {
        "name": text(hotel.get("name"), "待确认住宿区域"),
        "area": text(hotel.get("area")),
        "address": text(hotel.get("address")) or None if source == "user" else None,
        "location": text(hotel.get("location")) or None if source == "user" else None,
        "status": status,
        "reason": text(hotel.get("reason")),
        "source": source,
    }


def normalize_risk(
    value: Any, weather_evidence: dict[str, Any] | None = None
) -> dict[str, Any]:
    risk = mapping(value)
    risk_type = text(risk.get("type"), "other")
    requested_source = text(risk.get("source"), "model_judgment")
    evidence_hash = text(risk.get("evidence_hash"))
    weather = mapping(weather_evidence)
    source = "model_judgment"
    if requested_source == "user":
        source = "user"
    elif (
        risk_type == "weather"
        and evidence_hash
        and evidence_hash == text(weather.get("response_hash"))
        and requested_source == text(weather.get("provider"))
    ):
        source = requested_source
    return {
        "level": text(risk.get("level"), "info"),
        "type": risk_type,
        "title": text(risk.get("title"), "行程提醒"),
        "detail": text(risk.get("detail")),
        "mitigation": text(risk.get("mitigation")),
        "source": source,
        "evidence_hash": evidence_hash
        if source not in {"model_judgment", "user"}
        else None,
    }


def merge_adjacent_schedule(
    schedule: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for entry in schedule:
        if (
            merged
            and entry.get("place_id")
            and entry.get("place_id") == merged[-1].get("place_id")
        ):
            previous = merged[-1]
            previous["end"] = entry.get("end") or previous["end"]
            previous["duration_minutes"] = integer(
                previous.get("duration_minutes")
            ) + integer(entry.get("duration_minutes"))
            previous["practical_tips"] = list(
                dict.fromkeys(
                    [
                        *items(previous.get("practical_tips")),
                        *items(entry.get("practical_tips")),
                    ]
                )
            )
            continue
        merged.append(entry)
    return merged


def normalize_plan(
    plan: dict[str, Any],
    known_places: dict[str, dict[str, Any]],
    resolve_place: Callable[
        [dict[str, Any], dict[str, dict[str, Any]]], dict[str, Any] | None
    ],
    route_evidence: list[dict[str, Any]],
    weather_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(plan, dict) or not items(plan.get("days")):
        raise ValueError("plan.days 不能为空")
    hotel = normalize_hotel(plan.get("hotel"))
    days = [
        normalize_day(
            day,
            index,
            hotel,
            known_places,
            resolve_place,
            route_evidence,
            weather_evidence,
        )
        for index, day in enumerate(items(plan["days"]), 1)
    ]
    result = {
        "city": text(plan.get("city")),
        "title": text(plan.get("title"), f"{text(plan.get('city'))}深度行程"),
        "overview": text(plan.get("overview")),
        "date_range": {
            "start": text(mapping(plan.get("date_range")).get("start")) or None,
            "end": text(mapping(plan.get("date_range")).get("end")) or None,
        },
        "trip_profile": mapping(plan.get("trip_profile")),
        "hotel": hotel,
        "candidate_comparison": normalize_comparison(plan.get("candidate_comparison")),
        "days": days,
        "map": normalize_map(plan.get("map"), days),
        "narrative": normalize_narrative(plan.get("narrative")),
        "model_quality": mapping(plan.get("quality")),
        "warnings": [
            text(value) for value in items(plan.get("warnings")) if text(value)
        ],
        "verified_routes": route_evidence,
        "weather": weather_evidence,
    }
    result["completeness"] = build_completeness_report(result)
    return result


def normalize_day(
    value: Any,
    index: int,
    hotel: dict[str, Any],
    known_places: dict[str, dict[str, Any]],
    resolve_place: Callable[
        [dict[str, Any], dict[str, dict[str, Any]]], dict[str, Any] | None
    ],
    route_evidence: list[dict[str, Any]],
    weather_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    day = mapping(value)
    raw_schedule = items(day.get("schedule")) or items(day.get("stops"))
    schedule = merge_adjacent_schedule(
        [
            normalize_schedule_item(item, resolve_place(mapping(item), known_places))
            for item in raw_schedule
        ]
    )
    cluster = mapping(day.get("area_cluster"))
    fallback_anchor = hotel["name"]
    start_anchor = normalize_anchor(day.get("start_anchor"), fallback_anchor)
    end_anchor = normalize_anchor(day.get("end_anchor"), fallback_anchor)
    if hotel.get("name"):
        hotel_anchor = {
            "name": hotel["name"],
            "type": "hotel" if hotel.get("status") == "confirmed" else "area",
            "location": hotel.get("location"),
        }
        if start_anchor["type"] != "station":
            start_anchor = dict(hotel_anchor)
        if end_anchor["type"] != "station":
            end_anchor = dict(hotel_anchor)
    return {
        "day": integer(day.get("day"), index),
        "date": text(day.get("date")) or None,
        "weekday": text(day.get("weekday")) or None,
        "theme": text(day.get("theme"), "城市探索"),
        "summary": text(day.get("summary")),
        "start_time": text(
            day.get("start_time"), schedule[0]["start"] if schedule else "09:00"
        ),
        "end_time": text(
            day.get("end_time"), schedule[-1]["end"] if schedule else "18:00"
        ),
        "start_anchor": start_anchor,
        "end_anchor": end_anchor,
        "area_cluster": {
            "primary_area": text(cluster.get("primary_area")),
            "secondary_areas": [
                text(item)
                for item in items(cluster.get("secondary_areas"))
                if text(item)
            ],
            "rationale": text(cluster.get("rationale")),
        },
        "schedule": schedule,
        "transfers": [
            normalize_transfer(item, route_evidence, schedule)
            for item in items(day.get("transfers"))
        ],
        "risks": [
            normalize_risk(item, weather_evidence) for item in items(day.get("risks"))
        ],
    }


def normalize_schedule_item(
    value: dict[str, Any], evidence: dict[str, Any] | None
) -> dict[str, Any]:
    item_type = text(value.get("type"), "visit")
    evidence = evidence or {}
    evidence_type = text(evidence.get("type"))
    if (
        (item_type == "meal" and "餐饮服务" not in evidence_type)
        or (item_type == "hotel" and "住宿服务" not in evidence_type)
        or (
            item_type == "visit"
            and any(category in evidence_type for category in ("餐饮服务", "住宿服务"))
        )
    ):
        evidence = {}
    user_fact = text(value.get("source")) == "user"
    canonical_location = evidence.get("location") or (
        value.get("location") if user_fact else None
    )
    canonical_id = evidence.get("id") or (
        value.get("place_id") or value.get("id") if user_fact else None
    )
    canonical_address = evidence.get("address") or (
        value.get("address") if user_fact else None
    )
    canonical_area = (
        evidence.get("area")
        or evidence.get("adname")
        or evidence.get("business_area")
        or (value.get("area") if user_fact else None)
    )
    biz_ext = mapping(evidence.get("biz_ext"))
    verified_opening = text(
        evidence.get("business_hours")
        or evidence.get("opentime2")
        or evidence.get("opentime")
        or biz_ext.get("open_time")
        or biz_ext.get("open_time2")
    )
    opening_match = text(value.get("opening_match"), "unknown")
    if not verified_opening or opening_match not in {"matched", "risk"}:
        opening_match = "unknown"
    return {
        "period": text(value.get("period"), "afternoon"),
        "type": item_type,
        "start": text(value.get("start")),
        "end": text(value.get("end")),
        "duration_minutes": integer(value.get("duration_minutes")),
        "place_id": text(canonical_id) or None,
        "name": text(evidence.get("name") or value.get("name")),
        "reason": text(value.get("reason")),
        "opening_hours": verified_opening or None,
        "opening_match": opening_match,
        "reservation": normalize_reservation(value.get("reservation")),
        "address": text(canonical_address) or None,
        "area": text(canonical_area) or None,
        "location": text(canonical_location) or None,
        "source": "amap" if evidence else ("user" if user_fact else "model_judgment"),
        "practical_tips": [
            text(item) for item in items(value.get("practical_tips")) if text(item)
        ],
    }


def place_key(value: Any) -> str:
    return re.sub(r"[\s（）()·\-—]", "", text(value).casefold())


def schedule_location(name: Any, schedule: list[dict[str, Any]]) -> str:
    requested = place_key(name)
    if not requested:
        return ""
    for item in schedule:
        candidate = place_key(item.get("name"))
        if (
            candidate
            and item.get("location")
            and (
                candidate == requested
                or candidate in requested
                or requested in candidate
            )
        ):
            return text(item.get("location"))
    return ""


def normalize_transfer(
    value: Any,
    route_evidence: list[dict[str, Any]],
    schedule: list[dict[str, Any]],
) -> dict[str, Any]:
    transfer = mapping(value)
    evidence_hash = text(transfer.get("evidence_hash"))
    from_location = schedule_location(transfer.get("from_name"), schedule)
    to_location = schedule_location(transfer.get("to_name"), schedule)
    evidence = next(
        (
            item
            for item in route_evidence
            if from_location
            and to_location
            and text(item.get("origin")) == from_location
            and text(item.get("destination")) == to_location
            and text(item.get("source")) == "amap"
            and (not evidence_hash or text(item.get("response_hash")) == evidence_hash)
        ),
        None,
    )
    return {
        "from_name": text(transfer.get("from_name")),
        "to_name": text(transfer.get("to_name")),
        "from_location": from_location or None,
        "to_location": to_location or None,
        "mode": text((evidence or transfer).get("mode"), "unknown"),
        "start": text(transfer.get("start")),
        "end": text(transfer.get("end")),
        "duration_minutes": (
            round(integer(evidence.get("duration_seconds")) / 60) if evidence else 0
        ),
        "distance_meters": integer(evidence.get("distance_meters")) if evidence else 0,
        "instructions": text(transfer.get("instructions")),
        "source": "amap" if evidence else "unknown",
        "evidence_hash": evidence_hash if evidence else None,
    }


def normalize_comparison(value: Any) -> dict[str, Any]:
    comparison = mapping(value)
    areas = []
    for value_area in items(comparison.get("areas")):
        area = mapping(value_area)
        areas.append(
            {
                "name": text(area.get("name")),
                "highlights": [
                    text(item) for item in items(area.get("highlights")) if text(item)
                ],
                "tradeoffs": [
                    text(item) for item in items(area.get("tradeoffs")) if text(item)
                ],
                "fit_score": integer(area.get("fit_score")),
                "selected": bool(area.get("selected", False)),
            }
        )
    return {
        "areas": areas,
        "selected_areas": [
            text(item) for item in items(comparison.get("selected_areas")) if text(item)
        ],
        "selection_reason": text(comparison.get("selection_reason")),
    }


def normalize_map(value: Any, days: list[dict[str, Any]]) -> dict[str, Any]:
    map_data = mapping(value)
    points = []
    for day in days:
        for order, schedule_item in enumerate(day["schedule"], 1):
            if not schedule_item.get("location"):
                continue
            points.append(
                {
                    "place_id": schedule_item.get("place_id"),
                    "name": schedule_item["name"],
                    "location": schedule_item["location"],
                    "day": day["day"],
                    "order": order,
                }
            )
    return {
        "center": text(map_data.get("center")) or None,
        "points": points,
        "route_overview": text(map_data.get("route_overview")),
    }


def normalize_narrative(value: Any) -> dict[str, Any]:
    narrative = mapping(value)
    return {
        "headline": text(narrative.get("headline")),
        "summary": text(narrative.get("summary")),
        "highlights": [
            text(item) for item in items(narrative.get("highlights")) if text(item)
        ],
        "tradeoffs": [
            text(item) for item in items(narrative.get("tradeoffs")) if text(item)
        ],
        "weather_advice": text(narrative.get("weather_advice")) or None,
    }


def build_completeness_report(plan: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def check(name: str, passed: bool, ok: str, missing: str) -> None:
        checks.append(
            {
                "name": name,
                "status": "pass" if passed else "warning",
                "detail": ok if passed else missing,
            }
        )

    days = items(plan.get("days"))
    check(
        "每日起止时间",
        bool(days)
        and all(day.get("start_time") and day.get("end_time") for day in days),
        "每天都有开始和结束时间",
        "部分日期缺少开始或结束时间",
    )
    check(
        "每日锚点",
        bool(days)
        and all(
            mapping(day.get("start_anchor")).get("name")
            and mapping(day.get("end_anchor")).get("name")
            for day in days
        ),
        "每天都有明确起终点",
        "部分日期缺少起终点",
    )
    schedule = [entry for day in days for entry in items(day.get("schedule"))]
    timeline_complete = bool(schedule) and all(
        entry.get("start")
        and entry.get("end")
        and integer(entry.get("duration_minutes")) > 0
        for entry in schedule
    )
    check(
        "活动时间轴",
        timeline_complete,
        "活动均包含时间和停留时长",
        "部分活动缺少时间或停留时长",
    )
    visit_items = [
        entry for entry in schedule if entry.get("type") in {"visit", "meal"}
    ]
    evidence_complete = bool(visit_items) and all(
        entry.get("place_id") and entry.get("location") for entry in visit_items
    )
    check(
        "地点与地图证据",
        evidence_complete,
        "地点均有实体 ID 和坐标",
        "部分地点缺少实体 ID 或坐标",
    )
    transfers = [transfer for day in days for transfer in items(day.get("transfers"))]
    verified_transfers = [
        transfer
        for transfer in transfers
        if transfer.get("source") == "amap"
        and integer(transfer.get("duration_minutes")) > 0
        and integer(transfer.get("distance_meters")) > 0
    ]
    expected = sum(max(len(items(day.get("schedule"))) - 1, 0) for day in days)
    check(
        "交通衔接",
        len(verified_transfers) >= expected,
        f"已核验 {len(verified_transfers)} 段交通",
        f"已核验 {len(verified_transfers)} 段交通，时间轴约需 {expected} 段",
    )
    opening_complete = bool(visit_items) and all(
        entry.get("opening_match") in {"matched", "unknown", "risk"}
        for entry in visit_items
    )
    check(
        "开放时间匹配",
        opening_complete,
        "地点均标注开放匹配状态",
        "部分地点未标注开放匹配状态",
    )
    place_ids = [
        text(entry.get("place_id")) for entry in visit_items if entry.get("place_id")
    ]
    check(
        "重复地点",
        len(place_ids) == len(set(place_ids)),
        "未发现重复 POI",
        "存在跨天或同日重复 POI",
    )
    check(
        "风险提示",
        bool(days) and all(isinstance(day.get("risks"), list) for day in days),
        "每天都包含风险列表",
        "部分日期缺少风险列表",
    )
    check(
        "候选区域比较",
        len(items(mapping(plan.get("candidate_comparison")).get("areas"))) >= 2,
        "已比较至少两个候选区域",
        "候选区域比较不足",
    )
    narrative = mapping(plan.get("narrative"))
    check(
        "行程叙事",
        bool(narrative.get("headline") and narrative.get("summary")),
        "包含可读总览和体验叙事",
        "缺少完整行程叙事",
    )
    passed = sum(item["status"] == "pass" for item in checks)
    return {
        "score": round(passed / len(checks) * 100),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }
