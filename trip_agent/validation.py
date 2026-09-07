from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return re.sub(r"[\s·（）()\-—]", "", _text(value)).casefold()


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
    version: str = "hard-validator-v2"
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
                requested in name or name in requested for name in names if name
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
        hotel = plan.get("hotel") if isinstance(plan.get("hotel"), dict) else {}
        hotel_name = _key(hotel.get("name"))

        def matches_hotel_anchor(anchor: dict[str, Any]) -> bool:
            hotel_place_id = _text(hotel.get("place_id"))
            anchor_place_id = _text(anchor.get("place_id"))
            if hotel_place_id and anchor_place_id:
                return hotel_place_id == anchor_place_id
            hotel_location = _text(hotel.get("location"))
            anchor_location = _text(anchor.get("location"))
            if hotel_location and anchor_location:
                return hotel_location == anchor_location
            return hotel_name == _key(anchor.get("name"))

        window = (
            context.get("daily_window")
            if isinstance(context.get("daily_window"), dict)
            else {}
        )
        requested_start = _minutes(window.get("start"))
        requested_end = _minutes(window.get("end"))
        expected_start_date = _text(context.get("start_date"))

        for day_index, raw_day in enumerate(days):
            path = f"$.days[{day_index}]"
            if not isinstance(raw_day, dict):
                self._failures.append(_issue("INVALID_DAY", path, "每日行程必须是对象"))
                continue
            day = raw_day
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
            if (
                day_index == 0
                and expected_start_date
                and _text(day.get("date")) != expected_start_date
            ):
                self._failures.append(
                    _issue(
                        "START_DATE_MISMATCH",
                        f"{path}.date",
                        "首日日期与用户要求不一致",
                        actual=day.get("date"),
                        expected=expected_start_date,
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
            if not _text(start_anchor.get("name")) or not _text(end_anchor.get("name")):
                self._failures.append(
                    _issue("HOTEL_LOOP_MISSING", path, "每日必须有明确起终点")
                )
            elif hotel_name and (
                not matches_hotel_anchor(start_anchor)
                or not matches_hotel_anchor(end_anchor)
            ):
                self._failures.append(
                    _issue(
                        "HOTEL_LOOP_MISMATCH",
                        path,
                        "每日必须从住宿锚点出发并返回",
                        expected=hotel.get("name"),
                    )
                )
            missing_anchor_location = not start_anchor.get(
                "location"
            ) or not end_anchor.get("location")
            if missing_anchor_location and context.get("hotel_area"):
                self._failures.append(
                    _issue(
                        "ANCHOR_ROUTE_UNVERIFIED",
                        path,
                        "用户指定了住宿锚点，但首尾锚点没有绑定可核验坐标",
                        allowed_actions=[
                            "search_places",
                            "route",
                            "resolve_hotel_anchor",
                        ],
                    )
                )
            elif missing_anchor_location:
                self._warnings.append(
                    _warning(
                        "ANCHOR_ROUTE_UNVERIFIED",
                        path,
                        "住宿为未解析区域锚点，首尾路线无法精确核验",
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
                    self._failures.append(
                        _issue(
                            "DURATION_MISMATCH",
                            f"{item_path}.duration_minutes",
                            "停留时长与开始结束时间不一致",
                            actual=declared_duration,
                            expected=end - start,
                        )
                    )
                if item.get("type") in {"visit", "meal"}:
                    if (
                        not item.get("place_id")
                        or not item.get("location")
                        or item.get("source") != "amap"
                    ):
                        self._failures.append(
                            _issue(
                                "UNRESOLVED_ENTITY",
                                item_path,
                                "地点没有绑定 Provider 返回的真实实体",
                                allowed_actions=[
                                    "search_places",
                                    "place_detail",
                                    "replace_optional_stop",
                                ],
                            )
                        )
                    else:
                        place_id = _text(item.get("place_id"))
                        if place_id in seen_places:
                            self._failures.append(
                                _issue(
                                    "DUPLICATE_PLACE",
                                    item_path,
                                    "同一 POI 被重复安排",
                                    actual=item.get("name"),
                                    expected=f"仅出现一次；首次位于 {seen_places[place_id]}",
                                )
                            )
                        else:
                            seen_places[place_id] = item_path
                    if item.get("opening_match") == "risk":
                        self._failures.append(
                            _issue(
                                "OPENING_CONFLICT",
                                item_path,
                                "到访时间与已知开放时间冲突",
                                evidence_refs=[_text(item.get("place_id"))],
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
                self._failures.append(
                    _issue(
                        "MEAL_WINDOW_MISSING",
                        f"{path}.schedule",
                        "跨越午餐时段的完整行程必须显式安排午餐或用餐休息",
                        allowed_actions=["add_meal_or_break", "reschedule_activities"],
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
                self._failures.append(
                    _issue(
                        "MISSING_ROUTE_EVIDENCE",
                        edge_path,
                        f"{origin.get('name')}到{destination.get('name')}缺少真实路线证据",
                        allowed_actions=[
                            "route",
                            "change_day_order",
                            "remove_optional_stop",
                        ],
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
                self._failures.append(
                    _issue(
                        "ROUTE_TIME_CONFLICT",
                        edge_path,
                        "真实通勤时间及必要缓冲无法放入两个活动之间",
                        actual={
                            "gap_minutes": destination_start - origin_end,
                            "route_minutes": duration,
                            "buffer_minutes": buffer_minutes,
                        },
                        expected="gap_minutes >= route_minutes + buffer_minutes",
                        evidence_refs=[_text(transfer.get("evidence_hash"))],
                        allowed_actions=[
                            "move_activity_time",
                            "change_day_order",
                            "remove_optional_stop",
                        ],
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
                self._failures.append(
                    _issue(
                        "TRANSFER_TIMELINE_CONFLICT",
                        edge_path,
                        "通勤段起止时间与相邻活动或真实路线耗时不一致",
                        actual={
                            "origin_end": origin_end,
                            "transfer_start": transfer_start,
                            "transfer_end": transfer_end,
                            "destination_start": destination_start,
                            "route_minutes": duration,
                        },
                        expected="origin_end <= transfer_start < transfer_end <= destination_start，且通勤区间不少于真实路线耗时",
                        evidence_refs=[_text(transfer.get("evidence_hash"))],
                        allowed_actions=["align_transfer_timeline"],
                    )
                )
