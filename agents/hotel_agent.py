"""Hotel Agent - 4-layer filtering + LLM final selection.

Migrated from agent/graph.py select_hotel (4-layer: area → budget → brand → LLM)
while retaining the location-aware scoring from the original HotelAgent.
"""

import json
import logging
import re
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from agents.base import LLMAgent
from agents.constants import resolve_city_dir, haversine_km, compute_center, load_pois_by_type
from agents.state import TourState
from tools import hotel_price_api
from tools.matching import match_must_visit

logger = logging.getLogger(__name__)

# ── LLM Prompt ─────────────────────────────────────────────────────────────────

HOTEL_SELECTION_SYSTEM = """你是一个酒店推荐专家。根据用户的旅行需求和可用酒店列表，选出最合适的酒店。

选择标准（按优先级）：
1. 预算匹配：酒店价格区间必须在用户预算范围内（如果用户指定了预算）
2. 位置：酒店应在核心景点附近，减少每日通勤时间
3. 品牌档次：与用户预算档次匹配（经济型/中端/高端/豪华）
4. 人群匹配：带老人要选有电梯、安静的；亲子要选有家庭房的；情侣要选有特色的
5. 区域偏好：如果用户指定了区域，优先选该区域

输出要求：
- 从候选列表中选择1家酒店
- 给出选择理由（一句话，包含价格/档次/位置等关键信息）
- 输出严格 JSON: {{"hotel_id": "xxx", "reason": "xxx"}}
"""


# ── Budget helpers (migrated from agent/graph.py) ──────────────────────────────

def _matches_budget(hotel: dict, budget_min: int, budget_max: int) -> bool:
    """Check if a hotel's price range overlaps with the user's budget."""
    if budget_min <= 0 and budget_max <= 0:
        return True

    pr = hotel.get("price_range", "")
    if not pr:
        # Estimate from price_level
        level = hotel.get("price_level", 1)
        level_ranges = {
            1: (100, 300), 2: (200, 400), 3: (300, 600),
            4: (500, 1000), 5: (800, 2000),
        }
        lo, hi = level_ranges.get(level, (100, 300))
    else:
        nums = re.findall(r"\d+", pr)
        if len(nums) >= 2:
            lo, hi = int(nums[0]), int(nums[1])
        elif len(nums) == 1:
            lo = hi = int(nums[0])
        else:
            return True  # Can't parse, don't filter out

    if budget_max > 0 and lo > budget_max:
        return False
    if budget_min > 0 and hi < budget_min:
        return False
    return True


def _hotel_category_for_budget(budget: str | None) -> list[str]:
    """Map user budget string to preferred brand categories."""
    if budget == "budget":
        return ["经济型"]
    elif budget == "luxury":
        return ["高端", "豪华"]
    return ["中端"]


def _hotel_matches_area(hotel: dict, hotel_area: str) -> bool:
    """Return whether a hotel matches an administrative area or business district."""
    if not hotel_area:
        return True
    tags = hotel.get("tags") or []
    text = " ".join([
        str(hotel.get("area", "")),
        str(hotel.get("name", "")),
        str(hotel.get("address", "")),
        str(hotel.get("description", "")),
        str(hotel.get("recommendation", "")),
        " ".join(str(t) for t in tags),
    ])
    return hotel_area in text


# ── Location scoring (retained from original HotelAgent) ───────────────────────

def score_hotel_location(hotel: dict, poi_center: tuple[float, float], budget: str | None) -> float:
    """Score a hotel based on location, rating, and budget fit."""
    score = 0.0
    rating = hotel.get("popularity", 0) or hotel.get("rating", 0) or 0
    score += rating * 10

    hotel_lat = hotel.get("lat", 0)
    hotel_lng = hotel.get("lng", 0)
    center_lat, center_lng = poi_center

    if hotel_lat and hotel_lng and center_lat and center_lng:
        dist = haversine_km(hotel_lat, hotel_lng, center_lat, center_lng)
        score += max(0, 30 - dist * 3)

    price = hotel.get("price_per_night", 0) or 0
    budget_ranges = {
        "budget": (0, 200),
        "mid-range": (200, 500),
        "luxury": (500, 10000),
    }
    low, high = budget_ranges.get(budget or "mid-range", (0, 10000))
    if low <= price <= high:
        score += 20
    elif price < low:
        score += 15
    else:
        score += 5

    return score


def _hotel_text(hotel: dict) -> str:
    tags = hotel.get("tags") or []
    return " ".join([
        str(hotel.get("area", "")),
        str(hotel.get("name", "")),
        str(hotel.get("address", "")),
        str(hotel.get("description", "")),
        str(hotel.get("recommendation", "")),
        " ".join(str(t) for t in tags),
    ])


def _reference_pois_for_hotel_center(
    intent: dict,
    candidate_pois: list[dict],
    all_city_pois: list[dict],
) -> list[dict]:
    references: list[dict] = []
    seen: set[str] = set()

    for mv in intent.get("must_visit", []):
        for poi in match_must_visit(mv, all_city_pois):
            if poi.get("type") in ("hotel", "transit"):
                continue
            key = poi.get("id") or poi.get("name", "")
            if key and key not in seen:
                references.append(poi)
                seen.add(key)
                break

    for poi in candidate_pois:
        if poi.get("type") not in ("attraction", "nightlife"):
            continue
        key = poi.get("id") or poi.get("name", "")
        if key and key not in seen:
            references.append(poi)
            seen.add(key)

    return references


# ── Main agent ─────────────────────────────────────────────────────────────────

class HotelAgent(LLMAgent):
    """Search and recommend hotels with 4-layer filtering + LLM final selection.

    Pipeline:
    1. Area filter (if user specified hotel_area)
    2. Budget filter (if user specified hotel_budget_min/max)
    3. Brand category filter (based on user's budget level)
    4. LLM final selection from filtered candidates
    """

    def __init__(self, llm: BaseChatModel, data_dir: str = "data"):
        super().__init__(llm)
        self.data_dir = Path(data_dir)

    @property
    def name(self) -> str:
        return "HotelAgent"

    @property
    def description(self) -> str:
        return "Search and recommend hotels with 4-layer filtering + LLM selection"

    def build_prompt(self):
        from langchain_core.prompts import ChatPromptTemplate
        return ChatPromptTemplate.from_messages([
            ("system", HOTEL_SELECTION_SYSTEM),
            ("human", "{context}"),
        ])

    async def execute(self, state: TourState) -> dict:
        intent = state.get("trip_intent", {})
        city = intent.get("city", state.get("city", ""))
        budget = intent.get("budget", "mid-range")
        pois = state.get("pois", [])
        sse_events: list[dict] = []

        if not city:
            return {"selected_hotel": None, "errors": ["HotelAgent: no city specified"]}

        hotels = load_pois_by_type(self.data_dir, city, "hotel")
        if not hotels:
            return {"selected_hotel": None, "errors": [f"HotelAgent: no hotel data for {city}"]}

        city_pois = load_pois_by_type(self.data_dir, city, "attraction")
        reference_pois = _reference_pois_for_hotel_center(intent, pois, city_pois)

        price_result = await hotel_price_api.fetch_hotel_prices(city, hotels[:30])
        if price_result.get("prices"):
            hotels = hotel_price_api.merge_price_quotes(hotels, price_result["prices"])
            sse_events.append({
                "type": "hotel_prices_loaded",
                "content": f"已加载{price_result.get('provider', 'external')}酒店价格",
            })

        # Pre-sort by location score (for candidate selection before LLM)
        poi_center = compute_center(reference_pois or pois)
        hotels.sort(
            key=lambda h: score_hotel_location(h, poi_center, budget),
            reverse=True,
        )

        candidates = list(hotels)

        must_visit_terms = [mv for mv in intent.get("must_visit", []) if mv]
        if must_visit_terms:
            matched_hotels = [
                h for h in candidates
                if any(mv in _hotel_text(h) for mv in must_visit_terms)
            ]
            if matched_hotels:
                candidates = matched_hotels + [
                    h for h in candidates
                    if h.get("id") not in {mh.get("id") for mh in matched_hotels}
                ]

        # ── Layer 1: Area filter ──────────────────────────────────────────────
        hotel_area = intent.get("hotel_area", "")
        if hotel_area:
            area_hotels = [h for h in candidates if _hotel_matches_area(h, hotel_area)]
            if area_hotels:
                candidates = area_hotels
                logger.info("Area filter: %d hotels in '%s'", len(candidates), hotel_area)

        # ── Layer 2: Budget filter ────────────────────────────────────────────
        budget_min = int(intent.get("hotel_budget_min", 0) or 0)
        budget_max = int(intent.get("hotel_budget_max", 0) or 0)
        if budget_max > 0 or budget_min > 0:
            budget_hotels = [
                h for h in candidates if _matches_budget(h, budget_min, budget_max)
            ]
            if budget_hotels:
                candidates = budget_hotels
                logger.info(
                    "Budget filter: %d hotels match %d-%d元",
                    len(candidates), budget_min, budget_max,
                )

        # ── Layer 3: Brand category filter ────────────────────────────────────
        preferred_cats = _hotel_category_for_budget(budget)
        if preferred_cats:
            cat_hotels = [
                h for h in candidates
                if h.get("brand_category", "") in preferred_cats
            ]
            if cat_hotels:
                candidates = cat_hotels
                logger.info(
                    "Category filter: %d hotels in %s", len(candidates), preferred_cats,
                )

        # ── Layer 4: LLM final selection ──────────────────────────────────────
        # Build hotel list for LLM (top 15 candidates with enriched info)
        hotel_list = "\n".join([
            f"- {h.get('name', '')} (ID:{h.get('id', '')}, "
            f"区域:{h.get('area', '')}, 评分:{h.get('popularity', 0)}, "
            f"档次:{h.get('brand_category', '未知')}, "
            f"价格:{h.get('price_range', '未知')}, "
            f"描述:{(h.get('description', '') or '无')[:60]})"
            for h in candidates[:15]
        ])

        must_visit_str = ", ".join(intent.get("must_visit", [])) or "无特殊要求"
        user_context = (
            f"城市: {city}\n"
            f"出行人群: {intent.get('travelers', '普通')}\n"
            f"预算: {budget}"
        )
        if budget_min > 0 or budget_max > 0:
            user_context += f"（每晚{budget_min}-{budget_max}元）"
        user_context += (
            f"\n必去景点: {must_visit_str}\n"
            f"酒店偏好: {intent.get('hotel_preference', '') or '无特殊要求'}\n"
            f"希望区域: {hotel_area or '不限'}\n\n"
            f"候选酒店:\n{hotel_list}"
        )

        try:
            content = await self.invoke_llm({"context": user_context}, state=state)
            # Strip markdown fences
            if "```json" in content:
                content = content.split("```json", 1)[1].rsplit("```", 1)[0]
            elif "```" in content:
                content = content.split("```", 1)[1].rsplit("```", 1)[0]
            data = json.loads(content.strip())
            hotel_id = data.get("hotel_id", "")
            reason = data.get("reason", "")

            # Find the selected hotel
            for h in candidates:
                if h.get("id") == hotel_id:
                    logger.info("LLM selected hotel: %s (%s)", h.get("name"), reason)
                    sse_events.append({
                        "type": "hotel_selected",
                        "content": f"已选酒店: {h.get('name', '')}",
                    })
                    return {
                        "selected_hotel": h,
                        "sse_events": sse_events,
                    }

            # Fallback: pick first candidate if LLM selected unknown ID
            if candidates:
                best = candidates[0]
                logger.info("LLM hotel_id not found, using top candidate: %s", best.get("name"))
                sse_events.append({
                    "type": "hotel_selected",
                    "content": f"已选酒店: {best.get('name', '')}",
                })
                return {"selected_hotel": best, "sse_events": sse_events}

        except Exception as e:
            logger.warning("LLM hotel selection failed: %s; using top candidate", e)

        # Final fallback: first candidate (deterministic top-scored hotel)
        if candidates:
            best = candidates[0]
            sse_events.append({
                "type": "hotel_selected",
                "content": f"已选酒店: {best.get('name', '')}",
            })
            return {"selected_hotel": best, "sse_events": sse_events}

        return {"selected_hotel": None, "sse_events": sse_events}
