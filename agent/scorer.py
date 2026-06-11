"""Multi-dimensional POI scoring — Python port of C++ buildScoreBreakdown.

Scores POIs based on: popularity, interest match, strategy, must-visit,
travel time, type diversity, area diversity, time fitness, and more.

v2: Fixed score clustering, sub-POI flooding, and diversity issues.
"""
from __future__ import annotations
import math
import re
from collections import defaultdict
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

# Expanded interest → tag mappings for fuzzy matching
_INTEREST_TAGS = {
    "历史": {"历史", "文化", "古建筑", "世界遗产", "遗址", "故居", "纪念馆", "陵墓"},
    "文化": {"文化", "博物馆", "科教文化服务", "美术馆", "展览馆", "书院"},
    "美食": {"美食", "小吃", "夜市", "茶饮", "餐饮", "街区"},
    "自然": {"自然", "公园", "山水", "户外", "湖泊", "森林", "海滩", "山脉", "峡谷"},
    "购物": {"购物", "商圈", "商业街", "步行街", "商场"},
    "夜生活": {"夜生活", "酒吧", "夜景", "夜市"},
    "文艺": {"文艺", "文创", "艺术", "剧院", "音乐厅"},
    "亲子": {"亲子", "游乐场", "主题公园", "动物园", "水族馆", "科技馆"},
    "浪漫": {"浪漫", "情侣", "观景台", "日落", "花海"},
    "宗教": {"宗教", "寺庙", "教堂", "道观", "佛寺"},
    "拍照": {"拍照", "摄影", "观景台", "网红", "打卡"},
    "户外": {"户外", "徒步", "登山", "漂流", "滑雪", "潜水"},
    "温泉": {"温泉", "spa", "养生"},
    "古镇": {"古镇", "古村", "古城", "老街"},
}


def _is_must_visit(poi: PoiInfo, must_visit: list[str]) -> bool:
    """Check if a POI matches any must_visit keyword (substring or exact id match)."""
    for mv in must_visit:
        if mv in poi.name or mv == poi.id:
            return True
    return False


def _extract_scenic_group(name: str) -> str:
    """Extract the parent scenic area name from a sub-POI name.
    
    Examples:
        "故宫博物院-珍妃井" -> "故宫博物院"
        "故宫博物院-太和门" -> "故宫博物院"
        "天坛公园" -> "天坛公园"  (no sub-POI)
        "颐和园-苏州街" -> "颐和园"
    """
    if "-" in name:
        return name.split("-")[0]
    # Also handle parentheses like "故宫博物院(珍妃井)"
    if "(" in name:
        return name.split("(")[0]
    return name


def _fuzzy_interest_match(interests: list[str], tags: list[str], name: str) -> float:
    """Fuzzy interest matching score. Returns a bonus score.
    
    Instead of binary match (35 or 0), gives partial credit for related tags.
    """
    if not interests:
        return 0.0

    total_bonus = 0.0
    for interest in interests:
        # Direct tag match (highest bonus)
        if any(interest in tag for tag in tags):
            total_bonus += 35.0
            continue

        # Expanded tag match via _INTEREST_TAGS
        expanded = _INTEREST_TAGS.get(interest, set())
        if expanded and any(t in expanded for t in tags):
            total_bonus += 25.0
            continue

        # Name/description fuzzy match
        if any(kw in name for kw in expanded if len(kw) >= 2):
            total_bonus += 15.0

    return total_bonus


def _tag_richness(tags: list[str]) -> float:
    """Score based on tag richness — POIs with more descriptive tags are better.
    
    Filters out generic tags and counts meaningful ones.
    """
    generic = {"城市游览", "景点", "室内", "户外", "休闲"}
    meaningful = [t for t in tags if t not in generic and len(t) >= 2]
    # Cap at 5 meaningful tags for scoring
    return min(len(meaningful), 5) * 2.0


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

    # --- Popularity base (non-linear scaling for better spread) ---
    # Square-root scaling: high popularity still helps, but doesn't dominate as much
    # pop=5.0 -> 50, pop=4.9 -> 49, pop=4.0 -> 40, pop=3.0 -> 30
    pop_base = poi.popularity * 8.0
    # Add a non-linear bonus for very high popularity (>4.5)
    if poi.popularity >= 4.7:
        pop_base += 8.0  # Extra boost for top-tier
    elif poi.popularity >= 4.5:
        pop_base += 4.0
    breakdown.append(ScoreComponent("热度", pop_base, f"热度{poi.popularity}"))

    # --- Interest match (fuzzy, with partial credit) ---
    interest_score = _fuzzy_interest_match(intent.interests, poi.tags, poi.name)
    if interest_score > 0:
        breakdown.append(ScoreComponent("兴趣匹配", interest_score, f"兴趣标签匹配"))

    # --- Strategy weighting (increased from 65-70 to 55-60 for better balance) ---
    strategy = intent.strategy or "balanced"
    strategy_tags = _STRATEGY_TAGS.get(strategy, set())
    if strategy == "culture" and any(t in strategy_tags for t in poi.tags):
        breakdown.append(ScoreComponent("文化策略", 55.0, "文化优先加权"))
    elif strategy == "culinary" and any(t in strategy_tags for t in poi.tags):
        breakdown.append(ScoreComponent("美食策略", 50.0, "美食优先加权"))
    elif strategy == "nature" and any(t in strategy_tags for t in poi.tags):
        breakdown.append(ScoreComponent("自然策略", 50.0, "自然优先加权"))

    # --- Tag richness bonus (new: rewards well-described POIs) ---
    richness = _tag_richness(poi.tags)
    if richness > 0:
        generic = {'城市游览', '景点', '室内', '户外', '休闲'}
        meaningful_count = len([t for t in poi.tags if t not in generic and len(t) >= 2])
        breakdown.append(ScoreComponent("\u4fe1\u606f\u4e30\u5bcc", richness, f"{meaningful_count}\u4e2a\u6709\u6548\u6807\u7b7e"))

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

    # --- Area diversity (increased weight) ---
    if visited_areas and poi.area and poi.area not in visited_areas:
        breakdown.append(ScoreComponent("区域多样", 15.0, "探索新区域"))

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


def _deduplicate_scenic_groups(scored: list[ScoredPoi], max_per_group: int = 2) -> list[ScoredPoi]:
    """Deduplicate sub-POIs from the same scenic area.
    
    Problem: 故宫博物院 has 43 sub-attractions (珍妃井, 太和门, 乾清宫...)
    that all score similarly and flood the top results.
    
    Solution: Group by parent scenic area name, keep only top N per group.
    """
    groups: dict[str, list[ScoredPoi]] = defaultdict(list)
    no_group: list[ScoredPoi] = []

    for sp in scored:
        if sp.total_score <= -100000:
            no_group.append(sp)  # Keep exclusions
            continue
        group_name = _extract_scenic_group(sp.poi.name)
        groups[group_name].append(sp)

    result: list[ScoredPoi] = []
    result.extend(no_group)

    for group_name, members in groups.items():
        # Keep top N from each group (by score)
        members.sort(key=lambda x: x.total_score, reverse=True)
        kept = members[:max_per_group]
        result.extend(kept)

    # Re-sort by score
    result.sort(key=lambda x: x.total_score, reverse=True)
    return result


def _diversify_by_area(scored: list[ScoredPoi], top_k: int) -> list[ScoredPoi]:
    """Select top_k POIs with area diversity.
    
    Instead of just taking the top K by score (which concentrates in one area),
    distribute selections across areas proportionally to their score weight.
    
    Algorithm:
    1. Group scored POIs by area
    2. Allocate slots to areas proportional to their best score
    3. Pick top N from each area
    """
    if top_k <= 0 or len(scored) <= top_k:
        return scored

    # Separate must-visit (always included) from others
    must_visit_items = [s for s in scored if s.total_score > 90000]
    regular_items = [s for s in scored if s.total_score <= 90000]

    remaining_k = top_k - len(must_visit_items)
    if remaining_k <= 0:
        # Must-visit items alone fill or exceed top_k; return them sorted by score
        must_visit_items.sort(key=lambda x: x.total_score, reverse=True)
        return must_visit_items[:top_k]

    # Group regular items by area
    area_groups: dict[str, list[ScoredPoi]] = defaultdict(list)
    for sp in regular_items:
        area = sp.poi.area or "其他"
        area_groups[area].append(sp)

    # Calculate area weights (best score per area)
    area_weights = {}
    for area, members in area_groups.items():
        members.sort(key=lambda x: x.total_score, reverse=True)
        area_weights[area] = members[0].total_score

    total_weight = sum(area_weights.values())
    if total_weight <= 0:
        return scored[:top_k]

    # Allocate slots proportionally, with minimum 1 per area if possible
    area_slots = {}
    for area, weight in area_weights.items():
        raw_slot = max(1, round(remaining_k * weight / total_weight))
        area_slots[area] = min(raw_slot, len(area_groups[area]))

    # Adjust if over/under allocated
    total_allocated = sum(area_slots.values())
    if total_allocated > remaining_k:
        # Remove from largest areas first
        sorted_areas = sorted(area_slots.keys(), key=lambda a: area_slots[a], reverse=True)
        for area in sorted_areas:
            if total_allocated <= remaining_k:
                break
            reduce = min(area_slots[area] - 1, total_allocated - remaining_k)
            area_slots[area] -= reduce
            total_allocated -= reduce
    elif total_allocated < remaining_k:
        # Add to areas with more POIs
        sorted_areas = sorted(area_slots.keys(), key=lambda a: area_weights[a], reverse=True)
        for area in sorted_areas:
            if total_allocated >= remaining_k:
                break
            can_add = min(len(area_groups[area]) - area_slots[area], remaining_k - total_allocated)
            area_slots[area] += can_add
            total_allocated += can_add

    # Pick top N from each area
    result = list(must_visit_items)
    for area, slots in area_slots.items():
        result.extend(area_groups[area][:slots])

    result.sort(key=lambda x: x.total_score, reverse=True)
    return result[:top_k]


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
    """Score and rank all POIs with diversity and deduplication.
    
    Pipeline:
    1. Score all POIs
    2. Deduplicate sub-POIs from same scenic area (max 2 per group)
    3. Apply area-diverse top_k selection
    4. Protect must-visit POIs from truncation
    """
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

    # Deduplicate sub-POIs from same scenic area
    scored = _deduplicate_scenic_groups(scored, max_per_group=2)

    # Apply area-diverse top_k selection
    if top_k > 0:
        scored = _diversify_by_area(scored, top_k)

    # Protect must-visit POIs from truncation
    if top_k > 0:
        must_in_result = {s.poi.id for s in scored}
        # Check if any must_visit POI was removed
        for poi in pois:
            if _is_must_visit(poi, intent.must_visit) and poi.id not in must_in_result:
                # Find its score (re-score if needed)
                s = score_poi(poi=poi, intent=intent, used_ids=used)
                if s.total_score > -100000:
                    scored.append(s)

    return scored
