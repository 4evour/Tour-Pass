"""Intent Agent - Parse user natural language into structured TripIntent.

Optimized with better Chinese NLP handling and edge case coverage.
"""

import json
import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState, TripIntent

logger = logging.getLogger(__name__)

PARSE_INTENT_SYSTEM = """你是一个旅行意图解析专家。你的任务是从用户的自然语言请求中提取结构化信息。

请提取以下信息：

1. **city** (必填): 目的地城市名称（中文）
2. **days** (默认3): 旅行天数
3. **pace**: 旅行节奏
   - "relaxed" (轻松): 每天2-3个景点，慢慢逛
   - "balanced" (适中): 每天4-5个景点，不赶不慢
   - "intense" (紧凑): 每天6+个景点，尽可能多
4. **travelers**: 旅行者类型
   - "solo" (独行), "couple" (情侣), "family" (家庭), "friends" (朋友), "elderly" (老人)
5. **interests**: 兴趣标签列表
   - 可选: "culture" (文化), "food" (美食), "nature" (自然), "shopping" (购物), 
     "nightlife" (夜生活), "history" (历史), "art" (艺术), "photography" (摄影),
     "adventure" (冒险), "family" (亲子)
6. **must_visit** (重要!): 用户明确要求必须去的地方
   - 识别关键词: "一定要去", "必须去", "想去", "不能错过", "必去", "想看", "想玩"
   - 提取具体景点名称，不要提取类别
7. **avoid**: 用户想要避免的地方/类型
   - 识别关键词: "不想去", "不要", "避免", "不感兴趣", "不喜欢"
8. **budget**: 预算级别
   - "budget" (经济), "mid-range" (中等), "luxury" (豪华)
9. **special_requests**: 其他特殊要求

**特别注意**：
- must_visit 必须准确提取！这是用户最在意的
- 如果用户说"想去橘子洲和岳麓山"，must_visit = ["橘子洲", "岳麓山"]
- 如果用户说"不要去太商业化的地方"，avoid = ["商业化"]
- 天数提取: "3天", "三天", "3天2晚" -> days = 3

**输出格式** (严格JSON):
```json
{
  "city": "城市名",
  "days": 3,
  "pace": "balanced",
  "travelers": "solo",
  "interests": ["food", "culture"],
  "must_visit": ["景点1", "景点2"],
  "avoid": ["避免项"],
  "budget": null,
  "special_requests": null
}
```

**示例**：
输入: "我想去长沙玩3天，一定要去橘子洲和岳麓山，不要去太商业化的地方，喜欢吃辣的"
输出:
```json
{
  "city": "长沙",
  "days": 3,
  "pace": "balanced",
  "travelers": "solo",
  "interests": ["food", "culture"],
  "must_visit": ["橘子洲", "岳麓山"],
  "avoid": ["商业化"],
  "budget": null,
  "special_requests": "喜欢吃辣的"
}
```

输入: "下周带家人去广州玩5天，轻松点的行程，想去长隆和广州塔"
输出:
```json
{
  "city": "广州",
  "days": 5,
  "pace": "relaxed",
  "travelers": "family",
  "interests": ["family", "culture"],
  "must_visit": ["长隆", "广州塔"],
  "avoid": [],
  "budget": null,
  "special_requests": null
}
```"""


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
                       f"must_visit={intent.must_visit}, interests={intent.interests}")
            
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
                "厦门", "青岛", "哈尔滨", "苏州", "张家界", "郑州", "合肥",
                "济南", "福州", "贵阳", "南宁", "兰州", "太原", "石家庄",
            ]
            fallback_city = ""
            for c in known_cities:
                if c in user_message:
                    fallback_city = c
                    break
            
            # Try to extract days
            import re
            days_match = re.search(r'(\d+)\s*[天日]', user_message)
            days = int(days_match.group(1)) if days_match else 3
            
            # Try to extract must_visit
            must_visit = []
            must_patterns = [
                r'一定要去(.+?)(?:，|。|$)',
                r'必须去(.+?)(?:，|。|$)',
                r'想去(.+?)(?:，|。|$)',
                r'必去(.+?)(?:，|。|$)',
            ]
            for pattern in must_patterns:
                match = re.search(pattern, user_message)
                if match:
                    # Split by "和" or "、"
                    places = re.split(r'[和、]', match.group(1))
                    must_visit.extend([p.strip() for p in places if p.strip()])
                    break
            
            fallback_intent = TripIntent(
                city=fallback_city or "长沙",
                days=days,
                must_visit=must_visit,
            )
            
            return {
                "intent": fallback_intent.model_dump(),
                "city": fallback_intent.city,
                "days": fallback_intent.days,
                "errors": state.get("errors", []) + [f"Intent parsing fallback used: {e}"],
            }
