"""Tour Pass Multi-Agent System - POI Scoring Tools.

Merged from:
- agent/scorer.py  — 10+ dimension scoring, hard exclusions, sub-POI dedup,
                       area diversity, type diversity, time fitness
- tools/scoring.py — image bonus, shopping penalty (kept)

All functions operate on plain dicts so they work with both the multi-agent
LangGraph pipeline and the legacy single-agent pipeline.
"""

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from tools.matching import is_must_visit_covered


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
    breakdown: list[ScoreComponent] = field(default_factory=list)
    reason: str = ""


# ── Strategy → tag mappings ────────────────────────────────────────────────────
_STRATEGY_TAGS = {
    "culture": {"历史文化", "博物馆", "古建筑", "书院", "寺庙", "世界遗产", "科教文化服务"},
    "culinary": {"美食", "小吃", "夜市", "茶饮", "街区", "餐饮"},
    "nature": {"自然", "公园", "山水", "户外", "湖泊", "森林", "海滩"},
    "balanced": set(),
}

_CLASSIC_HOTSPOT_TAGS = {
    "地标", "国家级景点", "风景名胜", "博物馆", "历史文化", "世界遗产",
    "古建筑", "纪念馆", "公园广场", "寺庙道观", "美术馆", "科技馆",
}

# ── 14-group expanded interest → tag mappings for fuzzy matching ───────────────
# Migrated from agent/scorer.py; provides 3-level scoring (35/25/15).
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


# ── Helper functions ────────────────────────────────────────────────────────────

def _is_must_visit(poi: dict, must_visit: list[str]) -> bool:
    """Check if a POI matches any must_visit keyword."""
    name = poi.get("name", "")
    pid = poi.get("id", "")
    for mv in must_visit:
        if is_must_visit_covered(mv, {name}, {pid} if pid else None):
            return True
    return False


def _extract_scenic_group(name: str) -> str:
    """Extract parent scenic area name from a sub-POI name.

    Examples:
        "故宫博物院-珍妃井" → "故宫博物院"
        "颐和园-苏州街"     → "颐和园"
        "天坛公园"          → "天坛公园"
    """
    if "-" in name:
        return name.split("-")[0]
    if "(" in name:
        return name.split("(")[0]
    return name


def _fuzzy_interest_match(interests: list[str], tags: list[str], name: str) -> float:
    """3-level fuzzy interest matching (35/25/15).

    Migrated from agent/scorer.py — replaces the old 15/12/10/8 version.
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

        # Name / description fuzzy match
        if any(kw in name for kw in expanded if len(kw) >= 2):
            total_bonus += 15.0

    return total_bonus


def _tag_richness(tags: list[str]) -> float:
    """Score based on tag richness — POIs with more descriptive tags score higher."""
    generic = {"城市游览", "景点", "室内", "户外", "休闲"}
    meaningful = [t for t in tags if t not in generic and len(t) >= 2]
    return min(len(meaningful), 5) * 2.0


def classify_poi_tier(poi: dict, intent: dict) -> str:
    """Classify whether a POI is eligible for the main itinerary.

    This is an admission gate, separate from ranking score:
    - core_hotspot: classic/high-popularity POI
    - route_supported: lower-popularity POI backed by real route evidence
    - fallback_only: replacement/backup only
    """
    must_visit = intent.get("must_visit", [])
    if _is_must_visit(poi, must_visit):
        return "core_hotspot"

    if poi.get("type", "attraction") != "attraction":
        return "fallback_only"
    if not poi.get("lat") or not poi.get("lng") or not poi.get("area"):
        return "fallback_only"

    tags = set(poi.get("tags", []))
    popularity = float(poi.get("popularity", 0) or 0)
    xhs_freq = int(poi.get("xhs_frequency", 0) or 0)

    if popularity >= 4.7 or tags & _CLASSIC_HOTSPOT_TAGS or xhs_freq >= 3:
        return "core_hotspot"
    if xhs_freq >= 1:
        return "route_supported"
    return "fallback_only"


def build_poi_evidence_sources(poi: dict) -> list[str]:
    """Return compact evidence source labels for frontend/reviewer use."""
    sources: list[str] = []
    popularity = float(poi.get("popularity", 0) or 0)
    tags = set(poi.get("tags", []))
    if popularity >= 4.7:
        sources.append("amap_popularity")
    if tags & _CLASSIC_HOTSPOT_TAGS:
        sources.append("classic_tag")
    if int(poi.get("xhs_frequency", 0) or 0) > 0:
        sources.append("xhs_route")
    if poi.get("image_url") or poi.get("images"):
        sources.append("image")
    return sources


# ── Main scoring function ────────────────────────────────────────────────────────

def score_poi(
    poi: dict,
    intent: dict,
    used_ids: Optional[set[str]] = None,
    current_area: str = "",
    current_time: int = 540,
    day_attraction_count: int = 0,
    day_restaurant_count: int = 0,
    visited_areas: Optional[set[str]] = None,
) -> ScoredPoi:
    """Score a single POI against the user's intent and current context.

    Migrated dimensions from agent/scorer.py:
    - Hard exclusions (repeat/hotel/avoid)
    - Popularity (non-linear)
    - Interest match (3-level fuzzy)
    - Strategy weighting
    - Tag richness
    - Must-visit bonus (+120)
    - Avoid penalty (soft -40)
    - Price penalty
    - Type diversity (attraction vs restaurant ratio)
    - Time fitness (restaurant meal windows, nightlife)
    - Area diversity (+15)
    - Travel time penalty (-36)
    - Special requests match (+25)

    Retained from System B:
    - Image availability bonus (+8)
    - Shopping penalty (-35)
    """
    breakdown: list[ScoreComponent] = []
    used = used_ids or set()
    areas = visited_areas or set()
    name = poi.get("name", "")
    tags = poi.get("tags", [])
    poi_type = poi.get("type", "attraction")
    pid = poi.get("id", "")

    # ── Hard exclusions ─────────────────────────────────────────────────────
    if pid in used:
        return ScoredPoi(poi=poi, total_score=-100000, breakdown=[
            ScoreComponent("重复排除", -100000, "该POI已在行程中"),
        ])

    if poi_type in ("hotel", "transit"):
        return ScoredPoi(poi=poi, total_score=-100000, breakdown=[
            ScoreComponent("类型排除", -100000, "酒店/交通站点不参与评分"),
        ])

    avoid = intent.get("avoid", [])
    if name in avoid or pid in avoid:
        return ScoredPoi(poi=poi, total_score=-100000, breakdown=[
            ScoreComponent("避免项", -100000, "用户明确避开"),
        ])

    # ── Popularity base (non-linear scaling) ─────────────────────────────────
    pop = poi.get("popularity", 0) or 0
    pop_base = pop * 8.0
    if pop >= 4.7:
        pop_base += 8.0
    elif pop >= 4.5:
        pop_base += 4.0
    breakdown.append(ScoreComponent("热度", pop_base, f"热度{pop}"))

    # ── Interest match (3-level fuzzy) ───────────────────────────────────────
    interests = intent.get("interests", [])
    interest_score = _fuzzy_interest_match(interests, tags, name)
    if interest_score > 0:
        breakdown.append(ScoreComponent("兴趣匹配", interest_score, "兴趣标签匹配"))

    # ── Strategy weighting ───────────────────────────────────────────────────
    strategy = intent.get("strategy", "balanced")
    strategy_tags = _STRATEGY_TAGS.get(strategy, set())
    if strategy == "culture" and any(t in strategy_tags for t in tags):
        breakdown.append(ScoreComponent("文化策略", 55.0, "文化优先加权"))
    elif strategy == "culinary" and any(t in strategy_tags for t in tags):
        breakdown.append(ScoreComponent("美食策略", 50.0, "美食优先加权"))
    elif strategy == "nature" and any(t in strategy_tags for t in tags):
        breakdown.append(ScoreComponent("自然策略", 50.0, "自然优先加权"))

    # ── Tag richness bonus ───────────────────────────────────────────────────
    richness = _tag_richness(tags)
    if richness > 0:
        meaningful_count = len([
            t for t in tags
            if t not in {"城市游览", "景点", "室内", "户外", "休闲"} and len(t) >= 2
        ])
        breakdown.append(ScoreComponent("信息丰富", richness, f"{meaningful_count}个有效标签"))

    # ── Must-visit bonus ─────────────────────────────────────────────────────
    must_visit = intent.get("must_visit", [])
    for mv in must_visit:
        if is_must_visit_covered(mv, {name}, {pid} if pid else None):
            breakdown.append(ScoreComponent("必去加权", 120.0, f"命中必去「{mv}」"))
            break

    # ── Avoid penalty (soft) ─────────────────────────────────────────────────
    for avoid_term in avoid:
        if avoid_term and (avoid_term in (poi.get("description", "") or "") or
                           any(avoid_term in tag for tag in tags)):
            breakdown.append(ScoreComponent("避免项", -40.0, f"命中避免「{avoid_term}」"))

    # ── Price penalty ────────────────────────────────────────────────────────
    price_level = poi.get("price_level", 1) or 1
    price_penalty = -price_level * 3.0
    breakdown.append(ScoreComponent("价格惩罚", price_penalty, f"价格等级{price_level}"))

    # ── Type diversity ───────────────────────────────────────────────────────
    if poi_type == "attraction" and day_attraction_count > day_restaurant_count + 1:
        breakdown.append(ScoreComponent("类型多样", -15.0, "景点过多，偏好多样"))
    if poi_type == "restaurant" and day_restaurant_count < day_attraction_count:
        breakdown.append(ScoreComponent("类型多样", 12.0, "用餐时段加分"))

    # ── Time fitness for restaurants ─────────────────────────────────────────
    if poi_type == "restaurant":
        is_lunch = 660 <= current_time <= 780
        is_dinner = 1020 <= current_time <= 1200
        if is_lunch or is_dinner:
            breakdown.append(ScoreComponent("时间适配", 18.0, "用餐时段"))
        else:
            breakdown.append(ScoreComponent("时间适配", -10.0, "非用餐时段"))

    # ── Nightlife time fitness ───────────────────────────────────────────────
    if poi_type == "nightlife" and current_time >= 1080:
        breakdown.append(ScoreComponent("时间适配", 15.0, "夜间场景"))

    # ── Area diversity ───────────────────────────────────────────────────────
    poi_area = poi.get("area", "")
    if areas and poi_area and poi_area not in areas:
        breakdown.append(ScoreComponent("区域多样", 15.0, "探索新区域"))

    # ── Travel time penalty ──────────────────────────────────────────────────
    if current_area and poi_area and poi_area != current_area:
        travel_penalty = -30 * 1.2
        breakdown.append(ScoreComponent("通勤惩罚", travel_penalty, "跨区通勤"))
    elif current_area:
        breakdown.append(ScoreComponent("通勤惩罚", 0, "同区域"))

    # ── Special requests match ───────────────────────────────────────────────
    special_requests = intent.get("special_requests", "") or ""
    if special_requests:
        sr = special_requests.lower()
        if sr in (poi.get("description", "") or "").lower() or any(sr in t for t in tags):
            breakdown.append(ScoreComponent("特殊需求", 25.0, "匹配特殊要求"))

    # ── Image availability bonus (System B unique) ───────────────────────────
    if poi.get("image_url"):
        breakdown.append(ScoreComponent("图片加分", 8.0, "有实景图片"))

    # ── XHS (小红书) real-traveler frequency boost ───────────────────────────
    xhs_freq = poi.get("xhs_frequency", 0)
    if xhs_freq >= 5:
        breakdown.append(ScoreComponent("小红书热门", 25.0, f"出现{xhs_freq}次"))
    elif xhs_freq >= 3:
        breakdown.append(ScoreComponent("小红书推荐", 15.0, f"出现{xhs_freq}次"))
    elif xhs_freq >= 1:
        breakdown.append(ScoreComponent("小红书提及", 5.0, f"出现{xhs_freq}次"))

    # ── Shopping / commercial penalty (System B unique) ──────────────────────
    shopping_tags = {"购物", "商圈", "商场", "购物中心", "免税"}
    has_shopping_interest = any(i in ("shopping", "购物") for i in interests)
    if not has_shopping_interest and any(t in shopping_tags for t in tags):
        breakdown.append(ScoreComponent("购物降权", -35.0, "非购物行程，降低商场权重"))

    # ── Total ────────────────────────────────────────────────────────────────
    total = sum(c.score for c in breakdown)

    top_reasons = sorted(breakdown, key=lambda c: abs(c.score), reverse=True)[:3]
    reason = "；".join(f"{r.label}({r.score:+.0f})" for r in top_reasons if r.score != 0)

    return ScoredPoi(poi=poi, total_score=total, breakdown=breakdown, reason=reason)


# ── Sub-POI deduplication ───────────────────────────────────────────────────────

def _deduplicate_scenic_groups(scored: list[ScoredPoi], max_per_group: int = 2) -> list[ScoredPoi]:
    """Deduplicate sub-POIs from the same scenic area.

    Problem: 故宫博物院 has 43 sub-attractions (珍妃井, 太和门...) that flood
    top results.  Solution: keep at most *max_per_group* per parent scenic area.

    Migrated from agent/scorer.py.
    """
    groups: dict[str, list[ScoredPoi]] = defaultdict(list)
    no_group: list[ScoredPoi] = []

    for sp in scored:
        if sp.total_score <= -100000:
            no_group.append(sp)
            continue
        group_name = _extract_scenic_group(sp.poi.get("name", ""))
        groups[group_name].append(sp)

    result: list[ScoredPoi] = list(no_group)
    for group_name, members in groups.items():
        members.sort(key=lambda x: x.total_score, reverse=True)
        result.extend(members[:max_per_group])

    result.sort(key=lambda x: x.total_score, reverse=True)
    return result


# ── Area diversity enforcement ───────────────────────────────────────────────────

def _diversify_by_area(scored: list[ScoredPoi], top_k: int) -> list[ScoredPoi]:
    """Select top_k POIs with area diversity (migrated from agent/scorer.py).

    Instead of taking the top K by score (which concentrates in one area),
    distribute selections across areas proportionally.
    """
    if top_k <= 0 or len(scored) <= top_k:
        return scored

    must_visit_items = [s for s in scored if s.total_score > 90000]
    regular_items = [s for s in scored if s.total_score <= 90000]

    remaining_k = top_k - len(must_visit_items)
    if remaining_k <= 0:
        must_visit_items.sort(key=lambda x: x.total_score, reverse=True)
        return must_visit_items[:top_k]

    area_groups: dict[str, list[ScoredPoi]] = defaultdict(list)
    for sp in regular_items:
        area = sp.poi.get("area") or "其他"
        area_groups[area].append(sp)

    area_weights = {}
    for area, members in area_groups.items():
        members.sort(key=lambda x: x.total_score, reverse=True)
        area_weights[area] = members[0].total_score

    total_weight = sum(area_weights.values())
    if total_weight <= 0:
        return scored[:top_k]

    area_slots = {}
    for area, weight in area_weights.items():
        raw_slot = max(1, round(remaining_k * weight / total_weight))
        area_slots[area] = min(raw_slot, len(area_groups[area]))

    total_allocated = sum(area_slots.values())
    if total_allocated > remaining_k:
        sorted_areas = sorted(area_slots.keys(), key=lambda a: area_slots[a], reverse=True)
        for area in sorted_areas:
            if total_allocated <= remaining_k:
                break
            reduce = min(area_slots[area] - 1, total_allocated - remaining_k)
            area_slots[area] -= reduce
            total_allocated -= reduce
    elif total_allocated < remaining_k:
        sorted_areas = sorted(area_slots.keys(), key=lambda a: area_weights[a], reverse=True)
        for area in sorted_areas:
            if total_allocated >= remaining_k:
                break
            can_add = min(len(area_groups[area]) - area_slots[area], remaining_k - total_allocated)
            area_slots[area] += can_add
            total_allocated += can_add

    result = list(must_visit_items)
    for area, slots in area_slots.items():
        result.extend(area_groups[area][:slots])

    result.sort(key=lambda x: x.total_score, reverse=True)
    return result[:top_k]


# ── Public ranking API ───────────────────────────────────────────────────────────

def rank_pois(
    pois: list[dict],
    intent: dict,
    top_k: int = 20,
    current_area: str = "",
    visited_areas: Optional[set] = None,
    used_ids: Optional[set[str]] = None,
    current_time: int = 540,
    day_attraction_count: int = 0,
    day_restaurant_count: int = 0,
) -> list[dict]:
    """Score and rank all POIs with diversity and deduplication.

    Pipeline:
    1. Score all POIs (15+ dimensions)
    2. Deduplicate sub-POIs from same scenic area (max 2 per group)
    3. Apply area-diverse top_k selection
    4. Protect must_visit POIs from truncation

    Returns a list of enriched POI dicts with _score and _score_reason keys.
    """
    must_visit_list = intent.get("must_visit", [])
    used = used_ids or set()
    areas = visited_areas or set()

    scored: list[ScoredPoi] = []
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

    # Sub-POI deduplication (e.g. 故宫博物院-珍妃井 → keep max 2 per group)
    scored = _deduplicate_scenic_groups(scored, max_per_group=2)

    # Area-diverse top_k selection
    if top_k > 0:
        scored = _diversify_by_area(scored, top_k)

    # Protect must_visit POIs from truncation
    if top_k > 0:
        must_in_result = {s.poi.get("id") for s in scored}
        for poi in pois:
            if _is_must_visit(poi, must_visit_list) and poi.get("id") not in must_in_result:
                s = score_poi(poi=poi, intent=intent, used_ids=used)
                if s.total_score > -100000:
                    scored.append(s)

    # Convert to enriched dicts
    enriched = []
    for sp in scored:
        poi = sp.poi.copy()
        poi["_score"] = sp.total_score
        poi["_score_reason"] = sp.reason
        if _is_must_visit(poi, must_visit_list):
            poi["is_must_visit"] = True
        enriched.append(poi)

    return enriched
