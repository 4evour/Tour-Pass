"""Tour Pass Multi-Agent System - POI Scoring Tools.

Adapted from legacy agent/scorer.py with enhancements.
"""

import math
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScoreComponent:
    """A single scoring component."""
    label: str
    score: float
    detail: str


@dataclass
class ScoredPoi:
    """A POI with its score breakdown."""
    poi: dict
    total_score: float
    breakdown: list[ScoreComponent]
    reason: str = ""


# Strategy tag mappings
_STRATEGY_TAGS = {
    "culture": {"文化", "历史", "博物馆", "古迹", "寺庙", "教堂", "艺术", "展览"},
    "culinary": {"美食", "小吃", "餐厅", "咖啡", "甜点", "夜市", "火锅", "烧烤"},
    "nature": {"自然", "公园", "山", "湖", "海", "森林", "花园", "风景"},
    "shopping": {"购物", "商场", "市场", "特产", "免税", "奢侈品"},
    "nightlife": {"夜生活", "酒吧", "KTV", "演出", "音乐", "派对"},
    "family": {"亲子", "儿童", "游乐园", "动物园", "水族馆", "科技馆"},
    "photography": {"摄影", "网红", "打卡", "美景", "日出", "日落"},
    "adventure": {"户外", "徒步", "攀岩", "潜水", "滑雪", "漂流"},
}


def _fuzzy_interest_match(interests: list[str], tags: list[str], name: str) -> float:
    """Calculate fuzzy interest match score."""
    if not interests:
        return 0.0
    
    score = 0.0
    for interest in interests:
        # Direct tag match
        if interest in tags:
            score += 15.0
            continue
        
        # Strategy tag match
        strategy_set = _STRATEGY_TAGS.get(interest, set())
        if strategy_set and any(t in strategy_set for t in tags):
            score += 12.0
            continue
        
        # Fuzzy name match
        if interest in name:
            score += 10.0
            continue
        
        # Partial tag match
        for tag in tags:
            if interest in tag or tag in interest:
                score += 8.0
                break
    
    return min(score, 30.0)  # Cap at 30


def _tag_richness(tags: list[str]) -> float:
    """Calculate tag richness bonus."""
    generic = {"城市游览", "景点", "室内", "户外", "休闲", "风景名胜"}
    meaningful = [t for t in tags if t not in generic and len(t) >= 2]
    
    if len(meaningful) >= 5:
        return 8.0
    elif len(meaningful) >= 3:
        return 5.0
    elif len(meaningful) >= 1:
        return 2.0
    return 0.0


def score_poi(
    poi: dict,
    intent: dict,
    current_area: str = "",
    current_time: int = 540,  # 9:00 AM
    visited_areas: Optional[set] = None,
) -> ScoredPoi:
    """Score a single POI against the user's intent.
    
    Args:
        poi: POI data dictionary.
        intent: User intent dictionary.
        current_area: Current geographic area.
        current_time: Current time in minutes from midnight.
        visited_areas: Set of already visited areas.
    
    Returns:
        ScoredPoi with total score and breakdown.
    """
    breakdown = []
    
    # Popularity base (non-linear scaling)
    pop = poi.get("popularity", 0)
    pop_base = pop * 8.0
    if pop >= 4.7:
        pop_base += 8.0  # Extra boost for top-tier
    elif pop >= 4.5:
        pop_base += 4.0
    breakdown.append(ScoreComponent("热度", pop_base, f"热度{pop}"))
    
    # Interest match
    interests = intent.get("interests", [])
    tags = poi.get("tags", [])
    name = poi.get("name", "")
    interest_score = _fuzzy_interest_match(interests, tags, name)
    if interest_score > 0:
        breakdown.append(ScoreComponent("兴趣匹配", interest_score, "兴趣标签匹配"))
    
    # Strategy weighting
    strategy = intent.get("strategy", "balanced")
    strategy_tags = _STRATEGY_TAGS.get(strategy, set())
    if strategy == "culture" and any(t in strategy_tags for t in tags):
        breakdown.append(ScoreComponent("文化策略", 55.0, "文化优先加权"))
    elif strategy == "culinary" and any(t in strategy_tags for t in tags):
        breakdown.append(ScoreComponent("美食策略", 50.0, "美食优先加权"))
    elif strategy == "nature" and any(t in strategy_tags for t in tags):
        breakdown.append(ScoreComponent("自然策略", 50.0, "自然优先加权"))
    
    # Tag richness bonus
    richness = _tag_richness(tags)
    if richness > 0:
        meaningful_count = len([t for t in tags if t not in {"城市游览", "景点", "室内", "户外", "休闲"} and len(t) >= 2])
        breakdown.append(ScoreComponent("信息丰富", richness, f"{meaningful_count}个有效标签"))
    
    # Must-visit bonus
    must_visit = intent.get("must_visit", [])
    for mv in must_visit:
        if mv in name or mv == poi.get("id"):
            breakdown.append(ScoreComponent("必去加权", 120.0, f"命中必去「{mv}」"))
            break
    
    # Avoid penalty (soft)
    avoid = intent.get("avoid", [])
    for avoid_term in avoid:
        if avoid_term and (avoid_term in (poi.get("description", "") or "") or
                          any(avoid_term in tag for tag in tags)):
            breakdown.append(ScoreComponent("避免项", -40.0, f"命中避免「{avoid_term}」"))
    
    # Price penalty
    price_level = poi.get("price_level", 1)
    price_penalty = -(price_level) * 3.0
    breakdown.append(ScoreComponent("价格惩罚", price_penalty, f"价格等级{price_level}"))

    # Shopping/commercial penalty (unless user explicitly wants shopping)
    shopping_tags = {"购物", "商圈", "商场", "购物中心", "免税"}
    interests = intent.get("interests", [])
    has_shopping_interest = any(i in ("shopping", "购物") for i in interests)
    if not has_shopping_interest and any(t in shopping_tags for t in tags):
        breakdown.append(ScoreComponent("购物降权", -35.0, "非购物行程，降低商场权重"))


    # Image availability bonus - prefer POIs with photos for better UX
    if poi.get("image_url"):
        breakdown.append(ScoreComponent("图片加分", 8.0, "有实景图片"))

    
    # Area diversity
    if visited_areas and poi.get("area") and poi["area"] not in visited_areas:
        breakdown.append(ScoreComponent("区域多样", 15.0, "探索新区域"))
    
    # Travel time penalty (simplified)
    if current_area and poi.get("area") and poi["area"] != current_area:
        travel_penalty = -30 * 1.2  # 30min estimate
        breakdown.append(ScoreComponent("通勤惩罚", travel_penalty, "跨区通勤"))
    elif current_area:
        breakdown.append(ScoreComponent("通勤惩罚", 0, "同区域"))
    
    # Total score
    total = sum(c.score for c in breakdown)
    
    # Build reason
    top_reasons = sorted(breakdown, key=lambda c: abs(c.score), reverse=True)[:3]
    reason = "；".join(f"{r.label}({r.score:+.0f})" for r in top_reasons if r.score != 0)
    
    return ScoredPoi(poi=poi, total_score=total, breakdown=breakdown, reason=reason)


def rank_pois(
    pois: list[dict],
    intent: dict,
    top_k: int = 20,
    current_area: str = "",
    visited_areas: Optional[set] = None,
) -> list[dict]:
    """Rank POIs by score and return top K.
    
    Args:
        pois: List of POI dictionaries.
        intent: User intent dictionary.
        top_k: Number of top POIs to return.
        current_area: Current geographic area.
        visited_areas: Set of already visited areas.
    
    Returns:
        List of top K POIs with scores.
    """
    must_visit = set(intent.get("must_visit", []))
    
    # Score all POIs
    scored = []
    must_visit_pois = []
    
    for poi in pois:
        # Check if this is a must-visit
        is_must = any(mv in poi.get("name", "") or mv == poi.get("id") for mv in must_visit)
        
        result = score_poi(poi, intent, current_area, visited_areas=visited_areas)
        
        if is_must:
            result.poi["is_must_visit"] = True
            must_visit_pois.append(result)
        else:
            scored.append(result)
    
    # Sort by score
    scored.sort(key=lambda x: x.total_score, reverse=True)
    
    # Ensure must-visit POIs are included
    remaining_slots = top_k - len(must_visit_pois)
    top_scored = scored[:remaining_slots]
    
    # Combine and return
    all_results = must_visit_pois + top_scored
    
    # Add score to POI data
    enriched = []
    for result in all_results:
        poi = result.poi.copy()
        poi["_score"] = result.total_score
        poi["_score_reason"] = result.reason
        enriched.append(poi)
    
    return enriched

