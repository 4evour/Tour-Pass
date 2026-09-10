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


def _array(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def itinerary_skeleton_output_format(
    expected_days: int | None = None,
) -> dict[str, Any]:
    nullable_string = _nullable(_string())
    stop = _object(
        {
            "type": _string("visit", "meal", "free_time"),
            "name": _string(),
            "search_query": nullable_string,
            "period": _string(
                "breakfast", "morning", "lunch", "afternoon", "dinner", "evening"
            ),
            "visit_scale": _string("quick_stop", "standard", "half_day", "full_day"),
            "reason": _described_string(
                "用一句自然语言说明这里具体能看什么、怎么玩或吃什么，不写抽象推荐话术。"
            ),
            "optional": _boolean(),
        }
    )
    intercity_leg = _object(
        {
            "from": _string(),
            "to": _string(),
            "mode": _string("rail", "flight", "coach", "ferry", "driving", "unknown"),
            "departure_hint": nullable_string,
            "arrival_hint": nullable_string,
        }
    )
    day = _object(
        {
            "day": _integer(minimum=1),
            "destination": _string(),
            "theme": _string(),
            "summary": _described_string(
                "用一至两句自然语言串起当天上午、下午、晚上、三餐和路线，并说明主动取舍；景点不得使用分钟级到离时间。"
            ),
            "primary_area": _string(),
            "overnight_area": _string(),
            "intercity_leg": _nullable(intercity_leg),
            "fallback_note": _string(),
            "stops": _array(stop),
        }
    )
    hotel = _object(
        {
            "destination": _string(),
            "name": _string(),
            "area": _string(),
            "search_query": nullable_string,
            "reason": _string(),
        }
    )
    budget_category = _object(
        {
            "label": _string(),
            "percentage": _integer(minimum=0, maximum=100),
            "reason": _string(),
        }
    )
    days = _array(day)
    days["description"] = (
        f"必须返回恰好 {expected_days} 个按顺序排列的自然日。"
        if expected_days is not None
        else "根据用户需求选择合理天数，并返回连续、按顺序排列的自然日。"
    )
    return {
        "type": "json_schema",
        "name": "tour_pass_complete_itinerary_v5",
        "strict": True,
        "schema": _object(
            {
                "title": _string(),
                "overview": _string(),
                "highlights": _array(_string()),
                "tradeoffs": _array(_string()),
                "budget_notes": _array(
                    _described_string(
                        "结合目的地、天数和用户预算说明花费优先级、主要浮动项或控制办法；未提供金额时也要给出有用的预算边界。"
                    )
                ),
                "safety_notes": _array(
                    _described_string(
                        "只写与目的地、季节、路线、体力或同行人真正相关的条件式安全建议，不冒充官方预警。"
                    )
                ),
                "transport_notes": _array(
                    _described_string(
                        "说明本行程市内交通的主策略、适用场景和需要主动避开的折返或高峰风险。"
                    )
                ),
                "budget_allocation": _array(budget_category),
                "hotel": hotel,
                "hotels": _array(hotel),
                "days": days,
            }
        ),
    }
