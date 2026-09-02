from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx

from trip_agent.cache import ProviderCache
from trip_agent.loop import TripAgent, extract_json
from trip_agent.llm import OpenAICompatibleLLM
from trip_agent.plan_output import normalize_plan, normalize_risk, normalize_transfer
from trip_agent.providers.amap import AmapProvider
from trip_agent.providers.weather import WeatherProvider


class FakeLLM:
    def __init__(self, decisions: list[dict]) -> None:
        self.decisions = iter(decisions)

    async def ainvoke(self, messages: list[dict]) -> SimpleNamespace:
        return SimpleNamespace(
            content=json.dumps(next(self.decisions), ensure_ascii=False)
        )


class RawLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)

    async def ainvoke(self, messages: list[dict]) -> SimpleNamespace:
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
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        response = await llm.ainvoke([{"role": "user", "content": "test"}])
        await llm.close()

        self.assertEqual(response.content, '{"action":"ask"}')
        self.assertEqual(request_count, 2)

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


if __name__ == "__main__":
    unittest.main()
