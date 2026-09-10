from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import quote


def text(value: Any, default: str = "") -> str:
    return default if value is None else str(value).strip()


def integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def interval_minutes(start: Any, end: Any, fallback: Any = 0) -> int:
    values: list[int] = []
    for value in (start, end):
        match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", text(value))
        if match is None:
            return integer(fallback)
        values.append(int(match.group(1)) * 60 + int(match.group(2)))
    return values[1] - values[0] if values[1] > values[0] else integer(fallback)


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_anchor(
    value: Any,
    fallback: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    anchor = mapping(value)
    evidence = evidence or {}
    user_fact = text(anchor.get("source")) == "user"
    anchor_type = text(anchor.get("type"), "area")
    if (
        anchor_type == "hotel"
        and evidence
        and "住宿服务" not in text(evidence.get("type"))
    ):
        anchor_type = "area"
    return {
        "name": text(anchor.get("name"), fallback),
        "place_id": text(evidence.get("id"))
        or (text(anchor.get("place_id")) if user_fact else None),
        "type": anchor_type,
        "location": text(evidence.get("location"))
        or (text(anchor.get("location")) if user_fact else None),
        "source": "amap" if evidence else ("user" if user_fact else "model_judgment"),
    }


def normalize_reservation(
    value: Any,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reservation = mapping(value)
    verified = mapping(mapping(evidence).get("reservation"))
    required = verified.get("required")
    return {
        "required": required if isinstance(required, bool) else None,
        "status": text(verified.get("status"), "unknown"),
        "note": text(verified.get("note") or reservation.get("note")) or None,
    }


def normalize_hotel(
    value: Any,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hotel = mapping(value)
    evidence = evidence or {}
    requested_source = text(hotel.get("source"), "model_judgment")
    user_fact = requested_source == "user"
    source = "amap" if evidence else ("user" if user_fact else "model_judgment")
    status = text(hotel.get("status"), "unknown")
    if not user_fact and status == "confirmed":
        status = "recommended_area"
    return {
        "name": text(hotel.get("name"), "待确认住宿区域"),
        "place_id": text(evidence.get("id"))
        or (text(hotel.get("place_id")) if user_fact else None),
        "area": text(
            hotel.get("area") or evidence.get("adname") or evidence.get("business_area")
        ),
        "address": text(evidence.get("address"))
        or (text(hotel.get("address")) if user_fact else None),
        "location": text(evidence.get("location"))
        or (text(hotel.get("location")) if user_fact else None),
        "evidence_hash": text(evidence.get("response_hash")) or None,
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
            previous["duration_minutes"] = interval_minutes(
                previous.get("start"),
                previous.get("end"),
                integer(previous.get("duration_minutes"))
                + integer(entry.get("duration_minutes")),
            )
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
    raw_hotel = mapping(plan.get("hotel"))
    raw_hotels = [
        mapping(value) for value in items(plan.get("hotels")) if mapping(value)
    ] or [raw_hotel]
    hotels = [
        normalize_hotel(value, resolve_place(value, known_places))
        | {"destination": text(value.get("destination"), text(plan.get("city")))}
        for value in raw_hotels
    ]
    hotel = hotels[0]

    def hotel_for_day(day: Any) -> dict[str, Any]:
        destination = text(mapping(day).get("destination"))
        return next(
            (
                value
                for value in hotels
                if destination
                and place_key(value.get("destination")) == place_key(destination)
            ),
            hotel,
        )

    days = [
        normalize_day(
            day,
            index,
            hotel_for_day(day),
            known_places,
            resolve_place,
            route_evidence,
            weather_evidence,
        )
        for index, day in enumerate(items(plan["days"]), 1)
    ]
    result = {
        "schema_version": integer(plan.get("schema_version"), 2),
        "city": text(plan.get("city")),
        "title": text(plan.get("title"), f"{text(plan.get('city'))}深度行程"),
        "overview": text(plan.get("overview")),
        "duration": mapping(plan.get("duration")),
        "date_range": {
            "start": text(mapping(plan.get("date_range")).get("start")) or None,
            "end": text(mapping(plan.get("date_range")).get("end")) or None,
        },
        "arrival": mapping(plan.get("arrival")),
        "departure": mapping(plan.get("departure")),
        "destinations": items(plan.get("destinations")),
        "party": mapping(plan.get("party")),
        "trip_profile": mapping(plan.get("trip_profile")),
        "hotel": hotel,
        "hotels": hotels,
        "hotel_options": items(plan.get("hotel_options")),
        "transport_options": mapping(plan.get("transport_options")),
        "dining_options": items(plan.get("dining_options")),
        "booking_tasks": items(plan.get("booking_tasks")),
        "budget": mapping(plan.get("budget")),
        "safety": mapping(plan.get("safety")),
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
        "evidence": items(plan.get("evidence")),
        "unknowns": [
            text(value) for value in items(plan.get("unknowns")) if text(value)
        ],
    }
    add_traceability(result)
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
    raw_start_anchor = mapping(day.get("start_anchor"))
    raw_end_anchor = mapping(day.get("end_anchor"))
    start_anchor = normalize_anchor(
        raw_start_anchor,
        fallback_anchor,
        resolve_place(raw_start_anchor, known_places),
    )
    end_anchor = normalize_anchor(
        raw_end_anchor,
        fallback_anchor,
        resolve_place(raw_end_anchor, known_places),
    )
    if hotel.get("name"):
        hotel_anchor = {
            "name": hotel["name"],
            "place_id": hotel.get("place_id"),
            "type": "hotel" if hotel.get("status") == "confirmed" else "area",
            "location": hotel.get("location"),
            "source": hotel.get("source", "model_judgment"),
        }
        if start_anchor["type"] != "station":
            start_anchor = dict(hotel_anchor)
        if end_anchor["type"] != "station":
            end_anchor = dict(hotel_anchor)
    transfers = [
        normalize_transfer(
            item,
            route_evidence,
            [start_anchor, *schedule, end_anchor],
        )
        for item in items(day.get("transfers"))
    ]
    transfers = [
        item
        for item in transfers
        if not (
            item.get("from_location")
            and item.get("from_location") == item.get("to_location")
        )
    ]
    return {
        "destination": text(day.get("destination")),
        "intercity_leg": mapping(day.get("intercity_leg")),
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
        "transfers": transfers,
        "fallback": {
            "notes": text(mapping(day.get("fallback")).get("notes")),
            "late_drop_order": [
                text(item)
                for item in items(
                    mapping(day.get("fallback")).get("late_drop_order")
                )
                if text(item)
            ],
        },
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
        or biz_ext.get("opentime2")
        or biz_ext.get("opentime")
    )
    opening_match = text(value.get("opening_match"), "unknown")
    if not verified_opening or opening_match not in {"matched", "risk"}:
        opening_match = "unknown"
    start = text(value.get("start"))
    end = text(value.get("end"))
    return {
        "period": text(value.get("period"), "afternoon"),
        "type": item_type,
        "start": start,
        "end": end,
        "duration_minutes": interval_minutes(start, end, value.get("duration_minutes")),
        "place_id": text(canonical_id) or None,
        "name": text(evidence.get("name") or value.get("name")),
        "reason": text(value.get("reason")),
        "opening_hours": verified_opening or None,
        "opening_match": opening_match,
        "reservation": normalize_reservation(value.get("reservation"), evidence),
        "address": text(canonical_address) or None,
        "area": text(canonical_area) or None,
        "location": text(canonical_location) or None,
        "source": "amap" if evidence else ("user" if user_fact else "model_judgment"),
        "visit_scale": text(value.get("visit_scale"), "standard"),
        "evidence_hash": text(evidence.get("response_hash")) or None,
        "optional": bool(value.get("optional", True)),
        "evidence_refs": [],
        "practical_tips": [
            text(item) for item in items(value.get("practical_tips")) if text(item)
        ],
        "alternatives": [
            {
                "name": text(mapping(item).get("name")),
                "place_id": text(mapping(item).get("place_id")) or None,
                "area": text(mapping(item).get("area")) or None,
                "address": text(mapping(item).get("address")) or None,
                "location": text(mapping(item).get("location")) or None,
                "source": text(mapping(item).get("source"), "model_judgment"),
                "evidence_hash": text(mapping(item).get("evidence_hash")) or None,
                "evidence_refs": [],
            }
            for item in items(value.get("alternatives"))
            if text(mapping(item).get("name"))
        ],
    }

def place_key(value: Any) -> str:
    return re.sub(r"[\s（）()·\-—]", "", text(value).casefold())


def schedule_endpoint(name: Any, schedule: list[dict[str, Any]]) -> dict[str, Any]:
    requested = place_key(name)
    if not requested:
        return {}
    candidates = [
        item
        for item in schedule
        if place_key(item.get("name")) and item.get("location")
    ]
    exact = next(
        (item for item in candidates if place_key(item.get("name")) == requested),
        None,
    )
    if exact is not None:
        return exact
    fuzzy = [
        item
        for item in candidates
        if place_key(item.get("name")) in requested
        or requested in place_key(item.get("name"))
    ]
    return max(fuzzy, key=lambda item: len(place_key(item.get("name"))), default={})


def schedule_location(name: Any, schedule: list[dict[str, Any]]) -> str:
    return text(schedule_endpoint(name, schedule).get("location"))


def normalize_transfer(
    value: Any,
    route_evidence: list[dict[str, Any]],
    schedule: list[dict[str, Any]],
) -> dict[str, Any]:
    transfer = mapping(value)
    evidence_hash = text(transfer.get("evidence_hash"))
    from_endpoint = schedule_endpoint(transfer.get("from_name"), schedule)
    to_endpoint = schedule_endpoint(transfer.get("to_name"), schedule)
    schedule_locations = {
        text(item.get("location")) for item in schedule if text(item.get("location"))
    }
    raw_from_location = text(transfer.get("from_location"))
    raw_to_location = text(transfer.get("to_location"))
    if raw_from_location not in schedule_locations:
        raw_from_location = ""
    if raw_to_location not in schedule_locations:
        raw_to_location = ""
    from_location = raw_from_location or text(from_endpoint.get("location"))
    to_location = raw_to_location or text(to_endpoint.get("location"))
    evidence = next(
        (
            item
            for item in route_evidence
            if from_location
            if text(transfer.get("source")) != "estimate"
            and to_location
            and text(item.get("origin")) == from_location
            and text(item.get("destination")) == to_location
            and text(item.get("source")) == "amap"
            and (not evidence_hash or text(item.get("response_hash")) == evidence_hash)
        ),
        None,
    )
    estimated = (
        evidence is None
        and text(transfer.get("source")) == "estimate"
        and bool(from_location)
        and bool(to_location)
        and integer(transfer.get("duration_minutes")) > 0
    )
    return {
        "from_name": (
            text(transfer.get("from_name"))
            if raw_from_location
            else text(from_endpoint.get("name"), text(transfer.get("from_name")))
        ),
        "to_name": (
            text(transfer.get("to_name"))
            if raw_to_location
            else text(to_endpoint.get("name"), text(transfer.get("to_name")))
        ),
        "from_location": from_location or None,
        "to_location": to_location or None,
        "mode": text((evidence or transfer).get("mode"), "unknown"),
        "start": text(transfer.get("start")),
        "end": text(transfer.get("end")),
        "duration_minutes": (
            round(integer(evidence.get("duration_seconds")) / 60)
            if evidence
            else integer(transfer.get("duration_minutes"))
            if estimated
            else 0
        ),
        "distance_meters": (
            integer(evidence.get("distance_meters"))
            if evidence
            else integer(transfer.get("distance_meters"))
            if estimated
            else 0
        ),
        "instructions": text(transfer.get("instructions")),
        "source": "amap" if evidence else "estimate" if estimated else "unknown",
        "evidence_hash": text(evidence.get("response_hash")) if evidence else None,
    }


def add_traceability(plan: dict[str, Any]) -> None:
    """Attach evidence references and complete choice/task views without inventing facts."""
    evidence: dict[str, dict[str, Any]] = {}

    def evidence_id(prefix: str, value: Any) -> str:
        token = re.sub(r"[^0-9A-Za-z]+", "-", text(value)).strip("-").lower()
        return f"{prefix}-{token[-32:] or 'unknown'}"

    def add_evidence(
        evidence_ref: str,
        *,
        provider: str,
        title: str,
        url: str | None,
        supports: list[str],
        confidence: str,
        response_hash: str | None,
    ) -> None:
        evidence[evidence_ref] = {
            "id": evidence_ref,
            "provider": provider,
            "title": title,
            "url": url,
            "retrieved_at": None,
            "valid_for_date": None,
            "supports": supports,
            "confidence": confidence,
            "response_hash": response_hash,
        }

    hotels = items(plan.get("hotels"))
    raw_options = [*hotels, *items(plan.get("hotel_options"))]
    hotel_options: list[dict[str, Any]] = []
    seen_hotels: set[str] = set()
    for option in raw_options:
        key = text(option.get("place_id")) or (
            f"{text(option.get('destination'))}:{text(option.get('name'))}"
        )
        if not key or key in seen_hotels:
            continue
        seen_hotels.add(key)
        hotel_options.append(option)
    selected_ids = {
        text(hotel.get("place_id")) or text(hotel.get("name")) for hotel in hotels
    }
    for hotel_index, hotel in enumerate(hotel_options):
        selected_key = text(hotel.get("place_id")) or text(hotel.get("name"))
        hotel["selected"] = selected_key in selected_ids
        hotel.setdefault("price_per_night", None)
        hotel.setdefault("estimated_total", None)
        hotel.setdefault("cancellation", None)
        hotel["evidence_refs"] = []
        if hotel.get("source") != "amap" or not hotel.get("place_id"):
            continue
        ref = evidence_id("amap-poi", hotel.get("place_id"))
        hotel["evidence_refs"] = [ref]
        url = (
            f"https://uri.amap.com/marker?position={hotel['location']}"
            f"&name={quote(text(hotel.get('name')))}"
            if hotel.get("location")
            else None
        )
        add_evidence(
            ref,
            provider="amap",
            title=f"{text(hotel.get('name'))}地图实体",
            url=url,
            supports=[f"hotel_options[{hotel_index}].location"],
            confidence="medium",
            response_hash=text(hotel.get("evidence_hash")) or None,
        )
    plan["hotel_options"] = hotel_options

    dining_options: list[dict[str, Any]] = []
    booking_tasks: list[dict[str, Any]] = []
    local_transport: list[dict[str, Any]] = []
    period_labels = {
        "breakfast": "早餐",
        "morning": "上午",
        "lunch": "午餐",
        "afternoon": "下午",
        "dinner": "晚餐",
        "evening": "晚上",
    }
    for day_index, day in enumerate(items(plan.get("days"))):
        grouped: dict[str, list[str]] = {}
        optional_items: list[str] = []
        for item_index, item in enumerate(items(day.get("schedule"))):
            item_id = f"day-{day_index + 1}-item-{item_index + 1}"
            item["id"] = item_id
            grouped.setdefault(text(item.get("period"), "afternoon"), []).append(item_id)
            if item.get("optional"):
                optional_items.append(item_id)
            item["evidence_refs"] = []
            if item.get("source") == "amap" and item.get("place_id"):
                ref = evidence_id("amap-poi", item.get("place_id"))
                item["evidence_refs"] = [ref]
                url = (
                    f"https://uri.amap.com/marker?position={item['location']}"
                    f"&name={quote(text(item.get('name')))}"
                    if item.get("location")
                    else None
                )
                add_evidence(
                    ref,
                    provider="amap",
                    title=f"{text(item.get('name'))}地图实体",
                    url=url,
                    supports=[
                        f"days[{day_index}].schedule[{item_index}].place_id",
                        f"days[{day_index}].schedule[{item_index}].location",
                    ],
                    confidence="medium",
                    response_hash=text(item.get("evidence_hash")) or None,
                )
            for alternative_index, alternative in enumerate(
                items(item.get("alternatives"))
            ):
                alternative["evidence_refs"] = []
                if (
                    alternative.get("source") != "amap"
                    or not alternative.get("place_id")
                ):
                    continue
                alternative_ref = evidence_id(
                    "amap-poi", alternative.get("place_id")
                )
                alternative["evidence_refs"] = [alternative_ref]
                alternative_url = (
                    f"https://uri.amap.com/marker?position={alternative['location']}"
                    f"&name={quote(text(alternative.get('name')))}"
                    if alternative.get("location")
                    else None
                )
                add_evidence(
                    alternative_ref,
                    provider="amap",
                    title=f"{text(alternative.get('name'))}地图实体",
                    url=alternative_url,
                    supports=[
                        f"days[{day_index}].schedule[{item_index}]"
                        f".alternatives[{alternative_index}].place_id"
                    ],
                    confidence="medium",
                    response_hash=text(alternative.get("evidence_hash")) or None,
                )
            reservation = mapping(item.get("reservation"))
            if item.get("type") == "meal":
                dining_options.append(
                    {
                        "id": f"meal-{day_index + 1}-{item_index + 1}",
                        "day": day_index + 1,
                        "destination": day.get("destination"),
                        "name": item.get("name"),
                        "period": item.get("period"),
                        "area": item.get("area"),
                        "address": item.get("address"),
                        "description": item.get("reason"),
                        "status": (
                            "verified_place"
                            if item.get("place_id")
                            else "needs_verification"
                        ),
                        "price_per_person": None,
                        "reservation_required": reservation.get("required"),
                        "alternatives": items(item.get("alternatives")),
                        "evidence_refs": list(item.get("evidence_refs") or []),
                    }
                )
            if (
                item.get("type") == "visit"
                or reservation.get("required") is True
            ) and reservation.get("required") is not False:
                booking_tasks.append(
                    {
                        "id": f"booking-{day_index + 1}-{item_index + 1}",
                        "category": (
                            "dining" if item.get("type") == "meal" else "attraction"
                        ),
                        "target_ref": item.get("place_id"),
                        "target_name": item.get("name"),
                        "day": day_index + 1,
                        "status": (
                            "action_required"
                            if reservation.get("required") is True
                            else "needs_verification"
                        ),
                        "action": (
                            "立即预约"
                            if reservation.get("required") is True
                            else "出发前核对是否需要预约"
                        ),
                        "deadline": None,
                        "booking_url": None,
                        "delegation_supported": False,
                        "evidence_refs": list(item.get("evidence_refs") or []),
                    }
                )
        day["periods"] = [
            {
                "period": period,
                "label": period_labels[period],
                "item_refs": grouped.get(period, []),
            }
            for period in period_labels
        ]
        existing_fallback = mapping(day.get("fallback"))
        day["fallback"] = {
            "late_drop_order": [
                text(item)
                for item in items(existing_fallback.get("late_drop_order"))
                if text(item)
            ]
            or list(reversed(optional_items)),
            "rain": existing_fallback.get("rain"),
            "notes": text(existing_fallback.get("notes"))
            or (
                "发生晚点时按顺序删减可选项；雨天替代方案需结合实时天气和室内开放状态另行确认。"
                if optional_items
                else "当天没有自动可删减项，延误时需整体调整。"
            ),
        }
        for transfer_index, transfer in enumerate(items(day.get("transfers"))):
            transfer["evidence_refs"] = []
            if transfer.get("source") == "amap" and transfer.get("evidence_hash"):
                ref = evidence_id("amap-route", transfer.get("evidence_hash"))
                transfer["evidence_refs"] = [ref]
                add_evidence(
                    ref,
                    provider="amap",
                    title=(
                        f"{text(transfer.get('from_name'))}至"
                        f"{text(transfer.get('to_name'))}路线"
                    ),
                    url=None,
                    supports=[
                        f"days[{day_index}].transfers[{transfer_index}].duration_minutes",
                        f"days[{day_index}].transfers[{transfer_index}].distance_meters",
                    ],
                    confidence="medium",
                    response_hash=text(transfer.get("evidence_hash")) or None,
                )
            local_transport.append(
                {
                    "id": f"transfer-{day_index + 1}-{transfer_index + 1}",
                    "day": day_index + 1,
                    "from_name": transfer.get("from_name"),
                    "to_name": transfer.get("to_name"),
                    "mode": transfer.get("mode"),
                    "duration_minutes": transfer.get("duration_minutes"),
                    "distance_meters": transfer.get("distance_meters"),
                    "instructions": transfer.get("instructions"),
                    "source": transfer.get("source"),
                    "evidence_refs": list(transfer.get("evidence_refs") or []),
                }
            )
    plan["dining_options"] = dining_options
    plan["booking_tasks"] = booking_tasks
    transport = mapping(plan.get("transport_options"))
    transport["local"] = local_transport
    intercity_options = items(transport.get("intercity"))
    for option_index, option in enumerate(intercity_options):
        option["evidence_refs"] = []
        if (
            option.get("provider") == "rail12306"
            and option.get("source_url")
            and option.get("evidence_hash")
        ):
            ref = evidence_id("rail12306", option.get("evidence_hash"))
            option["evidence_refs"] = [ref]
            add_evidence(
                ref,
                provider="rail12306",
                title=(
                    f"{text(option.get('train_code'), '铁路班次')} "
                    f"{text(option.get('from'))}至{text(option.get('to'))}"
                ),
                url=text(option.get("source_url")) or None,
                supports=[
                    f"transport_options.intercity[{option_index}].departure_hint",
                    f"transport_options.intercity[{option_index}].arrival_hint",
                    f"transport_options.intercity[{option_index}].price",
                ],
                confidence="medium",
                response_hash=text(option.get("evidence_hash")) or None,
            )
    transport["intercity"] = intercity_options
    plan["transport_options"] = transport

    weather = mapping(plan.get("weather"))
    requested_dates = {
        text(day.get("date"))
        for day in items(plan.get("days"))
        if text(day.get("date"))
    }
    if requested_dates:
        weather["days"] = [
            day
            for day in items(weather.get("days"))
            if text(mapping(day).get("date")) in requested_dates
        ]
    if items(weather.get("days")):
        response_hash = text(weather.get("response_hash")) or None
        ref = evidence_id("weather", response_hash or weather.get("provider"))
        add_evidence(
            ref,
            provider=text(weather.get("provider"), "unknown"),
            title="行程日期内逐日天气预报",
            url=None,
            supports=["weather.days"],
            confidence="medium",
            response_hash=response_hash,
        )
        weather["evidence_refs"] = [ref]
        weather["mode"] = "forecast"
        weather["available"] = True
    elif weather:
        weather["mode"] = "unavailable"
        weather["available"] = False
        weather["coverage"] = "none"
        weather["fallback_reason"] = "天气预报窗口尚未覆盖行程日期"

    profile = mapping(plan.get("trip_profile"))
    safety = mapping(plan.get("safety"))
    mobility_needs = [
        text(value) for value in items(profile.get("mobility_needs")) if text(value)
    ]
    safety["special_population_notes"] = [
        {"note": value, "source": "user"} for value in mobility_needs
    ]
    safety.setdefault("source_status", "unavailable")
    plan["safety"] = safety
    plan["evidence"] = list(evidence.values())


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
    duration = mapping(plan.get("duration"))
    check(
        "天数与日期",
        integer(duration.get("days")) == len(days)
        and bool(mapping(plan.get("date_range")).get("start")),
        "行程天数与日期范围完整",
        "日期未填写或天数与每日行程不一致",
    )
    check(
        "每日时段与兜底",
        bool(days)
        and all(
            len(items(day.get("periods"))) == 6
            and isinstance(day.get("fallback"), dict)
            for day in days
        ),
        "每天均有六时段索引和延误/雨天兜底",
        "部分日期缺少时段索引或兜底方案",
    )
    check(
        "住宿选项",
        bool(items(plan.get("hotels"))) and bool(items(plan.get("hotel_options"))),
        "住宿按城市列出并标记证据状态",
        "住宿选项不完整",
    )
    transport = mapping(plan.get("transport_options"))
    check(
        "交通选项",
        bool(items(transport.get("local")) or items(transport.get("intercity"))),
        "已列出市内或跨城交通选项",
        "没有形成独立交通选项",
    )
    check(
        "餐饮选项",
        bool(items(plan.get("dining_options"))),
        "用餐点已形成可核验选项",
        "没有形成独立餐饮选项",
    )
    check(
        "预订清单",
        isinstance(plan.get("booking_tasks"), list),
        "预约状态已形成待办清单",
        "缺少预约待办清单",
    )
    budget = mapping(plan.get("budget"))
    check(
        "预算明细",
        bool(items(budget.get("categories"))) and bool(items(budget.get("assumptions"))),
        "预算按类别列出并说明估算假设",
        "预算类别或估算假设不足",
    )
    check(
        "安全信息",
        isinstance(plan.get("safety"), dict)
        and "source_status" in mapping(plan.get("safety")),
        "安全信息明确标注来源状态",
        "安全信息未标注来源状态",
    )
    evidence_ids = {
        text(item.get("id"))
        for item in items(plan.get("evidence"))
        if isinstance(item, dict) and text(item.get("id"))
    }
    claimed_refs = [
        text(ref)
        for day in days
        for entry in [
            *items(day.get("schedule")),
            *items(day.get("transfers")),
        ]
        for ref in items(mapping(entry).get("evidence_refs"))
        if text(ref)
    ]
    check(
        "事实证据链",
        bool(claimed_refs) and all(ref in evidence_ids for ref in claimed_refs),
        "地图或天气事实均可追溯到证据记录",
        "缺少可追溯事实，或存在失效证据引用",
    )
    passed = sum(item["status"] == "pass" for item in checks)
    return {
        "score": round(passed / len(checks) * 100),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }
