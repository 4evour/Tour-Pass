"""Deterministic itinerary quality smoke checks.

This script exercises SchedulerAgent and ReviewerAgent hard checks without
calling LLM APIs. It is intended for staging route data validation before
promoting refreshed edges into production data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


os.environ.setdefault("USE_CPP_ROUTE_OPTIMIZER", "false")
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_SCENARIOS = {
    "qingdao": {
        "city": "qingdao",
        "days": 3,
        "pace": "balanced",
        "strategy": "balanced",
        "interests": ["history", "culture"],
    },
    "chongqing": {
        "city": "chongqing",
        "days": 3,
        "pace": "balanced",
        "strategy": "balanced",
        "interests": ["history", "culture"],
        "must_visit": ["洪崖洞"],
        "hotel_area": "解放碑",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="output/data-routes-staging")
    parser.add_argument("--city", action="append", default=[])
    parser.add_argument("--days", type=int, default=0)
    parser.add_argument("--out", default="output/itinerary_quality_smoke.json")
    parser.add_argument("--fail-on-medium", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_city_pois(data_dir: Path, city: str) -> list[dict]:
    pois_path = data_dir / city / "pois.json"
    if not pois_path.exists():
        raise FileNotFoundError(f"missing pois: {pois_path}")
    pois = read_json(pois_path)
    if not isinstance(pois, list):
        raise ValueError(f"{pois_path} must be a JSON array")
    return pois


def select_hotel(pois: list[dict], hotel_area: str = "") -> dict | None:
    hotels = [p for p in pois if p.get("type") == "hotel"]
    if not hotels:
        return None
    if hotel_area:
        from agents.hotel_agent import _hotel_matches_area
        area_hotels = [h for h in hotels if _hotel_matches_area(h, hotel_area)]
        if area_hotels:
            hotels = area_hotels
    return sorted(hotels, key=lambda p: p.get("popularity", 0), reverse=True)[0]


async def run_city(data_dir: Path, scenario: dict, fail_on_medium: bool) -> dict:
    from agents.poi_agent import PoiAgent
    from agents.restaurant_agent import RestaurantAgent
    from agents.reviewer_agent import ReviewerAgent
    from agents.scheduler_agent import SchedulerAgent
    from unittest.mock import MagicMock

    city = scenario["city"]
    days = int(scenario.get("days", 3))
    pois_all = load_city_pois(data_dir, city)
    hotel = select_hotel(pois_all, hotel_area=scenario.get("hotel_area", ""))
    intent = {
        "city": city,
        "days": days,
        "pace": scenario.get("pace", "balanced"),
        "strategy": scenario.get("strategy", "balanced"),
        "interests": scenario.get("interests", []),
        "must_visit": scenario.get("must_visit", []),
        "avoid": scenario.get("avoid", []),
        "budget": scenario.get("budget", "mid-range"),
        "travelers": scenario.get("travelers", "solo"),
        "hotel_area": scenario.get("hotel_area", ""),
    }
    state = {
        "trip_intent": intent,
        "city": city,
        "days": days,
        "data_dir": str(data_dir),
        "available_pois": pois_all,
        "selected_hotel": hotel,
        "hotels": [hotel] if hotel else [],
        "weather": [],
        "city_guides": [],
        "xhs_routes": [],
        "xhs_popular_pois": {},
        "xhs_reference_routes": [],
        "review_feedback": {},
    }

    state.update(await PoiAgent(data_dir=str(data_dir)).execute(state))
    state.update(await RestaurantAgent(data_dir=str(data_dir)).execute(state))
    state.update(await SchedulerAgent().execute(state))

    daily_plans = state.get("daily_plans", [])
    reviewer = ReviewerAgent(MagicMock())
    missing = reviewer._check_must_visit(daily_plans, intent.get("must_visit", []))
    issues = reviewer._hard_check(daily_plans, intent.get("must_visit", []), missing)
    high_or_critical = [
        issue for issue in issues
        if issue.get("severity") in ("high", "critical")
        or (fail_on_medium and issue.get("severity") == "medium")
    ]
    estimated_segments = sum(
        day.get("route_quality", {}).get("estimated_segments", 0)
        for day in daily_plans
    )
    amap_segments = sum(
        day.get("route_quality", {}).get("amap_segments", 0)
        for day in daily_plans
    )
    replacement_count = sum(len(day.get("replacement_pool", [])) for day in daily_plans)
    restaurant_count = sum(
        1 for day in daily_plans for stop in day.get("stops", [])
        if stop.get("poi_type") == "restaurant"
    )
    attraction_count = sum(
        1 for day in daily_plans for stop in day.get("stops", [])
        if stop.get("poi_type", "attraction") == "attraction"
    )

    return {
        "city": city,
        "days": len(daily_plans),
        "stop_count": sum(len(day.get("stops", [])) for day in daily_plans),
        "attraction_count": attraction_count,
        "restaurant_count": restaurant_count,
        "amap_segments": amap_segments,
        "estimated_segments": estimated_segments,
        "replacement_count": replacement_count,
        "high_or_critical_issues": len(high_or_critical),
        "issue_types": sorted({issue.get("type", "") for issue in issues if issue.get("type")}),
        "blocking_issues": high_or_critical,
        "passed": not high_or_critical and estimated_segments == 0,
    }


async def run(args: argparse.Namespace) -> dict:
    data_dir = Path(args.data_dir)
    cities = args.city or ["qingdao", "chongqing"]
    reports = []
    for city in cities:
        scenario = dict(DEFAULT_SCENARIOS.get(city, {"city": city, "days": 3, "pace": "balanced"}))
        if args.days > 0:
            scenario["days"] = args.days
        reports.append(await run_city(data_dir, scenario, args.fail_on_medium))
    return {
        "data_dir": str(data_dir),
        "failed": any(not report["passed"] for report in reports),
        "cities": reports,
    }


def main() -> int:
    args = parse_args()
    report = asyncio.run(run(args))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for city in report["cities"]:
        print(
            f"{city['city']}: {'PASS' if city['passed'] else 'FAIL'} "
            f"stops={city['stop_count']} amap={city['amap_segments']} "
            f"estimated={city['estimated_segments']} issues={city['high_or_critical_issues']}"
        )
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
