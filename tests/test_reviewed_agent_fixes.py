import inspect
import unittest

from fastapi.testclient import TestClient
from pydantic import ValidationError

import api_multi_agent as api
import graph


class FakeSessionStore:
    def __init__(self):
        self.session = {
            "session_id": "review-session",
            "history": [],
            "itinerary": None,
            "intent": None,
            "state": {
                "city": "长沙",
                "data_dir": "data",
                "trip_intent": {"city": "长沙", "days": 1},
                "daily_plans": [{
                    "day": 1,
                    "stops": [{
                        "poi_id": "old",
                        "poi_name": "旧景点",
                        "start_minutes": 540,
                        "end_minutes": 600,
                        "visit_duration_minutes": 60,
                    }],
                }],
            },
            "ts": 0,
        }
        self.saved = []

    async def get(self, session_id):
        return self.session if session_id == self.session["session_id"] else None

    async def get_or_create(self, session_id):
        return self.session

    async def save(self, session):
        self.saved.append(session.copy())

    async def list_sessions(self):
        return [self.session]

    async def cleanup(self):
        return None


class TestReviewedAgentFixes(unittest.TestCase):
    def setUp(self):
        self.store = FakeSessionStore()
        self.original_get_session_store = api.get_session_store
        api.get_session_store = lambda: self.store
        self.client = TestClient(api.app, raise_server_exceptions=False)

    def tearDown(self):
        api.get_session_store = self.original_get_session_store

    def test_modify_reads_and_saves_session_store(self):
        response = self.client.post("/agent/modify", json={
            "session_id": "review-session",
            "action": "remove_poi",
            "day": 1,
            "poi_id": "old",
        })

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(len(self.store.saved), 1)

    def test_sessions_endpoint_lists_store_sessions(self):
        response = self.client.get("/agent/sessions")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["active"], 1)
        self.assertEqual(response.json()["sessions"][0]["id"], "review-session")

    def test_multi_plan_rejects_too_many_or_unknown_strategies(self):
        with self.assertRaises(ValidationError):
            api.MultiPlanRequest(message="test", strategies=["balanced"] * 5)
        with self.assertRaises(ValidationError):
            api.MultiPlanRequest(message="test", strategies=["unknown"])

    def test_xhs_user_id_rejects_path_segments(self):
        validator = getattr(api, "_safe_xhs_user_id", None)
        self.assertTrue(callable(validator))
        self.assertEqual(validator("123"), "123")
        with self.assertRaises(ValueError):
            validator("../../outside")

    def test_xhs_fetch_is_offloaded_from_event_loop(self):
        source = inspect.getsource(api.xhs_parse)
        self.assertIn("await asyncio.to_thread(extract_xhs_note, req.link)", source)

    def test_graph_does_not_keep_unbounded_memory_checkpoints(self):
        source = inspect.getsource(graph.build_tour_graph)
        self.assertNotIn("MemorySaver", source)
        self.assertIn("builder.compile()", source)


if __name__ == "__main__":
    unittest.main()
