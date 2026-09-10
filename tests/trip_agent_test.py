from __future__ import annotations
import asyncio
import json

from datetime import date
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import HTTPException, Request

from trip_agent.app import stream_chat_events
from trip_agent.auth import AuthManager
from trip_agent.cache import ProviderCache
from trip_agent.context import (
    MemoryPolicy,
    build_planning_context,
    compact_conversation_history,
    compact_plan_memory,
    compact_repair_memory,
)
from trip_agent.contracts import ChatRequest, ChatResponse, StructuredTripRequest
from trip_agent.observability import close_logging, configure_logging, log_event
from trip_agent.loop import TripAgent
from trip_agent.llm import LLMServiceUnavailableError, OpenAICompatibleLLM
from trip_agent.model_schema import itinerary_skeleton_output_format
from trip_agent.plan_output import (
    normalize_plan,
    normalize_risk,
    normalize_schedule_item,
    normalize_transfer,
)
from trip_agent.providers.amap import AmapProvider
from trip_agent.providers.rail import (
    Rail12306Provider,
    _STATION_SCRIPT,
    _parse_prices,
    _parse_station_script,
    _service_datetime,
)
from trip_agent.store import TripStore
from trip_agent.providers.weather import WeatherProvider
from trip_agent.validation import HardValidator, _matches_key
from trip_agent.workflow import (
    _closed_on_date,
    _matches,
    _select_place,
    repair_skeleton,
)


def skeleton_plan(city: str = "长沙", days: int = 1) -> dict:
    day_items = []
    for day in range(1, days + 1):
        day_items.append(
            {
                "day": day,
                "theme": "山水与城市",
                "summary": "按相邻片区安排主要景点和用餐。",
                "primary_area": "岳麓区",
                "secondary_areas": [],
                "stops": [
                    {
                        "type": "visit",
                        "name": "岳麓山",
                        "search_query": "岳麓山",
                        "period": "morning",
                        "duration_minutes": 120,
                        "reason": "代表性城市景观。",
                        "optional": False,
                        "practical_tip": "穿舒适的鞋。",
                    },
                    {
                        "type": "visit",
                        "name": "橘子洲",
                        "search_query": "橘子洲",
                        "period": "afternoon",
                        "duration_minutes": 90,
                        "reason": "体验城市滨水景观。",
                        "optional": True,
                        "practical_tip": "留意景区接驳信息。",
                    },
                ],
            }
        )
    return {
        "title": f"{city}{days}日行程",
        "overview": "兼顾代表性景点、交通和休息。",
        "hotel": {
            "name": "五一广场住宿区",
            "area": "五一广场",
            "status": "recommended_area",
            "reason": "公共交通方便。",
            "search_query": "五一广场地铁站",
        },
        "candidate_areas": [
            {
                "name": "五一广场",
                "highlights": ["交通方便"],
                "tradeoffs": ["热门时段人多"],
                "fit_score": 90,
                "selected": True,
            },
            {
                "name": "岳麓区",
                "highlights": ["靠近主要景点"],
                "tradeoffs": ["夜间选择较少"],
                "fit_score": 80,
                "selected": False,
            },
        ],
        "days": day_items,
        "narrative": {
            "headline": "按片区慢慢游",
            "summary": "减少折返并保留用餐时间。",
            "highlights": ["山水", "城市"],
            "tradeoffs": ["开放时间需复核"],
        },
        "warnings": [],
    }


class SkeletonLLM:
    reasoning_effort = "medium"
    model = "fake-model"

    def __init__(self, skeleton: dict | None = None) -> None:
        self.skeleton = skeleton or skeleton_plan()
        self.call_count = 0
        self.messages: list[list[dict]] = []
        self.invocations: list[dict] = []

    async def ainvoke(self, messages: list[dict], **kwargs) -> SimpleNamespace:
        self.call_count += 1
        self.messages.append(list(messages))
        self.invocations.append(dict(kwargs))
        return SimpleNamespace(
            content=json.dumps(self.skeleton, ensure_ascii=False),
            tool_calls=[],
            metrics={
                "usage": {
                    "input_tokens": 2000,
                    "output_tokens": 500,
                    "input_tokens_details.cached_tokens": 1024,
                }
            },
        )


class FakeAmap:
    def __init__(self) -> None:
        self.search_calls = 0
        self.route_calls = 0

    async def close(self) -> None:
        return None

    async def search_places(self, city: str, keywords: str, limit: int = 8) -> dict:
        self.search_calls += 1
        if "五一广场" in keywords:
            place = {
                "id": "AREA1",
                "name": "五一广场地铁站",
                "type": "交通设施服务;地铁站",
                "address": "五一大道",
                "area": "芙蓉区",
                "location": "112.977,28.196",
            }
        elif "橘子洲" in keywords:
            place = {
                "id": "B002",
                "name": "橘子洲景区",
                "type": "风景名胜",
                "address": "橘子洲头",
                "area": "岳麓区",
                "location": "112.962,28.174",
            }
        elif "餐厅" in keywords or "午餐" in keywords:
            place = {
                "id": "FOOD1",
                "name": "岳麓区本地餐厅",
                "type": "餐饮服务;中餐厅",
                "address": "麓山路",
                "area": "岳麓区",
                "location": "112.950,28.180",
            }
        else:
            place = {
                "id": "B001",
                "name": "岳麓山国家重点风景名胜区",
                "type": "风景名胜",
                "address": "登高路58号",
                "area": "岳麓区",
                "location": "112.94,28.18",
            }
        return {
            "places": [place],
            "source": "amap",
            "cache_hit": False,
            "response_hash": f"sha256:{place['id']}",
        }

    async def route(
        self, city: str, origin: str, destination: str, mode: str = "driving"
    ) -> dict:
        self.route_calls += 1
        return {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "distance_meters": 2400,
            "duration_seconds": 1200,
            "source": "amap",
            "cache_hit": False,
            "response_hash": f"sha256:{origin}:{destination}:{mode}",
        }


def single_place_plan(title: str = "岳麓山慢游") -> dict:
    return {
        "city": "长沙",
        "title": title,
        "trip_profile": {"days": 1},
        "hotel": {
            "name": "五一广场住宿区",
            "area": "五一广场",
            "status": "recommended_area",
        },
        "days": [
            {
                "day": 1,
                "start_time": "09:00",
                "end_time": "12:00",
                "start_anchor": {"name": "五一广场住宿区"},
                "end_anchor": {"name": "五一广场住宿区"},
                "schedule": [
                    {
                        "type": "visit",
                        "name": "岳麓山",
                        "start": "09:00",
                        "end": "12:00",
                        "duration_minutes": 180,
                        "opening_match": "unknown",
                    }
                ],
                "transfers": [],
            }
        ],
    }


class TripAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_retries_transient_transport_failure(self) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            self.assertEqual(json.loads(request.content)["max_tokens"], 4096)
            if request_count == 1:
                raise httpx.RemoteProtocolError(
                    "incomplete chunked read", request=request
                )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"action":"ask"}'}}]},
            )

        llm = OpenAICompatibleLLM()
        llm.key = "test-key"
        llm.wire_api = "chat_completions"
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        response = await llm.ainvoke([{"role": "user", "content": "test"}])
        await llm.close()

        self.assertEqual(response.content, '{"action":"ask"}')
        self.assertEqual(request_count, 2)

    async def test_llm_does_not_retry_read_timeout(self) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            raise httpx.ReadTimeout("slow response", request=request)

        llm = OpenAICompatibleLLM()
        llm.key = "test-key"
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with self.assertRaises(httpx.ReadTimeout):
            await llm.ainvoke([{"role": "user", "content": "test"}])
        await llm.close()

        self.assertEqual(request_count, 1)

    async def test_llm_uses_responses_stream_protocol(self) -> None:
        messages = [{"role": "user", "content": "test"}]

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/responses")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "gpt-5.6-luna")
            self.assertEqual(payload["input"], messages)
            self.assertEqual(payload["max_output_tokens"], 4096)
            self.assertEqual(payload["reasoning"], {"effort": "high"})
            self.assertTrue(payload["stream"])
            self.assertFalse(payload["store"])
            self.assertNotIn("temperature", payload)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    "event: response.output_text.delta\n"
                    'data: {"type":"response.output_text.delta",'
                    '"delta":"{\\"action\\":"}\n\n'
                    "event: response.output_text.delta\n"
                    'data: {"type":"response.output_text.delta",'
                    '"delta":"\\"ask\\"}"}\n\n'
                    "event: response.output_text.done\n"
                    'data: {"type":"response.output_text.done",'
                    '"text":"{\\"action\\":\\"ask\\"}"}\n\n'
                    "data: [DONE]\n\n"
                ).encode(),
            )

        llm = OpenAICompatibleLLM()
        llm.key = "test-key"
        llm.base_url = "https://ztoken.zlux.top"
        llm.model = "gpt-5.6-luna"
        llm.wire_api = "responses"
        llm.reasoning_effort = "high"
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        progress: list[dict] = []
        response = await llm.ainvoke(messages, on_progress=progress.append)
        await llm.close()

        self.assertEqual(response.content, '{"action":"ask"}')
        self.assertEqual(response.metrics["output_chars"], 16)
        self.assertEqual(
            [event["milestone"] for event in progress],
            ["connected", "first_event", "first_text"],
        )

    async def test_llm_hedges_slow_structured_response(self) -> None:
        request_count = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            if request_count == 1:
                await asyncio.sleep(0.08)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    "event: response.output_text.done\n"
                    'data: {"type":"response.output_text.done",'
                    '"text":"{\\"ok\\":true}"}\n\n'
                    "data: [DONE]\n\n"
                ).encode(),
            )

        llm = OpenAICompatibleLLM()
        llm.key = "test-key"
        llm.wire_api = "responses"
        llm.hedge_delay_seconds = 0.01
        llm.timeout_seconds = 1
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        response = await llm.ainvoke(
            [{"role": "user", "content": "test"}],
            output_format={"type": "json_schema"},
        )
        await llm.close()

        self.assertEqual(response.content, '{"ok":true}')
        self.assertEqual(request_count, 2)
        self.assertTrue(response.metrics["hedged"])
        self.assertEqual(response.metrics["provider_request_count"], 2)

    async def test_llm_retries_transient_responses_stream_error(self) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            if request_count == 1:
                content = (
                    "event: error\n"
                    'data: {"type":"error","error":'
                    '{"message":"stream_read_error"}}\n\n'
                )
            else:
                content = (
                    "event: response.output_text.done\n"
                    'data: {"type":"response.output_text.done",'
                    '"text":"{\\"action\\":\\"ask\\"}"}\n\n'
                    "data: [DONE]\n\n"
                )
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=content.encode(),
            )

        llm = OpenAICompatibleLLM()
        llm.key = "test-key"
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        response = await llm.ainvoke([{"role": "user", "content": "test"}])
        await llm.close()

        self.assertEqual(response.content, '{"action":"ask"}')
        self.assertEqual(request_count, 2)

    async def test_llm_retries_connect_error_a_third_time(self) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            if request_count < 3:
                raise httpx.ConnectError("gateway unavailable", request=request)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    "event: response.output_text.done\n"
                    'data: {"type":"response.output_text.done",'
                    '"text":"{\\"action\\":\\"ask\\"}"}\n\n'
                    "data: [DONE]\n\n"
                ).encode(),
            )

        llm = OpenAICompatibleLLM()
        llm.key = "test-key"
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("trip_agent.llm.asyncio.sleep", new=AsyncMock()):
            response = await llm.ainvoke([{"role": "user", "content": "test"}])
        await llm.close()

        self.assertEqual(response.content, '{"action":"ask"}')
        self.assertEqual(request_count, 3)

    async def test_llm_exhausted_transport_retries_raise_service_unavailable(
        self,
    ) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            raise httpx.ConnectError("gateway unavailable", request=request)

        llm = OpenAICompatibleLLM()
        llm.key = "test-key"
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with (
            patch("trip_agent.llm.asyncio.sleep", new=AsyncMock()),
            self.assertRaises(LLMServiceUnavailableError),
        ):
            await llm.ainvoke([{"role": "user", "content": "test"}])
        await llm.close()

        self.assertEqual(request_count, 3)

    def test_chat_tool_call_without_text_has_empty_content(self) -> None:
        llm = OpenAICompatibleLLM()
        llm.wire_api = "chat_completions"
        content = llm._response_content(
            {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        )

        self.assertEqual(content, "")

    def test_llm_usage_summary_keeps_token_metrics_only(self) -> None:
        summary = OpenAICompatibleLLM._usage_summary(
            {
                "input_tokens": 120,
                "output_tokens": 35,
                "total_tokens": 155,
                "output_tokens_details": {"reasoning_tokens": 20},
                "attribution": {"large": "provider-specific payload"},
            }
        )

        self.assertEqual(
            summary,
            {
                "input_tokens": 120,
                "output_tokens": 35,
                "total_tokens": 155,
                "output_tokens_details.reasoning_tokens": 20,
            },
        )

    def test_structured_trip_request_requires_destination(self) -> None:
        with self.assertRaises(ValueError):
            ChatRequest(message="", trip=StructuredTripRequest(destination=""))

        request = ChatRequest(
            message="",
            trip=StructuredTripRequest(
                destination="广州",
                days=3,
                date_range={"start": "2026-10-01", "end": "2026-10-03"},
                travellers="两位成人",
                pace="relaxed",
                transport_preference="public_transit",
                daily_window={"start": "08:30", "end": "19:00"},
            ),
        )
        payload = request.trip.model_dump(mode="json")
        self.assertEqual(payload["destination"], "广州")
        self.assertEqual(payload["days"], 3)
        self.assertEqual(
            payload["date_range"],
            {"start": "2026-10-01", "end": "2026-10-03"},
        )
        self.assertEqual(payload["travellers"], "两位成人")
        self.assertEqual(payload["pace"], "relaxed")
        self.assertEqual(payload["transport_preference"], "public_transit")
        self.assertEqual(payload["daily_window"], {"start": "08:30", "end": "19:00"})

    def test_structured_trip_request_rejects_explicit_empty_party(self) -> None:
        with self.assertRaises(ValueError):
            StructuredTripRequest(destination="广州", party={"adults": 0})

    async def test_fast_workflow_calls_model_once_and_builds_verified_plan(
        self,
    ) -> None:
        llm = SkeletonLLM()
        amap = FakeAmap()
        published: list[dict] = []
        agent = TripAgent(llm, amap=amap)

        response = await agent.run(
            "请生成行程",
            structured_request={
                "destination": "长沙",
                "days": 1,
                "daily_window": {"start": "09:00", "end": "20:00"},
                "transport_preference": "public_transit",
                "travellers": "两位成人",
                "must_visits": ["岳麓山"],
            },
            on_event=published.append,
        )

        self.assertTrue(response.plan)
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(amap.search_calls, 3)
        self.assertEqual(amap.route_calls, 1)
        self.assertEqual(llm.invocations[0]["reasoning_effort"], "medium")
        self.assertIn("prompt_cache_key", llm.invocations[0])
        self.assertNotIn("tools", llm.invocations[0])
        self.assertTrue(
            any(item["type"] == "meal" for item in response.plan["days"][0]["schedule"])
        )
        validation = [
            event
            for event in response.events
            if event["type"] == "plan_validation_finished"
        ][-1]
        self.assertTrue(validation["passed"])
        self.assertEqual(
            sum(event["type"] == "model_started" for event in response.events), 1
        )
        self.assertTrue(any(event["type"] == "prompt_cache" for event in published))

    async def test_fast_workflow_uses_resolved_city_for_map_calls(self) -> None:
        class ResolvingAmap(FakeAmap):
            def __init__(self) -> None:
                super().__init__()
                self.cities: list[str] = []

            async def resolve_search_city(self, destination: str) -> dict:
                self.assert_destination = destination
                return {
                    "search_city": "440100",
                    "cache_hit": False,
                    "response_hash": "sha256:region",
                }

            async def search_places(
                self, city: str, keywords: str, limit: int = 8
            ) -> dict:
                self.cities.append(city)
                return await super().search_places(city, keywords, limit)

            async def route(
                self,
                city: str,
                origin: str,
                destination: str,
                mode: str = "driving",
            ) -> dict:
                self.cities.append(city)
                return await super().route(city, origin, destination, mode)

        amap = ResolvingAmap()
        response = await TripAgent(
            SkeletonLLM(skeleton_plan("广州番禺")),
            amap=amap,
        ).run(
            "请生成行程",
            structured_request={
                "destination": "广州番禺",
                "days": 1,
                "daily_window": {"start": "09:00", "end": "20:00"},
            },
        )

        self.assertTrue(response.plan)
        self.assertEqual(amap.assert_destination, "广州番禺")
        self.assertEqual(set(amap.cities), {"440100"})

    async def test_optional_unresolved_meal_becomes_generic_meal_break(self) -> None:
        skeleton = skeleton_plan()
        skeleton["days"][0]["stops"].insert(
            1,
            {
                "type": "meal",
                "name": "不存在的午餐店",
                "search_query": "不存在的午餐店",
                "period": "lunch",
                "duration_minutes": 60,
                "optional": True,
            },
        )

        class MissingMealAmap(FakeAmap):
            async def search_places(
                self, city: str, keywords: str, limit: int = 8
            ) -> dict:
                if keywords == "不存在的午餐店":
                    self.search_calls += 1
                    return {
                        "places": [],
                        "source": "amap",
                        "cache_hit": False,
                        "response_hash": "sha256:empty",
                    }
                return await super().search_places(city, keywords, limit)

        response = await TripAgent(
            SkeletonLLM(skeleton),
            amap=MissingMealAmap(),
        ).run(
            "请生成行程",
            structured_request={
                "destination": "长沙",
                "days": 1,
                "daily_window": {"start": "09:00", "end": "20:00"},
            },
        )

        self.assertTrue(response.plan)
        meal = next(
            item
            for item in response.plan["days"][0]["schedule"]
            if item["type"] == "meal" and item["period"] == "lunch"
        )
        self.assertEqual(meal["name"], "岳麓区就近午餐")
        self.assertTrue(response.plan["validation"]["passed"])

    def test_skeleton_repair_adds_all_applicable_daily_meals(self) -> None:
        repaired, _ = repair_skeleton(
            skeleton_plan(),
            {
                "destination": "长沙",
                "days": 1,
                "daily_window": {"start": "09:00", "end": "21:00"},
            },
        )

        meals = [
            item for item in repaired["days"][0]["stops"] if item["type"] == "meal"
        ]
        self.assertEqual(
            [item["period"] for item in meals],
            ["breakfast", "lunch", "dinner"],
        )
        self.assertTrue(all(item["optional"] is False for item in meals))

    async def test_fast_workflow_delivers_partial_plan_for_optional_unresolved_stop(
        self,
    ) -> None:
        class PartialAmap(FakeAmap):
            async def search_places(
                self, city: str, keywords: str, limit: int = 8
            ) -> dict:
                if "橘子洲" in keywords:
                    self.search_calls += 1
                    return {
                        "places": [],
                        "source": "amap",
                        "cache_hit": False,
                        "response_hash": "sha256:empty",
                    }
                return await super().search_places(city, keywords, limit)

        llm = SkeletonLLM()
        agent = TripAgent(llm, amap=PartialAmap())
        response = await agent.run(
            "请生成行程",
            structured_request={
                "destination": "长沙",
                "days": 1,
                "daily_window": {"start": "09:00", "end": "20:00"},
                "must_visits": ["岳麓山"],
            },
        )

        self.assertTrue(response.plan)
        self.assertEqual(llm.call_count, 1)
        self.assertNotIn(
            "橘子洲",
            [item["name"] for item in response.plan["days"][0]["schedule"]],
        )
        self.assertTrue(
            any("可选项已移除" in warning for warning in response.plan["warnings"])
        )

    async def test_required_stop_survives_amap_quota_failure(self) -> None:
        class QuotaLimitedAmap(FakeAmap):
            async def search_places(
                self, city: str, keywords: str, limit: int = 8
            ) -> dict:
                if "岳麓山" in keywords:
                    self.search_calls += 1
                    raise RuntimeError(
                        "AMap place_search failed: CUQPS_HAS_EXCEEDED_THE_LIMIT"
                    )
                return await super().search_places(city, keywords, limit)

        response = await TripAgent(
            SkeletonLLM(),
            amap=QuotaLimitedAmap(),
        ).run(
            "请生成行程",
            structured_request={
                "destination": "长沙",
                "days": 1,
                "daily_window": {"start": "09:00", "end": "20:00"},
                "must_visits": ["岳麓山"],
            },
        )

        self.assertTrue(response.plan)
        self.assertIn(
            "岳麓山",
            [item["name"] for item in response.plan["days"][0]["schedule"]],
        )
        self.assertTrue(response.plan["validation"]["passed"])
        self.assertIn(
            "UNRESOLVED_ENTITY",
            [warning["code"] for warning in response.plan["validation"]["warnings"]],
        )

    async def test_optional_stop_removed_when_closed_on_requested_date(self) -> None:
        skeleton = skeleton_plan()
        skeleton["days"][0]["stops"][1]["name"] = "橘子洲"

        class OpeningAwareAmap(FakeAmap):
            async def search_places(
                self, city: str, keywords: str, limit: int = 8
            ) -> dict:
                result = await super().search_places(city, keywords, limit)
                if "橘子洲" in keywords:
                    result["places"][0]["business_hours"] = "周二 全天不开放"
                return result

        response = await TripAgent(
            SkeletonLLM(skeleton),
            amap=OpeningAwareAmap(),
        ).run(
            "请生成行程",
            structured_request={
                "destination": "长沙",
                "days": 1,
                "start_date": "2026-09-08",
                "daily_window": {"start": "09:00", "end": "20:00"},
            },
        )

        names = [item["name"] for item in response.plan["days"][0]["schedule"]]
        self.assertNotIn("橘子洲景区", names)
        self.assertTrue(
            any("橘子洲景区" in warning for warning in response.plan["warnings"])
        )

    def test_closed_on_date_matches_weekday_and_date_range(self) -> None:
        self.assertTrue(_closed_on_date("周二 全天不开放", date(2026, 9, 8)))
        self.assertFalse(_closed_on_date("周二 全天不开放", date(2026, 9, 9)))
        self.assertTrue(
            _closed_on_date("04/15-10/15 周二 全天不开放", date(2026, 9, 8))
        )
        self.assertFalse(
            _closed_on_date("04/15-10/15 周二 全天不开放", date(2026, 10, 16))
        )
        self.assertFalse(
            _closed_on_date(
                "周一至周五 09:00-18:00；周末 全天不开放",
                date(2026, 9, 9),
            )
        )
        self.assertFalse(_closed_on_date("法定节假日 全天不开放", date(2026, 9, 9)))

    async def test_fast_workflow_keeps_lunch_inside_meal_window(self) -> None:
        skeleton = skeleton_plan()
        skeleton["days"][0]["stops"] = [
            {
                "type": "visit",
                "name": "岳麓山",
                "search_query": "岳麓山",
                "period": "morning",
                "duration_minutes": 180,
            },
            {
                "type": "visit",
                "name": "橘子洲",
                "search_query": "橘子洲",
                "period": "morning",
                "duration_minutes": 180,
            },
            {
                "type": "meal",
                "name": "岳麓区本地餐厅",
                "search_query": "岳麓区本地餐厅",
                "period": "lunch",
                "duration_minutes": 75,
            },
        ]
        agent = TripAgent(SkeletonLLM(skeleton), amap=FakeAmap())

        response = await agent.run(
            "请生成行程",
            structured_request={
                "destination": "长沙",
                "days": 1,
                "daily_window": {"start": "09:00", "end": "20:00"},
            },
        )

        self.assertTrue(response.plan)
        lunch = next(
            item
            for item in response.plan["days"][0]["schedule"]
            if item["period"] == "lunch"
        )
        self.assertLess(lunch["start"], "13:30")

    async def test_fast_workflow_enforces_provider_request_budget(self) -> None:
        llm = SkeletonLLM()
        amap = FakeAmap()
        agent = TripAgent(llm, amap=amap, max_provider_calls=5)

        response = await agent.run(
            "请生成行程",
            structured_request={
                "destination": "长沙",
                "days": 1,
                "daily_window": {"start": "09:00", "end": "20:00"},
                "must_visits": ["岳麓山"],
            },
        )

        self.assertTrue(response.plan)
        self.assertLessEqual(amap.search_calls + amap.route_calls, 5)

    async def test_large_provider_budget_only_executes_required_calls(self) -> None:
        amap = FakeAmap()
        response = await TripAgent(
            SkeletonLLM(),
            amap=amap,
            max_provider_calls=100,
        ).run(
            "请生成行程",
            structured_request={
                "destination": "长沙",
                "days": 1,
                "daily_window": {"start": "09:00", "end": "20:00"},
            },
        )

        self.assertTrue(response.plan)
        self.assertEqual(amap.search_calls, 3)
        self.assertEqual(amap.route_calls, 1)
        self.assertEqual(amap.search_calls + amap.route_calls, 4)

    def test_provider_request_budget_is_capped_at_one_hundred(self) -> None:
        agent = TripAgent(
            SkeletonLLM(),
            amap=FakeAmap(),
            max_provider_calls=1000,
        )
        self.assertEqual(agent.max_provider_calls, 100)

    async def test_provider_budget_includes_rail_calls(self) -> None:
        class CountingRail:
            available = True

            def __init__(self) -> None:
                self.calls = 0

            async def search_trains(self, **_kwargs):
                self.calls += 1
                return {"provider": "rail12306", "available": True, "trains": []}

        skeleton = skeleton_plan("昆明", 2)
        skeleton["days"][1]["destination"] = "大理"
        skeleton["days"][1]["intercity_leg"] = {
            "from": "昆明",
            "to": "大理",
            "mode": "rail",
            "departure_hint": "09:00",
            "arrival_hint": None,
        }
        amap = FakeAmap()
        rail = CountingRail()
        response = await TripAgent(
            SkeletonLLM(skeleton),
            amap=amap,
            rail=rail,
            max_provider_calls=5,
        ).run(
            "昆明和大理两日行程",
            structured_request={
                "destination": "昆明、大理",
                "destinations": [
                    {"name": "昆明", "days": 1},
                    {"name": "大理", "days": 1},
                ],
                "days": 2,
                "start_date": "2026-09-14",
            },
        )

        self.assertTrue(response.plan)
        self.assertEqual(rail.calls, 1)
        self.assertLessEqual(amap.search_calls + amap.route_calls + rail.calls, 5)

    def test_risk_source_requires_matching_weather_evidence(self) -> None:
        weather = {"provider": "qweather", "response_hash": "sha256:weather"}
        verified = normalize_risk(
            {
                "type": "weather",
                "source": "qweather",
                "evidence_hash": "sha256:weather",
            },
            weather,
        )
        unbound = normalize_risk(
            {"type": "weather", "source": "qweather"},
            weather,
        )
        unsupported = normalize_risk(
            {"type": "opening", "source": "amap"},
            weather,
        )

        self.assertEqual(verified["source"], "qweather")
        self.assertEqual(unbound["source"], "model_judgment")
        self.assertEqual(unsupported["source"], "model_judgment")

    def test_normalizer_merges_adjacent_poi_and_closes_hotel_loop(self) -> None:
        place = {
            "id": "B001",
            "name": "广州塔",
            "type": "风景名胜",
            "location": "113.32,23.10",
        }
        plan = normalize_plan(
            {
                "city": "广州",
                "hotel": {
                    "name": "越秀区住宿区域",
                    "status": "recommended_area",
                },
                "days": [
                    {
                        "end_anchor": {"name": "广州塔", "type": "place"},
                        "schedule": [
                            {
                                "type": "visit",
                                "name": "广州塔",
                                "start": "14:00",
                                "end": "17:00",
                                "duration_minutes": 180,
                            },
                            {
                                "type": "visit",
                                "name": "广州塔",
                                "start": "17:00",
                                "end": "20:00",
                                "duration_minutes": 180,
                            },
                        ],
                    }
                ],
            },
            known_places={"广州塔": place},
            resolve_place=lambda item, places: places.get(item.get("name")),
            route_evidence=[],
            weather_evidence=None,
        )

        day = plan["days"][0]
        self.assertEqual(len(day["schedule"]), 1)
        self.assertEqual(day["schedule"][0]["duration_minutes"], 360)
        self.assertEqual(day["end_anchor"]["name"], "越秀区住宿区域")

    def test_normalizer_removes_unverified_facts_and_binds_route_hash(self) -> None:
        raw_plan = {
            "city": "长沙",
            "days": [
                {
                    "day": 1,
                    "schedule": [
                        {
                            "type": "visit",
                            "name": "模型地点",
                            "start": "09:00",
                            "end": "10:00",
                            "duration_minutes": 60,
                            "place_id": "FAKE",
                            "address": "模型地址",
                            "area": "模型区域",
                            "location": "1,2",
                            "opening_hours": "09:00-18:00",
                            "opening_match": "matched",
                            "source": "amap",
                        },
                        {
                            "type": "free_time",
                            "name": "散步",
                            "start": "10:30",
                            "end": "11:30",
                            "duration_minutes": 60,
                        },
                    ],
                    "transfers": [
                        {
                            "from_name": "模型地点",
                            "to_name": "散步",
                            "mode": "walking",
                            "duration_minutes": 5,
                            "distance_meters": 500,
                            "source": "amap",
                            "from_location": "112.1,28.1",
                            "to_location": "112.2,28.2",
                            "evidence_hash": "sha256:route",
                        }
                    ],
                }
            ],
        }
        route_evidence = [
            {
                "origin": "112.1,28.1",
                "destination": "112.2,28.2",
                "mode": "walking",
                "distance_meters": 720,
                "duration_seconds": 540,
                "source": "amap",
                "response_hash": "sha256:route",
            }
        ]

        result = normalize_plan(
            raw_plan,
            known_places={},
            resolve_place=lambda _item, _places: None,
            route_evidence=route_evidence,
            weather_evidence=None,
        )

        visit = result["days"][0]["schedule"][0]
        transfer = result["days"][0]["transfers"][0]
        self.assertIsNone(visit["place_id"])
        self.assertIsNone(visit["address"])
        self.assertIsNone(visit["location"])
        self.assertIsNone(visit["opening_hours"])
        self.assertEqual(visit["opening_match"], "unknown")
        self.assertEqual(visit["source"], "model_judgment")
        self.assertEqual(transfer["source"], "unknown")
        self.assertEqual(transfer["duration_minutes"], 0)
        self.assertEqual(transfer["distance_meters"], 0)

        schedule = [
            {"name": "模型地点", "location": "112.1,28.1"},
            {"name": "散步", "location": "112.2,28.2"},
        ]
        verified = normalize_transfer(
            raw_plan["days"][0]["transfers"][0],
            route_evidence,
            schedule,
        )
        self.assertEqual(verified["source"], "amap")
        self.assertEqual(verified["duration_minutes"], 9)
        self.assertEqual(verified["distance_meters"], 720)
        estimated = normalize_transfer(
            {
                "from_name": "模型地点",
                "to_name": "散步",
                "mode": "transit",
                "duration_minutes": 18,
                "distance_meters": 2200,
                "source": "estimate",
            },
            [],
            schedule,
        )
        self.assertEqual(estimated["source"], "estimate")
        self.assertEqual(estimated["duration_minutes"], 18)
        self.assertEqual(estimated["distance_meters"], 2200)
        aliased_anchor = normalize_transfer(
            {
                "from_name": "五一广场",
                "to_name": "岳麓山",
                "evidence_hash": "sha256:anchor-route",
            },
            [
                {
                    "origin": "112.977,28.196",
                    "destination": "112.936,28.184",
                    "mode": "transit",
                    "distance_meters": 6600,
                    "duration_seconds": 3360,
                    "source": "amap",
                    "response_hash": "sha256:anchor-route",
                }
            ],
            [
                {"name": "五一广场住宿区", "location": "112.977,28.196"},
                {"name": "岳麓山风景名胜区", "location": "112.936,28.184"},
            ],
        )
        self.assertEqual(aliased_anchor["from_name"], "五一广场住宿区")
        self.assertEqual(aliased_anchor["to_name"], "岳麓山风景名胜区")
        self.assertEqual(aliased_anchor["source"], "amap")
        specific_endpoint = normalize_transfer(
            {
                "from_name": "广州塔",
                "to_name": "广州塔璇玑地中海自助旋转餐厅(广州塔店)",
                "mode": "walking",
                "duration_minutes": 8,
                "distance_meters": 80,
                "source": "estimate",
            },
            [],
            [
                {"name": "广州塔", "location": "113.324521,23.106428"},
                {
                    "name": "广州塔璇玑地中海自助旋转餐厅(广州塔店)",
                    "location": "113.324530,23.106430",
                },
            ],
        )
        self.assertEqual(
            specific_endpoint["to_name"],
            "广州塔璇玑地中海自助旋转餐厅(广州塔店)",
        )
        explicit_endpoints = normalize_transfer(
            {
                "from_name": "喜洲古镇—洱海西岸就近午餐",
                "to_name": "洱海",
                "from_location": "100.131582,25.852950",
                "to_location": "100.223578,25.806450",
                "mode": "transit",
                "duration_minutes": 68,
                "distance_meters": 13200,
                "source": "estimate",
            },
            [],
            [
                {"name": "喜洲古镇", "location": "100.131582,25.852950"},
                {"name": "洱海", "location": "100.223578,25.806450"},
            ],
        )
        self.assertEqual(
            explicit_endpoints["from_name"],
            "喜洲古镇—洱海西岸就近午餐",
        )
        self.assertEqual(
            explicit_endpoints["from_location"],
            "100.131582,25.852950",
        )

        mismatched_route = [dict(route_evidence[0], origin="113.0,23.0")]
        mismatched = normalize_transfer(
            raw_plan["days"][0]["transfers"][0],
            mismatched_route,
            schedule,
        )
        self.assertEqual(mismatched["source"], "unknown")

    def test_schedule_normalizer_reads_nested_amap_opening_hours(self) -> None:
        normalized = normalize_schedule_item(
            {
                "type": "visit",
                "name": "橘子洲",
                "start": "14:00",
                "end": "17:00",
                "opening_match": "matched",
            },
            {
                "id": "B001",
                "name": "橘子洲风景名胜区",
                "type": "风景名胜",
                "biz_ext": {"opentime2": "周一至周日 07:00-22:00；节假日以公告为准"},
            },
        )

        self.assertEqual(
            normalized["opening_hours"],
            "周一至周日 07:00-22:00；节假日以公告为准",
        )
        self.assertEqual(normalized["opening_match"], "matched")

    def test_hard_validator_allows_unknown_opening_as_warning(self) -> None:
        place = {
            "id": "B001",
            "name": "岳麓山国家重点风景名胜区",
            "location": "112.94,28.18",
            "type": "风景名胜",
        }
        normalized = TripAgent.normalize_plan(
            single_place_plan(),
            known_places={"B001": place, "岳麓山": place},
        )
        context = build_planning_context(
            None,
            "请为我规划长沙1天行程；必去地点：岳麓山。",
        )

        report = HardValidator().validate(normalized, context)

        self.assertTrue(report["passed"])
        self.assertIn(
            "OPENING_UNVERIFIED",
            [warning["code"] for warning in report["warnings"]],
        )

    def test_validator_suggests_meal_break_without_blocking_plan(self) -> None:
        plan = single_place_plan()
        plan["days"][0]["end_time"] = "20:00"
        plan["days"][0]["schedule"].append(
            {
                "type": "free_time",
                "name": "晚间机动",
                "start": "17:00",
                "end": "20:00",
                "duration_minutes": 180,
            }
        )
        place = {
            "id": "B001",
            "name": "岳麓山国家重点风景名胜区",
            "location": "112.94,28.18",
            "type": "风景名胜",
        }
        normalized = TripAgent.normalize_plan(
            plan,
            known_places={"B001": place, "岳麓山": place},
        )

        report = HardValidator().validate(
            normalized,
            build_planning_context(
                None,
                "请为我规划长沙1天行程；必去地点：岳麓山。",
            ),
        )

        self.assertTrue(report["passed"])
        self.assertIn(
            "MEAL_BREAK_SUGGESTED",
            [warning["code"] for warning in report["warnings"]],
        )

    def test_hard_validator_rejects_date_inferred_from_weather(self) -> None:
        plan = single_place_plan()
        plan["date_range"] = {"start": "2026-09-07", "end": "2026-09-07"}
        plan["days"][0]["date"] = "2026-09-07"
        plan["days"][0]["weekday"] = "星期一"

        report = HardValidator().validate(
            plan,
            build_planning_context(None, "请规划长沙1天行程。"),
        )

        self.assertIn(
            "UNREQUESTED_DATE",
            [failure["code"] for failure in report["hard_failures"]],
        )

    def test_validator_warns_about_tight_or_estimated_transfers(self) -> None:
        plan = single_place_plan()
        plan["days"][0]["schedule"] = [
            {
                "type": "visit",
                "name": "地点甲",
                "start": "09:00",
                "end": "10:00",
                "duration_minutes": 60,
                "opening_match": "unknown",
            },
            {
                "type": "visit",
                "name": "地点乙",
                "start": "10:15",
                "end": "11:15",
                "duration_minutes": 60,
                "opening_match": "unknown",
            },
        ]
        plan["days"][0]["end_time"] = "11:15"
        plan["days"][0]["transfers"] = [
            {
                "from_name": "地点甲",
                "to_name": "地点乙",
                "mode": "transit",
                "start": "10:00",
                "end": "10:15",
            }
        ]
        first = {
            "id": "A",
            "name": "地点甲",
            "location": "112.1,28.1",
            "type": "风景名胜",
        }
        second = {
            "id": "B",
            "name": "地点乙",
            "location": "112.2,28.2",
            "type": "风景名胜",
        }
        normalized = TripAgent.normalize_plan(
            plan,
            known_places={"A": first, "地点甲": first, "B": second, "地点乙": second},
            route_evidence=[
                {
                    "origin": "112.1,28.1",
                    "destination": "112.2,28.2",
                    "mode": "transit",
                    "distance_meters": 1200,
                    "duration_seconds": 600,
                    "source": "amap",
                    "response_hash": "sha256:route",
                }
            ],
        )

        report = HardValidator().validate(
            normalized,
            build_planning_context(None, "请规划长沙1天行程。"),
        )

        conflict = next(
            warning
            for warning in report["warnings"]
            if warning["code"] == "TIGHT_TRANSFER"
        )
        self.assertEqual(conflict["path"], "$.days[0].transfers[0]")
        normalized["days"][0]["schedule"][1].update(
            {"start": "10:30", "end": "11:30", "duration_minutes": 60}
        )
        normalized["days"][0]["end_time"] = "11:30"
        normalized["days"][0]["transfers"][0].update({"start": "09:50", "end": "10:00"})
        misaligned = HardValidator().validate(
            normalized,
            build_planning_context(None, "请规划长沙1天行程。"),
        )
        self.assertIn(
            "TRANSFER_TIME_ESTIMATED",
            [warning["code"] for warning in misaligned["warnings"]],
        )

    def test_normalizer_derives_duration_from_fixed_timeline(self) -> None:
        plan = single_place_plan()
        plan["days"][0]["schedule"][0]["start"] = "09:15"
        plan["days"][0]["schedule"][0]["end"] = "11:00"
        plan["days"][0]["schedule"][0]["duration_minutes"] = 999
        place = {
            "id": "B001",
            "name": "岳麓山国家重点风景名胜区",
            "location": "112.94,28.18",
            "type": "风景名胜",
        }

        normalized = TripAgent.normalize_plan(
            plan,
            known_places={"B001": place, "岳麓山": place},
        )

        self.assertEqual(normalized["days"][0]["schedule"][0]["duration_minutes"], 105)

    def test_normalizer_keeps_area_anchor_and_unknown_reservation_semantics(
        self,
    ) -> None:
        plan = single_place_plan()
        plan["days"][0]["schedule"][0]["reservation"] = {
            "required": False,
            "status": "not_required",
            "note": None,
        }
        plan["hotel"]["status"] = "confirmed"
        plan["days"][0]["start_anchor"]["type"] = "hotel"
        plan["days"][0]["end_anchor"]["type"] = "hotel"
        plan["days"][0]["schedule"][0]["reservation"] = {
            "required": None,
            "status": "unknown",
            "note": "出发前核验",
        }
        area = {
            "id": "AREA1",
            "name": "五一广场",
            "location": "112.97,28.19",
            "type": "风景名胜;公园广场;城市广场",
        }
        place = {
            "id": "B001",
            "name": "岳麓山国家重点风景名胜区",
            "location": "112.94,28.18",
            "type": "风景名胜",
        }

        normalized = TripAgent.normalize_plan(
            plan,
            known_places={
                "AREA1": area,
                "五一广场": area,
                "B001": place,
                "岳麓山": place,
            },
        )

        self.assertEqual(normalized["hotel"]["status"], "recommended_area")
        self.assertEqual(normalized["days"][0]["start_anchor"]["type"], "area")
        self.assertIsNone(
            normalized["days"][0]["schedule"][0]["reservation"]["required"]
        )
        self.assertEqual(
            normalized["days"][0]["schedule"][0]["reservation"]["status"],
            "unknown",
        )

    def test_area_hotel_and_named_station_share_verified_anchor(self) -> None:
        plan = single_place_plan()
        plan["days"][0]["start_anchor"] = {
            "name": "五一广场(地铁站)",
            "type": "station",
        }
        plan["days"][0]["end_anchor"] = {
            "name": "五一广场(地铁站)",
            "type": "station",
        }
        station = {
            "id": "BV10231156",
            "name": "五一广场(地铁站)",
            "location": "112.976433,28.195317",
            "type": "交通设施服务;地铁站",
        }
        place = {
            "id": "B001",
            "name": "岳麓山国家重点风景名胜区",
            "location": "112.94,28.18",
            "type": "风景名胜",
        }
        restaurant = {
            "id": "B002",
            "name": "龙锦人家·长沙家菜馆(五一广场店)",
            "location": "112.976105,28.195945",
            "type": "餐饮服务;中餐厅",
        }

        normalized = TripAgent.normalize_plan(
            plan,
            known_places={
                "BV10231156": station,
                "五一广场地铁站": station,
                "B001": place,
                "岳麓山": place,
                "B002": restaurant,
                "龙锦人家长沙家菜馆五一广场店": restaurant,
            },
        )
        context = build_planning_context(
            None,
            "请规划长沙1天行程。住五一广场住宿区，必去岳麓山；09:00至20:00。",
        )
        report = HardValidator().validate(normalized, context)
        failure_codes = [failure["code"] for failure in report["hard_failures"]]

        self.assertEqual(normalized["hotel"]["place_id"], "BV10231156")
        self.assertEqual(
            normalized["days"][0]["start_anchor"]["place_id"],
            "BV10231156",
        )
        self.assertNotIn("HOTEL_LOOP_MISMATCH", failure_codes)
        self.assertNotIn("ANCHOR_ROUTE_UNVERIFIED", failure_codes)

    def test_place_resolver_does_not_match_empty_place_id(self) -> None:
        hotel = {"id": "H001", "name": "珠江新城地铁站"}
        attraction = {"id": "P001", "name": "陈家祠"}

        resolved = TripAgent._resolve_place_evidence(
            {"name": "陈家祠"},
            {"": hotel, "陈家祠": attraction},
        )

        self.assertIs(resolved, attraction)
        area = TripAgent._resolve_place_evidence(
            {"name": "体育西路—珠江新城"},
            {"体育西路珠江新城": hotel},
        )
        self.assertIs(area, hotel)

    def test_visit_place_selection_rejects_exact_named_address_hotspot(self) -> None:
        selected = _select_place(
            {
                "places": [
                    {
                        "id": "wrong",
                        "name": "陈家祠",
                        "location": "113.1,23.1",
                        "type": "地名地址信息;热点地名",
                    },
                    {
                        "id": "right",
                        "name": "陈家祠堂",
                        "location": "113.2,23.2",
                        "type": "风景名胜;人文景观",
                    },
                ]
            },
            name="陈家祠",
            query="陈家祠 广州",
            stop_type="visit",
        )

        self.assertEqual(selected["id"], "right")

    def test_hard_validator_warns_for_unresolved_requested_hotel_anchor(self) -> None:
        place = {
            "id": "B001",
            "name": "岳麓山国家重点风景名胜区",
            "location": "112.94,28.18",
            "type": "风景名胜",
            "response_hash": "sha256:stale-place",
            "fetched_at": 1_789_000_000.0,
            "stale": True,
        }
        normalized = TripAgent.normalize_plan(
            single_place_plan(),
            known_places={"B001": place, "岳麓山": place},
        )
        context = build_planning_context(
            None,
            ("请规划长沙1天行程。住五一广场住宿区，必去岳麓山；09:00至20:00。"),
        )

        report = HardValidator().validate(normalized, context)

        self.assertTrue(report["passed"])
        self.assertIn(
            "ANCHOR_ROUTE_UNVERIFIED",
            [warning["code"] for warning in report["warnings"]],
        )
        self.assertIn(
            "STALE_PLACE_EVIDENCE",
            [warning["code"] for warning in report["warnings"]],
        )

    def test_context_survives_question_without_an_accepted_plan(self) -> None:
        context = build_planning_context(
            None,
            "同行两位成人",
            [
                {
                    "role": "user",
                    "content": "请为我规划青岛3天行程；必去地点：栈桥、八大关。",
                },
                {"role": "assistant", "content": "请确认酒店区域"},
            ],
        )

        self.assertEqual(context["destination"], "青岛")
        self.assertEqual(context["days"], 3)
        self.assertEqual(context["must_visits"], ["栈桥", "八大关"])
        self.assertEqual(context["latest_request"], "同行两位成人")
        self.assertEqual(context["revision"], 2)

    async def test_weather_falls_back_to_amap_without_exposing_provider_error(
        self,
    ) -> None:
        class BrokenQWeather:
            available = True

            async def forecast(self, city: str, days: int) -> dict:
                raise RuntimeError("provider request failed")

        class WeatherAmap:
            available = True

            async def weather(self, city: str) -> dict:
                return {
                    "provider": "amap",
                    "available": True,
                    "days": [{"date": "2026-09-02"}],
                    "cache_hit": False,
                    "response_hash": "sha256:weather",
                }

        provider = WeatherProvider(amap=WeatherAmap())
        provider.qweather = BrokenQWeather()
        result = await provider.forecast("长沙", 1)

        self.assertEqual(result["provider"], "amap")
        self.assertEqual(result["fallback_from"], "qweather")
        self.assertEqual(result["fallback_reason"], "RuntimeError")

    async def test_provider_cache_turns_second_request_into_hot_hit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(Path(directory) / "cache.sqlite")
            provider = AmapProvider(cache)
            provider.api_key = "test-key"
            request_count = 0

            def handler(request: httpx.Request) -> httpx.Response:
                nonlocal request_count
                request_count += 1
                return httpx.Response(
                    200,
                    json={
                        "status": "1",
                        "pois": [
                            {"id": "B001", "name": "岳麓山", "location": "112.94,28.18"}
                        ],
                    },
                )

            provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            first = await provider.search_places("长沙", "岳麓山")
            second = await provider.search_places("长沙", "岳麓山")
            await provider.close()
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(request_count, 1)
            self.assertEqual(cache.stats(), {"entries": 1, "fresh_entries": 1})

    def test_stale_cache_respects_maximum_fetch_age(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(Path(directory) / "cache.sqlite")
            request = {"city": "广州", "keywords": "广州塔"}
            cache.put(
                "amap",
                "place_search",
                request,
                {"status": "1", "pois": []},
                ttl_seconds=0,
                latency_ms=1,
            )

            self.assertIsNotNone(
                cache.get_stale(
                    "amap",
                    "place_search",
                    request,
                    max_age_seconds=60,
                )
            )
            self.assertIsNone(
                cache.get_stale(
                    "amap",
                    "place_search",
                    request,
                    max_age_seconds=0,
                )
            )

    async def test_amap_stale_fallback_exposes_age_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(Path(directory) / "cache.sqlite")
            request = {
                "city": "广州",
                "keywords": "广州塔",
                "offset": 8,
                "page": 1,
                "extensions": "all",
                "citylimit": "true",
            }
            cache.put(
                "amap",
                "place_search",
                request,
                {
                    "status": "1",
                    "pois": [
                        {
                            "id": "B001",
                            "name": "广州塔",
                            "location": "113.32,23.11",
                        }
                    ],
                },
                ttl_seconds=0,
                latency_ms=1,
            )
            provider = AmapProvider(cache)
            provider.api_key = "test-key"
            provider.min_interval = 0

            def handler(_request: httpx.Request) -> httpx.Response:
                return httpx.Response(503)

            provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            result = await provider.search_places("广州", "广州塔")
            await provider.close()

            self.assertTrue(result["stale"])
            self.assertIsInstance(result["fetched_at"], float)

    async def test_amap_resolves_compound_destination_to_city_adcode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = AmapProvider(ProviderCache(Path(directory) / "cache.sqlite"))
            provider.api_key = "test-key"
            provider.min_interval = 0
            request_count = 0

            def handler(request: httpx.Request) -> httpx.Response:
                nonlocal request_count
                request_count += 1
                districts = [
                    {
                        "citycode": "020",
                        "adcode": "440100",
                        "name": "广州市",
                        "center": "113.264499,23.130061",
                        "level": "city",
                        "districts": [
                            {
                                "citycode": "020",
                                "adcode": "440113",
                                "name": "番禺区",
                                "center": "113.384129,22.937244",
                                "level": "district",
                                "districts": [],
                            }
                        ],
                    }
                ]
                return httpx.Response(
                    200,
                    json={"status": "1", "info": "OK", "districts": districts},
                )

            provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            result = await provider.resolve_search_city("广州番禺")
            await provider.close()

            self.assertEqual(result["search_city"], "440113")
            self.assertEqual(result["name"], "番禺区")
            self.assertEqual(request_count, 1)

    async def test_amap_retries_transient_qps_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = AmapProvider(ProviderCache(Path(directory) / "cache.sqlite"))
            provider.api_key = "test-key"
            provider.min_interval = 0
            request_count = 0

            def handler(_request: httpx.Request) -> httpx.Response:
                nonlocal request_count
                request_count += 1
                if request_count == 1:
                    return httpx.Response(
                        200,
                        json={
                            "status": "0",
                            "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT",
                        },
                    )
                return httpx.Response(
                    200,
                    json={
                        "status": "1",
                        "pois": [
                            {
                                "id": "B001",
                                "name": "广州塔",
                                "location": "113.324521,23.106428",
                            }
                        ],
                    },
                )

            provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            result = await provider.search_places("广州", "广州塔")
            await provider.close()

            self.assertEqual(request_count, 2)
            self.assertEqual(result["places"][0]["name"], "广州塔")

    def test_context_parses_relaxed_public_transit_request(self) -> None:
        context = build_planning_context(
            None,
            "我想去广州番禺玩三天，住长隆附近，"
            "想去长隆野生动物世界、广州长隆欢乐世界和沙湾古镇，"
            "公共交通为主，每天不要太赶。",
        )

        self.assertEqual(context["pace"], "relaxed")
        self.assertEqual(context["transport"], "public_transit")
        self.assertEqual(
            context["must_visits"],
            ["长隆野生动物世界", "广州长隆欢乐世界", "沙湾古镇"],
        )

    def test_context_does_not_split_place_name_containing_conjunction(self) -> None:
        context = build_planning_context(
            None,
            "我要去上海玩三天；必去地点：上海和平饭店、外滩。",
        )
        conjunction = build_planning_context(
            None,
            "我要去广州玩三天；必去地点：广州塔和越秀公园。",
        )

        self.assertEqual(context["must_visits"], ["上海和平饭店", "外滩"])
        self.assertEqual(conjunction["must_visits"], ["广州塔", "越秀公园"])

    def test_relaxed_skeleton_trims_optional_non_meal_stops(self) -> None:
        skeleton = skeleton_plan()
        skeleton["days"][0]["stops"].extend(
            [
                {
                    "type": "visit",
                    "name": "岳麓书院",
                    "search_query": "岳麓书院",
                    "period": "afternoon",
                    "duration_minutes": 90,
                    "optional": True,
                },
                {
                    "type": "visit",
                    "name": "爱晚亭",
                    "search_query": "爱晚亭",
                    "period": "evening",
                    "duration_minutes": 60,
                    "optional": True,
                },
            ]
        )

        repaired, repairs = repair_skeleton(
            skeleton,
            {
                "destination": "长沙",
                "days": 1,
                "pace": "relaxed",
                "must_visits": [],
                "daily_window": {"start": "09:00", "end": "20:00"},
            },
        )

        stops = repaired["days"][0]["stops"]
        self.assertLessEqual(
            sum(stop["type"] != "meal" for stop in stops),
            1,
        )
        self.assertEqual(sum(stop["type"] == "meal" for stop in stops), 3)
        self.assertTrue(any(item["reason"] == "trim_relaxed_stop" for item in repairs))

    def test_relaxed_skeleton_keeps_one_required_major_attraction(self) -> None:
        skeleton = skeleton_plan()
        skeleton["days"][0]["stops"] = [
            {
                "type": "visit",
                "name": "长隆野生动物世界",
                "search_query": "长隆野生动物世界",
                "period": "morning",
                "duration_minutes": 180,
                "optional": False,
            },
            {
                "type": "visit",
                "name": "长隆水上乐园",
                "search_query": "长隆水上乐园",
                "period": "afternoon",
                "duration_minutes": 120,
                "optional": True,
            },
        ]

        repaired, _ = repair_skeleton(
            skeleton,
            {
                "destination": "广州番禺",
                "days": 1,
                "pace": "relaxed",
                "must_visits": ["长隆野生动物世界"],
                "daily_window": {"start": "09:00", "end": "20:00"},
            },
        )

        names = [stop["name"] for stop in repaired["days"][0]["stops"]]
        self.assertIn("长隆野生动物世界", names)
        self.assertNotIn("长隆水上乐园", names)

    def test_relaxed_skeleton_spreads_required_major_attractions(self) -> None:
        skeleton = skeleton_plan(days=3)
        skeleton["days"][0]["stops"] = [
            {
                "type": "visit",
                "name": "长隆野生动物世界",
                "search_query": "长隆野生动物世界",
                "period": "morning",
                "duration_minutes": 180,
                "optional": False,
            },
            {
                "type": "visit",
                "name": "广州长隆欢乐世界",
                "search_query": "广州长隆欢乐世界",
                "period": "afternoon",
                "duration_minutes": 180,
                "optional": False,
            },
        ]

        repaired, repairs = repair_skeleton(
            skeleton,
            {
                "destination": "广州番禺",
                "days": 3,
                "pace": "relaxed",
                "must_visits": [
                    "长隆野生动物世界",
                    "广州长隆欢乐世界",
                ],
                "daily_window": {"start": "09:00", "end": "20:00"},
            },
        )

        major_days = [
            day["day"]
            for day in repaired["days"]
            for stop in day["stops"]
            if "野生动物世界" in stop["name"] or "欢乐世界" in stop["name"]
        ]
        self.assertEqual(len(major_days), 2)
        self.assertEqual(len(set(major_days)), 2)
        self.assertTrue(
            any(item["reason"] == "spread_relaxed_major_stop" for item in repairs)
        )

    def test_visit_selection_prefers_official_recreation_poi(self) -> None:
        selected = _select_place(
            {
                "places": [
                    {
                        "id": "official",
                        "name": "长隆欢乐世界",
                        "area": "番禺区",
                        "location": "113.3296,22.9990",
                        "type": "体育休闲服务;休闲场所;游乐场",
                    },
                    {
                        "id": "unofficial",
                        "name": "广州长隆欢乐世界(玩圣)",
                        "area": "番禺区",
                        "location": "113.3267,22.9960",
                        "type": "风景名胜;风景名胜",
                    },
                ]
            },
            name="广州长隆欢乐世界",
            query="广州长隆欢乐世界",
            stop_type="visit",
            area_hint="番禺区",
        )

        self.assertEqual(selected["id"], "official")

    def test_required_place_matches_city_prefixed_official_name(self) -> None:
        self.assertTrue(_matches("长隆欢乐世界南门游客中心", "广州长隆欢乐世界"))

    def test_validator_matches_city_prefixed_required_place(self) -> None:
        self.assertTrue(_matches_key("广州长隆欢乐世界", "长隆欢乐世界北门广场"))
        self.assertTrue(_matches_key("滇池或海埂一带", "滇池海埂公园"))
        self.assertTrue(_matches_key("滇池海埂一带", "滇池海埂公园"))
        self.assertTrue(
            _matches_key(
                "洱海西岸优先廊桥或磻溪S弯附近",
                "洱海西岸廊桥",
            )
        )

    def test_place_selection_rejects_cross_district_exact_match(self) -> None:
        selected = _select_place(
            {
                "places": [
                    {
                        "id": "wrong",
                        "name": "沙湾姜撞奶甜品店",
                        "area": "海珠区",
                        "location": "113.31,23.08",
                        "type": "餐饮服务",
                    }
                ]
            },
            name="沙湾姜撞奶甜品店",
            query="沙湾姜撞奶甜品店",
            stop_type="meal",
            area_hint="番禺区",
        )

        self.assertIsNone(selected)

    def test_hotel_selection_ignores_exact_named_transit_station(self) -> None:
        selected = _select_place(
            {
                "places": [
                    {
                        "id": "station",
                        "name": "塘子巷地铁站",
                        "area": "盘龙区",
                        "location": "102.72,25.04",
                        "type": "交通设施服务;地铁站",
                    },
                    {
                        "id": "hotel",
                        "name": "塘子巷轻居酒店",
                        "area": "盘龙区",
                        "location": "102.72,25.04",
                        "type": "住宿服务;宾馆酒店",
                    },
                ]
            },
            name="塘子巷地铁站附近",
            query="昆明塘子巷地铁站附近酒店",
            stop_type="hotel",
        )

        self.assertEqual(selected["id"], "hotel")

    def test_place_selection_rejects_semantically_unrelated_visit(self) -> None:
        selected = _select_place(
            {
                "places": [
                    {
                        "id": "wrong-shore",
                        "name": "洱海公园",
                        "area": "大理市",
                        "location": "100.231,25.584",
                        "type": "风景名胜;公园广场",
                    }
                ]
            },
            name="洱海西岸",
            query="洱海西岸",
            stop_type="visit",
            area_hint="大理市",
        )

        self.assertIsNone(selected)

    def test_skeleton_repair_removes_transport_hub_as_visit(self) -> None:
        skeleton = skeleton_plan("昆明", 1)
        skeleton["days"][0]["stops"] = [
            {
                "type": "visit",
                "name": "昆明长水国际机场",
                "period": "morning",
                "visit_scale": "quick_stop",
                "reason": "抵达并取行李。",
                "optional": False,
            },
            {
                "type": "visit",
                "name": "翠湖公园",
                "period": "afternoon",
                "visit_scale": "standard",
                "reason": "沿湖散步。",
                "optional": False,
            },
        ]

        repaired, repairs = repair_skeleton(
            skeleton,
            {"destination": "昆明", "days": 1, "must_visits": []},
        )

        self.assertEqual(
            [
                item["name"]
                for item in repaired["days"][0]["stops"]
                if item["type"] == "visit"
            ],
            ["翠湖公园"],
        )
        self.assertTrue(
            any(item["reason"] == "remove_transport_hub_stop" for item in repairs)
        )

    def test_place_selection_rejects_paused_venue(self) -> None:
        selected = _select_place(
            {
                "places": [
                    {
                        "id": "paused",
                        "name": "番禺博物馆(暂停开放)",
                        "area": "番禺区",
                        "location": "113.34,22.95",
                        "type": "科教文化服务",
                    }
                ]
            },
            name="番禺博物馆",
            query="广州番禺博物馆",
            stop_type="visit",
            area_hint="番禺区",
        )

        self.assertIsNone(selected)

    async def test_agent_publishes_progress_while_run_is_active(self) -> None:
        published: list[dict] = []
        agent = TripAgent(SkeletonLLM(), amap=FakeAmap())

        response = await agent.run("想旅行", on_event=published.append)

        self.assertEqual(published, response.events)
        self.assertEqual(
            [event["type"] for event in published],
            ["run_started", "assistant_message", "run_finished"],
        )
        self.assertTrue(all(event["elapsed_ms"] >= 0 for event in published))

    async def test_stream_chat_events_yields_progress_before_result(self) -> None:
        class StreamingAgent:
            async def run(self, message, session_id, on_event):
                on_event({"type": "run_started", "elapsed_ms": 0})
                await asyncio.sleep(0.01)
                return ChatResponse(
                    session_id="session-1",
                    run_id="run-1",
                    reply="请补充目的地",
                    events=[],
                )

        active_runtime = SimpleNamespace(
            agent=StreamingAgent(), request_timeout_seconds=1
        )
        stream = stream_chat_events(ChatRequest(message="想旅行"), active_runtime)

        first = await anext(stream)
        remaining = [chunk async for chunk in stream]
        first_payload = json.loads(
            next(line[5:] for line in first.splitlines() if line.startswith("data:"))
        )
        result_payload = json.loads(
            next(
                line[5:]
                for line in "".join(remaining).splitlines()
                if line.startswith("data:")
            )
        )

        self.assertEqual(first_payload["type"], "progress")
        self.assertEqual(first_payload["event"]["type"], "run_started")
        self.assertEqual(result_payload["type"], "result")
        self.assertEqual(result_payload["result"]["run_id"], "run-1")

    async def test_stream_chat_events_returns_typed_timeout(self) -> None:
        class SlowAgent:
            async def run(self, message, session_id, on_event):
                on_event({"type": "run_started", "elapsed_ms": 0})
                await asyncio.sleep(1)

        active_runtime = SimpleNamespace(
            agent=SlowAgent(), request_timeout_seconds=0.001
        )
        chunks = [
            chunk
            async for chunk in stream_chat_events(
                ChatRequest(message="想旅行"), active_runtime
            )
        ]
        payloads = [
            json.loads(line[5:])
            for line in "".join(chunks).splitlines()
            if line.startswith("data:")
        ]

        self.assertEqual(payloads[-1]["type"], "error")
        self.assertEqual(payloads[-1]["error"]["code"], "planning_timeout")

    async def test_stream_chat_events_returns_typed_service_unavailable(self) -> None:
        class UnavailableAgent:
            async def run(self, message, session_id, on_event):
                on_event({"type": "run_started", "elapsed_ms": 0})
                raise LLMServiceUnavailableError("gateway unavailable")

        active_runtime = SimpleNamespace(
            agent=UnavailableAgent(), request_timeout_seconds=1
        )
        chunks = [
            chunk
            async for chunk in stream_chat_events(
                ChatRequest(message="想旅行"), active_runtime
            )
        ]
        payloads = [
            json.loads(line[5:])
            for line in "".join(chunks).splitlines()
            if line.startswith("data:")
        ]

        self.assertEqual(payloads[-1]["type"], "error")
        self.assertEqual(payloads[-1]["error"]["code"], "planning_service_unavailable")
        self.assertNotIn("RuntimeError", payloads[-1]["error"]["message"])

    def test_context_parses_compact_natural_language_constraints(self) -> None:
        context = build_planning_context(
            None,
            ("请规划长沙1天行程。住五一广场住宿区，必去岳麓山、橘子洲；09:00至20:00。"),
        )

        self.assertEqual(context["destination"], "长沙")
        self.assertEqual(context["days"], 1)
        self.assertEqual(context["hotel_area"], "五一广场住宿区")
        self.assertEqual(context["must_visits"], ["岳麓山", "橘子洲"])
        self.assertEqual(context["daily_window"], {"start": "09:00", "end": "20:00"})
        labeled = build_planning_context(
            None,
            "请规划长沙1天行程。住宿地点或区域：五一广场住宿区。",
        )
        self.assertEqual(labeled["hotel_area"], "五一广场住宿区")
        conversational = build_planning_context(
            None,
            "我要去广州玩三天，给我规划一下行程，要具体，要合理",
        )
        self.assertEqual(conversational["destination"], "广州")
        self.assertEqual(conversational["days"], 3)

    def test_context_parses_detailed_multi_city_request(self) -> None:
        context = build_planning_context(
            None,
            "请为两位30岁左右、体力正常的成人规划一趟"
            "2026年9月12日至9月16日的昆明＋大理5天4晚旅行。"
            "9月12日10:30抵达昆明长水机场，"
            "9月16日18:30从大理凤仪机场返程；昆明住2晚，大理住2晚。"
            "每天大约9点出门，21点前回酒店，整体节奏均衡。"
            "昆明必去云南省博物馆、滇池或海埂一带，想吃过桥米线；"
            "大理必去大理古城、喜洲和洱海西岸，不安排大型演出。"
            "市内公共交通+短途打车。人均预算4500元。",
        )

        self.assertEqual(context["destination"], "昆明、大理")
        self.assertEqual(
            [item["destination"] for item in context["destinations"]],
            ["昆明", "大理"],
        )
        self.assertEqual(context["days"], 5)
        self.assertEqual(context["nights"], 4)
        self.assertEqual(context["start_date"], "2026-09-12")
        self.assertEqual(context["arrival"], {"time": "10:30"})
        self.assertEqual(context["departure"], {"time": "18:30"})
        self.assertIsNone(context.get("hotel_area"))
        self.assertEqual(context["party"], {"adults": 2})
        self.assertEqual(context["pace"], "balanced")
        self.assertEqual(context["transport"], "public_transit")
        self.assertEqual(
            build_planning_context(
                None,
                "市内以公共交通加短途打车为主。",
            )["transport"],
            "public_transit",
        )
        self.assertEqual(
            context["must_visits"],
            ["云南省博物馆", "滇池或海埂一带", "大理古城", "喜洲", "洱海西岸"],
        )
        self.assertEqual(context["daily_window"], {"start": "09:00", "end": "21:00"})
        self.assertEqual(
            context["budget_range"],
            {"per_person": 4500, "currency": "CNY"},
        )

    def test_memory_policy_compacts_history_and_previous_plan(self) -> None:
        policy = MemoryPolicy(
            history_messages=2,
            message_chars=160,
            plan_days=2,
            schedule_items_per_day=2,
        )
        history = [
            {"role": "user", "content": f"第{index}轮" + "长" * 300}
            for index in range(4)
        ]
        plan = {
            "city": "长沙",
            "title": "长沙三日行程",
            "overview": "不应进入模型记忆的长篇介绍",
            "days": [
                {
                    "day": day,
                    "summary": "摘要",
                    "schedule": [
                        {
                            "name": f"第{day}天地点{item}",
                            "start": "09:00",
                            "end": "10:00",
                        }
                        for item in range(3)
                    ],
                }
                for day in range(1, 4)
            ],
        }

        compact_history = compact_conversation_history(history, policy)
        compact_plan = compact_plan_memory(plan, policy)
        compact_repair = compact_repair_memory(
            {
                "candidate_plan": plan,
                "validation_report": {
                    "hard_failures": [
                        {
                            "code": "ROUTE_TIME_CONFLICT",
                            "path": "$.days[0].schedule[1]",
                            "message": "通勤时间不足",
                            "internal_debug": "不应发送",
                        }
                    ],
                    "repairs_remaining": 2,
                },
            },
            policy,
        )

        self.assertEqual(len(compact_history), 2)
        self.assertTrue(compact_history[0]["content"].startswith("第2轮"))
        self.assertTrue(all(len(item["content"]) <= 160 for item in compact_history))
        self.assertNotIn("overview", compact_plan)
        self.assertEqual(len(compact_plan["days"]), 2)
        self.assertEqual(len(compact_plan["days"][0]["schedule"]), 2)
        self.assertEqual(
            compact_plan["memory_limits"],
            {"source_days": 3, "included_days": 2, "items_truncated": True},
        )
        self.assertNotIn(
            "overview",
            compact_repair["candidate_plan_digest"],
        )
        self.assertEqual(
            compact_repair["validation_report"]["hard_failures"][0],
            {
                "code": "ROUTE_TIME_CONFLICT",
                "path": "$.days[0].schedule[1]",
                "message": "通勤时间不足",
            },
        )

    def test_structured_log_redacts_secrets_and_keeps_timing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "planning.jsonl"
            configure_logging(path)
            log_event(
                "llm_request_finished",
                run_id="run-1",
                total_ms=1234,
                api_key="must-not-leak",
            )
            record = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
            close_logging()

        self.assertEqual(record["event"], "llm_request_finished")
        self.assertEqual(record["total_ms"], 1234)
        self.assertEqual(record["api_key"], "[REDACTED]")

    def test_trip_store_survives_reopen_and_restores_latest_itinerary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trips.sqlite"
            store = TripStore(path)
            store.save_exchange(
                session_id="session-1",
                run_id="run-1",
                user_message="长沙三天",
                reply="已经规划完成",
                plan={"city": "长沙", "title": "长沙三日行程"},
                events=[{"type": "run_finished", "elapsed_ms": 1200}],
            )
            reopened = TripStore(path)

            summaries = reopened.list_sessions()
            detail = reopened.get_session("session-1")

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["title"], "长沙三日行程")
        self.assertEqual(detail["latest"]["plan"]["city"], "长沙")
        self.assertEqual(
            [message["role"] for message in detail["messages"]],
            ["user", "assistant"],
        )

    async def test_agent_restores_saved_plan_for_follow_up_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = TripStore(Path(directory) / "trips.sqlite")
            store.save_exchange(
                session_id="session-1",
                run_id="run-1",
                user_message="长沙三天",
                reply="已经规划完成",
                plan={
                    "city": "长沙",
                    "title": "长沙三日行程",
                    "overview": "这段完整介绍不应重复发送给模型",
                    "days": [{"day": 1}, {"day": 2}, {"day": 3}],
                },
                events=[],
            )
            llm = SkeletonLLM(skeleton_plan("长沙", 3))
            agent = TripAgent(llm, amap=FakeAmap(), store=store)

            response = await agent.run("把第二天下午改得轻松一些", "session-1")

            restored_context = "\n".join(
                message["content"] for message in llm.messages[0]
            )

        self.assertIn('"planning_context"', restored_context)
        self.assertIn('"previous_plan_digest":{"city":"长沙"', restored_context)
        self.assertIn("长沙三日行程", restored_context)
        self.assertNotIn("这段完整介绍不应重复发送给模型", restored_context)
        self.assertIn("session_restored", [event["type"] for event in response.events])
        model_started = next(
            event for event in response.events if event["type"] == "model_started"
        )
        self.assertEqual(model_started["phase"], "complete_plan")

    def test_guest_quota_account_upgrade_and_owner_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = TripStore(Path(directory) / "platform.sqlite")
            auth = AuthManager(store._sessions)
            guest = auth._issue(None).identity
            request = Request(
                {"type": "http", "client": ("203.0.113.7", 1234), "headers": []}
            )
            for remaining in range(4, -1, -1):
                self.assertEqual(auth.consume_quota(guest, request)[0], remaining)
            with self.assertRaises(HTTPException) as rejected:
                auth.consume_quota(guest, request)
            self.assertEqual(rejected.exception.status_code, 429)

            store.save_exchange(
                owner=guest.owner,
                session_id="private-trip",
                run_id="private-run",
                user_message="长沙三天",
                reply="完成",
                plan={"city": "长沙", "title": "长沙三日行程", "days": [{"day": 1}]},
                events=[],
            )
            user_session = auth.register("旅行者一号", "correct-horse-battery", guest)
            store.claim_guest_trips(guest.id, user_session.identity.id)

            self.assertIsNone(store.get_session("private-trip", guest.owner))
            self.assertIsNotNone(
                store.get_session("private-trip", user_session.identity.owner)
            )
            self.assertEqual(
                auth.login(
                    "旅行者一号", "correct-horse-battery", "203.0.113.7"
                ).identity.id,
                user_session.identity.id,
            )
            store.close()

    def test_guest_share_is_unlisted_until_account_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = TripStore(Path(directory) / "sharing.sqlite")
            auth = AuthManager(store._sessions)
            guest = auth._issue(None).identity
            store.save_exchange(
                owner=guest.owner,
                session_id="share-trip",
                run_id="share-run",
                user_message="青岛两天",
                reply="完成",
                plan={
                    "city": "青岛",
                    "title": "青岛海岸两日",
                    "days": [{"day": 1}, {"day": 2}],
                },
                events=[],
            )
            unlisted = store.publish("share-trip", guest.owner)
            self.assertEqual(unlisted["visibility"], "unlisted")
            self.assertEqual(store.list_public(), [])

            user = auth.register("青岛旅人", "correct-horse-battery", guest).identity
            store.claim_guest_trips(guest.id, user.id)
            published = store.publish("share-trip", user.owner)

            self.assertEqual(published["visibility"], "public")
            self.assertEqual(
                store.get_public(published["slug"])["plan"]["city"], "青岛"
            )
            self.assertEqual(len(store.list_public(city="青岛", days=2)), 1)
            store.close()

    def test_rich_multi_destination_request_preserves_user_constraints(self) -> None:
        request = StructuredTripRequest(
            destination="昆明、大理、丽江",
            destinations=[
                {"name": "昆明", "days": 3},
                {"name": "大理", "days": 2},
                {"name": "丽江", "days": 4},
            ],
            days=9,
            date_range={"start": "2026-09-26", "end": "2026-10-04"},
            arrival={
                "date": "2026-09-26",
                "time": "20:00",
                "station": "昆明长水机场",
            },
            departure={
                "date": "2026-10-04",
                "time": "14:00",
                "station": "丽江三义机场",
            },
            party={
                "adults": 2,
                "children_ages": [6, 10],
                "rooms": 2,
                "bed_requirement": "双床房",
            },
            budget_range={"total_max": 12000, "currency": "CNY"},
            dietary_requirements=["不吃辣"],
            mobility_needs=["午后休息"],
        )
        context = build_planning_context(
            None,
            "请按表单生成",
            structured_request=request.model_dump(mode="json"),
        )

        self.assertEqual(context["days"], 9)
        self.assertEqual(
            [item["destination"] for item in context["destinations"]],
            ["昆明", "大理", "丽江"],
        )
        self.assertEqual([item["days"] for item in context["destinations"]], [3, 2, 4])
        self.assertEqual(context["arrival"]["time"], "20:00")
        self.assertEqual(context["departure"]["station"], "丽江三义机场")
        self.assertEqual(context["party"]["children_ages"], [6, 10])
        self.assertEqual(context["budget_range"]["total_max"], 12000)
        self.assertEqual(context["dietary_requirements"], ["不吃辣"])
        self.assertEqual(context["mobility_needs"], ["午后休息"])

    def test_multi_destination_request_rejects_inconsistent_dates_and_days(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            StructuredTripRequest(
                destination="昆明、大理",
                destinations=[
                    {"name": "昆明", "days": 3},
                    {"name": "大理", "days": 2},
                ],
                days=6,
                date_range={"start": "2026-09-26", "end": "2026-10-01"},
            )
        with self.assertRaises(ValueError):
            StructuredTripRequest(
                destination="昆明、大理",
                destinations=[{"name": "昆明", "days": 3}, {"name": "大理"}],
                days=5,
            )

    def test_repair_skeleton_allocates_nine_days_across_three_cities(self) -> None:
        context = build_planning_context(
            None,
            "请按表单生成",
            structured_request={
                "destination": "昆明、大理、丽江",
                "destinations": [
                    {"name": "昆明", "days": 3},
                    {"name": "大理", "days": 2},
                    {"name": "丽江", "days": 4},
                ],
                "days": 9,
                "daily_window": {"start": "09:00", "end": "20:00"},
            },
        )

        repaired, _ = repair_skeleton({"days": []}, context)

        self.assertEqual(len(repaired["days"]), 9)
        self.assertEqual(
            [day["destination"] for day in repaired["days"]],
            ["昆明"] * 3 + ["大理"] * 2 + ["丽江"] * 4,
        )
        self.assertEqual(
            [hotel["destination"] for hotel in repaired["hotels"]],
            ["昆明", "大理", "丽江"],
        )
        self.assertTrue(all(1 <= len(day["stops"]) <= 5 for day in repaired["days"]))

    def test_repair_skeleton_completes_missing_intercity_leg(self) -> None:
        context = build_planning_context(
            None,
            "请按表单生成",
            structured_request={
                "destination": "昆明、大理",
                "destinations": [
                    {"name": "昆明", "days": 1},
                    {"name": "大理", "days": 1},
                ],
                "days": 2,
                "intercity_preferences": ["动车优先"],
            },
        )
        skeleton = skeleton_plan("昆明", 2)
        skeleton["days"][1]["destination"] = "大理"
        skeleton["days"][1]["intercity_leg"] = None

        repaired, repairs = repair_skeleton(skeleton, context)

        self.assertEqual(
            repaired["days"][1]["intercity_leg"],
            {
                "from": "昆明",
                "to": "大理",
                "mode": "rail",
                "departure_hint": None,
                "arrival_hint": None,
            },
        )
        self.assertTrue(
            any(item["reason"] == "repair_intercity_leg" for item in repairs)
        )

    async def test_fast_workflow_returns_decisions_budget_and_evidence(self) -> None:
        response = await TripAgent(SkeletonLLM(), amap=FakeAmap()).run(
            "请生成完整行程",
            structured_request={
                "destination": "长沙",
                "days": 1,
                "party": {"adults": 2},
                "budget_range": {"total_max": 2000, "currency": "CNY"},
                "daily_window": {"start": "09:00", "end": "20:00"},
            },
        )

        self.assertIsNotNone(response.plan)
        plan = response.plan or {}
        self.assertTrue(plan["hotel_options"])
        self.assertTrue(plan["transport_options"]["local"])
        self.assertTrue(plan["dining_options"])
        self.assertTrue(plan["booking_tasks"])
        self.assertTrue(
            all(item["category"] != "dining" for item in plan["booking_tasks"])
        )
        self.assertEqual(plan["budget"]["planning_ceiling"], 2000)
        self.assertEqual(
            sum(item["planning_cap"] for item in plan["budget"]["categories"]),
            2000,
        )
        evidence_ids = {item["id"] for item in plan["evidence"]}
        claimed_refs = {
            ref
            for day in plan["days"]
            for item in [*day["schedule"], *day["transfers"]]
            for ref in item["evidence_refs"]
        }
        self.assertTrue(claimed_refs)
        self.assertTrue(claimed_refs <= evidence_ids)
        self.assertEqual(len(plan["days"][0]["periods"]), 6)
        self.assertEqual(
            {
                item["period"]
                for item in plan["days"][0]["schedule"]
                if item["type"] == "meal"
            },
            {"breakfast", "lunch", "dinner"},
        )
        self.assertIn("late_drop_order", plan["days"][0]["fallback"])

    def test_normalize_plan_preserves_authoritative_booking_tasks(self) -> None:
        plan = single_place_plan()
        plan["booking_tasks"] = [
            {
                "id": "booking-user-supplied",
                "category": "transport",
                "target_name": "长沙南站",
                "status": "not_required",
                "action": "无需预约",
            }
        ]

        normalized = normalize_plan(
            plan,
            known_places={},
            resolve_place=lambda _item, _places: None,
            route_evidence=[],
            weather_evidence=None,
        )

        self.assertEqual(normalized["booking_tasks"], plan["booking_tasks"])

    def test_unspecified_duration_is_left_for_model_judgment(self) -> None:
        request = StructuredTripRequest(destination="云南")
        context = build_planning_context(None, "我想去云南玩一圈")

        self.assertIsNone(request.days)
        self.assertIsNone(request.nights)
        self.assertEqual(context["destination"], "云南")
        self.assertIsNone(context.get("days"))
        self.assertIsNone(context.get("nights"))

    def test_explicit_long_trip_is_not_rejected_by_product_limit(self) -> None:
        destinations = [{"name": f"城市{index}"} for index in range(1, 14)]
        request = StructuredTripRequest(
            destination="中国", destinations=destinations, days=45
        )

        self.assertEqual(request.days, 45)
        self.assertEqual(request.nights, 44)
        self.assertEqual(len(request.destinations), 13)

    async def test_model_selected_duration_drives_complete_plan(self) -> None:
        llm = SkeletonLLM(skeleton_plan("长沙", 4))
        response = await TripAgent(llm, amap=FakeAmap()).run("我想去长沙旅行")

        self.assertTrue(response.plan)
        self.assertEqual(len(response.plan["days"]), 4)
        self.assertEqual(response.plan["duration"]["days"], 4)
        self.assertEqual(response.plan["planning_context"]["days"], 4)
        self.assertEqual(llm.call_count, 1)
        days_schema = llm.invocations[0]["output_format"]["schema"]["properties"][
            "days"
        ]
        self.assertIn("根据用户需求选择合理天数", days_schema["description"])

    async def test_complete_model_judgment_survives_fact_enrichment(self) -> None:
        skeleton = skeleton_plan()
        skeleton.update(
            {
                "overview": "适合带父母的慢节奏长沙首访。",
                "highlights": ["上午游岳麓山，下午按体力调整"],
                "tradeoffs": ["减少景点数量换取更充足休息"],
                "budget_notes": ["住宿优先选择近地铁且有电梯的物业"],
                "safety_notes": ["同行有老人时避免连续长坡并预留午休"],
                "transport_notes": ["高峰期优先地铁，短距离按体力打车"],
                "budget_allocation": [
                    {"label": "住宿", "percentage": 60, "reason": "重视休息"},
                    {"label": "餐饮与交通", "percentage": 40, "reason": "减少步行"},
                ],
            }
        )
        skeleton["days"][0]["fallback_note"] = "下雨时缩短山顶停留。"
        skeleton["days"][0]["summary"] = (
            "上午十点后再进山，先看岳麓书院和古树山道；中午留出休息，"
            "下午按老人当天体力决定是否继续登高。"
        )
        skeleton["days"][0]["stops"][0].update(
            {
                "suggested_start": "10:00",
                "suggested_end": "12:00",
                "reservation_note": "出发前核对景区预约规则",
                "alternative": {"name": "岳麓书院", "reason": "雨天减少户外"},
            }
        )
        skeleton["days"][0]["stops"][0]["reason"] = (
            "从岳麓书院一侧慢慢上山，沿途能看古树、碑刻和湘江方向的城市景色。"
        )

        response = await TripAgent(SkeletonLLM(skeleton), amap=FakeAmap()).run(
            "请生成完整行程",
            structured_request={
                "destination": "长沙",
                "days": 1,
                "party": {"adults": 2, "seniors": 1},
                "budget_range": {"total_max": 2000, "currency": "CNY"},
            },
        )

        self.assertTrue(response.plan)
        plan = response.plan
        self.assertEqual(plan["overview"], skeleton["overview"])
        self.assertEqual(plan["days"][0]["summary"], skeleton["days"][0]["summary"])
        visit = next(
            item
            for item in plan["days"][0]["schedule"]
            if item["name"] == "岳麓山国家重点风景名胜区"
        )
        self.assertEqual(visit["reason"], skeleton["days"][0]["stops"][0]["reason"])
        self.assertGreaterEqual(visit["start"], "10:00")
        self.assertEqual(plan["days"][0]["fallback"]["notes"], "下雨时缩短山顶停留。")
        self.assertEqual(visit["alternatives"][0]["name"], "岳麓书院")
        self.assertEqual(plan["safety"]["source_status"], "model_judgment")
        self.assertIn("避免连续长坡", plan["safety"]["destination_alerts"][0])
        self.assertEqual(
            [item["planning_cap"] for item in plan["budget"]["categories"]],
            [1200, 800],
        )
        self.assertIn(
            "高峰期优先地铁",
            plan["transport_options"]["local_strategy"]["notes"][0],
        )
        self.assertTrue(plan["dining_options"][0]["description"])

    def test_rail_station_script_keeps_relative_index_path(self) -> None:
        match = _STATION_SCRIPT.search(
            '<script src="./script/core/common/station_name_new_v10115.js"></script>'
        )
        self.assertIsNotNone(match)
        self.assertEqual(
            match.group(1),
            "./script/core/common/station_name_new_v10115.js",
        )

    def test_rail_service_midnight_rolls_to_next_day(self) -> None:
        parsed = _service_datetime("20260914", "24:00")

        self.assertEqual(parsed.isoformat(), "2026-09-15T00:00:00")

    async def test_rail_retries_unsuccessful_response_with_refreshed_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = Rail12306Provider(
                ProviderCache(Path(directory) / "rail-cache.sqlite")
            )
            provider._stations = {
                "names": {"昆明南": "KOM", "大理": "DKM"},
                "cities": {},
                "code_to_name": {"KOM": "昆明南", "DKM": "大理"},
            }
            refreshes: list[bool] = []

            async def load_query_path(*, refresh: bool = False) -> str:
                refreshes.append(refresh)
                return "lcquery" if refresh else "query"

            responses = iter(
                [
                    {"status": False, "data": None},
                    {"status": True, "data": {"map": {}, "result": []}},
                ]
            )

            def handler(_request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json=next(responses))

            provider._load_query_path = load_query_path
            provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            provider.min_interval = 0
            result = await provider.search_trains(
                travel_date="2026-09-14",
                from_station="昆明南",
                to_station="大理",
            )
            await provider.close()

            self.assertEqual(refreshes, [False, True])
            self.assertEqual(result["trains"], [])

    async def test_rail_non_object_response_uses_documented_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = Rail12306Provider(
                ProviderCache(Path(directory) / "rail-cache.sqlite")
            )
            provider._stations = {
                "names": {"昆明南": "KOM", "大理": "DKM"},
                "cities": {},
                "code_to_name": {"KOM": "昆明南", "DKM": "大理"},
            }

            async def load_query_path(*, refresh: bool = False) -> str:
                return "lcquery" if refresh else "query"

            def handler(_request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json=[])

            provider._load_query_path = load_query_path
            provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            provider.min_interval = 0
            with self.assertRaisesRegex(
                RuntimeError,
                "12306 returned an unsuccessful timetable response",
            ):
                await provider.search_trains(
                    travel_date="2026-09-14",
                    from_station="昆明南",
                    to_station="大理",
                )
            await provider.close()

    def test_rail_parser_keeps_station_names_and_common_fares(self) -> None:
        stations = _parse_station_script(
            "var station_names ='@bjb|北京北|VAP|beijingbei|bjb|0|0357|北京|||"
            "@bj|北京|BJP|beijing|bj|1|0357|北京|||';"
        )
        self.assertEqual(stations["cities"]["北京"], "BJP")
        self.assertEqual(stations["names"]["北京北站"], "VAP")
        self.assertEqual(
            _parse_prices("M092900005O055300000"),
            [
                {
                    "seat_type": "二等座",
                    "seat_code": "O",
                    "amount": 553.0,
                    "currency": "CNY",
                },
                {
                    "seat_type": "一等座",
                    "seat_code": "M",
                    "amount": 929.0,
                    "currency": "CNY",
                },
            ],
        )

    async def test_rail_schedule_enriches_intercity_day(self) -> None:
        class FakeRail:
            available = True

            async def search_trains(self, **kwargs):
                self.request = kwargs
                return {
                    "provider": "rail12306",
                    "available": True,
                    "fetched_at": "2026-09-10T18:00:00+08:00",
                    "response_hash": "sha256:rail",
                    "source_url": "https://www.12306.cn/index/",
                    "trains": [
                        {
                            "train_code": "D8652",
                            "from_station": "昆明南",
                            "to_station": "大理",
                            "departure_time": "09:05",
                            "arrival_time": "11:22",
                            "arrival_date": "2026-09-12",
                            "duration_minutes": 137,
                            "price": {
                                "seat_type": "二等座",
                                "amount": 145.0,
                                "currency": "CNY",
                            },
                            "prices": [
                                {
                                    "seat_type": "二等座",
                                    "amount": 145.0,
                                    "currency": "CNY",
                                }
                            ],
                        }
                    ],
                }

        skeleton = skeleton_plan("昆明", 2)
        skeleton["days"][1]["destination"] = "大理"
        skeleton["days"][1]["intercity_leg"] = {
            "from": "昆明",
            "to": "大理",
            "mode": "rail",
            "departure_hint": "09:00",
            "arrival_hint": None,
        }
        skeleton["overview"] = (
            "动车实际车次、时刻和参考票价需由程序按2026年9月12日查询后填入。"
        )
        skeleton["budget_notes"] = ["动车票价和住宿价格需由程序按出行日期查询。"]
        rail = FakeRail()
        response = await TripAgent(
            SkeletonLLM(skeleton), amap=FakeAmap(), rail=rail
        ).run(
            "昆明和大理两日行程",
            structured_request={
                "destination": "昆明",
                "days": 2,
                "start_date": "2026-09-11",
            },
        )

        option = response.plan["transport_options"]["intercity"][0]
        self.assertEqual(rail.request["travel_date"], "2026-09-12")
        self.assertEqual(option["train_code"], "D8652")
        self.assertEqual(option["from"], "昆明南")
        self.assertEqual(option["to"], "大理")
        self.assertEqual(option["price"], 145.0)
        self.assertEqual(option["status"], "verified_schedule")
        self.assertTrue(option["evidence_refs"])
        self.assertFalse(
            any(
                item["period"] == "breakfast"
                for item in response.plan["days"][1]["schedule"]
            )
        )
        self.assertIn("D8652", response.plan["overview"])
        self.assertIn(
            "2026-09-12",
            response.plan["days"][1]["fallback"]["notes"],
        )
        self.assertNotIn("需由程序", response.plan["overview"])
        self.assertTrue(
            any(
                "铁路时刻与参考票价已核验" in item
                for item in response.plan["budget"]["assumptions"]
            )
        )
        self.assertFalse(
            any("城际班次与票价尚未接入" in item for item in response.plan["unknowns"])
        )

    def test_itinerary_schema_is_strict_output_compatible(self) -> None:
        schema = itinerary_skeleton_output_format(expected_days=3)["schema"]
        day_schema = schema["properties"]["days"]["items"]
        stop_schema = day_schema["properties"]["stops"]["items"]

        def schema_keywords(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key
                    yield from schema_keywords(item)
            elif isinstance(value, list):
                for item in value:
                    yield from schema_keywords(item)

        keywords = set(schema_keywords(schema))
        self.assertFalse({"minLength", "minItems", "maxItems"} & keywords)
        self.assertIn("恰好 3 个", schema["properties"]["days"]["description"])
        self.assertIn("自然语言", day_schema["properties"]["summary"]["description"])
        self.assertIn(
            "具体能看什么", stop_schema["properties"]["reason"]["description"]
        )
        self.assertNotIn("suggested_start", stop_schema["properties"])
        self.assertNotIn("suggested_end", stop_schema["properties"])
        self.assertNotIn("duration_minutes", stop_schema["properties"])
        self.assertEqual(
            stop_schema["properties"]["period"]["enum"],
            ["breakfast", "morning", "lunch", "afternoon", "dinner", "evening"],
        )


if __name__ == "__main__":
    unittest.main()
