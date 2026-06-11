"""POI Agent - Search and recommend Points of Interest."""

import json
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

POI_SYSTEM = """You are a POI (Point of Interest) recommendation expert. 

Given the user's intent and available POIs, select the best attractions for their trip.

RULES:
1. MUST include all must_visit places (marked with 【必去】)
2. Prioritize POIs that match user's interests
3. Consider geographic clustering (group nearby POIs)
4. Balance popular spots with hidden gems
5. Return top {top_k} POIs

Output format (JSON array):
[
  {
    "id": "poi_id",
    "name": "景点名称",
    "reason": "推荐理由",
    "match_score": 0.95
  }
]"""


class PoiAgent(BaseTourAgent):
    """Agent that searches and recommends POIs based on user intent."""
    
    def __init__(self, llm: BaseChatModel, data_dir: str = "data"):
        super().__init__(llm)
        self.data_dir = Path(data_dir)
    
    @property
    def name(self) -> str:
        return "PoiAgent"
    
    @property
    def description(self) -> str:
        return "Search and recommend Points of Interest"
    
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
                # Filter to attractions only
                attractions = [p for p in data if p.get("type") == "attraction"]
                logger.info(f"Loaded {len(attractions)} attractions for {city}")
                return attractions
        except Exception as e:
            logger.error(f"Failed to load POIs: {e}")
            return []
    
    async def execute(self, state: TourState) -> dict:
        """Search and recommend POIs."""
        intent = state.get("intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)
        must_visit = intent.get("must_visit", [])
        interests = intent.get("interests", [])
        
        if not city:
            return {"errors": state.get("errors", []) + ["No city specified"]}
        
        # Load POIs from local data
        all_pois = self._load_pois(city)
        
        if not all_pois:
            return {"errors": state.get("errors", []) + [f"No POI data for {city}"]}
        
        # Mark must_visit POIs
        for poi in all_pois:
            poi["is_must_visit"] = any(mv in poi["name"] for mv in must_visit)
        
        # Prepare context for LLM
        poi_list = "\n".join([
            f"- {p['name']} (ID:{p['id']}, 区域:{p.get('area', '')}, "
            f"评分:{p.get('popularity', 0)}, 标签:{','.join(p.get('tags', [])[:3])})"
            + (" 【必去】" if p.get("is_must_visit") else "")
            for p in all_pois[:50]  # Limit to top 50 for context window
        ])
        
        context = f"""城市: {city}
旅行天数: {days}
用户兴趣: {', '.join(interests) if interests else '综合'}
必去景点: {', '.join(must_visit) if must_visit else '无'}

候选景点列表:
{poi_list}

请推荐 {days * 4} 个最适合的景点。"""
        
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
                    poi["match_score"] = rec.get("match_score", 0)
                    enriched_pois.append(poi)
            
            logger.info(f"Recommended {len(enriched_pois)} POIs")
            return {"pois": enriched_pois}
        
        except Exception as e:
            logger.error(f"Failed to parse POI recommendations: {e}")
            # Fallback: return top POIs by popularity
            must_visit_pois = [p for p in all_pois if p.get("is_must_visit")]
            other_pois = [p for p in all_pois if not p.get("is_must_visit")]
            other_pois.sort(key=lambda x: x.get("popularity", 0), reverse=True)
            
            fallback = must_visit_pois + other_pois[:days * 4]
            return {"pois": fallback}
