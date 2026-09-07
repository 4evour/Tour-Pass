from __future__ import annotations

from typing import Any


def _string(*values: str) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if values:
        schema["enum"] = list(values)
    return schema


def _described_string(description: str, *values: str) -> dict[str, Any]:
    schema = _string(*values)
    schema["description"] = description
    return schema


def _integer(*, minimum: int = 0, maximum: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer", "minimum": minimum}
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def _boolean() -> dict[str, Any]:
    return {"type": "boolean"}


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _array(
    items: dict[str, Any],
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": items}
    if minimum is not None:
        schema["minItems"] = minimum
    if maximum is not None:
        schema["maxItems"] = maximum
    return schema


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


SEARCH_ARGUMENTS = _object(
    {
        "city": _described_string("目的地城市名称。"),
        "keywords": _described_string("要解析的一个地点、住宿锚点或餐饮需求关键词。"),
        "limit": _integer(minimum=1, maximum=10),
    }
)
PLACE_DETAIL_ARGUMENTS = _object({"place_id": _string()})
ROUTE_ARGUMENTS = _object(
    {
        "city": _described_string("路线所在城市。"),
        "origin": _described_string(
            "起点经度,纬度；也可传本次地点工具返回的 POI ID、准确名称或包含坐标的字符串。"
        ),
        "destination": _described_string(
            "终点经度,纬度；也可传本次地点工具返回的 POI ID、准确名称或包含坐标的字符串。"
        ),
        "mode": _described_string(
            "路线方式。",
            "driving",
            "walking",
            "transit",
        ),
    }
)
WEATHER_ARGUMENTS = _object(
    {
        "city": _string(),
        "days": _integer(minimum=1, maximum=7),
    }
)


def plan_schema() -> dict[str, Any]:
    nullable_string = _nullable(_string())
    date_range = _object({"start": nullable_string, "end": nullable_string})
    trip_profile = _object(
        {
            "days": _integer(minimum=1, maximum=30),
            "pace": _string("relaxed", "balanced", "intensive"),
            "transport_preference": _string(
                "public_transit", "driving", "walking", "mixed"
            ),
            "travelers": _string(),
            "preferences": _array(_string()),
            "assumptions": _array(_string()),
        }
    )
    hotel = _object(
        {
            "name": _string(),
            "area": _string(),
            "status": _string("confirmed", "recommended_area", "unknown"),
            "reason": _string(),
        }
    )
    candidate_area = _object(
        {
            "name": _string(),
            "highlights": _array(_string()),
            "tradeoffs": _array(_string()),
            "fit_score": _integer(minimum=0, maximum=100),
            "selected": _boolean(),
        }
    )
    candidate_comparison = _object(
        {
            "areas": _array(candidate_area, minimum=2, maximum=3),
            "selected_areas": _array(_string(), minimum=1, maximum=3),
            "selection_reason": _string(),
        }
    )
    anchor = _object(
        {
            "name": _string(),
            "type": _string("hotel", "area", "station", "place"),
        }
    )
    area_cluster = _object(
        {
            "primary_area": _string(),
            "secondary_areas": _array(_string()),
            "rationale": _string(),
        }
    )
    reservation = _object(
        {
            "required": _nullable(_boolean()),
            "status": _string("not_required", "recommended", "required", "unknown"),
            "note": nullable_string,
        }
    )
    schedule_item = _object(
        {
            "period": _string("morning", "lunch", "afternoon", "dinner", "evening"),
            "type": _string("visit", "meal", "hotel", "free_time"),
            "start": _described_string(
                "活动在地点实际开始的 HH:MM；必须晚于上一段通勤结束及执行缓冲，首个活动不得等于酒店出发时间。"
            ),
            "end": _described_string("活动在地点实际结束的 HH:MM。"),
            "name": _string(),
            "reason": _string(),
            "opening_match": _string("matched", "unknown", "risk"),
            "reservation": reservation,
            "practical_tips": _array(_string(), maximum=1),
        }
    )
    transfer = _object(
        {
            "from_name": _string(),
            "to_name": _string(),
            "mode": _string("walking", "transit", "driving", "taxi", "mixed"),
            "start": _described_string("通勤从上一活动或住宿锚点实际出发的 HH:MM。"),
            "end": _described_string("按工具路线耗时计算的实际抵达 HH:MM。"),
            "instructions": _string(),
        }
    )
    risk = _object(
        {
            "level": _string("info", "warning", "critical"),
            "type": _string(
                "weather", "opening", "reservation", "traffic", "walking", "other"
            ),
            "title": _string(),
            "detail": _string(),
            "mitigation": _string(),
            "source": _string("amap", "qweather", "model_judgment"),
            "evidence_hash": nullable_string,
        }
    )
    day = _object(
        {
            "day": _integer(minimum=1),
            "date": nullable_string,
            "weekday": nullable_string,
            "theme": _string(),
            "summary": _string(),
            "start_time": _string(),
            "end_time": _string(),
            "start_anchor": anchor,
            "end_anchor": anchor,
            "area_cluster": area_cluster,
            "schedule": _array(schedule_item, minimum=2, maximum=5),
            "transfers": _array(transfer),
            "risks": _array(risk, maximum=2),
        }
    )
    map_summary = _object({"route_overview": _string()})
    narrative = _object(
        {
            "headline": _string(),
            "summary": _string(),
            "highlights": _array(_string()),
            "tradeoffs": _array(_string()),
            "weather_advice": nullable_string,
        }
    )
    return _object(
        {
            "city": _string(),
            "title": _string(),
            "overview": _string(),
            "date_range": date_range,
            "trip_profile": trip_profile,
            "hotel": hotel,
            "candidate_comparison": candidate_comparison,
            "days": _array(day, minimum=1, maximum=30),
            "map": map_summary,
            "narrative": narrative,
            "warnings": _array(_string(), maximum=3),
        }
    )


def planner_tools(*, allow_submit: bool = True) -> list[dict[str, Any]]:
    definitions = [
        (
            "search_places",
            "搜索指定城市中的真实地点候选；名称不明确或需要挑选分店时先调用。",
            SEARCH_ARGUMENTS,
        ),
        (
            "place_detail",
            "按高德 POI ID 查询规范名称、坐标、地址和开放信息。",
            PLACE_DETAIL_ARGUMENTS,
        ),
        (
            "route",
            "查询两个已解析坐标之间的真实路线、距离和通勤时间。",
            ROUTE_ARGUMENTS,
        ),
        (
            "weather",
            "查询目的地在旅行日期附近的天气；无明确日期时只用于一般风险提示。",
            WEATHER_ARGUMENTS,
        ),
        (
            "ask_user",
            "只有目的地缺失、必去地点无法消除歧义或硬约束互相冲突时，向用户追问一个关键问题。",
            _object({"question": _string()}),
        ),
    ]
    if allow_submit:
        definitions.append(
            (
                "submit_itinerary",
                "提交完整行程候选。程序会执行确定性硬校验；未通过时错误报告会作为工具结果返回供你修复。",
                _object({"reply": _string(), "plan": plan_schema()}),
            )
        )
    return [
        {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": parameters,
            "strict": True,
        }
        for name, description, parameters in definitions
    ]


def review_output_format() -> dict[str, Any]:
    issue = _object(
        {
            "code": _string(),
            "severity": _string("quality", "suspected_fact", "suggestion"),
            "path": _string(),
            "message": _string(),
            "evidence_refs": _array(_string()),
            "suggested_action": _string(),
        }
    )
    return {
        "type": "json_schema",
        "name": "trip_agent_independent_review",
        "strict": True,
        "schema": _object(
            {
                "verdict": _string("pass", "revise"),
                "summary": _string(),
                "issues": _array(issue, maximum=5),
            }
        ),
    }
