"""Restaurant Agent - Recommend restaurants with interest-aware scoring.

Pure deterministic agent — no LLM required.
Returns a broader candidate pool; the clustering step handles per-day
assignment and cross-day deduplication.
"""

import logging
import re
from pathlib import Path

from agents.base import BaseAgent
from agents.constants import haversine_km, load_pois_by_type
from agents.state import TourState

logger = logging.getLogger(__name__)

# Cuisine keywords for interest matching
FOOD_KEYWORDS = {
    "美食", "小吃", "夜市", "火锅", "烧烤", "粤菜", "川菜", "湘菜",
    "日料", "西餐", "甜品", "茶饮", "早茶", "海鲜", "老字号",
}

CUISINE_INTEREST_MAP: dict[str, set[str]] = {
    "culinary": {"美食", "小吃", "夜市", "火锅", "烧烤", "老字号"},
    "food": {"美食", "小吃", "火锅", "粤菜", "川菜", "湘菜", "海鲜"},
    "nightlife": {"夜市", "酒吧", "烧烤"},
    "culture": {"老字号", "传统"},
}

# Budget → price_level range
BUDGET_PRICE_MAP = {
    "budget": (0, 1),
    "mid-range": (1, 3),
    "luxury": (3, 5),
}

# Extract cuisine type from tags or description
_CUISINE_PATTERNS = {
    "粤菜": re.compile(r"粤菜|广东菜|广府|早茶|点心|肠粉|烧鹅|虾饺"),
    "川菜": re.compile(r"川菜|火锅|串串|麻辣|重庆"),
    "湘菜": re.compile(r"湘菜|湖南菜|辣椒|剁椒"),
    "潮汕": re.compile(r"潮汕|潮州|牛肉|砂锅粥|卤水"),
    "日料": re.compile(r"日料|日本|寿司|刺身|拉面"),
    "西餐": re.compile(r"西餐|牛排|意面|披萨|法餐"),
    "东南亚": re.compile(r"东南亚|泰式|越南|冬阴功"),
    "海鲜": re.compile(r"海鲜|石斑|螃蟹|虾|生蚝"),
    "烧烤": re.compile(r"烧烤|烤肉|串串|撸串"),
    "甜品": re.compile(r"甜品|糖水|蛋糕|奶茶|咖啡"),
}


def _detect_cuisine(rest: dict) -> str:
    """Detect primary cuisine type from tags and description."""
    tags = " ".join(rest.get("tags", []))
    desc = rest.get("description", "") or ""
    text = tags + " " + desc

    for cuisine, pattern in _CUISINE_PATTERNS.items():
        if pattern.search(text):
            return cuisine
    return "综合"


def _detect_meal_period(rest: dict) -> str:
    """Detect suitable meal period from tags and description."""
    tags = " ".join(rest.get("tags", []))
    desc = rest.get("description", "") or ""
    text = tags + " " + desc

    if re.search(r"早茶|早点|早餐|brunch", text):
        return "breakfast"
    if re.search(r"夜市|宵夜|夜宵|酒吧|夜景|深夜|night", text, re.IGNORECASE):
        return "dinner"
    if re.search(r"下午茶|甜品|咖啡|tea", text, re.IGNORECASE):
        return "afternoon"
    return "any"


class RestaurantAgent(BaseAgent):
    """Recommend restaurants with interest-aware scoring.

    Returns enough candidates for the clustering step to assign
    per-day restaurants with cross-day deduplication.
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)

    @property
    def name(self) -> str:
        return "RestaurantAgent"

    @property
    def description(self) -> str:
        return "Search and recommend restaurants with interest awareness"

    def _score(self, rest: dict, interests: list[str], budget: str) -> float:
        score = 0.0

        # Rating (0-5 → 0-50)
        rating = rest.get("rating", 0) or rest.get("popularity", 0) or 0
        score += rating * 10

        # Interest match bonus
        tags = set(rest.get("tags", []))
        name = rest.get("name", "")
        for interest in interests:
            preferred = CUISINE_INTEREST_MAP.get(interest, set())
            if preferred & tags:
                score += 30
                break
            if interest in ("food", "culinary"):
                if tags & FOOD_KEYWORDS or any(kw in name for kw in FOOD_KEYWORDS):
                    score += 25
                    break

        # Popularity bonus
        pop = rest.get("popularity", 0)
        if pop and pop >= 4.5:
            score += 10

        # Budget match
        price_level = rest.get("price_level", 1)
        lo, hi = BUDGET_PRICE_MAP.get(budget, (0, 5))
        if lo <= price_level <= hi:
            score += 15
        elif price_level < lo:
            score += 5  # cheaper is OK
        else:
            score -= 10  # over budget

        # Description richness bonus (prefer POIs with useful descriptions)
        desc = rest.get("description", "") or ""
        if len(desc) > 50:
            score += 5

        return score

    async def execute(self, state: TourState) -> dict:
        intent = state.get("trip_intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)
        interests = intent.get("interests", [])
        budget = intent.get("budget", "mid-range") or "mid-range"

        if not city:
            return {"restaurants": [], "errors": ["RestaurantAgent: no city specified"]}

        restaurants = load_pois_by_type(self.data_dir, city, "restaurant")
        if not restaurants:
            return {"restaurants": [], "errors": [f"RestaurantAgent: no restaurant data for {city}"]}

        # Score all candidates
        scored = [
            (self._score(r, interests, budget), r)
            for r in restaurants
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        # Enrich with cuisine type and meal period metadata
        # Return enough candidates: days * 4 (clustering will select per-day)
        candidates = []
        seen_names = set()
        for score, r in scored:
            name = r.get("name", "")
            if name in seen_names:
                continue
            seen_names.add(name)

            r_copy = r.copy()
            r_copy["_score"] = score
            r_copy["_cuisine"] = _detect_cuisine(r)
            r_copy["_meal_period"] = _detect_meal_period(r)

            # Build reason
            reasons = []
            cuisine = r_copy["_cuisine"]
            if cuisine != "综合":
                reasons.append(cuisine)
            if interests and (set(r.get("tags", [])) & FOOD_KEYWORDS):
                reasons.append("符合美食偏好")
            if r.get("popularity", 0) and r["popularity"] >= 4.5:
                reasons.append(f"高评分{r['popularity']}")
            r_copy["recommend_reason"] = "；".join(reasons) if reasons else "推荐餐厅"

            candidates.append(r_copy)

        # Return top candidates plus one representative per area so clustering
        # can choose nearby meals for area-focused days.
        base_limit = max(days * 5, 5)
        result = []
        selected_ids: set[str] = set()

        def add_candidate(candidate: dict) -> None:
            candidate_id = candidate.get("id") or candidate.get("name", "")
            if candidate_id and candidate_id in selected_ids:
                return
            result.append(candidate)
            if candidate_id:
                selected_ids.add(candidate_id)

        for candidate in candidates[:base_limit]:
            add_candidate(candidate)

        represented_areas = {c.get("area", "") for c in result if c.get("area")}
        for candidate in candidates:
            area = candidate.get("area", "")
            if not area or area in represented_areas:
                continue
            add_candidate(candidate)
            represented_areas.add(area)

        logger.info("Selected %d restaurant candidates for %s (from %d total)",
                     len(result), city, len(restaurants))
        return {
            "restaurants": result,
            "sse_events": [{
                "type": "restaurants_found",
                "content": f"找到 {len(result)} 家餐厅",
            }],
        }
