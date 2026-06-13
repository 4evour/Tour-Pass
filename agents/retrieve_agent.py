"""Retrieve Agent - RAG-based city guide retrieval.

Pure deterministic agent — uses BM25 RAG, no LLM required.
Now prioritizes poi_knowledge.json for real traveler tips.
"""

import logging

from agents.base import BaseAgent
from agents.state import TourState
from tools import rag

logger = logging.getLogger(__name__)


class RetrieveAgent(BaseAgent):
    """Retrieve relevant city guides and tips via BM25 RAG."""

    @property
    def name(self) -> str:
        return "RetrieveAgent"

    @property
    def description(self) -> str:
        return "Retrieve city guides and travel tips via BM25 RAG"

    async def execute(self, state: TourState) -> dict:
        intent = state.get("trip_intent") or {}
        city = intent.get("city", state.get("city", ""))
        interests = intent.get("interests", [])
        must_visit = intent.get("must_visit", [])

        if not city:
            return {"city_guides": []}

        # Ensure RAG is initialised
        if not rag.is_rag_ready():
            try:
                rag.init_rag("data")
            except Exception as e:
                logger.warning("RAG init failed: %s", e)
                return {"city_guides": []}

        all_guides: list[str] = []

        # 1. Must-visit POI tips from poi_knowledge (highest priority)
        for mv in must_visit[:5]:
            tips = rag.get_poi_tips(city, mv)
            if tips:
                tip_texts = [f"[{mv}·{t['category']}] {t['text']}" for t in tips]
                all_guides.extend(tip_texts)
                logger.info("RetrieveAgent: %d poi_knowledge tips for '%s'", len(tips), mv)

        # 2. POI knowledge search by interest
        for interest in interests[:3]:
            q = f"{city}{interest}"
            results = rag.search_poi_tips(city, q, top_k=3)
            all_guides.extend(results)

        # 3. General travel tips (city_guide + guidebook via BM25)
        results = rag.search_guides(city, f"{city}旅行攻略", top_k=3)
        all_guides.extend(results)

        # 4. Interest-specific queries
        interest_queries = {
            "food": f"{city}美食推荐",
            "culinary": f"{city}美食小吃",
            "culture": f"{city}历史文化景点",
            "nature": f"{city}自然风光户外",
            "shopping": f"{city}购物商圈",
            "nightlife": f"{city}夜生活酒吧",
            "photography": f"{city}拍照打卡",
            "family": f"{city}亲子游",
        }
        for interest in interests[:3]:
            q = interest_queries.get(interest, f"{city}{interest}")
            all_guides.extend(rag.search_guides(city, q, top_k=2))

        # 5. Transport & timing from city_guide
        for category in ("transport_tips", "timing_tips", "crowd_tips"):
            all_guides.extend(rag.search_guides_broad(city, categories=[category], top_k=2))

        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for g in all_guides:
            if g not in seen:
                seen.add(g)
                unique.append(g)

        logger.info("RetrieveAgent: retrieved %d guide snippets for %s", len(unique), city)
        return {"city_guides": unique}
