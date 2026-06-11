"""Intent Agent - Parse user natural language into structured TripIntent."""

import json
import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState, TripIntent

logger = logging.getLogger(__name__)

PARSE_INTENT_SYSTEM = """You are a travel intent parser. Your job is to extract structured information from user's natural language request.

Extract the following information:
1. city: Destination city name (in Chinese)
2. days: Number of travel days (default 3 if not specified)
3. pace: Travel pace - "relaxed" (轻松), "balanced" (适中), or "intense" (紧凑)
4. travelers: Traveler type - "solo" (独行), "couple" (情侣), "family" (家庭), "friends" (朋友), "elderly" (老人)
5. interests: List of interest tags like ["culture", "food", "nature", "shopping", "nightlife", "history", "art", "photography"]
6. must_visit: List of specific places the user MUST visit (extract from phrases like "一定要去", "必须去", "想去")
7. avoid: List of places/types to avoid (extract from phrases like "不想去", "不要", "避免")
8. budget: Budget level - "budget" (经济), "mid-range" (中等), "luxury" (豪华), or null
9. special_requests: Any other special requests

IMPORTANT RULES:
- If user says "必去XXX" or "一定要去XXX", add to must_visit
- If user says "不要XXX" or "不想去XXX", add to avoid
- Extract exact place names for must_visit, not categories
- Return valid JSON only

Example input: "我想去长沙玩3天，一定要去橘子洲和岳麓山，不要去太商业化的地方，喜欢吃辣的"
Example output:
{
  "city": "长沙",
  "days": 3,
  "pace": "balanced",
  "travelers": "solo",
  "interests": ["food", "culture"],
  "must_visit": ["橘子洲", "岳麓山"],
  "avoid": ["商业化景点"],
  "budget": null,
  "special_requests": "喜欢吃辣的"
}"""


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
    
    async def execute(self, state: TourState) -> dict:
        """Parse user intent from natural language."""
        user_message = state.get("user_message", "")
        
        # Skip if intent already parsed
        if state.get("intent") and state["intent"].get("city"):
            logger.info("Intent already parsed, skipping")
            return {}
        
        logger.info(f"Parsing intent from: {user_message[:50]}...")
        
        runnable = self.get_runnable()
        response = await runnable.ainvoke({"user_message": user_message})
        
        try:
            # Extract JSON from response
            content = response.content
            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            data = json.loads(content.strip())
            intent = TripIntent(**data)
            
            logger.info(f"Parsed intent: city={intent.city}, days={intent.days}, "
                       f"must_visit={intent.must_visit}")
            
            return {
                "intent": intent.model_dump(),
                "city": intent.city,
                "days": intent.days,
            }
        except Exception as e:
            logger.error(f"Failed to parse intent: {e}")
            # Fallback: try to extract city from known cities
            known_cities = [
                "北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "武汉",
                "南京", "西安", "长沙", "昆明", "大理", "丽江", "三亚", "桂林",
                "厦门", "青岛", "哈尔滨", "苏州", "张家界",
            ]
            fallback_city = ""
            for c in known_cities:
                if c in user_message:
                    fallback_city = c
                    break
            
            fallback_intent = TripIntent(city=fallback_city or "长沙", days=3)
            return {
                "intent": fallback_intent.model_dump(),
                "city": fallback_intent.city,
                "days": fallback_intent.days,
                "errors": state.get("errors", []) + [f"Intent parsing failed, using fallback: {e}"],
            }
