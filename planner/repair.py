"""Deterministic candidate repair helpers."""

from __future__ import annotations

from planner.models import PlaceEvidence


def drop_lowest_optional(places_by_day: dict[int, list[PlaceEvidence]]) -> bool:
    candidates: list[tuple[float, int, PlaceEvidence]] = []
    for day, places in places_by_day.items():
        for place in places:
            if place.role != "must_visit":
                candidates.append((place.popularity, day, place))
    if not candidates:
        return False
    _, day, selected = min(candidates, key=lambda item: item[0])
    places_by_day[day] = [
        place for place in places_by_day[day] if place.entity_id != selected.entity_id
    ]
    return True
