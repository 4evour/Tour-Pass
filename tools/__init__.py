"""Tour Pass Multi-Agent System - Tools."""

from tools.scoring import score_poi, rank_pois, ScoredPoi, ScoreComponent, _is_must_visit
from tools.clustering import cluster_pois_for_days, DayCluster
from tools.route import (
    optimize_route,
    optimize_route_2opt,
    optimize_route_cpp,
    optimize_route_smart,
    estimate_travel_time,
    calculate_total_travel_time,
    get_real_travel_time,
    get_route_metric,
    load_edges_cache,
)
from tools import rag
from tools import hotel_price_api

__all__ = [
    # Scoring
    "score_poi",
    "rank_pois",
    "ScoredPoi",
    "ScoreComponent",
    "_is_must_visit",

    # Clustering
    "cluster_pois_for_days",
    "DayCluster",

    # Route
    "optimize_route",
    "optimize_route_2opt",
    "optimize_route_cpp",
    "optimize_route_smart",
    "estimate_travel_time",
    "calculate_total_travel_time",
    "get_real_travel_time",
    "get_route_metric",
    "load_edges_cache",

    # RAG
    "rag",
    "hotel_price_api",
]
