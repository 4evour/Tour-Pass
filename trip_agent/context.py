from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


_LABELS = {
    "目的地": "destination",
    "途经城市": "destinations",
    "出发日期": "start_date",
    "住宿地点或区域": "hotel_area",
    "住宿地点": "hotel_area",
    "住宿区域": "hotel_area",
    "住宿偏好": "hotel_preferences",
    "同行人": "travelers",
    "旅行节奏": "pace",
    "主要交通方式": "transport",
    "城际交通偏好": "intercity_preferences",
    "预算偏好": "budget",
    "必去地点": "must_visits",
    "饮食要求": "dietary_requirements",
    "行动需求": "mobility_needs",
    "预订偏好": "booking_preferences",
    "其他要求": "notes",
    "感兴趣的体验": "interests",
}


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    history_messages: int = 6
    message_chars: int = 4000
    plan_days: int = 30
    schedule_items_per_day: int = 8
    evidence_places: int = 40
    evidence_routes: int = 40

    def __post_init__(self) -> None:
        limits = {
            "history_messages": (0, 12),
            "message_chars": (160, 12000),
            "plan_days": (1, 30),
            "schedule_items_per_day": (2, 12),
            "evidence_places": (6, 80),
            "evidence_routes": (6, 40),
        }
        for name, (minimum, maximum) in limits.items():
            object.__setattr__(
                self,
                name,
                max(minimum, min(int(getattr(self, name)), maximum)),
            )

    def as_dict(self) -> dict[str, int]:
        return {
            "history_messages": self.history_messages,
            "message_chars": self.message_chars,
            "plan_days": self.plan_days,
            "schedule_items_per_day": self.schedule_items_per_day,
            "evidence_places": self.evidence_places,
            "evidence_routes": self.evidence_routes,
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _split_values(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[、,，/]+", value) if item.strip()]

def _split_must_visits(value: str) -> list[str]:
    result: list[str] = []
    for item in _split_values(value):
        conjunction = re.fullmatch(r"(.{2,})和(.{2,})", item)
        if conjunction:
            result.extend(
                part.strip() for part in conjunction.groups() if part.strip()
            )
        else:
            result.append(item)
    return result


_DAY_DIGITS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _day_count(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        return _DAY_DIGITS.get(left, 1) * 10 + _DAY_DIGITS.get(right, 0)
    return _DAY_DIGITS.get(value, 0)


_DAY_TOKEN = r"(?:[1-9]\d*|[一二两三四五六七八九十]+)"


def _clip(value: Any, limit: int) -> str:
    content = " ".join(_text(value).split())
    if len(content) <= limit:
        return content
    head = max(1, limit * 2 // 3)
    return f"{content[:head]}…{content[-(limit - head - 1) :]}"


def compact_conversation_history(
    history: list[dict[str, str]] | None,
    policy: MemoryPolicy,
) -> list[dict[str, str]]:
    """Keep only recent dialogue needed to interpret the current request."""
    eligible = [
        {
            "role": item.get("role", ""),
            "content": _clip(item.get("content"), policy.message_chars),
        }
        for item in history or []
        if item.get("role") in {"user", "assistant"} and _text(item.get("content"))
    ]
    return eligible[-policy.history_messages :] if policy.history_messages else []


def compact_planning_context(context: dict[str, Any]) -> dict[str, Any]:
    """Return user constraints, including the raw requests that carry nuance."""
    result: dict[str, Any] = {}
    for key in (
        "schema_version",
        "destination",
        "destinations",
        "days",
        "nights",
        "start_date",
        "arrival",
        "departure",
        "hotel_area",
        "hotel_preferences",
        "travelers",
        "party",
        "pace",
        "transport",
        "intercity_preferences",
        "budget",
        "budget_range",
        "notes",
        "dietary_requirements",
        "mobility_needs",
        "booking_preferences",
        "daily_window",
        "revision",
    ):
        value = context.get(key)
        if value not in (None, "", [], {}):
            result[key] = (
                _clip(value, 4000) if isinstance(value, str) else deepcopy(value)
            )
    for key in (
        "must_visits",
        "interests",
        "dietary_requirements",
        "mobility_needs",
        "intercity_preferences",
    ):
        values = context.get(key)
        if isinstance(values, list):
            result[key] = [_clip(value, 160) for value in values[:60] if _text(value)]
    raw_requests = context.get("freeform_requests")
    if isinstance(raw_requests, list):
        result["freeform_requests"] = [
            _clip(value, 4000) for value in raw_requests[-6:] if _text(value)
        ]
    return result


def _compact_anchor(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: deepcopy(value.get(key))
        for key in ("name", "type", "place_id", "location", "source", "status")
        if value.get(key) not in (None, "", [], {})
    }


def _compact_reservation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = {
        key: deepcopy(value.get(key))
        for key in ("required", "status")
        if value.get(key) is not None
    }
    if value.get("note"):
        result["note"] = _clip(value["note"], 160)
    return result


def compact_plan_memory(
    plan: dict[str, Any] | None,
    policy: MemoryPolicy,
) -> dict[str, Any] | None:
    """Summarize an accepted plan without replaying its full evidence and prose."""
    if not isinstance(plan, dict):
        return None
    profile = (
        plan.get("trip_profile") if isinstance(plan.get("trip_profile"), dict) else {}
    )
    hotel = plan.get("hotel") if isinstance(plan.get("hotel"), dict) else {}
    raw_days = plan.get("days") if isinstance(plan.get("days"), list) else []
    compact_profile = {
        key: deepcopy(profile.get(key))
        for key in ("days", "pace", "transport_preference", "travelers")
        if profile.get(key) not in (None, "", [], {})
    }
    preferences = profile.get("preferences")
    if isinstance(preferences, list):
        compact_profile["preferences"] = [
            _clip(value, 120) for value in preferences[:20] if _text(value)
        ]
    memory: dict[str, Any] = {
        "city": _clip(plan.get("city"), 80),
        "title": _clip(plan.get("title"), 160),
        "date_range": deepcopy(plan.get("date_range") or {}),
        "trip_profile": compact_profile,
        "hotel": {
            key: deepcopy(hotel.get(key))
            for key in ("name", "place_id", "area", "location", "status")
            if hotel.get(key) not in (None, "", [], {})
        },
        "days": [],
        "warnings": [
            _clip(value, 240)
            for value in (plan.get("warnings") or [])[:5]
            if _text(value)
        ],
    }
    truncated_items = False
    for raw_day in raw_days[: policy.plan_days]:
        if not isinstance(raw_day, dict):
            continue
        schedule = (
            raw_day.get("schedule") if isinstance(raw_day.get("schedule"), list) else []
        )
        transfers = (
            raw_day.get("transfers")
            if isinstance(raw_day.get("transfers"), list)
            else []
        )
        risks = raw_day.get("risks") if isinstance(raw_day.get("risks"), list) else []
        truncated_items = (
            truncated_items or len(schedule) > policy.schedule_items_per_day
        )
        day_memory = {
            key: deepcopy(raw_day.get(key))
            for key in (
                "day",
                "date",
                "weekday",
                "theme",
                "start_time",
                "end_time",
                "area_cluster",
            )
            if raw_day.get(key) not in (None, "", [], {})
        }
        if raw_day.get("summary"):
            day_memory["summary"] = _clip(raw_day["summary"], 240)
        for key in ("start_anchor", "end_anchor"):
            anchor = _compact_anchor(raw_day.get(key))
            if anchor:
                day_memory[key] = anchor
        day_memory["schedule"] = []
        for item in schedule[: policy.schedule_items_per_day]:
            if not isinstance(item, dict):
                continue
            compact_item = {
                key: deepcopy(item.get(key))
                for key in (
                    "period",
                    "type",
                    "start",
                    "end",
                    "duration_minutes",
                    "place_id",
                    "name",
                    "opening_match",
                )
                if item.get(key) not in (None, "", [], {})
            }
            if item.get("reason"):
                compact_item["reason"] = _clip(item["reason"], 240)
            reservation = _compact_reservation(item.get("reservation"))
            if reservation:
                compact_item["reservation"] = reservation
            day_memory["schedule"].append(compact_item)
        day_memory["transfers"] = [
            {
                key: deepcopy(item.get(key))
                for key in (
                    "from_name",
                    "to_name",
                    "mode",
                    "start",
                    "end",
                    "duration_minutes",
                    "distance_meters",
                    "source",
                    "evidence_hash",
                )
                if item.get(key) not in (None, "", [], {})
            }
            for item in transfers[: policy.schedule_items_per_day + 1]
            if isinstance(item, dict)
        ]
        day_memory["risks"] = [
            {
                key: (
                    _clip(item.get(key), 240)
                    if key in {"detail", "mitigation"}
                    else deepcopy(item.get(key))
                )
                for key in ("level", "type", "title", "detail", "mitigation")
                if item.get(key) not in (None, "", [], {})
            }
            for item in risks[:4]
            if isinstance(item, dict)
        ]
        memory["days"].append(day_memory)
    memory["memory_limits"] = {
        "source_days": len(raw_days),
        "included_days": len(memory["days"]),
        "items_truncated": truncated_items,
    }
    return memory


def compact_repair_memory(
    repair_context: dict[str, Any] | None,
    policy: MemoryPolicy,
) -> dict[str, Any] | None:
    if not isinstance(repair_context, dict):
        return None
    report = (
        repair_context.get("validation_report")
        if isinstance(repair_context.get("validation_report"), dict)
        else {}
    )

    def issues(name: str) -> list[dict[str, Any]]:
        values = report.get(name) if isinstance(report.get(name), list) else []
        return [
            {
                key: (
                    _clip(item.get(key), 360)
                    if isinstance(item.get(key), str)
                    else deepcopy(item.get(key))
                )
                for key in (
                    "code",
                    "path",
                    "message",
                    "actual",
                    "expected",
                    "allowed_actions",
                    "suggested_action",
                )
                if item.get(key) not in (None, "", [], {})
            }
            for item in values[:6]
            if isinstance(item, dict)
        ]

    return {
        "candidate_plan_digest": compact_plan_memory(
            repair_context.get("candidate_plan"),
            policy,
        ),
        "validation_report": {
            "hard_failures": issues("hard_failures"),
            "warnings": issues("warnings"),
            "review_issues": issues("review_issues"),
            "repairs_remaining": report.get("repairs_remaining"),
        },
    }


def _derive_from_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {}
    existing = plan.get("planning_context")
    if isinstance(existing, dict):
        return deepcopy(existing)
    profile = (
        plan.get("trip_profile") if isinstance(plan.get("trip_profile"), dict) else {}
    )
    hotel = plan.get("hotel") if isinstance(plan.get("hotel"), dict) else {}
    days = plan.get("days") if isinstance(plan.get("days"), list) else []
    duration = plan.get("duration") if isinstance(plan.get("duration"), dict) else {}
    return {
        "schema_version": 2,
        "destination": _text(plan.get("city")),
        "destinations": deepcopy(plan.get("destinations") or []),
        "days": int(profile.get("days") or duration.get("days") or len(days) or 0),
        "nights": int(duration.get("nights") or max(len(days) - 1, 0)),
        "start_date": _text((plan.get("date_range") or {}).get("start")),
        "arrival": deepcopy(plan.get("arrival") or {}),
        "departure": deepcopy(plan.get("departure") or {}),
        "hotel_area": _text(hotel.get("name") or hotel.get("area")),
        "hotel_preferences": "",
        "travelers": _text(profile.get("travelers")),
        "party": deepcopy(plan.get("party") or {}),
        "pace": _text(profile.get("pace")),
        "transport": _text(profile.get("transport_preference")),
        "intercity_preferences": [],
        "budget": _text(profile.get("budget")),
        "budget_range": {},
        "must_visits": [],
        "notes": "",
        "interests": list(profile.get("preferences") or []),
        "dietary_requirements": [],
        "mobility_needs": [],
        "booking_preferences": "",
        "freeform_requests": [],
        "daily_window": {"start": "", "end": ""},
    }


def build_planning_context(
    previous_plan: dict[str, Any] | None,
    current_message: str,
    history: list[dict[str, str]] | None = None,
    structured_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge explicit fields and raw conversation into one durable planning brief."""
    context = _derive_from_plan(previous_plan)
    context["schema_version"] = 2
    for key in (
        "destinations",
        "must_visits",
        "interests",
        "intercity_preferences",
        "dietary_requirements",
        "mobility_needs",
        "freeform_requests",
    ):
        context.setdefault(key, [])
    previous_revision = int(context.get("revision") or 0)
    if not previous_revision and history:
        previous_revision = sum(item.get("role") == "user" for item in history)
    context.setdefault("daily_window", {"start": "", "end": ""})

    def destination_list(value: str) -> list[str]:
        parts = re.split(
            r"\s*(?:、|，|,|＋|\+|→|—>|->|再去|然后去|最后去|到)\s*",
            value,
        )
        cleaned = []
        for part in parts:
            name = re.sub(
                r"^(?:(?:\d{1,2})?日的|从|先去|去|到|途经|目的地(?:是|为)?|的)",
                "",
                part.strip(),
            )
            name = re.sub(r"(?:游玩|旅行|旅游|玩)$", "", name).strip()
            if 2 <= len(name) <= 40 and re.fullmatch(r"[\u4e00-\u9fffA-Za-z·\s]+", name):
                cleaned.append(name)
        return list(dict.fromkeys(cleaned))

    def apply(message: str) -> None:
        message = _text(message)
        if not message:
            return
        requests = list(context.get("freeform_requests") or [])
        if message not in requests:
            requests.append(message)
        context["freeform_requests"] = requests[-8:]

        day_pattern = f"({_DAY_TOKEN})"
        multi_match = re.search(
            rf"((?:[\u4e00-\u9fffA-Za-z·]{{2,20}})"
            rf"(?:\s*(?:、|，|,|＋|\+|→|—>|->|再去|然后去|最后去|到)\s*"
            rf"[\u4e00-\u9fffA-Za-z·]{{2,20}})+)"
            rf"(?:游玩|旅行|旅游|玩)?\s*{day_pattern}\s*天",
            message,
        )
        if multi_match:
            names = destination_list(multi_match.group(1))
            if len(names) > 1:
                context["destinations"] = [{"name": name} for name in names]
                context["destination"] = "、".join(names)
                context["days"] = _day_count(multi_match.group(2))

        request_match = re.search(
            rf"(?:请)?(?:为我)?规划\s*([\u4e00-\u9fff]{{2,20}}?)"
            rf"\s*{day_pattern}\s*天(?:行程)?",
            message,
        )
        travel_match = re.search(
            rf"(?:想|要|准备|计划|打算|希望)?(?:去|到)"
            rf"([\u4e00-\u9fff]{{2,10}}?)(?:玩|游玩|旅游|旅行|逛|待)?"
            rf"\s*{day_pattern}\s*天",
            message,
        )
        compact_match = re.search(
            rf"(?:^|[，,；;。\s])([\u4e00-\u9fff]{{2,10}}?)"
            rf"(?:玩|游玩|旅游|旅行)?\s*{day_pattern}\s*天",
            message,
        )
        trip_match = request_match or travel_match or compact_match
        if trip_match and not multi_match:
            destination = trip_match.group(1).strip()
            context["destination"] = destination
            context["destinations"] = [{"name": destination}]
            context["days"] = _day_count(trip_match.group(2))
        elif not multi_match:
            destination_match = re.search(
                r"(?:想|要|准备|计划|打算|希望|我要)?(?:去|到)"
                r"([\u4e00-\u9fffA-Za-z·]{2,20}?)"
                r"(?:游玩|旅游|旅行|逛|待|玩)?"
                r"(?:一圈|看看|走走)?(?:[，,。；;\s]|$)",
                message,
            )
            if destination_match and not context.get("destination"):
                destination = destination_match.group(1).strip()
                context["destination"] = destination
                context["destinations"] = [{"name": destination}]
            days_match = re.search(
                rf"(?:改成|调整为|规划|安排)?\s*{day_pattern}\s*天", message
            )
            if days_match:
                context["days"] = _day_count(days_match.group(1))

        date_match = re.search(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日"
            r"\s*(?:至|到|—|-)\s*"
            r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日",
            message,
        )
        if date_match:
            context["start_date"] = (
                f"{int(date_match.group(1)):04d}-"
                f"{int(date_match.group(2)):02d}-"
                f"{int(date_match.group(3)):02d}"
            )

        nights_match = re.search(rf"({_DAY_TOKEN})\s*晚", message)
        if nights_match:
            context["nights"] = _day_count(nights_match.group(1))

        list_keys = {
            "must_visits",
            "interests",
            "intercity_preferences",
            "dietary_requirements",
            "mobility_needs",
        }
        for segment in re.split(r"[；;。\n]", message):
            if "：" not in segment and ":" not in segment:
                continue
            parts = re.split(r"[：:]", segment, maxsplit=1)
            if len(parts) != 2:
                continue
            label, value = parts[0].strip(), parts[1].strip()
            key = next(
                (target for name, target in _LABELS.items() if label.endswith(name)),
                None,
            )
            if not key or not value:
                continue
            if key == "destinations":
                names = destination_list(value)
                if names:
                    context[key] = [{"name": name} for name in names]
                    context["destination"] = "、".join(names)
            elif key in list_keys:
                context[key] = _split_values(value)
            else:
                context[key] = value

        hotel_match = re.search(
            r"(?:住宿地点或区域|住宿地点|住宿区域|住宿|住在?)(?:在|为)?"
            r"[：:\s]*([^，,；;。]{2,80})",
            message,
        )
        if hotel_match:
            hotel_area = hotel_match.group(1).strip()
            if not re.fullmatch(rf"{_DAY_TOKEN}\s*晚.*", hotel_area):
                context["hotel_area"] = hotel_area

        if any(marker in message for marker in ("不要太赶", "轻松一点", "节奏轻松")):
            context["pace"] = "relaxed"
        elif any(marker in message for marker in ("行程紧凑", "多安排一些", "特种兵")):
            context["pace"] = "intensive"
        elif any(marker in message for marker in ("节奏均衡", "节奏适中", "整体均衡")):
            context["pace"] = "balanced"
        if any(
            marker in message
            for marker in (
                "公共交通为主",
                "公交地铁为主",
                "公共交通+短途打车",
                "公共交通加短途打车",
                "公共交通和短途打车",
            )
        ):
            context["transport"] = "public_transit"
        elif "打车为主" in message:
            context["transport"] = "taxi"
        elif "步行为主" in message:
            context["transport"] = "walking"
        elif "自驾" in message:
            context["transport"] = "driving"

        must_visit_groups = re.findall(
            r"(?:[\u4e00-\u9fff]{0,8})?必去(?:地点)?[：:\s]*"
            r"([^；;。]{2,600}?)(?=[，,](?:想|希望|不|每天|每日|请)|[；;。]|$)",
            message,
        )
        if must_visit_groups:
            context["must_visits"] = list(
                dict.fromkeys(
                    visit
                    for group in must_visit_groups
                    for visit in _split_must_visits(group)
                )
            )
        elif wish_matches := re.findall(
            r"(?:，|,|；|;)\s*想去([^，,；;。]{2,200})",
            message,
        ):
            context["must_visits"] = _split_must_visits(wish_matches[-1])

        window = re.search(
            r"(?:每日游玩时段[：:]\s*)?"
            r"(\d{1,2}:\d{2}|不限)\s*至\s*(\d{1,2}:\d{2}|不限)",
            message,
        )
        if window:
            context["daily_window"] = {
                "start": "" if window.group(1) == "不限" else window.group(1),
                "end": "" if window.group(2) == "不限" else window.group(2),
            }
        elif natural_window := re.search(
            r"每天.{0,16}?(\d{1,2})点(?:左右)?(?:出门|开始)"
            r".{0,24}?(\d{1,2})点(?:前)?(?:回|结束)",
            message,
        ):
            context["daily_window"] = {
                "start": f"{int(natural_window.group(1)):02d}:00",
                "end": f"{int(natural_window.group(2)):02d}:00",
            }

        budget_match = re.search(
            r"(?:总预算|(?<!人均)预算)\s*(?:约|大约|控制在)?\s*(\d{3,8})\s*元",
            message,
        )
        per_person_match = re.search(
            r"人均\s*(?:预算)?\s*(?:约)?\s*(\d{2,7})\s*元", message
        )
        if budget_match or per_person_match:
            budget_range = dict(context.get("budget_range") or {})
            if budget_match:
                budget_range["total_max"] = int(budget_match.group(1))
            if per_person_match:
                budget_range["per_person"] = int(per_person_match.group(1))
            budget_range.setdefault("currency", "CNY")
            context["budget_range"] = budget_range

        adults = re.search(
            rf"({_DAY_TOKEN})\s*(?:名|位)[^，,。；;]{{0,24}}?成人",
            message,
        )
        child_clauses = [
            segment
            for segment in re.split(r"[，,。；;]", message)
            if any(marker in segment for marker in ("儿童", "孩子", "小孩"))
        ]
        children = [
            age
            for segment in child_clauses
            for age in re.findall(r"(\d+)\s*岁", segment)
        ]
        seniors = re.search(rf"({_DAY_TOKEN})\s*(?:名|位)?老人", message)
        rooms = re.search(rf"({_DAY_TOKEN})\s*间房", message)
        if adults or children or seniors or rooms:
            party = dict(context.get("party") or {})
            if adults:
                party["adults"] = _day_count(adults.group(1))
            if children:
                party["children_ages"] = [int(age) for age in children]
            if seniors:
                party["seniors"] = _day_count(seniors.group(1))
            if rooms:
                party["rooms"] = _day_count(rooms.group(1))
            context["party"] = party

        endpoint_markers = {
            "arrival": ("抵达", "到达", "落地"),
            "departure": ("返程", "离开", "返回"),
        }
        for kind, markers in endpoint_markers.items():
            marker_pattern = "|".join(markers)
            match = re.search(
                rf"(\d{{1,2}}):(\d{{2}})[^，,。；;]{{0,30}}(?:{marker_pattern})",
                message,
            ) or re.search(
                rf"(?:{marker_pattern})[^，,。；;]{{0,30}}"
                rf"(\d{{1,2}}):(\d{{2}})",
                message,
            )
            if not match:
                continue
            endpoint = dict(context.get(kind) or {})
            endpoint["time"] = f"{int(match.group(1)):02d}:{match.group(2)}"
            context[kind] = endpoint

    if not previous_plan:
        for historical in history or []:
            if historical.get("role") == "user":
                apply(historical.get("content", ""))
    apply(current_message)
    if structured_request is not None:
        date_range = (
            structured_request.get("date_range")
            if isinstance(structured_request.get("date_range"), dict)
            else {}
        )
        daily_window = (
            structured_request.get("daily_window")
            if isinstance(structured_request.get("daily_window"), dict)
            else {}
        )
        requested_days = structured_request.get("days")
        context.update(
            {
                "destination": _text(structured_request.get("destination")),
                "destinations": deepcopy(
                    structured_request.get("destinations") or context["destinations"]
                ),
                "days": (
                    int(requested_days)
                    if requested_days not in (None, "")
                    else None
                ),
                "nights": structured_request.get("nights"),
                "start_date": _text(
                    date_range.get("start") or structured_request.get("start_date")
                ),
                "arrival": deepcopy(structured_request.get("arrival") or {}),
                "departure": deepcopy(structured_request.get("departure") or {}),
                "hotel_area": _text(structured_request.get("hotel_area")),
                "hotel_preferences": _text(
                    structured_request.get("hotel_preferences")
                ),
                "travelers": _text(
                    structured_request.get("travellers")
                    or structured_request.get("travelers")
                ),
                "party": deepcopy(structured_request.get("party") or {}),
                "pace": _text(structured_request.get("pace")),
                "transport": _text(
                    structured_request.get("transport_preference")
                    or structured_request.get("transport")
                ),
                "intercity_preferences": list(
                    structured_request.get("intercity_preferences") or []
                ),
                "budget": _text(structured_request.get("budget")),
                "budget_range": deepcopy(
                    structured_request.get("budget_range") or {}
                ),
                "must_visits": list(structured_request.get("must_visits") or []),
                "notes": _text(structured_request.get("notes")),
                "interests": list(structured_request.get("interests") or []),
                "dietary_requirements": list(
                    structured_request.get("dietary_requirements") or []
                ),
                "mobility_needs": list(
                    structured_request.get("mobility_needs") or []
                ),
                "booking_preferences": _text(
                    structured_request.get("booking_preferences")
                ),
                "daily_window": {
                    "start": _text(
                        daily_window.get("start") or structured_request.get("day_start")
                    ),
                    "end": _text(
                        daily_window.get("end") or structured_request.get("day_end")
                    ),
                },
            }
        )
    raw_destinations = [
        item
        for item in context.get("destinations") or []
        if isinstance(item, dict)
        and _text(item.get("destination") or item.get("name"))
    ]
    explicit_days = (
        int(context["days"]) if context.get("days") not in (None, "") else None
    )
    if raw_destinations:
        normalized_destinations = [
            {
                "destination": _text(item.get("destination") or item.get("name")),
                "days": int(item.get("days") or 0),
                "hotel_area": _text(item.get("hotel_area")) or None,
                "notes": _text(item.get("notes")) or None,
            }
            for item in raw_destinations
        ]
        assigned = sum(item["days"] for item in normalized_destinations)
        if explicit_days is None and assigned:
            context["days"] = assigned
            explicit_days = assigned
        context["destinations"] = normalized_destinations
        context["destination"] = "、".join(
            item["destination"] for item in normalized_destinations
        )
    context["nights"] = (
        max(explicit_days - 1, 0)
        if explicit_days is not None and context.get("nights") in (None, "")
        else int(context["nights"])
        if context.get("nights") not in (None, "")
        else None
    )
    context["revision"] = previous_revision + 1
    context["latest_request"] = _text(current_message)
    return context
