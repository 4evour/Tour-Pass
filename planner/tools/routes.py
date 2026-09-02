"""Verified route acquisition for resolved entities."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from agents.constants import resolve_city_dir
from planner.models import PlaceEvidence, RouteEvidence

from .amap import AmapClient


class RouteProvider:
    def __init__(self, amap: AmapClient, data_dir: str | Path = "data") -> None:
        self.amap = amap
        self.data_dir = Path(data_dir)
        self._edge_cache: dict[str, dict[tuple[str, str], dict]] = {}
        self._request_cache: dict[tuple[str, str, str], RouteEvidence] = {}

    def begin_request(self) -> None:
        self._request_cache.clear()

    def _load_edges(self, city: str) -> dict[tuple[str, str], dict]:
        city_dir = resolve_city_dir(self.data_dir, city)
        key = city_dir.name
        if key in self._edge_cache:
            return self._edge_cache[key]
        path = city_dir / "edges.json"
        result: dict[tuple[str, str], dict] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for edge in data if isinstance(data, list) else []:
                source, target = str(edge.get("from", "")), str(edge.get("to", ""))
                if source and target:
                    result[(source, target)] = edge
        self._edge_cache[key] = result
        return result

    def _local_route(
        self, city: str, origin: PlaceEvidence, destination: PlaceEvidence, mode: str
    ) -> RouteEvidence | None:
        if not origin.local_id or not destination.local_id or mode == "transit":
            return None
        edge = self._load_edges(city).get((origin.local_id, destination.local_id))
        if not edge or edge.get("amap_status") != "ok":
            return None
        field = "walk_minutes" if mode == "walking" else "taxi_minutes"
        minutes = edge.get(field)
        if not isinstance(minutes, (int, float)) or minutes <= 0:
            return None
        return RouteEvidence(
            from_entity_id=origin.entity_id,
            to_entity_id=destination.entity_id,
            mode=mode,
            duration_minutes=max(1, round(minutes)),
            distance_meters=max(0, int(edge.get("distance_meters", 0) or 0)),
            provider="amap_cache",
            retrieved_at=datetime.now(UTC),
            confidence="verified",
            cache_status="hit",
        )

    async def get_route(
        self, city: str, origin: PlaceEvidence, destination: PlaceEvidence, mode: str
    ) -> RouteEvidence | None:
        cache_key = (origin.entity_id, destination.entity_id, mode)
        if cache_key in self._request_cache:
            cached = self._request_cache[cache_key].model_copy(
                update={"cache_status": "hit"}
            )
            return cached
        local = self._local_route(city, origin, destination, mode)
        if local:
            self._request_cache[cache_key] = local
            return local
        if not self.amap.available:
            return None
        try:
            data = await self.amap.route(
                (origin.lat, origin.lng), (destination.lat, destination.lng), mode, city
            )
            route = data.get("route", {})
            if mode == "transit":
                candidates = route.get("transits", [])
            else:
                candidates = route.get("paths", [])
            if not candidates:
                return None
            first = candidates[0]
            seconds = int(float(first.get("duration", 0) or 0))
            distance = int(float(first.get("distance", route.get("distance", 0)) or 0))
            if seconds <= 0:
                return None
            evidence = RouteEvidence(
                from_entity_id=origin.entity_id,
                to_entity_id=destination.entity_id,
                mode=mode,
                duration_minutes=max(1, round(seconds / 60)),
                distance_meters=max(0, distance),
                provider="amap",
                retrieved_at=datetime.now(UTC),
                confidence="verified",
                cache_status="miss",
            )
            self._request_cache[cache_key] = evidence
            return evidence
        except Exception:
            return None

    async def get_day_matrix(
        self, city: str, places: list[PlaceEvidence], mode: str
    ) -> dict[tuple[str, str], RouteEvidence]:
        matrix: dict[tuple[str, str], RouteEvidence] = {}
        for index, origin in enumerate(places):
            for destination in places[index + 1 :]:
                forward = await self.get_route(city, origin, destination, mode)
                reverse = await self.get_route(city, destination, origin, mode)
                if forward:
                    matrix[(origin.entity_id, destination.entity_id)] = forward
                if reverse:
                    matrix[(destination.entity_id, origin.entity_id)] = reverse
        return matrix

    async def verify_sequence(
        self, city: str, places: list[PlaceEvidence], mode: str
    ) -> list[RouteEvidence] | None:
        routes: list[RouteEvidence] = []
        for origin, destination in zip(places, places[1:]):
            route = await self.get_route(city, origin, destination, mode)
            if not route or route.confidence != "verified":
                return None
            routes.append(route)
        return routes
