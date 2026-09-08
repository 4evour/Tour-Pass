from __future__ import annotations
import asyncio

import json
import tempfile
import unittest
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
from trip_agent.llm import OpenAICompatibleLLM
from trip_agent.plan_output import (
    normalize_plan,
    normalize_risk,
    normalize_schedule_item,
    normalize_transfer,
)
from trip_agent.providers.amap import AmapProvider
from trip_agent.store import TripStore
from trip_agent.providers.weather import WeatherProvider
from trip_agent.validation import HardValidator
from trip_agent.workflow import _select_place


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
        self.assertEqual(amap.search_calls, 4)
        self.assertEqual(amap.route_calls, 4)
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
        self.assertEqual(amap.search_calls + amap.route_calls, 5)
        self.assertTrue(
            any("保守估算" in warning for warning in response.plan["warnings"])
        )

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

    def test_hard_validator_requires_explicit_lunch_for_full_day(self) -> None:
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

        self.assertIn(
            "MEAL_WINDOW_MISSING",
            [failure["code"] for failure in report["hard_failures"]],
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

    def test_hard_validator_requires_route_buffer_and_aligned_transfer(self) -> None:
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
            failure
            for failure in report["hard_failures"]
            if failure["code"] == "ROUTE_TIME_CONFLICT"
        )
        self.assertEqual(conflict["actual"]["buffer_minutes"], 10)
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
            "TRANSFER_TIMELINE_CONFLICT",
            [failure["code"] for failure in misaligned["hard_failures"]],
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
        self.assertEqual(model_started["phase"], "skeleton")

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


if __name__ == "__main__":
    unittest.main()
