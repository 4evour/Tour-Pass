"""Deterministic solver with C++ Beam Search ordering and verified-route scheduling."""

from __future__ import annotations

import itertools
import os
import uuid
from datetime import timedelta

import httpx

from planner.errors import SolverError
from planner.models import (
    ItineraryPlan,
    PlaceEvidence,
    PlannedDay,
    PlannedStop,
    RouteEvidence,
    SkeletonDay,
    TripContext,
    WeatherDay,
)
from planner.tools.routes import RouteProvider


def time_to_minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":", 1))
    return hour * 60 + minute


def minutes_to_time(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def _period_start(period: str) -> int:
    return {"morning": 9 * 60, "afternoon": 13 * 60, "evening": 18 * 60}.get(period, 0)


def _cpp_type(place: PlaceEvidence) -> str:
    if place.category == "restaurant" or place.role in {
        "restaurant",
        "lunch",
        "dinner",
    }:
        return "restaurant"
    if place.role in {"night_view", "nightlife"}:
        return "nightlife"
    if place.category == "hotel" or place.role == "hotel":
        return "hotel"
    return "attraction"


class GroundedSolver:
    def __init__(
        self,
        routes: RouteProvider,
        cpp_backend_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.routes = routes
        self.cpp_backend_url = (
            cpp_backend_url
            or os.environ.get("CPP_BACKEND_URL", "http://127.0.0.1:8080")
        ).rstrip("/")
        self._client = client
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client and self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def _cpp_order(
        self,
        ctx: TripContext,
        hotel: PlaceEvidence,
        places: list[PlaceEvidence],
        matrix: dict[tuple[str, str], RouteEvidence],
    ) -> list[str]:
        all_places = [hotel, *places]
        candidate_pois = []
        for place in all_places:
            window = place.open_windows[0] if place.open_windows else None
            candidate_pois.append(
                {
                    "id": place.entity_id,
                    "name": place.canonical_name,
                    "type": _cpp_type(place),
                    "lat": place.lat,
                    "lng": place.lng,
                    "area": place.area,
                    "open_time": window.start if window else ctx.daily_window.start,
                    "close_time": window.end if window else ctx.daily_window.end,
                    "visit_duration_minutes": 30
                    if place.role == "hotel"
                    else place.visit_duration_minutes,
                    "popularity": place.popularity,
                    "price_level": 1,
                    "description": "grounded candidate",
                    "meal_type": "main",
                    "tags": place.tags,
                    "recommendation": "",
                    "image_url": place.image_url,
                }
            )
        payload = {
            "city": ctx.city,
            "days": 1,
            "start_time": ctx.daily_window.start,
            "end_time": ctx.daily_window.end,
            "hotel_location": hotel.entity_id,
            "must_visit": [place.entity_id for place in places],
            "interests": ctx.interests,
            "avoid": ctx.avoid,
            "pace": ctx.pace,
            "strategy": ctx.strategy,
            "candidate_count": 1,
            "candidate_pois": candidate_pois,
            "route_matrix": [
                route.model_dump(mode="json") for route in matrix.values()
            ],
        }
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.cpp_backend_url}/api/optimize-route", json=payload
            )
            response.raise_for_status()
            body = response.json()
            days = body.get("days", [])
            if not days:
                return []
            order = [str(stop.get("poi_id", "")) for stop in days[0].get("stops", [])]
            expected = {place.entity_id for place in places}
            return order if set(order) == expected else []
        except Exception:
            return []

    @staticmethod
    def _fallback_order(
        hotel: PlaceEvidence,
        places: list[PlaceEvidence],
        matrix: dict[tuple[str, str], RouteEvidence],
    ) -> list[str]:
        ids = [place.entity_id for place in places]
        best: tuple[float, tuple[str, ...]] | None = None
        for order in itertools.permutations(ids):
            sequence = (hotel.entity_id, *order, hotel.entity_id)
            score = 0.0
            feasible = True
            for origin, destination in zip(sequence, sequence[1:]):
                route = matrix.get((origin, destination))
                if not route:
                    feasible = False
                    break
                score += route.duration_minutes
            if feasible and (best is None or score < best[0]):
                best = (score, order)
        return list(best[1]) if best else []

    async def solve_day(
        self,
        ctx: TripContext,
        skeleton_day: SkeletonDay,
        places: list[PlaceEvidence],
        hotel: PlaceEvidence,
        matrix: dict[tuple[str, str], RouteEvidence],
        weather: WeatherDay | None,
    ) -> PlannedDay:
        if not places:
            raise SolverError(f"day {skeleton_day.day} has no resolved places")
        if (
            ctx.constraints.max_stops_per_day
            and len(places) > ctx.constraints.max_stops_per_day
        ):
            required = [place for place in places if place.role == "must_visit"]
            optional = sorted(
                (place for place in places if place.role != "must_visit"),
                key=lambda place: place.popularity,
                reverse=True,
            )
            optional_slots = max(0, ctx.constraints.max_stops_per_day - len(required))
            places = [*required, *optional[:optional_slots]]
        order = await self._cpp_order(ctx, hotel, places, matrix)
        if not order:
            order = self._fallback_order(hotel, places, matrix)
        if not order:
            raise SolverError(f"day {skeleton_day.day} has no route-feasible order")

        by_id = {place.entity_id: place for place in places}
        ordered = [by_id[entity_id] for entity_id in order]
        sequence = [hotel, *ordered, hotel]
        verified_routes = await self.routes.verify_sequence(
            ctx.city, sequence, ctx.transport_mode
        )
        if not verified_routes:
            raise SolverError(f"day {skeleton_day.day} contains an unverified route")

        current = time_to_minutes(ctx.daily_window.start)
        day_end = time_to_minutes(ctx.daily_window.end)
        stops: list[PlannedStop] = []
        segments: list[dict] = []
        total_visit = 0
        total_travel = 0
        preferred = {
            query.query: query.preferred_period for query in skeleton_day.place_queries
        }

        for index, place in enumerate(ordered):
            route = verified_routes[index]
            current += route.duration_minutes
            period = preferred.get(place.query, "any")
            current = max(current, _period_start(period))
            lunch_start = ctx.constraints.lunch_start_minutes
            lunch_end = lunch_start + ctx.constraints.reserve_lunch_minutes
            if (
                ctx.constraints.reserve_lunch_minutes > 0
                and current < lunch_end
                and current + place.visit_duration_minutes > lunch_start
                and place.category != "restaurant"
            ):
                current = lunch_end
            if place.open_windows:
                window = place.open_windows[0]
                current = max(current, time_to_minutes(window.start))
                if current + place.visit_duration_minutes > time_to_minutes(window.end):
                    raise SolverError(
                        f"{place.canonical_name} is outside its verified open window"
                    )
            stop_end = current + place.visit_duration_minutes
            if stop_end > day_end:
                raise SolverError(f"day {skeleton_day.day} exceeds daily end time")
            slot = (
                "上午" if current < 12 * 60 else "下午" if current < 18 * 60 else "晚上"
            )
            if place.category == "restaurant":
                slot = "午餐" if current < 15 * 60 else "晚餐"
            stops.append(
                PlannedStop(
                    entity_id=place.entity_id,
                    local_id=place.local_id,
                    poi_name=place.canonical_name,
                    poi_type=_cpp_type(place),
                    role=place.role,
                    area=place.area,
                    lat=place.lat,
                    lng=place.lng,
                    slot=slot,
                    start_minutes=current,
                    end_minutes=stop_end,
                    visit_duration_minutes=place.visit_duration_minutes,
                    reason=f"符合第{skeleton_day.day}天“{skeleton_day.theme}”主题，实体与路线已解析。",
                    open_status=place.open_status,
                    evidence_provider=place.provider,
                    image_url=place.image_url,
                    travel_minutes_from_previous=route.duration_minutes,
                    distance_meters_from_previous=route.distance_meters,
                    route_source=route.provider,
                    transport_hint=ctx.transport_mode,
                )
            )
            segments.append(
                {
                    "from_entity_id": route.from_entity_id,
                    "to_entity_id": route.to_entity_id,
                    "from_name": sequence[index].canonical_name,
                    "to_name": place.canonical_name,
                    "travel_minutes": route.duration_minutes,
                    "distance_meters": route.distance_meters,
                    "mode": route.mode,
                    "provider": route.provider,
                    "confidence": route.confidence,
                    "retrieved_at": route.retrieved_at.isoformat(),
                }
            )
            total_travel += route.duration_minutes
            total_visit += place.visit_duration_minutes
            current = stop_end

        return_route = verified_routes[-1]
        total_travel += return_route.duration_minutes
        if current + return_route.duration_minutes > day_end:
            raise SolverError(
                f"day {skeleton_day.day} cannot return to the hotel before daily end"
            )
        segments.append(
            {
                "from_entity_id": return_route.from_entity_id,
                "to_entity_id": return_route.to_entity_id,
                "from_name": ordered[-1].canonical_name,
                "to_name": hotel.canonical_name,
                "travel_minutes": return_route.duration_minutes,
                "distance_meters": return_route.distance_meters,
                "mode": return_route.mode,
                "provider": return_route.provider,
                "confidence": return_route.confidence,
                "retrieved_at": return_route.retrieved_at.isoformat(),
            }
        )
        warnings = [warning for place in ordered for warning in place.warnings]
        if weather and weather.provider == "unavailable":
            warnings.append("天气数据不可用，行程未宣称经过天气优化")
        day_date = ctx.date_start + timedelta(days=skeleton_day.day - 1)
        return PlannedDay(
            day=skeleton_day.day,
            date=day_date.isoformat(),
            theme=skeleton_day.theme,
            start_anchor=hotel.entity_id,
            end_anchor=hotel.entity_id,
            stops=stops,
            route_segments=segments,
            total_travel_minutes=total_travel,
            total_visit_minutes=total_visit,
            summary=(
                f"第{skeleton_day.day}天围绕{skeleton_day.theme}安排{len(stops)}站，"
                f"含酒店往返共通勤{total_travel}分钟；"
                f"已预留{ctx.constraints.reserve_lunch_minutes}分钟午餐时间。"
            ),
            weather=weather,
            warnings=list(dict.fromkeys(warnings)),
        )

    async def solve(
        self,
        ctx: TripContext,
        skeleton_days: list[SkeletonDay],
        places_by_day: dict[int, list[PlaceEvidence]],
        hotel: PlaceEvidence,
        matrices: dict[int, dict[tuple[str, str], RouteEvidence]],
        weather: list[WeatherDay],
    ) -> ItineraryPlan:
        days = []
        for skeleton_day in skeleton_days:
            weather_day = (
                weather[skeleton_day.day - 1]
                if skeleton_day.day - 1 < len(weather)
                else None
            )
            days.append(
                await self.solve_day(
                    ctx,
                    skeleton_day,
                    places_by_day.get(skeleton_day.day, []),
                    hotel,
                    matrices.get(skeleton_day.day, {}),
                    weather_day,
                )
            )
        return ItineraryPlan(
            plan_id=uuid.uuid4().hex,
            city=ctx.city,
            planning_run_id=ctx.planning_run_id,
            hotel_anchor=hotel,
            days=days,
            evidence_snapshot_id=uuid.uuid4().hex,
            warnings=list(
                dict.fromkeys(
                    [
                        *ctx.assumptions,
                        *(warning for day in days for warning in day.warnings),
                    ]
                )
            ),
        )
