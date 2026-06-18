"""POI Agent - Search and recommend Points of Interest with scoring.

Pure deterministic agent — no LLM required.
Uses algorithmic scoring from ``tools.scoring`` and local JSON data.
"""

import json
import logging
from pathlib import Path

from agents.base import BaseAgent
from agents.constants import resolve_city_dir, CITY_DIR_MAP
from agents.state import TourState
from tools.scoring import rank_pois

logger = logging.getLogger(__name__)


class PoiAgent(BaseAgent):
    """Search and recommend POIs using hybrid scoring."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)

    @property
    def name(self) -> str:
        return "PoiAgent"

    @property
    def description(self) -> str:
        return "Search and recommend Points of Interest with intelligent scoring"

    @staticmethod
    def _is_low_value_business_venue(poi: dict, must_visit: list[str]) -> bool:
        name = poi.get("name", "")
        if any(mv and (mv in name or mv == poi.get("id", "")) for mv in must_visit):
            return False
        return any(term in name for term in ("会议中心", "会展中心"))

    def _load_pois(self, city: str) -> list[dict]:
        """Load attraction-type POIs from local JSON."""
        city_dir = resolve_city_dir(self.data_dir, city)
        poi_file = city_dir / "pois.json"
        if not poi_file.exists():
            logger.warning("POI file not found: %s", poi_file)
            return []
        try:
            with open(poi_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            attractions = [p for p in data if p.get("type") in ("attraction", "nightlife")]

            # De-duplicate sub-POIs (e.g. "广州塔-东广场" when "广州塔" exists)
            attractions.sort(key=lambda p: len(p["name"]))
            seen_bases: set[str] = set()
            deduped: list[dict] = []
            for p in attractions:
                name = p["name"]
                if any(name.startswith(b) and len(name) > len(b) for b in seen_bases):
                    continue
                deduped.append(p)
                if len(name) <= 6:
                    seen_bases.add(name)

            logger.info("Loaded %d attractions for %s (deduped from %d)", len(deduped), city, len(attractions))
            return deduped
        except Exception as e:
            logger.error("Failed to load POIs: %s", e)
            return []

    async def execute(self, state: TourState) -> dict:
        intent = state.get("trip_intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)
        must_visit = intent.get("must_visit", [])

        if not city:
            return {"pois": [], "errors": ["PoiAgent: no city specified"]}

        all_pois = self._load_pois(city)
        if not all_pois:
            return {"pois": [], "errors": [f"PoiAgent: no POI data found for {city}"]}
        all_pois = [
            poi for poi in all_pois
            if not self._is_low_value_business_venue(poi, must_visit)
        ]

        # ── Inject XHS frequency into each POI for scoring boost ────────────
        xhs_popular_pois = state.get("xhs_popular_pois") or {}
        if xhs_popular_pois:
            from tools.xhs_loader import match_poi_name
            for poi in all_pois:
                freq = match_poi_name(poi.get("name", ""), xhs_popular_pois)
                if freq > 0:
                    poi["xhs_frequency"] = freq
            logger.info(
                "PoiAgent: injected XHS frequency for %d/%d POIs",
                sum(1 for p in all_pois if p.get("xhs_frequency")),
                len(all_pois),
            )

        # Algorithmic scoring + ranking
        top_k = days * 5
        scored_pois = rank_pois(pois=all_pois, intent=intent, top_k=top_k)

        # Ensure must_visit POIs are included
        enriched: list[dict] = []
        enriched_keys: set[str] = set()
        for mv in must_visit:
            candidates = [p for p in scored_pois if mv in p.get("name", "")]
            if candidates:
                best = min(candidates, key=lambda p: (p.get("name", "") != mv, len(p.get("name", ""))))
                best = best.copy()
                best["is_must_visit"] = True
                best["recommend_reason"] = f"Must visit: {mv}"
                enriched.append(best)
                enriched_keys.add(best.get("id") or best.get("name", ""))

        for poi in scored_pois:
            key = poi.get("id") or poi.get("name", "")
            if key not in enriched_keys:
                enriched.append(poi)
                enriched_keys.add(key)

        enriched = enriched[: days * 3]
        logger.info("Selected %d POIs for %s", len(enriched), city)
        return {
            "pois": enriched,
            "available_pois": all_pois,  # Store full list for must_visit rescue
            "sse_events": [{
                "type": "data_loaded",
                "content": f"找到 {len(enriched)} 个景点",
            }],
        }
