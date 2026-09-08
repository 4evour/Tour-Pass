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


def itinerary_skeleton_output_format() -> dict[str, Any]:
    nullable_string = _nullable(_string())
    stop = _object(
        {
            "type": _string("visit", "meal", "free_time"),
            "name": _string(),
            "search_query": nullable_string,
            "period": _string("morning", "lunch", "afternoon", "dinner", "evening"),
            "duration_minutes": _integer(minimum=30, maximum=240),
        }
    )
    day = _object(
        {
            "day": _integer(minimum=1, maximum=7),
            "theme": _string(),
            "primary_area": _string(),
            "stops": _array(stop, minimum=2, maximum=4),
        }
    )
    hotel = _object(
        {
            "name": _string(),
            "area": _string(),
            "search_query": nullable_string,
        }
    )
    return {
        "type": "json_schema",
        "name": "tour_pass_itinerary_skeleton_v2",
        "strict": True,
        "schema": _object(
            {
                "title": _string(),
                "hotel": hotel,
                "days": _array(day, minimum=1, maximum=7),
            }
        ),
    }
