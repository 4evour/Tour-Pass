"""POI Agent - Search and recommend Points of Interest with scoring."""

import json
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState
from tools.scoring import rank_pois

logger = logging.getLogger(__name__)

# City name to directory mapping
CITY_DIR_MAP = {
    "广州": "guangzhou",
    "北京": "beijing",
    "上海": "shanghai",
    "深圳": "shenzhen",
    "成都": "chengdu",
    "重庆": "chongqing",
    "杭州": "hangzhou",
    "武汉": "wuhan",
    "南京": "nanjing",
    "西安": "xian",
    "长沙": "changsha",
    "昆明": "kunming",
    "大理": "dali",
    "丽江": "lijiang",
    "三亚": "sanya",
    "桂林": "guilin",
    "厦门": "xiamen",
    "青岛": "qingdao",
    "哈尔滨": "harbin",
    "苏州": "suzhou",
    "张家界": "zhangjiajie",
}

POI_SYSTEM = """You are a POI recommendation expert.

You receive a pre-scored list of candidate POIs. Select the best POIs for the trip.

Output format: JSON array with objects containing id, name, reason, priority fields.

RULES:
- MUST include all must_visit POIs
- Select diverse attractions
- Consider geographic distribution"""


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
    
    def _get_city_dir(self, city: str) -> str:
        """Get directory name for city."""
        if (self.data_dir / city).exists():
            return city
        if city in CITY_DIR_MAP:
            return CITY_DIR_MAP[city]
        return city.lower()
    
    def _load_pois(self, city: str) -> list[dict]:
        """Load POIs from local JSON file."""
        city_dir = self._get_city_dir(city)
        poi_file = self.data_dir / city_dir / "pois.json"
        
        if not poi_file.exists():
            logger.warning("POI file not found: " + str(poi_file))
            return []
        
        try:
            with open(poi_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                attractions = [p for p in data if p.get("type") in ("attraction", "nightlife")]
                logger.info("Loaded " + str(len(attractions)) + " attractions for " + city)
                return attractions
        except Exception as e:
            logger.error("Failed to load POIs: " + str(e))
            return []
    
    async def execute(self, state: TourState) -> dict:
        """Search and recommend POIs."""
        intent = state.get("trip_intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)
        must_visit = intent.get("must_visit", [])
        
        if not city:
            return {"pois": []}
        
        # Load POIs
        all_pois = self._load_pois(city)
        
        if not all_pois:
            return {"pois": []}
        
        # Score and rank POIs
        logger.info("Scoring and ranking POIs...")
        top_k = days * 5
        scored_pois = rank_pois(pois=all_pois, intent=intent, top_k=top_k)
        
        # Ensure must_visit are included
        enriched_pois = []
        for mv in must_visit:
            for poi in scored_pois:
                if mv in poi.get("name", ""):
                    poi_copy = poi.copy()
                    poi_copy["is_must_visit"] = True
                    poi_copy["recommend_reason"] = "Must visit: " + mv
                    enriched_pois.append(poi_copy)
                    break
        
        # Add other top POIs
        for poi in scored_pois:
            if poi not in enriched_pois:
                enriched_pois.append(poi)
        
        # Limit to days * 3
        enriched_pois = enriched_pois[:days * 3]
        
        logger.info("Selected " + str(len(enriched_pois)) + " POIs")
        return {"pois": enriched_pois}
