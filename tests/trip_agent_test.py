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
from trip_agent.contracts import ChatRequest, ChatResponse
from trip_agent.observability import close_logging, configure_logging, log_event
from trip_agent.loop import TripAgent, extract_json
from trip_agent.llm import OpenAICompatibleLLM
from trip_agent.plan_output import normalize_plan, normalize_risk, normalize_transfer
from trip_agent.providers.amap import AmapProvider
from trip_agent.store import TripStore
from trip_agent.providers.weather import WeatherProvider


class FakeLLM:
    def __init__(self, decisions: list[dict]) -> None:
        self.decisions = iter(decisions)

    async def ainvoke(self, messages: list[dict], **kwargs) -> SimpleNamespace:
        return SimpleNamespace(
            content=json.dumps(next(self.decisions), ensure_ascii=False)
        )


class RawLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)

    async def ainvoke(self, messages: list[dict], **kwargs) -> SimpleNamespace:
        return SimpleNamespace(content=next(self.responses))


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


class TripAgentTests(unittest.IsolatedAsyncioTestCase):
    def test_extract_json_accepts_fenced_payload(self) -> None:
        self.assertEqual(
            extract_json('```json\n{"action":"ask"}\n```')["action"], "ask"
        )

    async def test_llm_retries_transient_transport_failure(self) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            self.assertEqual(json.loads(request.content)["max_tokens"], 8192)
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
            self.assertEqual(payload["max_output_tokens"], 8192)
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

    async def test_model_json_decision_retries_from_clean_context(self) -> None:
        agent = TripAgent(
            RawLLM(
                [
                    '{"action":"tool",',
                    "{not-json}",
                    '{"action":"ask","reply":"请补充目的地"}',
                ]
            ),
            amap=FakeAmap(),
        )

        decision = await agent.ask_model(
            [{"role": "user", "content": "想旅行"}],
            allow_plan=False,
        )

        self.assertEqual(decision["action"], "ask")
        self.assertEqual(decision["reply"], "请补充目的地")

    async def test_batch_tool_executes_independent_queries(self) -> None:
        amap = FakeAmap()
        agent = TripAgent(FakeLLM([]), amap=amap)

        result = await agent.call_tool(
            "batch",
            {
                "calls": [
                    {
                        "tool": "search_places",
                        "arguments": {"city": "长沙", "keywords": "岳麓山"},
                    },
                    {
                        "tool": "search_places",
                        "arguments": {"city": "长沙", "keywords": "橘子洲"},
                    },
                ]
            },
        )

        self.assertEqual(amap.search_calls, 2)
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(
            all(
                "result" in item and not item.get("error") for item in result["results"]
            )
        )

    async def test_agent_accepts_top_level_calls_for_batch_action(self) -> None:
        batch = {
            "action": "batch",
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
            FakeLLM([batch, {"action": "ask", "reply": "证据已收集"}]),
            amap=amap,
            max_steps=2,
        ).run("长沙一日游")

        self.assertEqual(amap.search_calls, 2)
        self.assertEqual(result.reply, "证据已收集")
        self.assertNotIn(
            "error",
            next(event for event in result.events if event["type"] == "tool_finished"),
        )

    async def test_agent_rejects_duplicate_batch_without_spending_budget(self) -> None:
        batch = {
            "action": "batch",
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
            FakeLLM([batch, batch, {"action": "ask", "reply": "证据已收集"}]),
            amap=amap,
            max_steps=3,
        ).run("长沙一日游")

        self.assertEqual(amap.search_calls, 2)
        self.assertIn(
            "duplicate_tool_call",
            [
                event.get("error")
                for event in result.events
                if event["type"] == "tool_rejected"
            ],
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

        mismatched_route = [dict(route_evidence[0], origin="113.0,23.0")]
        mismatched = normalize_transfer(
            raw_plan["days"][0]["transfers"][0],
            mismatched_route,
            schedule,
        )
        self.assertEqual(mismatched["source"], "unknown")

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

    async def test_tool_budget_reserves_a_final_plan_decision(self) -> None:
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
                "days": [{"day": 1, "stops": [{"name": "岳麓山"}]}],
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
        self.assertIn("tool_rejected", [event["type"] for event in result.events])

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
            final_reasoning_effort = "medium"

            def __init__(self) -> None:
                self.messages = []

            async def ainvoke(self, messages, **kwargs):
                self.messages = messages
                return SimpleNamespace(
                    content='{"action":"ask","reply":"需要确认修改范围"}'
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
                    "days": [{"day": 1}, {"day": 2}, {"day": 3}],
                },
                events=[],
            )
            llm = CapturingLLM()
            agent = TripAgent(llm, amap=FakeAmap(), store=store)

            response = await agent.run("把第二天下午改得轻松一些", "session-1")

            restored_context = "\n".join(message["content"] for message in llm.messages)
            detail = store.get_session("session-1")

        self.assertIn("当前已保存行程", restored_context)
        self.assertIn("长沙三日行程", restored_context)
        self.assertIn("session_restored", [event["type"] for event in response.events])
        model_started = next(
            event for event in response.events if event["type"] == "model_started"
        )
        self.assertIn("已核验地点 0/6", model_started["detail"])
        self.assertEqual(len(detail["messages"]), 4)

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
