"""Independent hard validator for grounded itineraries."""

from __future__ import annotations

from planner.models import (
    ItineraryPlan,
    PlaceEvidence,
    TripContext,
    ValidationIssue,
    ValidationReport,
)
from planner.tools.places import normalize_place_name


def validate_itinerary(
    ctx: TripContext, plan: ItineraryPlan, evidence: dict[str, PlaceEvidence]
) -> ValidationReport:
    failures: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    planned = {stop.entity_id for day in plan.days for stop in day.stops}
    planned_names: set[str] = set()
    for entity_id in planned:
        place = evidence.get(entity_id)
        if not place:
            failures.append(
                ValidationIssue(
                    code="ENTITY_UNRESOLVED",
                    message=f"最终地点缺少证据：{entity_id}",
                    entity_id=entity_id,
                )
            )
            continue
        planned_names.add(normalize_place_name(place.canonical_name))
        planned_names.update(normalize_place_name(alias) for alias in place.aliases)
        if (
            place.status != "resolved"
            or not place.entity_id
            or not place.lat
            or not place.lng
        ):
            failures.append(
                ValidationIssue(
                    code="ENTITY_UNRESOLVED",
                    message=f"地点未唯一解析：{place.query}",
                    entity_id=entity_id,
                )
            )
        if place.open_status == "closed":
            failures.append(
                ValidationIssue(
                    code="PLACE_CLOSED",
                    message=f"地点已确认关闭：{place.canonical_name}",
                    entity_id=entity_id,
                )
            )
        elif place.open_status == "unknown":
            issue = ValidationIssue(
                code="OPENING_UNKNOWN",
                message=f"缺少日期化开放证据：{place.canonical_name}",
                repairable=place.role != "must_visit",
                entity_id=entity_id,
            )
            if place.role == "must_visit":
                failures.append(issue)
            else:
                warnings.append(issue)

    for required_name in ctx.must_visit:
        normalized = normalize_place_name(required_name)
        if not any(
            normalized == name or normalized in name or name in normalized
            for name in planned_names
            if name
        ):
            failures.append(
                ValidationIssue(
                    code="MUST_VISIT_MISSING",
                    message=f"必去项未进入行程：{required_name}",
                    repairable=True,
                )
            )

    day_end = int(ctx.daily_window.end.split(":")[0]) * 60 + int(
        ctx.daily_window.end.split(":")[1]
    )
    for day in plan.days:
        if (
            day.start_anchor != plan.hotel_anchor.entity_id
            or day.end_anchor != plan.hotel_anchor.entity_id
        ):
            failures.append(
                ValidationIssue(
                    code="HOTEL_LOOP_BROKEN",
                    message=f"第{day.day}天未形成酒店闭环",
                    day=day.day,
                )
            )
        if len(day.route_segments) != len(day.stops) + 1:
            failures.append(
                ValidationIssue(
                    code="ROUTE_UNVERIFIED",
                    message=f"第{day.day}天路线段不完整",
                    day=day.day,
                )
            )
        for segment in day.route_segments:
            if (
                segment.get("confidence") != "verified"
                or segment.get("mode") != ctx.transport_mode
            ):
                failures.append(
                    ValidationIssue(
                        code="ROUTE_UNVERIFIED",
                        message=f"第{day.day}天存在未核验的{ctx.transport_mode}路线",
                        day=day.day,
                    )
                )
        previous_end = int(ctx.daily_window.start.split(":")[0]) * 60 + int(
            ctx.daily_window.start.split(":")[1]
        )
        for stop in day.stops:
            if (
                stop.start_minutes < previous_end
                or stop.end_minutes <= stop.start_minutes
            ):
                failures.append(
                    ValidationIssue(
                        code="TIME_OVERLAP",
                        message=f"第{day.day}天时间冲突：{stop.poi_name}",
                        day=day.day,
                        entity_id=stop.entity_id,
                    )
                )
            previous_end = stop.end_minutes
        if (
            day.stops
            and day.stops[-1].end_minutes
            + day.route_segments[-1].get("travel_minutes", 0)
            > day_end
        ):
            failures.append(
                ValidationIssue(
                    code="DAILY_WINDOW_EXCEEDED",
                    message=f"第{day.day}天无法按时返回酒店",
                    day=day.day,
                )
            )

    route_minutes = sum(day.total_travel_minutes for day in plan.days)
    visit_minutes = sum(day.total_visit_minutes for day in plan.days)
    soft_scores = {
        "commute_efficiency": round(
            visit_minutes / max(visit_minutes + route_minutes, 1), 3
        ),
        "must_visit_coverage": 1.0
        if not any(issue.code == "MUST_VISIT_MISSING" for issue in failures)
        else 0.0,
    }
    return ValidationReport(
        passed=not failures,
        hard_failures=failures,
        warnings=warnings,
        soft_scores=soft_scores,
    )
