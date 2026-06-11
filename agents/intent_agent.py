"""Intent Agent - Parse user natural language into structured TripIntent."""

import json
import logging
import re
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState, TripIntent

logger = logging.getLogger(__name__)

# City name mapping for DeepSeek API encoding issues
CITY_NAME_MAP = {
    "guangzhou": "广州",
    "beijing": "北京",
    "shanghai": "上海",
    "shenzhen": "深圳",
    "chengdu": "成都",
    "chongqing": "重庆",
    "hangzhou": "杭州",
    "wuhan": "武汉",
    "nanjing": "南京",
    "xian": "西安",
    "changsha": "长沙",
    "kunming": "昆明",
    "dali": "大理",
    "lijiang": "丽江",
    "sanya": "三亚",
    "guilin": "桂林",
    "xiamen": "厦门",
    "qingdao": "青岛",
    "harbin": "哈尔滨",
    "suzhou": "苏州",
    "zhangjiajie": "张家界",
}

# Known Chinese city names
KNOWN_CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "武汉",
    "南京", "西安", "长沙", "昆明", "大理", "丽江", "三亚", "桂林",
    "厦门", "青岛", "哈尔滨", "苏州", "张家界", "郑州", "合肥",
    "济南", "福州", "贵阳", "南宁", "兰州", "太原", "石家庄",
]

PARSE_INTENT_SYSTEM = """You are a travel intent parser. Extract structured information from user's natural language request.

Extract the following information:
1. city: Destination city name
2. days: Number of travel days (default 3)
3. pace: Travel pace - "relaxed", "balanced", or "intense"
4. travelers: Traveler type - "solo", "couple", "family", "friends", "elderly"
5. interests: List of interest tags like ["culture", "food", "nature", "shopping"]
6. must_visit: List of specific places the user MUST visit
7. avoid: List of places/types to avoid
8. budget: Budget level - "budget", "mid-range", "luxury", or null
9. special_requests: Any other special requests

Return valid JSON only."""


class IntentAgent(BaseTourAgent):
    """Agent that parses user's natural language into structured TripIntent."""
    
    @property
    def name(self) -> str:
        return "IntentAgent"
    
    @property
    def description(self) -> str:
        return "Parse user's natural language request into structured TripIntent"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", PARSE_INTENT_SYSTEM),
            ("human", "{user_message}"),
        ])
    
    def _extract_city_from_text(self, text: str) -> str:
        """Extract city name from text using regex."""
        # Try to find Chinese city names
        for city in KNOWN_CITIES:
            if city in text:
                return city
        
        # Try to find English city names and map to Chinese
        for eng, chn in CITY_NAME_MAP.items():
            if eng in text.lower():
                return chn
        
        return ""
    
    def _extract_days_from_text(self, text: str) -> int:
        """Extract number of days from text."""
        days_match = re.search(r'(\d+)\s*[天日]', text)
        if days_match:
            return int(days_match.group(1))
        return 3
    
    def _extract_must_visit_from_text(self, text: str) -> list:
        """Extract must-visit places from text."""
        must_visit = []
        must_patterns = [
            r'一定要去(.+?)(?:，|。|$)',
            r'必须去(.+?)(?:，|。|$)',
            r'想去(.+?)(?:，|。|$)',
            r'必去(.+?)(?:，|。|$)',
        ]
        for pattern in must_patterns:
            match = re.search(pattern, text)
            if match:
                places = re.split(r'[和、]', match.group(1))
                must_visit.extend([p.strip() for p in places if p.strip()])
                break
        return must_visit
    
    def _extract_interests_from_text(self, text: str) -> list:
        """Extract interests from text."""
        interests = []
        interest_map = {
            "美食": "food",
            "吃": "food",
            "文化": "culture",
            "历史": "history",
            "自然": "nature",
            "购物": "shopping",
            "夜生活": "nightlife",
            "摄影": "photography",
        }
        for chn, eng in interest_map.items():
            if chn in text:
                interests.append(eng)
        return interests
    
    async def execute(self, state: TourState) -> dict:
        """Parse user intent from natural language."""
        user_message = state.get("user_message", "")
        
        # Skip if intent already parsed
        if state.get("trip_intent") and state["trip_intent"].get("city"):
            logger.info("Intent already parsed, skipping")
            return {}
        
        logger.info("Parsing intent from: " + user_message[:50] + "...")
        
        # Use regex-based extraction as primary method
        city = self._extract_city_from_text(user_message)
        days = self._extract_days_from_text(user_message)
        must_visit = self._extract_must_visit_from_text(user_message)
        interests = self._extract_interests_from_text(user_message)
        
        if not city:
            # Fallback to LLM
            try:
                runnable = self.get_runnable()
                response = await runnable.ainvoke({"user_message": user_message})
                
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                data = json.loads(content.strip())
                
                # Map city name if needed
                llm_city = data.get("city", "")
                if llm_city in CITY_NAME_MAP:
                    city = CITY_NAME_MAP[llm_city]
                elif llm_city in KNOWN_CITIES:
                    city = llm_city
                
                if not days:
                    days = data.get("days", 3)
                if not must_visit:
                    must_visit = data.get("must_visit", [])
                if not interests:
                    interests = data.get("interests", [])
            except Exception as e:
                logger.error("LLM parsing failed: " + str(e))
        
        if not city:
            city = "广州"  # Default to Guangzhou
        
        intent = TripIntent(
            city=city,
            days=days,
            must_visit=must_visit,
            interests=interests,
        )
        
        logger.info("Parsed intent: city=" + intent.city + ", days=" + str(intent.days) + 
                   ", must_visit=" + str(intent.must_visit))
        
        return {
            "trip_intent": intent.model_dump(),
            "city": intent.city,
            "days": intent.days,
        }
