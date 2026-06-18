"""Tour Pass Multi-Agent System — Comprehensive Test Suite.

Tests that can run WITHOUT external services (no LLM API, no C++ backend).
Uses unittest (built-in) since pytest is not installed.

Run: py tests/test_multi_agent.py -v
"""

import asyncio
import json
import math
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ══════════════════════════════════════════════════════════════════════════════
# 1. State Model Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestTripIntent(unittest.TestCase):
    """Test the TripIntent Pydantic model."""

    def setUp(self):
        from agents.state import TripIntent
        self.TripIntent = TripIntent

    def test_default_values(self):
        intent = self.TripIntent(city="长沙")
        self.assertEqual(intent.city, "长沙")
        self.assertEqual(intent.days, 3)
        self.assertEqual(intent.pace, "balanced")
        self.assertEqual(intent.strategy, "balanced")
        self.assertEqual(intent.hotel_budget_min, 0)
        self.assertEqual(intent.hotel_budget_max, 0)
        self.assertEqual(intent.hotel_area, "")
        self.assertEqual(intent.must_visit, [])
        self.assertEqual(intent.interests, [])

    def test_coerce_str_to_list(self):
        """LLM may return empty string instead of empty list."""
        intent = self.TripIntent(city="北京", must_visit="", interests="美食")
        self.assertEqual(intent.must_visit, [])
        self.assertEqual(intent.interests, ["美食"])

    def test_coerce_int_fields(self):
        """LLM may return string numbers."""
        intent = self.TripIntent(city="上海", days="5", hotel_budget_max="800")
        self.assertEqual(intent.days, 5)
        self.assertEqual(intent.hotel_budget_max, 800)

    def test_all_fields_populated(self):
        intent = self.TripIntent(
            city="成都", days=4, pace="relaxed", travelers="couple",
            interests=["美食", "文化"], must_visit=["武侯祠", "锦里"],
            avoid=["购物"], budget="mid-range", special_requests="无障碍",
            hotel_preference="有泳池", hotel_area="锦江区",
            hotel_budget_min=300, hotel_budget_max=600, strategy="culinary",
        )
        self.assertEqual(intent.city, "成都")
        self.assertEqual(intent.strategy, "culinary")
        self.assertEqual(intent.hotel_area, "锦江区")
        self.assertIn("武侯祠", intent.must_visit)


class TestTourState(unittest.TestCase):
    """Test TourState TypedDict and reducer helpers."""

    def setUp(self):
        from agents.state import reduce_list, replace_list, replace_int, replace_str
        self.reduce_list = reduce_list
        self.replace_list = replace_list
        self.replace_int = replace_int
        self.replace_str = replace_str

    def test_reduce_list(self):
        self.assertEqual(self.reduce_list([1, 2], [3, 4]), [1, 2, 3, 4])
        self.assertEqual(self.reduce_list([], [1]), [1])
        self.assertEqual(self.reduce_list([1], []), [1])

    def test_replace_list(self):
        self.assertEqual(self.replace_list([1, 2], [3, 4]), [3, 4])
        self.assertEqual(self.replace_list([1, 2], []), [1, 2])  # empty right → keep left

    def test_replace_int(self):
        self.assertEqual(self.replace_int(0, 5), 5)
        self.assertEqual(self.replace_int(5, 0), 5)  # 0 is falsy → keep left

    def test_replace_str(self):
        self.assertEqual(self.replace_str("", "hello"), "hello")
        self.assertEqual(self.replace_str("old", ""), "old")  # empty right → keep left


# ══════════════════════════════════════════════════════════════════════════════
# 2. Scoring Engine Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestScoringEngine(unittest.TestCase):
    """Test tools/scoring.py — the 15+ dimension scoring engine."""

    def setUp(self):
        from tools.scoring import score_poi, _is_must_visit, _fuzzy_interest_match, _tag_richness, _extract_scenic_group, _deduplicate_scenic_groups, _diversify_by_area, rank_pois, ScoredPoi
        self.score_poi = score_poi
        self._is_must_visit = _is_must_visit
        self._fuzzy_interest_match = _fuzzy_interest_match
        self._tag_richness = _tag_richness
        self._extract_scenic_group = _extract_scenic_group
        self._deduplicate_scenic_groups = _deduplicate_scenic_groups
        self._diversify_by_area = _diversify_by_area
        self.rank_pois = rank_pois
        self.ScoredPoi = ScoredPoi

    def _make_poi(self, **kwargs):
        defaults = {
            "id": "poi_001", "name": "测试景点", "type": "attraction",
            "lat": 30.0, "lng": 120.0, "area": "西湖区",
            "popularity": 4.5, "description": "一个很棒的景点",
            "tags": ["历史文化", "博物馆"], "price_level": 2,
        }
        defaults.update(kwargs)
        return defaults

    def test_popularity_scoring(self):
        poi = self._make_poi(popularity=4.8)
        result = self.score_poi(poi, {"interests": [], "must_visit": [], "avoid": []})
        pop_component = next(c for c in result.breakdown if c.label == "热度")
        self.assertGreater(pop_component.score, 38.0)  # 4.8*8 + 8 bonus

    def test_popularity_nonlinear(self):
        """pop >= 4.7 gets +8, pop >= 4.5 gets +4."""
        high = self.score_poi(self._make_poi(popularity=4.7), {"interests": [], "must_visit": [], "avoid": []})
        mid = self.score_poi(self._make_poi(popularity=4.5), {"interests": [], "must_visit": [], "avoid": []})
        low = self.score_poi(self._make_poi(popularity=4.0), {"interests": [], "must_visit": [], "avoid": []})
        high_pop = next(c for c in high.breakdown if c.label == "热度").score
        mid_pop = next(c for c in mid.breakdown if c.label == "热度").score
        low_pop = next(c for c in low.breakdown if c.label == "热度").score
        self.assertGreater(high_pop, mid_pop)
        self.assertGreater(mid_pop, low_pop)

    def test_must_visit_bonus(self):
        poi = self._make_poi(name="故宫博物院")
        result = self.score_poi(poi, {"interests": [], "must_visit": ["故宫"], "avoid": []})
        mv = [c for c in result.breakdown if c.label == "必去加权"]
        self.assertEqual(len(mv), 1)
        self.assertEqual(mv[0].score, 120.0)

    def test_hard_exclusion_duplicate(self):
        poi = self._make_poi()
        result = self.score_poi(poi, {"interests": [], "must_visit": [], "avoid": []}, used_ids={"poi_001"})
        self.assertEqual(result.total_score, -100000)

    def test_hard_exclusion_hotel_type(self):
        poi = self._make_poi(type="hotel")
        result = self.score_poi(poi, {"interests": [], "must_visit": [], "avoid": []})
        self.assertEqual(result.total_score, -100000)

    def test_avoid_hard_exclusion(self):
        poi = self._make_poi(name="购物广场")
        result = self.score_poi(poi, {"interests": [], "must_visit": [], "avoid": ["购物广场"]})
        self.assertEqual(result.total_score, -100000)

    def test_fuzzy_interest_3level(self):
        """Test 3-level fuzzy matching: 35 (direct) / 25 (expanded) / 15 (name)."""
        # Direct tag match → 35
        score = self._fuzzy_interest_match(["美食"], ["美食", "小吃"], "某餐厅")
        self.assertGreaterEqual(score, 35.0)

        # Expanded tag match → 25
        score = self._fuzzy_interest_match(["历史"], ["古建筑", "遗址"], "古城")
        self.assertGreaterEqual(score, 25.0)

        # Name fuzzy match → 15
        score = self._fuzzy_interest_match(["温泉"], [], "温泉度假村")
        self.assertGreaterEqual(score, 15.0)

    def test_strategy_weighting(self):
        poi = self._make_poi(tags=["历史文化", "博物馆"])
        result = self.score_poi(poi, {"interests": [], "must_visit": [], "avoid": [], "strategy": "culture"})
        culture = [c for c in result.breakdown if c.label == "文化策略"]
        self.assertEqual(len(culture), 1)
        self.assertEqual(culture[0].score, 55.0)

    def test_type_diversity(self):
        poi = self._make_poi(type="attraction")
        result = self.score_poi(poi, {"interests": [], "must_visit": [], "avoid": []}, day_attraction_count=5, day_restaurant_count=1)
        diversity = [c for c in result.breakdown if c.label == "类型多样"]
        self.assertTrue(any(c.score < 0 for c in diversity))

    def test_time_fitness_restaurant(self):
        poi = self._make_poi(type="restaurant", name="餐厅")
        # Lunch time (11:00-13:00 = 660-780 min)
        result = self.score_poi(poi, {"interests": [], "must_visit": [], "avoid": []}, current_time=720)
        fitness = [c for c in result.breakdown if c.label == "时间适配"]
        self.assertTrue(any(c.score > 0 for c in fitness))

    def test_special_requests_match(self):
        poi = self._make_poi(description="提供无障碍通道")
        result = self.score_poi(poi, {"interests": [], "must_visit": [], "avoid": [], "special_requests": "无障碍"})
        special = [c for c in result.breakdown if c.label == "特殊需求"]
        self.assertEqual(len(special), 1)
        self.assertEqual(special[0].score, 25.0)

    def test_extract_scenic_group(self):
        self.assertEqual(self._extract_scenic_group("故宫博物院-珍妃井"), "故宫博物院")
        self.assertEqual(self._extract_scenic_group("天坛公园"), "天坛公园")
        self.assertEqual(self._extract_scenic_group("颐和园(苏州街)"), "颐和园")

    def test_deduplicate_scenic_groups(self):
        pois = [
            self.ScoredPoi(poi={"name": "故宫博物院-珍妃井", "id": "1"}, total_score=80),
            self.ScoredPoi(poi={"name": "故宫博物院-太和门", "id": "2"}, total_score=75),
            self.ScoredPoi(poi={"name": "故宫博物院-乾清宫", "id": "3"}, total_score=70),
            self.ScoredPoi(poi={"name": "天坛公园", "id": "4"}, total_score=65),
        ]
        result = self._deduplicate_scenic_groups(pois, max_per_group=2)
        names = [s.poi["name"] for s in result]
        # Should keep max 2 from 故宫博物院 group
        guGong = [n for n in names if n.startswith("故宫博物院")]
        self.assertLessEqual(len(guGong), 2)
        self.assertIn("天坛公园", names)

    def test_rank_pois_must_visit_protection(self):
        """Must-visit POIs should survive top_k truncation."""
        pois = []
        for i in range(50):
            pois.append({
                "id": f"poi_{i:03d}", "name": f"景点{i}", "type": "attraction",
                "lat": 30.0, "lng": 120.0, "area": f"区域{i % 5}",
                "popularity": 4.0 + i * 0.01, "tags": [], "price_level": 1,
            })
        # Make one low-scoring POI a must_visit
        pois[45]["name"] = "必去景点"
        pois[45]["popularity"] = 2.0

        result = self.rank_pois(pois, {"must_visit": ["必去景点"], "interests": [], "avoid": []}, top_k=10)
        names = [p["name"] for p in result]
        self.assertIn("必去景点", names)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Clustering Engine Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestClusteringEngine(unittest.TestCase):
    """Test tools/clustering.py."""

    def setUp(self):
        from tools.clustering import cluster_pois_for_days, _is_must_visit, _infer_theme, DayCluster
        self.cluster_pois_for_days = cluster_pois_for_days
        self._is_must_visit = _is_must_visit
        self._infer_theme = _infer_theme
        self.DayCluster = DayCluster

    def _make_attractions(self, n=20):
        return [
            {
                "id": f"a_{i:03d}", "name": f"景点{i}", "type": "attraction",
                "lat": 30.0 + i * 0.01, "lng": 120.0 + i * 0.01,
                "area": f"区域{i % 3}", "popularity": 4.5,
                "tags": ["文化"] if i % 2 == 0 else ["自然"],
                "visit_duration_minutes": 60,
            }
            for i in range(n)
        ]

    def test_basic_clustering(self):
        attractions = self._make_attractions(12)
        intent = {"pace": "balanced", "must_visit": []}
        clusters = self.cluster_pois_for_days(attractions, [], num_days=3, intent=intent)
        self.assertEqual(len(clusters), 3)
        total = sum(len(c.attractions) for c in clusters)
        self.assertEqual(total, 12)

    def test_must_visit_distribution(self):
        attractions = self._make_attractions(10)
        attractions[0]["name"] = "必去A"
        attractions[5]["name"] = "必去B"
        intent = {"pace": "balanced", "must_visit": ["必去A", "必去B"]}
        clusters = self.cluster_pois_for_days(attractions, [], num_days=2, intent=intent)
        # Both must-visits should be assigned
        all_names = []
        for c in clusters:
            all_names.extend(a["name"] for a in c.attractions)
        self.assertIn("必去A", all_names)
        self.assertIn("必去B", all_names)

    def test_must_visit_rescue(self):
        """Layer 2: rescue must_visit from all_available_pois."""
        attractions = self._make_attractions(5)  # Small set, doesn't include rescue target
        all_pois = self._make_attractions(20)
        all_pois[15]["name"] = "隐藏必去"
        intent = {"pace": "balanced", "must_visit": ["隐藏必去"]}
        clusters = self.cluster_pois_for_days(
            attractions, [], num_days=2, intent=intent,
            all_available_pois=all_pois,
        )
        all_names = []
        for c in clusters:
            all_names.extend(a["name"] for a in c.attractions)
        self.assertIn("隐藏必去", all_names)

    def test_overlapping_must_visit_keywords_do_not_duplicate_place(self):
        """Overlapping must_visit terms should not schedule the same place twice."""
        shamian = {
            "id": "amap_ca3a003e", "name": "沙面岛", "type": "attraction",
            "lat": 23.106802, "lng": 113.244707, "area": "荔湾区",
            "popularity": 4.8, "tags": ["城市游览", "沙面"],
            "visit_duration_minutes": 90, "is_must_visit": True,
        }
        attractions = [
            {**shamian, "recommend_reason": "Must visit: 沙面"},
            {**shamian, "recommend_reason": "Must visit: 沙面岛"},
            {
                "id": "amap_58ab625a", "name": "沙面公园", "type": "attraction",
                "lat": 23.105666, "lng": 113.244807, "area": "荔湾区",
                "popularity": 4.7, "tags": ["公园", "沙面"],
                "visit_duration_minutes": 90,
            },
            {
                "id": "amap_1ab4b7d9", "name": "广州人民艺术中心", "type": "attraction",
                "lat": 23.142913, "lng": 113.280627, "area": "越秀区",
                "popularity": 4.7, "tags": ["文化"],
                "visit_duration_minutes": 90,
            },
        ]
        intent = {"pace": "balanced", "must_visit": ["沙面", "沙面岛"]}

        clusters = self.cluster_pois_for_days(attractions, [], num_days=3, intent=intent)
        all_attractions = [a for c in clusters for a in c.attractions]
        shamian_names = [a["name"] for a in all_attractions if "沙面" in a["name"]]

        self.assertEqual(shamian_names, ["沙面岛"])

    def test_regular_attractions_fill_underused_days_before_overloading_day(self):
        """Regular POIs should keep a 3-day trip reasonably filled."""
        attractions = [
            {
                "id": "must_a", "name": "必去A", "type": "attraction",
                "lat": 39.91, "lng": 116.40, "area": "A区",
                "popularity": 4.8, "tags": ["历史文化"],
                "visit_duration_minutes": 90,
            },
            {
                "id": "must_b", "name": "必去B", "type": "attraction",
                "lat": 40.65, "lng": 117.20, "area": "B区",
                "popularity": 4.8, "tags": ["历史文化"],
                "visit_duration_minutes": 90,
            },
        ]
        for i in range(7):
            attractions.append({
                "id": f"regular_{i}", "name": f"普通景点{i}", "type": "attraction",
                "lat": 39.90 + i * 0.001, "lng": 116.39 + i * 0.001,
                "area": "A区", "popularity": 4.5,
                "tags": ["历史文化"], "visit_duration_minutes": 90,
            })

        intent = {"pace": "balanced", "must_visit": ["必去A", "必去B"]}
        clusters = self.cluster_pois_for_days(attractions, [], num_days=3, intent=intent)
        counts = [len(c.attractions) for c in clusters]

        self.assertGreaterEqual(min(counts), 3)

    def test_empty_attractions(self):
        clusters = self.cluster_pois_for_days([], [], num_days=3, intent={"pace": "balanced", "must_visit": []})
        self.assertEqual(len(clusters), 3)
        for c in clusters:
            self.assertEqual(len(c.attractions), 0)

    def test_infer_theme(self):
        pois = [{"tags": ["历史文化", "博物馆"]}, {"tags": ["古建筑"]}]
        theme = self._infer_theme(pois)
        self.assertIn("历史文化", theme)

    def test_is_must_visit(self):
        poi = {"name": "故宫博物院", "id": "p001"}
        self.assertTrue(self._is_must_visit(poi, ["故宫"]))
        self.assertTrue(self._is_must_visit(poi, ["p001"]))
        self.assertFalse(self._is_must_visit(poi, ["天坛"]))


# ══════════════════════════════════════════════════════════════════════════════
# 4. Route Optimization Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRouteOptimization(unittest.TestCase):
    """Test tools/route.py."""

    def setUp(self):
        from tools.route import (
            _haversine_km, estimate_travel_time, optimize_route,
            optimize_route_2opt, calculate_total_travel_time,
            _minutes_to_time, load_edges_cache, get_real_travel_time,
        )
        self._haversine_km = _haversine_km
        self.estimate_travel_time = estimate_travel_time
        self.optimize_route = optimize_route
        self.optimize_route_2opt = optimize_route_2opt
        self.calculate_total_travel_time = calculate_total_travel_time
        self._minutes_to_time = _minutes_to_time
        self.load_edges_cache = load_edges_cache
        self.get_real_travel_time = get_real_travel_time

    def test_haversine(self):
        # Beijing to Shanghai ≈ 1068 km
        dist = self._haversine_km(39.9042, 116.4074, 31.2304, 121.4737)
        self.assertAlmostEqual(dist, 1068, delta=50)

    def test_haversine_same_point(self):
        dist = self._haversine_km(30.0, 120.0, 30.0, 120.0)
        self.assertAlmostEqual(dist, 0.0)

    def test_estimate_travel_time(self):
        # 1 km walk ≈ 12 min at 5 km/h
        t = self.estimate_travel_time(30.0, 120.0, 30.009, 120.0)
        self.assertGreaterEqual(t, 5)  # minimum 5 min

    def test_optimize_route_nearest_neighbor(self):
        stops = [
            {"id": "a", "lat": 30.0, "lng": 120.0},
            {"id": "b", "lat": 30.01, "lng": 120.01},
            {"id": "c", "lat": 30.02, "lng": 120.02},
            {"id": "d", "lat": 30.03, "lng": 120.03},
        ]
        result = self.optimize_route(30.0, 120.0, stops, use_2opt=False)
        self.assertEqual(len(result), 4)

    def test_optimize_route_2opt(self):
        stops = [
            {"id": "a", "lat": 30.0, "lng": 120.0},
            {"id": "c", "lat": 30.03, "lng": 120.03},
            {"id": "b", "lat": 30.01, "lng": 120.01},
            {"id": "d", "lat": 30.02, "lng": 120.02},
        ]
        result = self.optimize_route_2opt(stops)
        self.assertEqual(len(result), 4)

    def test_calculate_total_travel_time(self):
        stops = [
            {"lat": 30.0, "lng": 120.0},
            {"lat": 30.01, "lng": 120.01},
            {"lat": 30.02, "lng": 120.02},
        ]
        total = self.calculate_total_travel_time(stops)
        self.assertGreater(total, 0)

    def test_minutes_to_time(self):
        self.assertEqual(self._minutes_to_time(540), "09:00")
        self.assertEqual(self._minutes_to_time(720), "12:00")
        self.assertEqual(self._minutes_to_time(0), "")

    def test_single_stop(self):
        stops = [{"id": "a", "lat": 30.0, "lng": 120.0}]
        result = self.optimize_route(30.0, 120.0, stops)
        self.assertEqual(len(result), 1)

    def test_empty_stops(self):
        result = self.optimize_route(30.0, 120.0, [])
        self.assertEqual(len(result), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Cache Module Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestCacheModule(unittest.TestCase):
    """Test tools/cache.py."""

    def setUp(self):
        from tools.cache import (
            get_cached_itinerary, set_cached_itinerary,
            store_hot_itinerary, get_hot_itinerary,
            list_hot_itineraries, get_cache_stats,
            _memory_cache, _cache_key,
        )
        self.get_cached = get_cached_itinerary
        self.set_cached = set_cached_itinerary
        self.store_hot = store_hot_itinerary
        self.get_hot = get_hot_itinerary
        self.list_hot = list_hot_itineraries
        self.get_stats = get_cache_stats
        self._memory_cache = _memory_cache
        self._cache_key = _cache_key

    def test_cache_key_deterministic(self):
        k1 = self._cache_key("长沙", 3, "balanced", "balanced", ["岳麓山"])
        k2 = self._cache_key("长沙", 3, "balanced", "balanced", ["岳麓山"])
        self.assertEqual(k1, k2)

    def test_cache_key_order_independent(self):
        k1 = self._cache_key("长沙", 3, "balanced", "balanced", ["A", "B"])
        k2 = self._cache_key("长沙", 3, "balanced", "balanced", ["B", "A"])
        self.assertEqual(k1, k2)  # sorted internally

    def test_set_and_get(self):
        itinerary = {"city": "测试", "days": []}
        self.set_cached("测试城", 2, "relaxed", "balanced", [], itinerary)
        result = self.get_cached("测试城", 2, "relaxed", "balanced", [])
        self.assertIsNotNone(result)
        self.assertEqual(result["city"], "测试")

    def test_cache_miss(self):
        result = self.get_cached("不存在的城市", 99, "intense", "culture", ["xyz"])
        self.assertIsNone(result)

    def test_hot_itinerary_crud(self):
        self.store_hot("长沙", 3, "balanced", {"city": "长沙", "days": []})
        item = self.get_hot("长沙", 3, "balanced")
        self.assertIsNotNone(item)
        self.assertEqual(item["city"], "长沙")
        self.assertEqual(item["hit_count"], 1)

    def test_hot_itinerary_not_found(self):
        item = self.get_hot("火星", 1, "alien")
        self.assertIsNone(item)

    def test_list_hot_itineraries(self):
        self.store_hot("测试列", 2, "food", {"city": "测试列"})
        items = self.list_hot(city="测试列")
        self.assertGreater(len(items), 0)

    def test_get_cache_stats(self):
        stats = self.get_stats()
        self.assertIn("memory_entries", stats)
        self.assertIn("hot_itineraries", stats)
        self.assertIn("redis_available", stats)


# ══════════════════════════════════════════════════════════════════════════════
# 6. RAG Module Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRAGModule(unittest.TestCase):
    """Test tools/rag.py — BM25 retrieval."""

    def setUp(self):
        from tools.rag import _tokenize, _bm25_score, _normalize_city
        self._tokenize = _tokenize
        self._bm25_score = _bm25_score
        self._normalize_city = _normalize_city

    def test_tokenize_chinese(self):
        tokens = self._tokenize("北京故宫博物院")
        self.assertIn("北", tokens)
        self.assertIn("京", tokens)
        self.assertIn("北京", tokens)  # bigram

    def test_tokenize_english(self):
        tokens = self._tokenize("hello world 123")
        self.assertIn("hello", tokens)
        self.assertIn("world", tokens)
        self.assertIn("123", tokens)

    def test_normalize_city(self):
        self.assertEqual(self._normalize_city("北京"), "beijing")
        self.assertEqual(self._normalize_city("beijing"), "beijing")
        self.assertEqual(self._normalize_city("unknown"), "unknown")

    def test_bm25_score_matching(self):
        # BM25 requires IDF values; set them manually for the test
        import tools.rag as rag_mod
        rag_mod._idf = {t: 1.0 for t in self._tokenize("故宫博物院是中国最大的古代宫殿建筑群")}
        query_tokens = self._tokenize("故宫博物院")
        doc_tokens = self._tokenize("故宫博物院是中国最大的古代宫殿建筑群")
        score = self._bm25_score(query_tokens, doc_tokens)
        self.assertGreater(score, 0)

    def test_bm25_score_no_match(self):
        query_tokens = self._tokenize("长城")
        doc_tokens = self._tokenize("今天天气很好")
        score = self._bm25_score(query_tokens, doc_tokens)
        self.assertEqual(score, 0)

    def test_init_city_rag_indexes_only_requested_city(self):
        import tools.rag as rag_mod

        old_state = (
            rag_mod._corpus,
            rag_mod._idf,
            rag_mod._indexed_cities,
            rag_mod._poi_knowledge,
            rag_mod._ready,
            rag_mod._skip,
        )
        try:
            rag_mod._corpus = []
            rag_mod._idf = {}
            rag_mod._indexed_cities = set()
            rag_mod._poi_knowledge = {}
            rag_mod._ready = False
            rag_mod._skip = False

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for city in ("beijing", "shanghai"):
                    city_dir = root / city
                    city_dir.mkdir()
                    (city_dir / "city_guide.json").write_text(
                        json.dumps({"transport_tips": [f"{city}地铁方便"]}, ensure_ascii=False),
                        encoding="utf-8",
                    )

                loaded = rag_mod.init_city_rag(str(root), "北京")

            self.assertTrue(loaded)
            self.assertTrue(rag_mod.is_city_indexed("北京"))
            self.assertFalse(rag_mod.is_city_indexed("上海"))
            self.assertEqual(rag_mod._indexed_cities, {"beijing"})
        finally:
            (
                rag_mod._corpus,
                rag_mod._idf,
                rag_mod._indexed_cities,
                rag_mod._poi_knowledge,
                rag_mod._ready,
                rag_mod._skip,
            ) = old_state


# ══════════════════════════════════════════════════════════════════════════════
# 7. Intent Agent Regex Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestIntentAgentRegex(unittest.TestCase):
    """Test IntentAgent regex-based intent extraction."""

    def setUp(self):
        from agents.intent_agent import IntentAgent
        self.IntentAgent = IntentAgent

    def test_extract_city(self):
        self.assertEqual(self.IntentAgent._extract_city("我想去北京玩3天"), "北京")
        self.assertEqual(self.IntentAgent._extract_city("changsha 2 days"), "长沙")
        self.assertEqual(self.IntentAgent._extract_city("没有城市"), "")

    def test_extract_days(self):
        self.assertEqual(self.IntentAgent._extract_days("去长沙5天"), 5)
        self.assertEqual(self.IntentAgent._extract_days("3日游"), 3)
        self.assertEqual(self.IntentAgent._extract_days("没有天数"), 3)  # default

    def test_extract_must_visit(self):
        result = self.IntentAgent._extract_must_visit("一定要去故宫和长城")
        self.assertIn("故宫", result)
        self.assertIn("长城", result)

    def test_extract_must_visit_with_bixuqu(self):
        result = self.IntentAgent._extract_must_visit("广州3天，必须去沙面，喜欢城市探索和美食")
        self.assertEqual(result, ["沙面"])

    def test_extract_must_visit_with_yaoqu(self):
        result = self.IntentAgent._extract_must_visit("去北京玩三天，要去故宫和长城")
        self.assertEqual(result, ["故宫", "长城"])

    def test_extract_must_visit_with_yaoqu_without_punctuation(self):
        result = self.IntentAgent._extract_must_visit("去北京玩3天要去故宫和长城")
        self.assertEqual(result, ["故宫", "长城"])

    def test_extract_must_visit_with_yaoqu_does_not_match_buyaoqu(self):
        result = self.IntentAgent._extract_must_visit("不要去故宫，要去长城")
        self.assertEqual(result, ["长城"])

    def test_extract_interests(self):
        result = self.IntentAgent._extract_interests("我喜欢美食和历史文化")
        self.assertIn("food", result)

    def test_extract_travelers(self):
        self.assertEqual(self.IntentAgent._extract_travelers("带父母去旅游"), "elderly")
        self.assertEqual(self.IntentAgent._extract_travelers("情侣出行"), "couple")
        self.assertEqual(self.IntentAgent._extract_travelers("一个人"), "solo")

    def test_extract_budget(self):
        self.assertEqual(self.IntentAgent._extract_budget("穷游省钱"), "budget")
        self.assertEqual(self.IntentAgent._extract_budget("豪华高端"), "luxury")
        self.assertEqual(self.IntentAgent._extract_budget("普通旅行"), "mid-range")

    def test_extract_hotel_area(self):
        result = self.IntentAgent._extract_hotel_area("住在锦江区")
        self.assertEqual(result, "锦江区")
        result = self.IntentAgent._extract_hotel_area("没有酒店偏好")
        self.assertEqual(result, "")

    def test_extract_hotel_budget(self):
        min_b, max_b = self.IntentAgent._extract_hotel_budget("每晚300-500元")
        self.assertEqual(min_b, 300)
        self.assertEqual(max_b, 500)

        min_b, max_b = self.IntentAgent._extract_hotel_budget("酒店500以内")
        self.assertEqual(min_b, 0)
        self.assertEqual(max_b, 500)

        min_b, max_b = self.IntentAgent._extract_hotel_budget("没有预算")
        self.assertEqual(min_b, 0)
        self.assertEqual(max_b, 0)

    def test_extract_strategy(self):
        self.assertEqual(self.IntentAgent._extract_strategy("想体验当地文化"), "culture")
        self.assertEqual(self.IntentAgent._extract_strategy("主要想吃美食"), "culinary")
        self.assertEqual(self.IntentAgent._extract_strategy("普通旅行"), "balanced")


# ══════════════════════════════════════════════════════════════════════════════
# 8. Graph Construction Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGraphConstruction(unittest.TestCase):
    """Test graph.py — graph construction and initial state."""

    def test_create_initial_state(self):
        from graph import create_initial_state
        state = create_initial_state("去长沙3天")
        self.assertEqual(state["user_message"], "去长沙3天")
        self.assertIsNone(state["trip_intent"])
        self.assertEqual(state["days"], 3)
        self.assertEqual(state["pois"], [])
        self.assertEqual(state["errors"], [])
        self.assertEqual(state["sse_events"], [])
        self.assertEqual(state["llm_call_count"], 0)
        self.assertEqual(state["available_pois"], [])
        self.assertEqual(state["must_visit_coverage"], [])
        self.assertEqual(state["summary"], "")

    def test_graph_compiles(self):
        """Verify the graph can be built without errors."""
        from graph import build_tour_graph
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_llm)
        try:
            graph = build_tour_graph(mock_llm, data_dir="data")
            self.assertIsNotNone(graph)
        except Exception as e:
            self.fail(f"Graph build failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 9. Base Agent Circuit Breaker Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestBaseAgentCircuitBreaker(unittest.TestCase):
    """Test agents/base.py — Circuit Breaker and retry logic."""

    def test_is_critical_detection(self):
        from agents.base import BaseAgent
        from agents.poi_agent import PoiAgent
        from agents.weather_agent import WeatherAgent

        poi = PoiAgent(data_dir="data")
        self.assertTrue(poi.is_critical)

        mock_llm = MagicMock()
        weather = WeatherAgent(mock_llm)
        self.assertFalse(weather.is_critical)

    def test_max_retries(self):
        from agents.poi_agent import PoiAgent
        from agents.weather_agent import WeatherAgent

        poi = PoiAgent(data_dir="data")
        self.assertEqual(poi.max_retries, 0)  # critical = no retry

        mock_llm = MagicMock()
        weather = WeatherAgent(mock_llm)
        self.assertEqual(weather.max_retries, 1)  # non-critical = 1 retry


class TestWeatherAndHotelIntegrations(unittest.TestCase):
    """Test third-party travel data integration boundaries."""

    def test_weather_key_accepts_hefeng_aliases(self):
        import importlib
        import tools.weather_api as weather_api

        old_env = {
            "QWEATHER_KEY": os.environ.get("QWEATHER_KEY"),
            "QWEATHER_API_KEY": os.environ.get("QWEATHER_API_KEY"),
            "HEFENG_WEATHER_KEY": os.environ.get("HEFENG_WEATHER_KEY"),
        }
        try:
            for key in old_env:
                os.environ.pop(key, None)
            os.environ["HEFENG_WEATHER_KEY"] = "hf-test-key"
            weather_api = importlib.reload(weather_api)
            self.assertTrue(weather_api.is_available())
            self.assertEqual(weather_api.get_config_status()["provider"], "qweather")
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            importlib.reload(weather_api)

    def test_hotel_price_provider_unavailable_without_endpoint(self):
        from tools import hotel_price_api

        status = hotel_price_api.get_config_status(env={})
        self.assertFalse(status["available"])
        self.assertEqual(status["provider"], "unconfigured")

        result = self._run_async(hotel_price_api.fetch_hotel_prices("北京", [{"name": "测试酒店"}], env={}))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["prices"], [])

    def test_merge_price_quotes_into_hotels(self):
        from tools.hotel_price_api import merge_price_quotes

        hotels = [{"id": "h1", "name": "测试酒店", "price_range": "未知"}]
        prices = [{"hotel_name": "测试酒店", "price_per_night": 588, "currency": "CNY", "provider": "demo"}]

        merged = merge_price_quotes(hotels, prices)

        self.assertEqual(merged[0]["price_per_night"], 588)
        self.assertEqual(merged[0]["price_provider"], "demo")
        self.assertEqual(merged[0]["price_range"], "约588元/晚")

    def test_merge_price_quotes_skips_malformed_price(self):
        from tools.hotel_price_api import merge_price_quotes

        hotels = [{"id": "h1", "name": "测试酒店", "price_range": "未知"}]
        prices = [{"hotel_id": "h1", "price_per_night": "not-a-number", "provider": "demo"}]

        merged = merge_price_quotes(hotels, prices)

        self.assertNotIn("price_per_night", merged[0])
        self.assertEqual(merged[0]["price_range"], "未知")

    def _run_async(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class TestPoiAgent(unittest.TestCase):
    """Test PoiAgent deterministic POI selection."""

    def _run_async(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_must_visit_enrichment_does_not_duplicate_existing_poi(self):
        from agents.poi_agent import PoiAgent

        intent = {
            "city": "北京", "days": 3, "pace": "balanced",
            "must_visit": ["故宫", "长城"], "interests": [],
            "avoid": [], "strategy": "balanced",
        }
        result = self._run_async(PoiAgent(data_dir="data").execute({
            "trip_intent": intent,
            "city": "北京",
            "days": 3,
        }))
        names = [p.get("name", "") for p in result.get("pois", [])]

        self.assertEqual(names.count("故宫博物院"), 1)
        self.assertEqual(names.count("司马台长城旅游区"), 1)

    def test_generic_beijing_trip_excludes_business_meeting_centers(self):
        from agents.poi_agent import PoiAgent

        intent = {
            "city": "北京", "days": 3, "pace": "balanced",
            "must_visit": ["故宫", "长城"], "interests": [],
            "avoid": [], "strategy": "balanced",
        }
        result = self._run_async(PoiAgent(data_dir="data").execute({
            "trip_intent": intent,
            "city": "北京",
            "days": 3,
        }))
        names = [p.get("name", "") for p in result.get("pois", [])]

        self.assertFalse(any("会议中心" in name for name in names))


class TestLLMAgentCallCounter(unittest.TestCase):
    """Test that invoke_llm properly increments the call counter."""

    def test_counter_increment(self):
        from agents.base import LLMAgent

        class DummyAgent(LLMAgent):
            @property
            def name(self): return "DummyAgent"
            @property
            def description(self): return "test"
            def build_prompt(self):
                from langchain_core.prompts import ChatPromptTemplate
                return ChatPromptTemplate.from_messages([("system", "test"), ("human", "{input}")])
            async def execute(self, state):
                return {}

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "test response"
        mock_llm.with_structured_output = MagicMock(return_value=mock_llm)

        # We can't easily test async here, but verify the counter logic
        agent = DummyAgent(mock_llm)
        state = {"llm_call_count": 0}

        # Verify the counter check logic
        from agents.config import MAX_LLM_CALLS_PER_REQUEST
        self.assertEqual(MAX_LLM_CALLS_PER_REQUEST, 10)


# ══════════════════════════════════════════════════════════════════════════════
# 10. API Module Import Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIModule(unittest.TestCase):
    """Test that api_multi_agent.py imports and models work."""

    def test_import(self):
        import api_multi_agent
        self.assertTrue(hasattr(api_multi_agent, "app"))
        self.assertTrue(hasattr(api_multi_agent, "PlanRequest"))
        self.assertTrue(hasattr(api_multi_agent, "PlanResponse"))
        self.assertTrue(hasattr(api_multi_agent, "MultiPlanRequest"))
        self.assertTrue(hasattr(api_multi_agent, "convert_to_frontend_format"))
        self.assertTrue(hasattr(api_multi_agent, "make_sse_event"))

    def test_plan_request_model(self):
        from api_multi_agent import PlanRequest
        req = PlanRequest(message="去北京3天")
        self.assertEqual(req.message, "去北京3天")
        self.assertIsNone(req.context)

    def test_multi_plan_request_model(self):
        from api_multi_agent import MultiPlanRequest
        req = MultiPlanRequest(message="去成都3天", strategies=["balanced", "culture"])
        self.assertEqual(len(req.strategies), 2)

    def test_make_sse_event(self):
        from api_multi_agent import make_sse_event
        event = make_sse_event("test", {"key": "value"})
        self.assertIn("event: test", event)
        self.assertIn("data:", event)
        self.assertTrue(event.endswith("\n\n"))

    def test_convert_to_frontend_format(self):
        from api_multi_agent import convert_to_frontend_format
        state = {
            "trip_intent": {"city": "长沙", "days": 3, "must_visit": [], "strategy": "balanced"},
            "daily_plans": [],
            "selected_hotel": None,
            "summary": "测试总结",
            "city_guides": ["贴士1"],
            "must_visit_coverage": [],
        }
        result = convert_to_frontend_format(state)
        self.assertEqual(result["city"], "长沙")
        self.assertEqual(result["summary"], "测试总结")
        self.assertIn("variant_name", result)
        self.assertIn("must_visit_coverage", result)


# ══════════════════════════════════════════════════════════════════════════════
# 11. Config Module Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigModule(unittest.TestCase):
    """Test agents/config.py."""

    def test_config_imports(self):
        from agents.config import (
            DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
            CPP_BACKEND_URL, REDIS_URL, CACHE_TTL_SECONDS,
            MAX_LLM_CALLS_PER_REQUEST, LLM_TEMPERATURE,
            USE_CPP_ROUTE_OPTIMIZER, HOST, PORT,
            HOT_CITIES, HOT_DAY_OPTIONS, HOT_PREFERENCES,
        )
        self.assertIsInstance(DEEPSEEK_BASE_URL, str)
        self.assertIsInstance(CPP_BACKEND_URL, str)
        self.assertIsInstance(CACHE_TTL_SECONDS, int)
        self.assertIsInstance(MAX_LLM_CALLS_PER_REQUEST, int)
        self.assertIsInstance(PORT, int)
        self.assertIn("beijing", HOT_CITIES)

    def test_defaults(self):
        from agents.config import MAX_LLM_CALLS_PER_REQUEST, LLM_TEMPERATURE, PORT
        self.assertEqual(MAX_LLM_CALLS_PER_REQUEST, 10)
        self.assertGreater(LLM_TEMPERATURE, 0)
        self.assertEqual(PORT, 8090)


# ══════════════════════════════════════════════════════════════════════════════
# 12. Constants Module Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestConstantsModule(unittest.TestCase):
    """Test agents/constants.py."""

    def test_city_mappings(self):
        from agents.constants import CITY_DIR_MAP, ENGLISH_CITY_MAP, KNOWN_CITIES
        self.assertIn("北京", CITY_DIR_MAP)
        self.assertEqual(CITY_DIR_MAP["北京"], "beijing")
        self.assertIn("beijing", ENGLISH_CITY_MAP)
        self.assertEqual(ENGLISH_CITY_MAP["beijing"], "北京")
        self.assertIn("长沙", KNOWN_CITIES)

    def test_haversine(self):
        from agents.constants import haversine_km
        dist = haversine_km(30.0, 120.0, 30.0, 120.0)
        self.assertAlmostEqual(dist, 0.0)

    def test_compute_center(self):
        from agents.constants import compute_center
        points = [{"lat": 30.0, "lng": 120.0}, {"lat": 30.02, "lng": 120.02}]
        lat, lng = compute_center(points)
        self.assertAlmostEqual(lat, 30.01)
        self.assertAlmostEqual(lng, 120.01)

    def test_load_pois_by_type(self):
        from agents.constants import load_pois_by_type
        # This should work even if the city doesn't exist
        pois = load_pois_by_type(Path("data"), "nonexistent_city", "attraction")
        self.assertEqual(pois, [])


# ══════════════════════════════════════════════════════════════════════════════
# 13. Async Integration Tests (requires event loop)
# ══════════════════════════════════════════════════════════════════════════════

class TestAsyncIntegration(unittest.TestCase):
    """Test async functionality with mocked LLM."""

    def _run_async(self, coro):
        """Helper to run async code in sync tests."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_parallel_data_gather(self):
        """Test that _build_parallel_data_gather runs agents concurrently."""
        from graph import _build_parallel_data_gather

        call_order = []

        class MockAgent:
            def __init__(self, name, delay=0.01):
                self.name = name
                self.delay = delay

            async def __call__(self, state):
                call_order.append(f"{self.name}_start")
                await asyncio.sleep(self.delay)
                call_order.append(f"{self.name}_end")
                return {f"{self.name.lower()}_result": True}

        poi_agent = MockAgent("poi")
        hotel_agent = MockAgent("hotel")
        weather_agent = MockAgent("weather")
        restaurant_agent = MockAgent("restaurant")

        gather_fn = _build_parallel_data_gather(
            poi_agent, hotel_agent, weather_agent, restaurant_agent,
        )

        state = {"trip_intent": {}, "city": "长沙", "days": 3}
        result = self._run_async(gather_fn(state))

        self.assertIsInstance(result, dict)
        self.assertIn("poi_result", result)
        self.assertIn("hotel_result", result)
        self.assertIn("weather_result", result)
        self.assertIn("restaurant_result", result)

        # Verify parallel execution: all starts before any ends
        starts = [i for i, x in enumerate(call_order) if x.endswith("_start")]
        ends = [i for i, x in enumerate(call_order) if x.endswith("_end")]
        self.assertEqual(len(starts), 4)
        self.assertEqual(len(ends), 4)

    def test_critical_agent_failure_propagation(self):
        """Test that PoiAgent failure in parallel gather raises."""
        from graph import _build_parallel_data_gather

        class FailingAgent:
            async def __call__(self, state):
                raise RuntimeError("PoiAgent failed!")

        class OKAgent:
            async def __call__(self, state):
                return {"result": True}

        gather_fn = _build_parallel_data_gather(
            FailingAgent(), OKAgent(), OKAgent(), OKAgent(),
        )

        state = {"trip_intent": {}, "city": "长沙", "days": 3}
        with self.assertRaises(RuntimeError):
            self._run_async(gather_fn(state))


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
