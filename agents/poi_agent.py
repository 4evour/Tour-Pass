"""POI Agent - Search and recommend Points of Interest with scoring.

This agent uses a hybrid approach:
1. Score-based pre-filtering (from legacy scorer.py)
2. LLM-based selection and explanation
"""

import json
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState
from tools.scoring import rank_pois

logger = logging.getLogger(__name__)

POI_SYSTEM = """You are a POI (Point of Interest) recommendation expert.

You receive a pre-scored list of candidate POIs. Your job is to:
1. Select the best {top_k} POIs for the trip
2. Ensure ALL must_visit places (marked with 【必去】) are included
3. Provide a brief reason for each selection
4. Balance variety (different types of attractions)

Output format (JSON array):
[
  {
    "id": "poi_id",
    "name": "景点名称",
    "reason": "推荐理由",
    "priority": 1
  }
]

RULES:
- MUST include all 【必去】 POIs (priority 1)
- Select diverse attractions (not all temples or all parks)
- Consider geographic distribution
- Return exactly {top_k} POIs"""


class PoiAgent(BaseTourAgent):
    """Agent that searches and recommends POIs using hybrid scoring + LLM."""
    
    def __init__(self, llm: BaseChatModel, data_dir: str = "data"):
        super().__init__(llm)
        self.data_dir = Path(data_dir)
    
    @property
    def name(self) -> str:
        return "PoiAgent"
    
    @property
    def description(self) -> str:
        return "Search and recommend Points of Interest with intelligent scoring"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", POI_SYSTEM),
            ("human", "{context}"),
        ])
    
    def _load_pois(self, city: str) -> list[dict]:
        """Load POIs from local JSON file."""
        poi_file = self.data_dir / city / "pois.json"
        if not poi_file.exists():
            logger.warning(f"POI file not found: {poi_file}")
            return []
        
        try:
            with open(poi_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Filter to attractions and nightlife
                attractions = [p for p in data if p.get("type") in ("attraction", "nightlife")]
                logger.info(f"Loaded {len(attractions)} attractions for {city}")
                return attractions
        except Exception as e:
            logger.error(f"Failed to load POIs: {e}")
            return []
    
    async def execute(self, state: TourState) -> dict:
        """Search and recommend POIs using hybrid scoring + LLM."""
        intent = state.get("intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)
        must_visit = intent.get("must_visit", [])
        
        if not city:
            return {"errors": state.get("errors", []) + ["No city specified"]}
        
        # Load POIs from local data
        all_pois = self._load_pois(city)
        
        if not all_pois:
            return {"errors": state.get("errors", []) + [f"No POI data for {city}"]}
        
        # Step 1: Score-based pre-filtering
        logger.info("Step 1: Scoring and ranking POIs...")
        top_k = days * 5  # 5 POIs per day as candidates
        scored_pois = rank_pois(
            pois=all_pois,
            intent=intent,
            top_k=top_k,
        )
        
        # Step 2: LLM-based selection
        logger.info("Step 2: LLM selection from top candidates...")
        
        # Prepare context for LLM
        poi_list = "\n".join([
            f"- {p['name']} (ID:{p['id']}, 区域:{p.get('area', '')}, "
            f"评分:{p.get('popularity', 0)}, 分数:{p.get('_score', 0):.1f}, "
            f"标签:{','.join(p.get('tags', [])[:3])})"
            + (" 【必去】" if p.get("is_must_visit") or any(mv in p["name"] for mv in must_visit) else "")
            for p in scored_pois
        ])
        
        context = f"""城市: {city}
旅行天数: {days}
必去景点: {', '.join(must_visit) if must_visit else '无'}

预筛选候选景点 (已按评分排序):
{poi_list}

请从以上候选中选择 {days * 3} 个最合适的景点。"""
        
        runnable = self.get_runnable()
        response = await runnable.ainvoke({"context": context})
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            recommended = json.loads(content.strip())
            
            # Merge with full POI data
            poi_map = {p["id"]: p for p in all_pois}
            enriched_pois = []
            
            for rec in recommended:
                poi_id = rec.get("id", "")
                if poi_id in poi_map:
                    poi = poi_map[poi_id].copy()
                    poi["recommend_reason"] = rec.get("reason", "")
                    poi["priority"] = rec.get("priority", 5)
                    enriched_pois.append(poi)
            
            # Ensure must_visit are included
            for mv in must_visit:
                if not any(mv in p.get("name", "") for p in enriched_pois):
                    # Find in original data
                    for poi in all_pois:
                        if mv in poi.get("name", ""):
                            poi_copy = poi.copy()
                            poi_copy["recommend_reason"] = f"用户必去: {mv}"
                            poi_copy["priority"] = 1
                            poi_copy["is_must_visit"] = True
                            enriched_pois.insert(0, poi_copy)
                            break
            
            logger.info(f"Selected {len(enriched_pois)} POIs (including {len(must_visit)} must-visit)")
            return {"pois": enriched_pois}
        
        except Exception as e:
            logger.error(f"Failed to parse POI recommendations: {e}")
            # Fallback: use scored POIs directly
            return {"pois": scored_pois[:days * 3]}
