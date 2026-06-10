"""Multi-dimensional POI scoring — Python port of C++ buildScoreBreakdown.

Scores POIs based on: popularity, interest match, strategy, must-visit,
travel time, type diversity, area diversity, time fitness, and more.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional

from .models import PoiInfo, TripIntent


@dataclass
class ScoreComponent:
    label: str
    score: float
    reason: str


@dataclass
class ScoredPoi:
    poi: PoiInfo
    total_score: float
    breakdown: list[ScoreComponent] = field(default_factory=list)
    reason: str = ""  # human-readable summary


# Strategy → tag mappings (mirrors C++ hasAnyTag logic)
_STRATEGY_TAGS = {
    "culture": {"历史文化", "博物馆", "古建筑", "书院", "寺庙", "世界遗产", "科教文化服务"},
    "culinary": {"美食", "小吃", "夜市", "茶饮", "街区", "餐饮"},
    "nature": {"自然", "公园", "山水", "户外", "湖泊", "森林", "海滩"},
    "balanced": set(),  # no special weighting
}


def score_poi(
    poi: PoiInfo,
    intent: TripIntent,
    used_ids: set[str],
    current_area: str = "",
    current_time: int = 540,
    day_attraction_count: int = 0,
    day_restaurant_count: int = 0,
    visited_areas: Optional[set[str]] = None,
) -> ScoredPoi:
    """Score a single POI against the user's intent and current context."""
    breakdown: list[ScoreComponent] = []

    # --- Hard exclusions ---
    if poi.id in used_ids:
        return ScoredPoi(poi=poi, total_score=-100000, breakdown=[
            ScoreComponent("重复排除", -100000, "该POI已在行程中")
        ])

    if poi.type in ("hotel", "transit"):
        return ScoredPoi(poi=poi, total_score=-100000, breakdown=[
            ScoreComponent("类型排除", -100000, "酒店/交通站点不参与评分")
        ])

    if poi.name in intent.avoid or poi.id in intent.avoid:
        return ScoredPoi(poi=poi, total_score=-100000, breakdown=[
            ScoreComponent("避免项", -100000, "用户明确避开")
        ])

    # --- Popularity base ---
    pop_mult = 12.0 if intent.strategy == "compact" else 10.0
    pop_score = poi.popularity * pop_mult
    breakdown.append(ScoreComponent("热度", pop_score, f"热度{poi.popularity}"))

    # --- Interest match ---
    interest_bonus = 42.0 if intent.strategy == "compact" else 35.0
    for interest in intent.interests:
        if any(interest in tag for tag in poi.tags):
            breakdown.append(ScoreComponent("兴趣匹配", interest_bonus, f"匹配「{interest}」"))

    # --- Strategy weighting ---
    strategy = intent.strategy or "balanced"
    strategy_tags = _STRATEGY_TAGS.get(strategy, set())
    if strategy == "culture" and any(t in strategy_tags for t in poi.tags):
        breakdown.append(ScoreComponent("文化策略", 70.0, "文化优先加权"))
    elif strategy == "culinary" and any(t in strategy_tags for t in poi.tags):
        breakdown.append(ScoreComponent("美食策略", 65.0, "美食优先加权"))
    elif strategy == "nature" and any(t in strategy_tags for t in poi.tags):
        breakdown.append(ScoreComponent("自然策略", 65.0, "自然优先加权"))

    # --- Must-visit bonus ---
    for mv in intent.must_visit:
        if mv in poi.name or mv == poi.id:
            breakdown.append(ScoreComponent("必去加权", 120.0, f"命中必去「{mv}」"))
            break

    # --- Avoid penalty (soft) ---
    for avoid_term in intent.avoid:
        if avoid_term and (avoid_term in (poi.description or "") or
                          any(avoid_term in tag for tag in poi.tags)):
            breakdown.append(ScoreComponent("避免项", -40.0, f"命中避免「{avoid_term}」"))

    # --- Price penalty ---
    price_penalty = -(poi.price_level or 1) * 3.0
    breakdown.append(ScoreComponent("价格惩罚", price_penalty, f"价格等级{poi.price_level}"))

    # --- Type diversity ---
    if poi.type == "attraction" and day_attraction_count > day_restaurant_count + 1:
        breakdown.append(ScoreComponent("类型多样", -15.0, "景点过多，偏好多样"))
    if poi.type == "restaurant" and day_restaurant_count < day_attraction_count:
        breakdown.append(ScoreComponent("类型多样", 12.0, "用餐时段加分"))

    # --- Area diversity ---
    if visited_areas and poi.area and poi.area not in visited_areas:
        breakdown.append(ScoreComponent("区域多样", 8.0, "探索新区域"))

    # --- Time fitness for restaurants ---
    if poi.type == "restaurant":
        is_lunch = 660 <= current_time <= 780
        is_dinner = 1020 <= current_time <= 1200
        if is_lunch or is_dinner:
            breakdown.append(ScoreComponent("时间适配", 18.0, "用餐时段"))
        else:
            breakdown.append(ScoreComponent("时间适配", -10.0, "非用餐时段"))

    # --- Nightlife time ---
    if poi.type == "nightlife" and current_time >= 1080:
        breakdown.append(ScoreComponent("时间适配", 15.0, "夜间场景"))

    # --- Top attraction tier ---
    if poi.popularity >= 4.7:
        breakdown.append(ScoreComponent("热门加分", 10.0, "顶级热门"))
    elif poi.popularity >= 4.3:
        breakdown.append(ScoreComponent("热门加分", 5.0, "高人气"))

    # --- Travel time penalty (simplified: same area = 0, different = 30min estimate) ---
    if current_area and poi.area and poi.area != current_area:
        travel_penalty = -30 * 1.2  # 30min estimate, multiplier 1.2
        breakdown.append(ScoreComponent("通勤惩罚", travel_penalty, f"跨区通勤"))
    elif current_area:
        breakdown.append(ScoreComponent("通勤惩罚", 0, "同区域"))

    # --- Special requests match ---
    if intent.special_requests:
        sr = intent.special_requests.lower()
        if sr in (poi.description or "").lower() or any(sr in t for t in poi.tags):
            breakdown.append(ScoreComponent("特殊需求", 25.0, "匹配特殊要求"))

    total = sum(c.score for c in breakdown)

    # Build human-readable reason
    top_reasons = sorted(breakdown, key=lambda c: abs(c.score), reverse=True)[:3]
    reason = "；".join(f"{r.label}({r.score:+.0f})" for r in top_reasons if r.score != 0)

    return ScoredPoi(poi=poi, total_score=total, breakdown=breakdown, reason=reason)


def rank_pois(
    pois: list[PoiInfo],
    intent: TripIntent,
    used_ids: Optional[set[str]] = None,
    current_area: str = "",
    current_time: int = 540,
    day_attraction_count: int = 0,
    day_restaurant_count: int = 0,
    visited_areas: Optional[set[str]] = None,
    top_k: int = 0,
) -> list[ScoredPoi]:
    """Score and rank all POIs. Returns sorted list (highest first)."""
    used = used_ids or set()
    areas = visited_areas or set()

    scored = []
    for poi in pois:
        s = score_poi(
            poi=poi,
            intent=intent,
            used_ids=used,
            current_area=current_area,
            current_time=current_time,
            day_attraction_count=day_attraction_count,
            day_restaurant_count=day_restaurant_count,
            visited_areas=areas,
        )
        scored.append(s)

    scored.sort(key=lambda x: x.total_score, reverse=True)
    if top_k > 0:
        scored = scored[:top_k]
    return scored