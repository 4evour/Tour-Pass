"""Typed tool registry for one planning run."""

from __future__ import annotations

from pathlib import Path

from .amap import AmapClient
from .places import LocalPlaceStore, PlaceResolver
from .routes import RouteProvider
from .solver import GroundedSolver
from .weather import WeatherProvider


class ToolRegistry:
    def __init__(
        self, data_dir: str | Path = "data", amap: AmapClient | None = None
    ) -> None:
        self.amap = amap or AmapClient()
        self.local_places = LocalPlaceStore(data_dir=data_dir)
        self.places = PlaceResolver(self.local_places, self.amap)
        self.routes = RouteProvider(self.amap, data_dir=data_dir)
        self.weather = WeatherProvider(self.amap)
        self.solver = GroundedSolver(self.routes)

    def begin_request(self) -> None:
        self.amap.begin_request()
        self.routes.begin_request()

    async def close(self) -> None:
        await self.solver.close()
        await self.amap.close()
