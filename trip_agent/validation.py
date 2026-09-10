from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return re.sub(r"[\s·（）()\-—]", "", _text(value)).casefold()

def _matches_key(left: str, right: str) -> bool:
    def options(value: str) -> list[str]:
        return [
            re.sub(r"(?:一带|附近|周边|区域|择一)$", "", item)
            for item in re.split(r"(?:优先|或者|或|/)", value)
            if item
        ]

    def matches_one(left_value: str, right_value: str) -> bool:
        if left_value in right_value or right_value in left_value:
            return True
        left_without_city = left_value[2:] if len(left_value) >= 6 else left_value
        right_without_city = right_value[2:] if len(right_value) >= 6 else right_value
        return bool(
            left_without_city in right_value
            or right_without_city in left_value
            or left_without_city in right_without_city
            or right_without_city in left_without_city
        )

    if not left or not right:
        return False
    return any(
        matches_one(left_value, right_value)
        for left_value in options(left)
        for right_value in options(right)
        if left_value and right_value
    )


def _minutes(value: Any) -> int | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", _text(value))
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _issue(
    code: str,
    path: str,
    message: str,
    *,
    actual: Any = None,
    expected: Any = None,
    evidence_refs: list[str] | None = None,
    allowed_actions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "hard",
        "path": path,
        "message": message,
        "actual": actual,
        "expected": expected,
        "evidence_refs": evidence_refs or [],
        "allowed_actions": allowed_actions or [],
    }


def _warning(code: str, path: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": "warning", "path": path, "message": message}


@dataclass
class HardValidator:
    version: str = "hard-validator-v4"
    _failures: list[dict[str, Any]] = field(default_factory=list, init=False)
    _warnings: list[dict[str, Any]] = field(default_factory=list, init=False)

    def validate(
        self,
        plan: dict[str, Any],
        planning_context: dict[str, Any],
    ) -> dict[str, Any]:
        self._failures = []
        self._warnings = []
        days = plan.get("days") if isinstance(plan.get("days"), list) else []
        self._validate_request(plan, days, planning_context)
        self._validate_days(plan, days, planning_context)
        plan_hash = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        )
        fingerprint = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    [(item["code"], item["path"]) for item in self._failures],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        )
        return {
            "passed": not self._failures,
            "validator_version": self.version,
            "plan_hash": plan_hash,
            "failure_fingerprint": fingerprint,
            "hard_failures": self._failures,
            "warnings": self._warnings,
        }

    def _validate_request(
        self,
        plan: dict[str, Any],
        days: list[Any],
        context: dict[str, Any],
    ) -> None:
        expected_city = _key(context.get("destination"))
        actual_city = _key(plan.get("city"))
        if expected_city and actual_city and expected_city != actual_city:
            self._failures.append(
                _issue(
                    "CITY_MISMATCH",
                    "$.city",
                    "行程城市与用户目的地不一致",
                    actual=plan.get("city"),
                    expected=context.get("destination"),
                )
            )
        date_range = (
            plan.get("date_range") if isinstance(plan.get("date_range"), dict) else {}
        )
        if not context.get("start_date") and (
            date_range.get("start") or date_range.get("end")
        ):
            self._failures.append(
                _issue(
                    "UNREQUESTED_DATE",
                    "$.date_range",
                    "用户未指定日期，不得把天气参考日或当前日期写成行程日期",
                    actual=date_range,
                    expected={"start": None, "end": None},
                    allowed_actions=["clear_unrequested_dates"],
                )
            )
        expected_days = int(context.get("days") or 0)
        if expected_days and len(days) != expected_days:
            self._failures.append(
                _issue(
                    "DAY_COUNT_MISMATCH",
                    "$.days",
                    "行程天数与用户要求不一致",
                    actual=len(days),
                    expected=expected_days,
                )
            )
        requested_hotel = _key(context.get("hotel_area"))
        hotel = plan.get("hotel") if isinstance(plan.get("hotel"), dict) else {}
        actual_hotel = _key(f"{_text(hotel.get('name'))}{_text(hotel.get('area'))}")
        if requested_hotel and requested_hotel not in actual_hotel:
            self._failures.append(
                _issue(
                    "HOTEL_CONSTRAINT_MISMATCH",
                    "$.hotel",
                    "住宿锚点与用户指定的酒店或区域不一致",
                    actual=hotel.get("name") or hotel.get("area"),
                    expected=context.get("hotel_area"),
                )
            )
        names = [
            _key(item.get("name"))
            for day in days
            if isinstance(day, dict)
            for item in day.get("schedule", [])
            if isinstance(item, dict)
        ]
        for index, must_visit in enumerate(context.get("must_visits") or []):
            requested = _key(must_visit)
            if requested and not any(
                _matches_key(requested, name) for name in names if name
            ):
                self._failures.append(
                    _issue(
                        "MUST_VISIT_MISSING",
                        "$.days",
                        f"必去地点“{must_visit}”未进入行程",
                        expected=must_visit,
                        allowed_actions=[
                            "search_places",
                            "place_detail",
                            "add_required_stop",
                        ],
                    )
                )

    def _validate_days(
        self,
        plan: dict[str, Any],
        days: list[Any],
        context: dict[str, Any],
    ) -> None:
        seen_places: dict[str, str] = {}
        hotels = [
            item for item in plan.get("hotels") or [] if isinstance(item, dict)
        ]
        if not hotels and isinstance(plan.get("hotel"), dict):
            hotels = [plan["hotel"]]

        def matches_hotel_anchor(
            anchor: dict[str, Any], expected_hotel: dict[str, Any]
        ) -> bool:
            hotel_place_id = _text(expected_hotel.get("place_id"))
            anchor_place_id = _text(anchor.get("place_id"))
            if hotel_place_id and anchor_place_id:
                return hotel_place_id == anchor_place_id
            hotel_location = _text(expected_hotel.get("location"))
            anchor_location = _text(anchor.get("location"))
            if hotel_location and anchor_location:
                return hotel_location == anchor_location
            return _key(expected_hotel.get("name")) == _key(anchor.get("name"))

        window = (
            context.get("daily_window")
            if isinstance(context.get("daily_window"), dict)
            else {}
        )
        requested_start = _minutes(window.get("start"))
        requested_end = _minutes(window.get("end"))
        expected_start_date = _text(context.get("start_date"))
        requested_destinations = [
            item
            for item in context.get("destinations") or []
            if isinstance(item, dict)
        ]
        allocations_are_explicit = bool(requested_destinations) and all(
            int(item.get("days") or 0) > 0 for item in requested_destinations
        )
        expected_destinations = (
            [
                _text(item.get("destination"))
                for item in requested_destinations
                for _ in range(int(item.get("days") or 0))
            ]
            if allocations_are_explicit
            else []
        )
        arrival = context.get("arrival") if isinstance(context.get("arrival"), dict) else {}
        departure = (
            context.get("departure")
            if isinstance(context.get("departure"), dict)
            else {}
        )

        for day_index, raw_day in enumerate(days):
            path = f"$.days[{day_index}]"
            if not isinstance(raw_day, dict):
                self._failures.append(_issue("INVALID_DAY", path, "每日行程必须是对象"))
                continue
            day = raw_day
            expected_destination = (
                expected_destinations[day_index]
                if day_index < len(expected_destinations)
                else ""
            )
            actual_destination = _text(day.get("destination"))
            if expected_destination and not (
                actual_destination == expected_destination
                or expected_destination in actual_destination
                or actual_destination in expected_destination
            ):
                self._failures.append(
                    _issue(
                        "DESTINATION_SEQUENCE_INVALID",
                        f"{path}.destination",
                        "每日目的地必须按用户给定顺序分配",
                        actual=actual_destination,
                        expected=expected_destination,
                    )
                )
            intercity_leg = (
                day.get("intercity_leg")
                if isinstance(day.get("intercity_leg"), dict)
                else {}
            )
            if (
                day_index > 0
                and expected_destinations
                and expected_destinations[day_index - 1] != expected_destination
                and not (
                    _text(intercity_leg.get("mode"))
                    and _text(intercity_leg.get("from"))
                    and _text(intercity_leg.get("to"))
                )
            ):
                self._failures.append(
                    _issue(
                        "MISSING_INTERCITY_LEG",
                        f"{path}.intercity_leg",
                        "跨城日必须说明城际移动方式和时间偏移",
                    )
                )
            hotel = next(
                (
                    item
                    for item in hotels
                    if _text(item.get("destination")) == actual_destination
                    or (
                        expected_destination
                        and _text(item.get("destination")) == expected_destination
                    )
                ),
                hotels[0] if hotels else {},
            )
            hotel_name = _key(hotel.get("name"))
            if int(day.get("day") or 0) != day_index + 1:
                self._failures.append(
                    _issue(
                        "DAY_SEQUENCE_INVALID",
                        f"{path}.day",
                        "日期序号必须连续",
                        actual=day.get("day"),
                        expected=day_index + 1,
                    )
                )
            if expected_start_date:
                try:
                    expected_date = (
                        date.fromisoformat(expected_start_date)
                        + timedelta(days=day_index)
                    ).isoformat()
                except ValueError:
                    expected_date = expected_start_date
                if _text(day.get("date")) != expected_date:
                    self._failures.append(
                        _issue(
                            "DATE_SEQUENCE_MISMATCH",
                            f"{path}.date",
                            "每日日期必须从出发日期连续递增",
                            actual=day.get("date"),
                            expected=expected_date,
                        )
                    )
            if not expected_start_date and (day.get("date") or day.get("weekday")):
                self._failures.append(
                    _issue(
                        "UNREQUESTED_DATE",
                        path,
                        "用户未指定日期时，每日日期和星期必须留空",
                        actual={
                            "date": day.get("date"),
                            "weekday": day.get("weekday"),
                        },
                        expected={"date": None, "weekday": None},
                        allowed_actions=["clear_unrequested_dates"],
                    )
                )
            if day.get("date"):
                try:
                    date.fromisoformat(_text(day.get("date")))
                except ValueError:
                    self._failures.append(
                        _issue(
                            "INVALID_DATE", f"{path}.date", "日期必须使用 YYYY-MM-DD"
                        )
                    )

            day_start, day_end = (
                _minutes(day.get("start_time")),
                _minutes(day.get("end_time")),
            )
            if (
                day_index == 0
                and _text(arrival.get("time"))
                and day_start is not None
                and _minutes(arrival.get("time")) is not None
                and day_start < int(_minutes(arrival.get("time")) or 0)
            ):
                self._failures.append(
                    _issue(
                        "ACTIVITY_BEFORE_ARRIVAL",
                        f"{path}.start_time",
                        "首日活动不能早于抵达时间",
                        actual=day.get("start_time"),
                        expected=arrival.get("time"),
                    )
                )
            if (
                day_index == len(days) - 1
                and _text(departure.get("time"))
                and day_end is not None
                and _minutes(departure.get("time")) is not None
                and day_end > int(_minutes(departure.get("time")) or 0)
            ):
                self._failures.append(
                    _issue(
                        "ACTIVITY_AFTER_DEPARTURE",
                        f"{path}.end_time",
                        "末日活动不能晚于返程时间",
                        actual=day.get("end_time"),
                        expected=departure.get("time"),
                    )
                )
            if day_start is None or day_end is None or day_start >= day_end:
                self._failures.append(
                    _issue("INVALID_DAY_WINDOW", path, "每日开始和结束时间无效")
                )
            if (
                requested_start is not None
                and day_start is not None
                and day_start < requested_start
            ):
                self._failures.append(
                    _issue(
                        "DAILY_START_VIOLATION",
                        f"{path}.start_time",
                        "开始时间早于用户允许时段",
                        actual=day.get("start_time"),
                        expected=window.get("start"),
                    )
                )
            if (
                requested_end is not None
                and day_end is not None
                and day_end > requested_end
            ):
                self._failures.append(
                    _issue(
                        "DAILY_END_VIOLATION",
                        f"{path}.end_time",
                        "结束时间晚于用户允许时段",
                        actual=day.get("end_time"),
                        expected=window.get("end"),
                    )
                )

            start_anchor = (
                day.get("start_anchor")
                if isinstance(day.get("start_anchor"), dict)
                else {}
            )
            end_anchor = (
                day.get("end_anchor") if isinstance(day.get("end_anchor"), dict) else {}
            )
            hotel_loop_issue = None
            if not _text(start_anchor.get("name")) or not _text(end_anchor.get("name")):
                hotel_loop_issue = _issue(
                    "HOTEL_LOOP_MISSING", path, "每日缺少明确起终点"
                )
            elif hotel_name and (
                not matches_hotel_anchor(start_anchor, hotel)
                or not matches_hotel_anchor(end_anchor, hotel)
            ):
                hotel_loop_issue = _issue(
                    "HOTEL_LOOP_MISMATCH",
                    path,
                    "每日起终点与建议住宿锚点不一致",
                    expected=hotel.get("name"),
                )
            if hotel_loop_issue:
                (
                    self._failures
                    if context.get("hotel_area")
                    else self._warnings
                ).append(hotel_loop_issue)
            missing_anchor_location = not start_anchor.get(
                "location"
            ) or not end_anchor.get("location")
            if missing_anchor_location:
                self._warnings.append(
                    _warning(
                        "ANCHOR_ROUTE_UNVERIFIED",
                        path,
                        (
                            "住宿锚点未绑定地图坐标，首尾路线暂未核验"
                            if context.get("hotel_area")
                            else "住宿为未解析区域锚点，首尾路线无法精确核验"
                        ),
                    )
                )

            schedule = [
                item for item in day.get("schedule", []) if isinstance(item, dict)
            ]
            if not schedule:
                self._failures.append(
                    _issue("EMPTY_SCHEDULE", f"{path}.schedule", "每天至少需要一项活动")
                )
            physical = []
            previous_end: int | None = None
            for item_index, item in enumerate(schedule):
                item_path = f"{path}.schedule[{item_index}]"
                start, end = _minutes(item.get("start")), _minutes(item.get("end"))
                if start is None or end is None or start >= end:
                    self._failures.append(
                        _issue("INVALID_ACTIVITY_TIME", item_path, "活动时间无效")
                    )
                    continue
                if previous_end is not None and start < previous_end:
                    self._failures.append(
                        _issue("TIME_OVERLAP", item_path, "活动时间与上一项重叠")
                    )
                previous_end = end
                declared_duration = int(item.get("duration_minutes") or 0)
                if abs(declared_duration - (end - start)) > 1:
                    self._warnings.append(
                        _warning(
                            "DURATION_ESTIMATE_ADJUSTED",
                            f"{item_path}.duration_minutes",
                            "建议停留时长与展示时段不同，以当天节奏灵活调整",
                        )
                    )
                if item.get("type") in {"visit", "meal"}:
                    required_place = any(
                        _matches_key(requested, _key(item.get("name")))
                        for requested in (
                            _key(value) for value in context.get("must_visits") or []
                        )
                    )
                    if (
                        not item.get("place_id")
                        or not item.get("location")
                        or item.get("source") != "amap"
                    ):
                        self._warnings.append(
                            _warning(
                                "UNRESOLVED_ENTITY",
                                item_path,
                                (
                                    "用户指定的必去地点已保留，但地图服务未能绑定真实实体，"
                                    "坐标与路线需手动确认"
                                    if required_place
                                    else "可选地点没有绑定地图实体，已标记为待确认"
                                ),
                            )
                        )
                    else:
                        place_id = _text(item.get("place_id"))
                        if place_id in seen_places:
                            self._warnings.append(
                                _warning(
                                    "DUPLICATE_PLACE",
                                    item_path,
                                    f"同一 POI 重复出现；首次位于 {seen_places[place_id]}",
                                )
                            )
                        else:
                            seen_places[place_id] = item_path
                    if item.get("opening_match") == "risk":
                        self._warnings.append(
                            _warning(
                                "OPENING_CONFLICT",
                                item_path,
                                "建议到访时段可能与已知开放信息冲突，出发前请按官方信息调整",
                            )
                        )
                    elif item.get("opening_match") == "unknown":
                        self._warnings.append(
                            _warning(
                                "OPENING_UNVERIFIED",
                                item_path,
                                "开放时间未知，交付时必须明确提示",
                            )
                        )
                    physical.append((item_index, item, start, end))

            valid_schedule = [
                item
                for item in schedule
                if _minutes(item.get("start")) is not None
                and _minutes(item.get("end")) is not None
            ]
            spans_lunch = bool(
                valid_schedule
                and _minutes(valid_schedule[0].get("start")) <= 11 * 60 + 30
                and _minutes(valid_schedule[-1].get("end")) >= 13 * 60 + 30
            )
            has_lunch = any(
                (
                    item.get("type") == "meal"
                    or any(
                        marker in _text(item.get("name"))
                        for marker in ("午餐", "午饭", "用餐")
                    )
                )
                and (_minutes(item.get("end")) or 0) > 11 * 60 + 30
                and (_minutes(item.get("start")) or 24 * 60) < 14 * 60
                for item in valid_schedule
            )
            if spans_lunch and not has_lunch:
                self._warnings.append(
                    _warning(
                        "MEAL_BREAK_SUGGESTED",
                        f"{path}.schedule",
                        "行程跨越午餐时段，可按现场情况插入用餐或休息",
                    )
                )

            route_chain = list(physical)
            if start_anchor.get("location") and day_start is not None:
                route_chain.insert(
                    0,
                    (-1, start_anchor, day_start, day_start),
                )
            if end_anchor.get("location") and day_end is not None:
                route_chain.append(
                    (len(schedule), end_anchor, day_end, day_end),
                )
            self._validate_transfers(path, route_chain, day.get("transfers"))

    def _validate_transfers(
        self,
        day_path: str,
        physical: list[tuple[int, dict[str, Any], int, int]],
        raw_transfers: Any,
    ) -> None:
        transfers = [item for item in raw_transfers or [] if isinstance(item, dict)]
        for edge_index, (left, right) in enumerate(zip(physical, physical[1:])):
            _, origin, _, origin_end = left
            _, destination, destination_start, _ = right
            if origin.get("location") == destination.get("location"):
                continue
            transfer = next(
                (
                    item
                    for item in transfers
                    if _key(item.get("from_name")) == _key(origin.get("name"))
                    and _key(item.get("to_name")) == _key(destination.get("name"))
                ),
                None,
            )
            edge_path = f"{day_path}.transfers[{edge_index}]"
            if (
                not transfer
                or transfer.get("source") != "amap"
                or not transfer.get("evidence_hash")
            ):
                self._warnings.append(
                    _warning(
                        "MISSING_ROUTE_EVIDENCE",
                        edge_path,
                        f"{origin.get('name')}到{destination.get('name')}的路线暂未核验",
                    )
                )
                continue
            duration = int(transfer.get("duration_minutes") or 0)
            mode = _text(transfer.get("mode"))
            buffer_minutes = (
                10 if mode == "transit" else 5 if mode in {"driving", "taxi"} else 0
            )
            if (
                duration <= 0
                or origin_end + duration + buffer_minutes > destination_start
            ):
                self._warnings.append(
                    _warning(
                        "TIGHT_TRANSFER",
                        edge_path,
                        "地图参考通勤时间可能挤压相邻活动，建议当天灵活缩短停留或顺延",
                    )
                )
                continue
            transfer_start = _minutes(transfer.get("start"))
            transfer_end = _minutes(transfer.get("end"))
            if (
                transfer_start is None
                or transfer_end is None
                or transfer_start < origin_end
                or transfer_end > destination_start
                or transfer_end - transfer_start < duration
            ):
                self._warnings.append(
                    _warning(
                        "TRANSFER_TIME_ESTIMATED",
                        edge_path,
                        "通勤时段与地图参考耗时未完全对齐，实际以实时导航为准",
                    )
                )
