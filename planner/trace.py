"""Structured in-memory trace for one planning run."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter


class PlanningTrace:
    def __init__(self, planning_run_id: str) -> None:
        self.planning_run_id = planning_run_id
        self.started = perf_counter()
        self.events: list[dict] = []

    def record(self, stage: str, **details) -> None:
        safe = {
            key: value
            for key, value in details.items()
            if key not in {"key", "authorization", "raw_response"}
        }
        self.events.append(
            {
                "stage": stage,
                "at": datetime.now(UTC).isoformat(),
                "elapsed_ms": round((perf_counter() - self.started) * 1000),
                **safe,
            }
        )
