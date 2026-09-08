from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


_LABELS = {
    "出发日期": "start_date",
    "住宿地点或区域": "hotel_area",
    "同行人": "travelers",
    "旅行节奏": "pace",
    "主要交通方式": "transport",
    "预算偏好": "budget",
    "必去地点": "must_visits",
    "其他要求": "notes",
    "感兴趣的体验": "interests",
}


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    history_messages: int = 4
    message_chars: int = 800
    plan_days: int = 7
    schedule_items_per_day: int = 8
    evidence_places: int = 24
    evidence_routes: int = 24

    def __post_init__(self) -> None:
        limits = {
            "history_messages": (0, 12),
            "message_chars": (160, 2400),
            "plan_days": (1, 7),
            "schedule_items_per_day": (2, 12),
            "evidence_places": (6, 40),
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
    """Return stable user constraints without duplicating the current request."""
    result: dict[str, Any] = {}
    for key in (
        "schema_version",
        "destination",
        "days",
        "start_date",
        "hotel_area",
        "travelers",
        "pace",
        "transport",
        "budget",
        "notes",
        "daily_window",
        "revision",
    ):
        value = context.get(key)
        if value not in (None, "", [], {}):
            result[key] = (
                _clip(value, 500) if isinstance(value, str) else deepcopy(value)
            )
    for key in ("must_visits", "interests"):
        values = context.get(key)
        if isinstance(values, list):
            result[key] = [_clip(value, 120) for value in values[:20] if _text(value)]
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
    return {
        "schema_version": 1,
        "destination": _text(plan.get("city")),
        "days": int(profile.get("days") or len(days) or 0),
        "start_date": _text((plan.get("date_range") or {}).get("start")),
        "hotel_area": _text(hotel.get("name") or hotel.get("area")),
        "travelers": _text(profile.get("travelers")),
        "pace": _text(profile.get("pace")),
        "transport": _text(profile.get("transport_preference")),
        "budget": "",
        "must_visits": [],
        "notes": "",
        "interests": list(profile.get("preferences") or []),
        "daily_window": {"start": "", "end": ""},
    }


def build_planning_context(
    previous_plan: dict[str, Any] | None,
    current_message: str,
    history: list[dict[str, str]] | None = None,
    structured_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge explicit requests onto the last accepted structured context."""
    context = _derive_from_plan(previous_plan)
    context.setdefault("schema_version", 1)
    context.setdefault("must_visits", [])
    context.setdefault("interests", [])
    previous_revision = int(context.get("revision") or 0)
    if not previous_revision and history:
        previous_revision = sum(item.get("role") == "user" for item in history)
    context.setdefault("daily_window", {"start": "", "end": ""})

    def apply(message: str) -> None:
        message = _text(message)
        day_pattern = f"({_DAY_TOKEN})"
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
        if trip_match:
            context["destination"] = trip_match.group(1).strip()
            context["days"] = _day_count(trip_match.group(2))
        else:
            days_match = re.search(
                rf"(?:改成|调整为|规划|安排)?\s*{day_pattern}\s*天", message
            )
            if days_match:
                context["days"] = _day_count(days_match.group(1))

        for segment in re.split(r"[；;。]", message):
            if "：" not in segment and ":" not in segment:
                continue
            parts = re.split(r"[：:]", segment, maxsplit=1)
            if len(parts) != 2:
                continue
            label = parts[0].strip()
            value = parts[1].strip()
            key = next(
                (target for name, target in _LABELS.items() if label.endswith(name)),
                None,
            )
            if not key or not value:
                continue
            context[key] = (
                _split_values(value) if key in {"must_visits", "interests"} else value
            )
        hotel_match = re.search(
            r"(?:住宿地点或区域|住宿地点|住宿区域|住宿|住在?)(?:在|为)?"
            r"[：:\s]*([^，,；;。]{2,30})",
            message,
        )
        if hotel_match:
            context["hotel_area"] = hotel_match.group(1).strip()

        must_visit_match = re.search(
            r"必去(?:地点)?[：:\s]*([^；;。]{2,100})",
            message,
        )
        if must_visit_match:
            context["must_visits"] = _split_values(must_visit_match.group(1))

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
        context.update(
            {
                "destination": _text(structured_request.get("destination")),
                "days": int(structured_request.get("days") or 3),
                "start_date": _text(
                    date_range.get("start") or structured_request.get("start_date")
                ),
                "hotel_area": _text(structured_request.get("hotel_area")),
                "travelers": _text(
                    structured_request.get("travellers")
                    or structured_request.get("travelers")
                ),
                "pace": _text(structured_request.get("pace")),
                "transport": _text(
                    structured_request.get("transport_preference")
                    or structured_request.get("transport")
                ),
                "budget": _text(structured_request.get("budget")),
                "must_visits": list(structured_request.get("must_visits") or []),
                "notes": _text(structured_request.get("notes")),
                "interests": list(structured_request.get("interests") or []),
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
    context["revision"] = previous_revision + 1
    context["latest_request"] = _text(current_message)
    return context
