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
from trip_agent.contracts import ChatRequest, ChatResponse
from trip_agent.observability import close_logging, configure_logging, log_event
from trip_agent.loop import TripAgent
from trip_agent.llm import OpenAICompatibleLLM
from trip_agent.model_schema import planner_tools
from trip_agent.plan_output import (
    normalize_plan,
    normalize_risk,
    normalize_schedule_item,
    normalize_transfer,
)
from trip_agent.providers.amap import AmapProvider
from trip_agent.store import TripStore
from trip_agent.providers.weather import WeatherProvider
from trip_agent.reviewer import ItineraryReviewer
from trip_agent.validation import HardValidator


def native_response(decision: dict, call_prefix: str = "call") -> SimpleNamespace:
    action = str(decision.get("action") or "")
    if decision.get("calls"):
        calls = decision["calls"]
    elif action == "tool" or decision.get("tool"):
        calls = [
            {
                "tool": decision.get("tool"),
                "arguments": decision.get("arguments") or {},
            }
        ]
    elif action == "plan":
        calls = [
            {
                "tool": "submit_itinerary",
                "arguments": {
                    "reply": decision.get("reply") or "",
                    "plan": decision.get("plan") or {},
                },
            }
        ]
    elif action == "ask":
        calls = [
            {
                "tool": "ask_user",
                "arguments": {"question": decision.get("reply") or ""},
            }
        ]
    else:
        calls = []
    return SimpleNamespace(
        content="",
        tool_calls=[
            {
                "call_id": f"{call_prefix}-{index}",
                "name": item["tool"],
                "arguments": json.dumps(item["arguments"], ensure_ascii=False),
            }
            for index, item in enumerate(calls)
        ],
        metrics={},
    )


class FakeLLM:
    def __init__(self, decisions: list[dict]) -> None:
        self.decisions = iter(decisions)
        self.call_count = 0

    async def ainvoke(self, messages: list[dict], **kwargs) -> SimpleNamespace:
        self.call_count += 1
        return native_response(next(self.decisions), f"call-{self.call_count}")


class RecordingLLM(FakeLLM):
    final_reasoning_effort = "medium"
    reasoning_effort = "low"

    def __init__(self, decisions: list[dict]) -> None:
        super().__init__(decisions)
        self.messages: list[list[dict]] = []
        self.invocations: list[dict] = []

    async def ainvoke(self, messages: list[dict], **kwargs) -> SimpleNamespace:
        self.invocations.append(dict(kwargs))
        self.messages.append(list(messages))
        if kwargs.get("output_format") is not None:
            self.call_count += 1
            decision = next(self.decisions)
            return SimpleNamespace(
                content=json.dumps({"decision": decision}, ensure_ascii=False)
            )
        return await super().ainvoke(messages, **kwargs)


class FakeAmap:
    def __init__(self) -> None:
        self.search_calls = 0

    async def close(self) -> None:
        return None

    async def search_places(self, city: str, keywords: str, limit: int = 8) -> dict:
        self.search_calls += 1
        return {
            "places": [
                {
                    "id": "B001",
                    "name": "岳麓山国家重点风景名胜区",
                    "address": "登高路58号",
                    "area": "岳麓区",
                    "location": "112.94,28.18",
                }
            ],
            "source": "amap",
            "cache_hit": False,
            "response_hash": "sha256:place",
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
            self.assertEqual(json.loads(request.content)["max_tokens"], 12000)
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
            self.assertEqual(payload["max_output_tokens"], 12000)
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

    async def test_llm_parses_native_responses_function_call(self) -> None:
        tools = planner_tools()

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertEqual(payload["tools"], tools)
            self.assertEqual(payload["tool_choice"], "required")
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    "event: response.completed\n"
                    'data: {"type":"response.completed","response":{"output":['
                    '{"type":"function_call","call_id":"call-1",'
                    '"name":"search_places","arguments":'
                    '"{\\"city\\":\\"长沙\\",\\"keywords\\":\\"岳麓山\\",'
                    '\\"limit\\":3}"}],"usage":{"input_tokens":10,'
                    '"output_tokens":5}}}\n\n'
                    "data: [DONE]\n\n"
                ).encode(),
            )

        llm = OpenAICompatibleLLM()
        llm.key = "test-key"
        llm.base_url = "https://ztoken.zlux.top"
        llm.model = "gpt-5.6-luna"
        llm.wire_api = "responses"
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        response = await llm.ainvoke(
            [{"role": "user", "content": "test"}],
            tools=tools,
            tool_choice="required",
        )
        await llm.close()

        self.assertEqual(response.content, "")
        self.assertEqual(
            response.tool_calls,
            [
                {
                    "call_id": "call-1",
                    "name": "search_places",
                    "arguments": ('{"city":"长沙","keywords":"岳麓山","limit":3}'),
                }
            ],
        )
        self.assertEqual(response.metrics["tool_call_count"], 1)

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

    def test_model_tool_result_drops_large_provider_payloads(self) -> None:
        route = TripAgent._model_tool_result(
            "route",
            {
                "origin": "120.1,36.1",
                "destination": "120.2,36.2",
                "mode": "transit",
                "duration_seconds": 1200,
                "distance_meters": 8000,
                "source": "amap",
                "response_hash": "sha256:route",
                "summary": {"segments": ["large-sensitive-route-payload"]},
            },
        )
        detail = TripAgent._model_tool_result(
            "place_detail",
            {
                "source": "amap",
                "response_hash": "sha256:place",
                "place": {
                    "id": "B001",
                    "name": "栈桥",
                    "location": "120.1,36.1",
                    "business_hours": "08:00-18:00",
                    "photos": ["large-sensitive-photo-payload"],
                    "biz_ext": {
                        "rating": "4.8",
                        "open_time": "08:00-18:00",
                        "unsupported": "large-sensitive-business-payload",
                    },
                },
            },
        )

        serialized = json.dumps([route, detail], ensure_ascii=False)
        self.assertNotIn("large-sensitive", serialized)
        self.assertNotIn("summary", route)
        self.assertEqual(route["duration_seconds"], 1200)
        self.assertEqual(detail["place"]["business_hours"], "08:00-18:00")
        self.assertEqual(
            detail["place"]["biz_ext"],
            {"rating": "4.8", "open_time": "08:00-18:00"},
        )

    async def test_agent_only_sends_compact_route_evidence_to_model(self) -> None:
        class LargeResultAmap(FakeAmap):
            async def search_places(
                self, city: str, keywords: str, limit: int = 8
            ) -> dict:
                return {
                    "places": [
                        {
                            "id": f"B00{index}",
                            "name": f"地点{index}",
                            "location": f"120.{index},36.{index}",
                        }
                        for index in range(1, 4)
                    ],
                    "source": "amap",
                    "cache_hit": False,
                    "response_hash": "sha256:places",
                }

            async def route(
                self,
                city: str,
                origin: str,
                destination: str,
                mode: str = "driving",
            ) -> dict:
                return {
                    "origin": origin,
                    "destination": destination,
                    "mode": mode,
                    "distance_meters": 5000,
                    "duration_seconds": 900,
                    "summary": {"segments": ["large-route-payload"]},
                    "source": "amap",
                    "cache_hit": False,
                    "response_hash": "sha256:route",
                }

        llm = RecordingLLM(
            [
                {
                    "action": "tool",
                    "tool": "search_places",
                    "arguments": {"city": "青岛", "keywords": "海滨景点"},
                },
                {
                    "action": "tool",
                    "tool": "route",
                    "arguments": {
                        "city": "青岛",
                        "origin": "120.1,36.1",
                        "destination": "120.2,36.2",
                        "mode": "transit",
                    },
                },
                {"action": "ask", "reply": "证据已收集"},
            ]
        )
        result = await TripAgent(llm, amap=LargeResultAmap(), max_steps=3).run(
            "青岛一日游"
        )

        final_input = json.dumps(llm.messages[-1], ensure_ascii=False)
        route_event = [
            event
            for event in result.events
            if event["type"] == "tool_finished" and event["tool"] == "route"
        ][0]
        self.assertNotIn("large-route-payload", final_input)
        self.assertGreater(
            route_event["raw_result_chars"], route_event["model_context_chars"]
        )
        self.assertIn("当前已核验证据", final_input)
        first_tools = {tool["name"] for tool in llm.invocations[0]["tools"]}
        second_tools = {tool["name"] for tool in llm.invocations[1]["tools"]}
        final_tools = {tool["name"] for tool in llm.invocations[2]["tools"]}
        self.assertNotIn("submit_itinerary", first_tools)
        self.assertNotIn("submit_itinerary", second_tools)
        self.assertIn("submit_itinerary", final_tools)
        self.assertEqual(llm.invocations[0]["reasoning_effort"], "low")
        self.assertEqual(llm.invocations[2]["reasoning_effort"], "medium")

    async def test_agent_executes_native_parallel_tool_calls(self) -> None:
        native_calls = {
            "calls": [
                {
                    "tool": "search_places",
                    "arguments": {"city": "长沙", "keywords": "岳麓山"},
                },
                {
                    "tool": "search_places",
                    "arguments": {"city": "长沙", "keywords": "橘子洲"},
                },
            ],
        }
        amap = FakeAmap()
        result = await TripAgent(
            FakeLLM([native_calls, {"action": "ask", "reply": "证据已收集"}]),
            amap=amap,
            max_steps=2,
        ).run("长沙一日游")

        self.assertEqual(amap.search_calls, 2)
        self.assertEqual(result.reply, "证据已收集")
        self.assertNotIn(
            "error",
            next(event for event in result.events if event["type"] == "tool_finished"),
        )

    async def test_agent_coalesces_duplicate_calls_in_same_parallel_batch(
        self,
    ) -> None:
        duplicate_calls = {
            "calls": [
                {
                    "tool": "search_places",
                    "arguments": {"city": "长沙", "keywords": "岳麓山"},
                },
                {
                    "tool": "search_places",
                    "arguments": {"city": "长沙", "keywords": "岳麓山"},
                },
            ],
        }
        amap = FakeAmap()
        result = await TripAgent(
            FakeLLM([duplicate_calls, {"action": "ask", "reply": "证据已收集"}]),
            amap=amap,
            max_steps=2,
        ).run("长沙一日游")

        self.assertEqual(amap.search_calls, 1)
        reused = [
            event
            for event in result.events
            if event["type"] == "tool_finished" and event.get("reused")
        ]
        self.assertEqual(len(reused), 1)

    async def test_agent_reuses_repeated_native_tool_results(self) -> None:
        native_calls = {
            "calls": [
                {
                    "tool": "search_places",
                    "arguments": {"city": "长沙", "keywords": "岳麓山"},
                },
                {
                    "tool": "search_places",
                    "arguments": {"city": "长沙", "keywords": "橘子洲"},
                },
            ],
        }
        amap = FakeAmap()
        result = await TripAgent(
            FakeLLM(
                [native_calls, native_calls, {"action": "ask", "reply": "证据已收集"}]
            ),
            amap=amap,
            max_steps=3,
        ).run("长沙一日游")

        self.assertEqual(amap.search_calls, 2)
        reused = [
            event
            for event in result.events
            if event["type"] == "tool_finished" and event.get("reused")
        ]
        self.assertEqual(len(reused), 2)

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

    async def test_agent_enriches_model_schedule_with_canonical_place(self) -> None:
        llm = FakeLLM(
            [
                {
                    "tool": "search_places",
                    "arguments": {"city": "长沙", "keywords": "岳麓山"},
                },
                {
                    "action": "plan",
                    "reply": "已规划",
                    "plan": {
                        "city": "长沙",
                        "title": "岳麓山慢游",
                        "hotel": {
                            "name": "五一广场住宿区",
                            "status": "recommended_area",
                        },
                        "candidate_comparison": {
                            "areas": [
                                {"name": "岳麓山", "selected": True},
                                {"name": "五一广场", "selected": False},
                            ]
                        },
                        "days": [
                            {
                                "day": 1,
                                "theme": "山水",
                                "start_time": "09:00",
                                "end_time": "12:00",
                                "start_anchor": {"name": "五一广场住宿区"},
                                "end_anchor": {"name": "五一广场住宿区"},
                                "schedule": [
                                    {
                                        "period": "morning",
                                        "type": "visit",
                                        "name": "岳麓山",
                                        "reason": "登高看城",
                                        "start": "09:00",
                                        "end": "12:00",
                                        "duration_minutes": 180,
                                        "opening_match": "unknown",
                                    }
                                ],
                                "transfers": [],
                                "risks": [],
                            }
                        ],
                        "narrative": {
                            "headline": "把一天留给岳麓山",
                            "summary": "上午集中游览，不追求打卡数量。",
                        },
                    },
                },
            ]
        )
        amap = FakeAmap()
        result = await TripAgent(llm, amap=amap, max_steps=3).run("长沙一日游")

        schedule_item = result.plan["days"][0]["schedule"][0]
        self.assertEqual(amap.search_calls, 1)
        self.assertEqual(result.reply, "已规划")
        self.assertEqual(schedule_item["place_id"], "B001")
        self.assertEqual(schedule_item["name"], "岳麓山国家重点风景名胜区")
        self.assertEqual(schedule_item["duration_minutes"], 180)
        self.assertEqual(schedule_item["source"], "amap")
        self.assertIn("completeness", result.plan)

    async def test_reused_tool_result_does_not_consume_budget(self) -> None:
        tool_decision = {
            "action": "tool",
            "tool": "search_places",
            "arguments": {"city": "长沙", "keywords": "岳麓山"},
        }
        final_decision = {
            "action": "plan",
            "reply": "已规划",
            "plan": {
                "city": "长沙",
                "days": [
                    {
                        "day": 1,
                        "schedule": [
                            {
                                "type": "free_time",
                                "name": "自由活动",
                                "start": "09:00",
                                "end": "10:00",
                                "duration_minutes": 60,
                            }
                        ],
                    }
                ],
            },
        }
        amap = FakeAmap()
        result = await TripAgent(
            FakeLLM([tool_decision, tool_decision, final_decision]),
            amap=amap,
            max_steps=3,
            max_tool_calls=1,
        ).run("长沙一日游")

        self.assertIsNotNone(result.plan)
        self.assertEqual(amap.search_calls, 1)
        self.assertTrue(any(event.get("reused") for event in result.events))

    def test_native_tool_contract_exposes_terminal_submission(self) -> None:
        tools = planner_tools()
        names = {tool["name"] for tool in tools}

        self.assertEqual(
            names,
            {
                "search_places",
                "place_detail",
                "route",
                "weather",
                "ask_user",
                "submit_itinerary",
            },
        )
        submit = next(tool for tool in tools if tool["name"] == "submit_itinerary")
        plan = submit["parameters"]["properties"]["plan"]
        hotel_fields = plan["properties"]["hotel"]["properties"]
        day = plan["properties"]["days"]["items"]
        schedule_item = day["properties"]["schedule"]["items"]
        transfer = day["properties"]["transfers"]["items"]
        self.assertNotIn("place_id", hotel_fields)
        self.assertNotIn("place_id", schedule_item["properties"])
        self.assertNotIn("evidence_hash", transfer["properties"])
        self.assertTrue(submit["strict"])
        self.assertIn("plan", submit["parameters"]["properties"])
        self.assertNotIn("batch", names)

    def test_planner_tools_withhold_submission_during_evidence_stage(self) -> None:
        names = {tool["name"] for tool in planner_tools(allow_submit=False)}

        self.assertEqual(
            names,
            {"search_places", "place_detail", "route", "weather", "ask_user"},
        )

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

    def test_route_timeline_repair_moves_activity_after_arrival_buffer(self) -> None:
        plan = {
            "days": [
                {
                    "start_time": "09:00",
                    "end_time": "20:00",
                    "start_anchor": {"name": "住宿锚点"},
                    "schedule": [
                        {
                            "type": "visit",
                            "name": "景点甲",
                            "start": "09:00",
                            "end": "10:10",
                        },
                        {
                            "type": "meal",
                            "name": "午餐",
                            "start": "12:25",
                            "end": "13:20",
                        },
                    ],
                    "transfers": [
                        {
                            "from_name": "住宿锚点",
                            "to_name": "景点甲",
                            "mode": "transit",
                            "start": "09:00",
                            "end": "09:58",
                            "duration_minutes": 58,
                        }
                    ],
                }
            ]
        }

        repairs = TripAgent._repair_route_timeline(plan)

        self.assertEqual(repairs[0]["reason"], "route_execution_buffer")
        self.assertEqual(plan["days"][0]["schedule"][0]["start"], "10:08")
        self.assertEqual(plan["days"][0]["schedule"][0]["end"], "11:18")

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

    def test_hard_validator_rejects_unresolved_requested_hotel_anchor(self) -> None:
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

        self.assertFalse(report["passed"])
        self.assertIn(
            "ANCHOR_ROUTE_UNVERIFIED",
            [failure["code"] for failure in report["hard_failures"]],
        )

    def test_route_arguments_resolve_known_names_and_embedded_coordinates(self) -> None:
        known = {
            "岳麓山风景名胜区": {
                "id": "B001",
                "name": "岳麓山风景名胜区",
                "location": "112.936104,28.183601",
            }
        }

        resolved = TripAgent._resolve_route_arguments(
            {
                "city": "长沙",
                "origin": "岳麓山风景名胜区",
                "destination": "五一广场，112.977340,28.196500",
                "mode": "transit",
            },
            known,
        )

        self.assertEqual(resolved["origin"], "112.936104,28.183601")
        self.assertEqual(resolved["destination"], "112.977340,28.196500")

    async def test_submit_itinerary_returns_failures_then_accepts_repair(self) -> None:
        plan = single_place_plan()
        plan["overview"] = "不应在修复轮重复发送的完整候选内容"
        llm = RecordingLLM(
            [
                {"action": "plan", "reply": "初稿", "plan": plan},
                {
                    "action": "tool",
                    "tool": "search_places",
                    "arguments": {
                        "city": "长沙",
                        "keywords": "岳麓山",
                        "limit": 3,
                    },
                },
                {"action": "plan", "reply": "已修复", "plan": plan},
            ]
        )

        result = await TripAgent(
            llm,
            amap=FakeAmap(),
            max_steps=3,
            max_submit_attempts=3,
        ).run("请为我规划长沙1天行程；必去地点：岳麓山。")

        reports = [
            event["validation_report"]
            for event in result.events
            if event["type"] == "plan_validation_finished"
        ]
        self.assertEqual([report["passed"] for report in reports], [False, True])
        self.assertEqual(reports[0]["repairs_remaining"], 2)
        self.assertEqual(reports[1]["repairs_used"], 1)
        self.assertEqual(result.reply, "已修复")
        self.assertIsNotNone(result.plan)
        repair_messages = llm.messages[1]
        repair_context = "\n".join(
            message.get("content", "")
            for message in repair_messages
            if isinstance(message.get("content"), str)
        )
        self.assertIn("当前待修复候选", repair_context)
        self.assertIn("UNRESOLVED_ENTITY", repair_context)
        self.assertNotIn("不应在修复轮重复发送的完整候选内容", repair_context)
        self.assertFalse(
            any(message.get("type") == "function_call" for message in repair_messages)
        )

    async def test_submit_itinerary_stops_after_two_repairs(self) -> None:
        llm = FakeLLM(
            [
                {
                    "action": "plan",
                    "reply": "初稿",
                    "plan": single_place_plan("初稿"),
                },
                {
                    "action": "plan",
                    "reply": "修复一",
                    "plan": single_place_plan("修复一"),
                },
                {
                    "action": "plan",
                    "reply": "修复二",
                    "plan": single_place_plan("修复二"),
                },
            ]
        )

        result = await TripAgent(
            llm,
            amap=FakeAmap(),
            max_steps=3,
            max_submit_attempts=3,
        ).run("请为我规划长沙1天行程；必去地点：岳麓山。")

        self.assertIsNone(result.plan)
        self.assertIn("UNRESOLVED_ENTITY", result.reply)
        exhausted = next(
            event
            for event in result.events
            if event.get("error") == "repair_budget_exhausted"
        )
        self.assertEqual(exhausted["hard_failure_codes"], ["UNRESOLVED_ENTITY"])

    async def test_reviewer_receives_full_quality_digest_at_high_reasoning(
        self,
    ) -> None:
        class ReviewerLLM:
            async def ainvoke(self, messages, **kwargs):
                self.messages = messages
                self.kwargs = kwargs
                return SimpleNamespace(
                    content=json.dumps(
                        {"verdict": "pass", "summary": "一致", "issues": []},
                        ensure_ascii=False,
                    ),
                    metrics={},
                )

        llm = ReviewerLLM()
        reviewer = ItineraryReviewer(llm)
        result = await reviewer.review(
            planning_context={"destination": "长沙"},
            plan={
                "city": "长沙",
                "overview": "09:00 出发",
                "candidate_comparison": {"areas": []},
                "days": [],
                "warnings": [],
            },
            validation_report={"passed": True},
        )

        digest = json.loads(llm.messages[1]["content"])
        self.assertEqual(digest["candidate_plan"]["overview"], "09:00 出发")
        self.assertIn("candidate_comparison", digest["candidate_plan"])
        self.assertEqual(llm.kwargs["reasoning_effort"], "high")
        self.assertEqual(result["reviewer_version"], "reviewer-v3")

    async def test_shadow_reviewer_cannot_block_hard_valid_plan(self) -> None:
        class ShadowReviewer:
            async def review(self, **kwargs):
                return {
                    "verdict": "revise",
                    "summary": "建议调整",
                    "issues": [{"code": "PACE"}],
                    "shadow": True,
                    "reviewer_version": "reviewer-test",
                }

        result = await TripAgent(
            FakeLLM(
                [
                    {
                        "action": "tool",
                        "tool": "search_places",
                        "arguments": {
                            "city": "长沙",
                            "keywords": "岳麓山",
                            "limit": 3,
                        },
                    },
                    {
                        "action": "plan",
                        "reply": "已完成",
                        "plan": single_place_plan(),
                    },
                ]
            ),
            amap=FakeAmap(),
            reviewer=ShadowReviewer(),
            max_steps=2,
        ).run("请为我规划长沙1天行程；必去地点：岳麓山。")

        self.assertIsNotNone(result.plan)
        self.assertEqual(result.plan["review"]["verdict"], "revise")
        self.assertTrue(result.plan["review"]["shadow"])
        self.assertLess(result.plan["completeness"]["score"], 100)
        self.assertEqual(
            result.plan["completeness"]["checks"][-1]["name"], "独立质量审查"
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
        agent = TripAgent(
            FakeLLM([{"action": "ask", "reply": "请补充目的地"}]),
            amap=FakeAmap(),
        )

        response = await agent.run("想旅行", on_event=published.append)

        self.assertEqual(published, response.events)
        self.assertEqual(
            [event["type"] for event in published],
            [
                "run_started",
                "model_started",
                "model_finished",
                "model_tool_calls",
                "assistant_message",
                "run_finished",
            ],
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

    def test_evidence_memory_prioritizes_candidate_places_with_fixed_caps(self) -> None:
        policy = MemoryPolicy(evidence_places=6, evidence_routes=6)
        places = {
            f"B{index:03d}": {
                "id": f"B{index:03d}",
                "name": f"地点{index}",
                "location": f"112.{index},28.{index}",
            }
            for index in range(10)
        }
        routes = [
            {
                "origin": f"B{index:03d}",
                "destination": f"B{index + 1:03d}",
                "mode": "walking",
                "response_hash": f"route-{index}",
            }
            for index in range(10)
        ]
        snapshot = TripAgent._evidence_snapshot(
            places,
            routes,
            None,
            policy=policy,
            focus_plan={
                "days": [
                    {
                        "schedule": [{"place_id": "B009", "name": "地点9"}],
                        "transfers": [{"evidence_hash": "route-9"}],
                    }
                ]
            },
        )

        self.assertEqual(len(snapshot["places"]), 6)
        self.assertEqual(len(snapshot["routes"]), 6)
        self.assertIn("B009", [place["id"] for place in snapshot["places"]])
        self.assertIn(
            "route-9",
            [route["response_hash"] for route in snapshot["routes"]],
        )
        self.assertEqual(
            snapshot["memory_limits"],
            {
                "source_places": 10,
                "included_places": 6,
                "source_routes": 10,
                "included_routes": 6,
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
        class CapturingLLM:
            def __init__(self) -> None:
                self.messages = []

            async def ainvoke(self, messages, **kwargs):
                self.messages = list(messages)
                return native_response(
                    {"action": "ask", "reply": "需要确认修改范围"},
                    "follow-up",
                )

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
            llm = CapturingLLM()
            agent = TripAgent(llm, amap=FakeAmap(), store=store)

            response = await agent.run("把第二天下午改得轻松一些", "session-1")

            restored_context = "\n".join(message["content"] for message in llm.messages)

        self.assertIn("当前结构化会话状态", restored_context)
        self.assertIn('"previous_plan_digest":{"city":"长沙"', restored_context)
        self.assertIn("长沙三日行程", restored_context)
        self.assertNotIn("这段完整介绍不应重复发送给模型", restored_context)
        self.assertIn("session_restored", [event["type"] for event in response.events])
        model_started = next(
            event for event in response.events if event["type"] == "model_started"
        )
        self.assertIn("提交 0/4", model_started["detail"])

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
