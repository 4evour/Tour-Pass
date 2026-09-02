"""Grounded Planner contract and orchestration tests."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from planner.models import PlaceEvidence, PlaceQuery, PlanSkeleton  # noqa: E402
from planner.runtime import GroundedPlanner  # noqa: E402
from planner.tools.amap import AmapClient  # noqa: E402
from planner.tools.places import LocalPlaceStore, PlaceResolver  # noqa: E402
from planner.tools.routes import RouteProvider  # noqa: E402
from planner.tools.validator import validate_itinerary  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def test_trip_context_defaults_to_future_date():
    context = GroundedPlanner.build_context({"city": "长沙", "days": 3})
    assert context.city == "长沙"
    assert context.days == 3
    assert context.date_start >= date.today()
    assert context.transport_mode == "driving"


def test_empty_optional_fields_use_transparent_defaults():
    context = GroundedPlanner.build_context(
        {
            "city": "长沙",
            "days": "",
            "pace": "",
            "strategy": "",
            "budget": "",
            "travelers": "",
            "interests": "",
            "must_visit": "",
            "avoid": None,
            "date_start": "",
            "transport_mode": "",
        }
    )
    assert context.days == 3
    assert context.pace == "balanced"
    assert context.strategy == "balanced"
    assert context.budget_level is None
    assert context.must_visit == []
    assert context.transport_mode == "driving"
    assert context.assumptions


def test_special_requests_become_deterministic_constraints():
    context = GroundedPlanner.build_context(
        {
            "city": "长沙",
            "pace": "intense",
            "transport_mode": "walking",
            "special_requests": "少走路，每天最多3个景点，中午留正常时间吃饭，想住五一广场附近，不去购物中心",
        }
    )
    assert context.pace == "balanced"
    assert context.transport_mode == "driving"
    assert context.constraints.prefer_low_walking
    assert context.constraints.max_stops_per_day == 3
    assert context.constraints.reserve_lunch_minutes == 75
    assert "购物中心" in context.avoid
    assert "五一广场附近" in context.hotel.area


def test_avoid_constraint_matches_resolved_place_metadata():
    context = GroundedPlanner.build_context(
        {"city": "长沙", "special_requests": "不去购物中心"}
    )
    place = PlaceEvidence(
        query="万家丽",
        entity_id="amap:mall",
        canonical_name="万家丽国际购物广场",
        category="urban_walk",
        role="attraction",
        lat=28.19,
        lng=113.04,
        tags=["购物中心"],
        provider="amap",
        retrieved_at=datetime.now(UTC),
        confidence=1,
    )
    assert GroundedPlanner._matches_avoid(place, context.avoid) == "购物中心"


def test_local_alias_resolves_hunan_museum():
    store = LocalPlaceStore(
        ROOT / "data", ROOT / "tests/fixtures/grounded-planner/core_places.json"
    )
    results = store.search("长沙", "湖南省博物院", "must_visit")
    assert results
    assert results[0][1]["name"] == "湖南省博物馆"


def test_amap_search_is_request_deduplicated():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"status": "1", "pois": [{"id": "x"}]})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    amap = AmapClient(api_key="test", client=client)
    amap.min_interval_seconds = 0
    first = run(amap.search_text("长沙", "爱晚亭"))
    second = run(amap.search_text("长沙", "爱晚亭"))
    amap.begin_request()
    third = run(amap.search_text("长沙", "爱晚亭"))
    run(client.aclose())
    assert first == second == third
    assert calls == 2


def test_place_resolver_prefers_correct_online_alias():
    store = LocalPlaceStore(
        ROOT / "data", ROOT / "tests/fixtures/grounded-planner/core_places.json"
    )
    amap = SimpleNamespace(
        available=True,
        search_text=AsyncMock(
            return_value=[
                {
                    "id": "wrong",
                    "name": "爱晚亭家纺",
                    "type": "购物服务",
                    "location": "112.9,28.1",
                },
                {
                    "id": "right",
                    "name": "爱晚亭",
                    "type": "风景名胜;风景名胜;红色景区",
                    "location": "112.934,28.187",
                    "adname": "岳麓区",
                },
            ]
        ),
        place_detail=AsyncMock(return_value=None),
    )
    resolver = PlaceResolver(store, amap)
    result = run(
        resolver.resolve(
            "长沙", PlaceQuery(query="爱晚亭", role="must_visit", required=True)
        )
    )
    assert result is not None
    assert result.entity_id == "amap:right"
    assert result.canonical_name == "爱晚亭"


def test_partial_local_edge_is_not_verified():
    store = LocalPlaceStore(
        ROOT / "data", ROOT / "tests/fixtures/grounded-planner/core_places.json"
    )
    origin_item = store.search("长沙", "橘子洲", "must_visit")[0][1]
    destination_item = store.search("长沙", "岳麓山", "must_visit")[0][1]
    now = datetime.now(UTC)

    def evidence(item):
        return PlaceEvidence(
            query=item["name"],
            entity_id=f"amap:{item['source_id']}",
            local_id=item["id"],
            source_id=item["source_id"],
            canonical_name=item["name"],
            lat=item["lat"],
            lng=item["lng"],
            area=item["area"],
            provider="local_cache",
            retrieved_at=now,
            confidence=0.9,
        )

    amap = SimpleNamespace(available=False)
    provider = RouteProvider(amap, ROOT / "data")
    assert (
        run(
            provider.get_route(
                "长沙", evidence(origin_item), evidence(destination_item), "driving"
            )
        )
        is None
    )


def test_closed_optional_place_is_dropped():
    store = LocalPlaceStore(
        ROOT / "data", ROOT / "tests/fixtures/grounded-planner/core_places.json"
    )
    amap = SimpleNamespace(available=False)
    resolver = PlaceResolver(store, amap)
    result = run(
        resolver.resolve(
            "长沙",
            PlaceQuery(query="贾谊故居(暂停开放)", role="attraction", required=False),
        )
    )
    assert result is None


def test_skeleton_requires_all_must_visit_queries():
    context = GroundedPlanner.build_context(
        {"city": "长沙", "days": 1, "must_visit": ["橘子洲", "岳麓山"]}
    )
    skeleton = PlanSkeleton.model_validate(
        {
            "days": [
                {
                    "day": 1,
                    "theme": "测试",
                    "place_queries": [{"query": "橘子洲", "required": True}],
                }
            ]
        }
    )
    assert GroundedPlanner._missing_must_visit(context, skeleton) == ["岳麓山"]


def test_model_must_visit_role_cannot_promote_optional_query():
    context = GroundedPlanner.build_context({"city": "长沙", "must_visit": ["橘子洲"]})
    query = PlaceQuery(query="岳麓书院", role="must_visit", required=False)
    normalized = GroundedPlanner._mark_required(context, query)
    assert normalized.required is False
    assert normalized.role == "attraction"


def test_validation_rejects_unknown_must_visit_opening():
    context = GroundedPlanner.build_context(
        {"city": "长沙", "days": 1, "must_visit": ["橘子洲"]}
    )
    now = datetime.now(UTC)
    place = PlaceEvidence(
        query="橘子洲",
        entity_id="amap:a",
        canonical_name="橘子洲风景名胜区",
        aliases=["橘子洲"],
        role="must_visit",
        lat=28.19,
        lng=112.96,
        provider="amap",
        retrieved_at=now,
        confidence=1.0,
        open_status="unknown",
    )
    plan = SimpleNamespace(days=[], hotel_anchor=SimpleNamespace(entity_id="hotel"))
    report = validate_itinerary(context, plan, {place.entity_id: place})
    assert not report.passed
    assert any(issue.code == "MUST_VISIT_MISSING" for issue in report.hard_failures)


def test_structured_api_model_accepts_empty_optional_fields():
    import api_multi_agent

    request = api_multi_agent.StructuredPlanRequest.model_validate(
        {
            "city": "长沙",
            "days": None,
            "pace": "",
            "strategy": "",
            "budget": "",
            "interests": None,
            "must_visit": "",
            "avoid": None,
            "transport_mode": "",
        }
    )
    assert request.days == 3
    assert request.pace == "balanced"
    assert request.must_visit == []


def test_planner_api_routes_are_registered():
    import api_multi_agent

    paths = {route.path for route in api_multi_agent.app.routes}
    assert "/planner/plan" in paths
    assert "/api/itineraries/plan" in paths
    assert "/agent/plan-structured" in paths
