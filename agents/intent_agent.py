"""Intent Agent - Parse user natural language into structured TripIntent.

Uses a three-tier strategy:
1. Regex fast-path (zero cost, instant)
2. LLM structured-output fallback (only when regex fails city extraction)
3. Explicit error if city cannot be resolved (no silent default)
"""

import json
import logging
import re
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import LLMAgent
from agents.constants import KNOWN_CITIES, ENGLISH_CITY_MAP, CITY_DIR_MAP
from agents.state import TourState, TripIntent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex extractors
# ---------------------------------------------------------------------------

_DAYS_RE = re.compile(r"(\d+)\s*[天日]")

_MUST_VISIT_RES = [
    re.compile(r"(?:一定|必须|必)要去(.+?)(?:[，。]|$)"),
    re.compile(r"(?:必须|务必)去(.+?)(?:[，。]|$)"),
    re.compile(r"(?<!不)(?<!别)(?<!没)(?<!勿)要去(.+?)(?:[，。；;,.!?！？]|$)"),
    re.compile(r"想去(.+?)(?:[，。]|$)"),
    re.compile(r"必去(.+?)(?:[，。]|$)"),
]

_AVOID_RES = [
    re.compile(r"(?:不去|别去|不想去|避免|不要|别安排|不想|跳过)(.+?)(?:[，。]|$)"),
]

_PLACE_CONNECTOR_RE = re.compile(r"[、/；;]|以及|还有|跟|与")
_HE_SUFFIX_CHARS = set("园院寺山湖海塔城街巷宫门台馆岛湾镇村峰洞桥路店坊祠庙阁楼")

_RELAXED_PACE_KEYWORDS = (
    "休闲", "轻松", "放松", "少走路", "不赶", "别太赶",
    "慢节奏", "松弛", "悠闲", "半日",
)
_INTENSE_PACE_KEYWORDS = (
    "紧凑", "特种兵", "高强度", "多安排", "多玩", "从早到晚",
    "上午下午晚上", "排满", "满一点", "赶一点", "打卡多",
)

_INTEREST_MAP: dict[str, str] = {
    "美食": "food", "吃": "food", "火锅": "food", "串串": "food",
    "小吃": "food", "夜市": "food", "烧烤": "food", "早茶": "food",
    "文化": "culture", "历史": "history", "古迹": "history",
    "博物馆": "culture", "寺庙": "culture", "古城": "culture", "古镇": "culture",
    "自然": "nature", "风景": "nature", "爬山": "nature", "登山": "nature",
    "徒步": "nature", "海边": "nature", "沙滩": "nature", "公园": "nature",
    "购物": "shopping", "逛街": "shopping",
    "夜生活": "nightlife", "夜景": "nightlife", "酒吧": "nightlife",
    "摄影": "photography", "拍照": "photography",
    "休闲": "leisure", "度假": "leisure", "温泉": "leisure",
    "游乐": "entertainment", "主题公园": "entertainment", "演出": "entertainment",
}

_TRAVELER_MAP: list[tuple[str, str]] = [
    # Longer patterns first to avoid false positives
    ("一家人", "family"), ("一家", "family"), ("带孩子", "family"),
    ("带娃", "family"), ("亲子", "family"), ("小孩", "family"), ("宝宝", "family"),
    ("男朋友", "couple"), ("女朋友", "couple"), ("情侣", "couple"),
    ("老公", "couple"), ("老婆", "couple"), ("媳妇", "couple"), ("两人", "couple"),
    ("和朋友", "friends"), ("闺蜜", "friends"), ("哥们", "friends"),
    ("同学", "friends"), ("同事", "friends"), ("团建", "friends"),
    ("爸妈", "elderly"), ("父母", "elderly"), ("长辈", "elderly"), ("老人", "elderly"),
    ("一个人", "solo"), ("独自", "solo"), ("自己去", "solo"), ("单独", "solo"),
    ("朋友", "friends"),  # after "和朋友"
    ("孩子", "family"),
]

_BUDGET_LUXURY = {"奢华", "豪华", "高端", "五星", "5星", "顶级", "不差钱", "住好", "好的酒店", "好点的酒店"}
_BUDGET_CHEAP = {"穷游", "省钱", "便宜", "经济", "实惠", "性价比", "背包", "青年旅舍", "青旅"}
_BUDGET_MID = {"中等", "适中", "一般", "普通", "差不多"}

# ---------------------------------------------------------------------------
# Hotel / strategy extractors
# ---------------------------------------------------------------------------

# Hotel area patterns: "住在XX区", "住XX", "酒店在XX"
_HOTEL_AREA_RE = re.compile(r"(?:住在?|酒店在?)(.{2,6}(?:区|商圈|路|街|镇))")

# Hotel budget patterns: "每晚300-500", "预算200元", "酒店500以内"
_HOTEL_BUDGET_RANGE_RE = re.compile(r"(?:每晚|酒店|住宿).{0,5}?(\d+)\s*[-~到至]\s*(\d+)")
_HOTEL_BUDGET_MAX_RE = re.compile(r"(?:每晚|酒店|住宿).{0,5}?(\d+)\s*(?:以內|以内|以下|左右)")

# Strategy keywords
_STRATEGY_KEYWORDS: dict[str, list[str]] = {
    "culture": ["文化", "历史", "古迹", "博物馆", "寺庙"],
    "culinary": ["美食", "小吃", "吃货", "火锅", "烧烤", "夜市"],
    "nature": ["自然", "风景", "户外", "爬山", "登山", "海边"],
}

# ---------------------------------------------------------------------------
# Prompt for LLM fallback
# ---------------------------------------------------------------------------

PARSE_SYSTEM = """You are a travel intent parser. Extract structured information from the user's request.

Return valid JSON only with these fields:
city (string, Chinese), days (int, default 3), pace (relaxed|balanced|intense),
travelers (solo|couple|family|friends|elderly), interests (string[]),
must_visit (string[]), avoid (string[]), budget (budget|mid-range|luxury|null),
special_requests (string|null),
hotel_preference (string, hotel type preference, default ""),
hotel_area (string, preferred hotel district, default ""),
hotel_budget_min (int, min nightly budget in CNY, default 0),
hotel_budget_max (int, max nightly budget in CNY, default 0),
strategy (balanced|culture|culinary|nature, default balanced)."""


class IntentAgent(LLMAgent):
    """Parse user natural language into structured TripIntent."""

    def __init__(self, llm: BaseChatModel):
        super().__init__(llm)

    @property
    def name(self) -> str:
        return "IntentAgent"

    @property
    def description(self) -> str:
        return "Parse user natural language into TripIntent"

    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", PARSE_SYSTEM),
            ("human", "{user_message}"),
        ])

    # -- regex helpers -------------------------------------------------------

    @staticmethod
    def _extract_city(text: str) -> str:
        for city in KNOWN_CITIES:
            if city in text:
                return city
        lower = text.lower()
        for eng, chn in ENGLISH_CITY_MAP.items():
            if eng in lower:
                return chn
        return ""

    @staticmethod
    def _extract_days(text: str) -> int:
        m = _DAYS_RE.search(text)
        return int(m.group(1)) if m else 3

    @staticmethod
    def _split_place_list(raw: str) -> list[str]:
        """Split place names while preserving names like 颐和园 and 和平公园."""
        places: list[str] = []
        for piece in _PLACE_CONNECTOR_RE.split(raw):
            piece = piece.strip()
            if not piece:
                continue

            start = 0
            for idx, ch in enumerate(piece):
                if ch != "和":
                    continue
                prev_len = idx - start
                next_ch = piece[idx + 1] if idx + 1 < len(piece) else ""
                if prev_len >= 2 and next_ch and next_ch not in _HE_SUFFIX_CHARS:
                    part = piece[start:idx].strip()
                    if part:
                        places.append(part)
                    start = idx + 1

            tail = piece[start:].strip()
            if tail:
                places.append(tail)

        return places

    @staticmethod
    def _extract_must_visit(text: str) -> list[str]:
        for pat in _MUST_VISIT_RES:
            m = pat.search(text)
            if m:
                return IntentAgent._split_place_list(m.group(1))
        return []

    @staticmethod
    def _extract_pace(text: str) -> str:
        if any(kw in text for kw in _RELAXED_PACE_KEYWORDS):
            return "relaxed"
        if any(kw in text for kw in _INTENSE_PACE_KEYWORDS):
            return "intense"
        return "balanced"

    @staticmethod
    def _extract_avoid(text: str) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for pat in _AVOID_RES:
            m = pat.search(text)
            if m:
                for item in re.split(r"[和、]", m.group(1)):
                    item = item.strip()
                    if item and item not in seen:
                        seen.add(item)
                        result.append(item)
        return result

    @staticmethod
    def _extract_interests(text: str) -> list[str]:
        interests: list[str] = []
        for chn, eng in _INTEREST_MAP.items():
            if chn in text and eng not in interests:
                interests.append(eng)
        return interests

    @staticmethod
    def _extract_travelers(text: str) -> str:
        for chn, eng in _TRAVELER_MAP:
            if chn in text:
                return eng
        return "solo"

    @staticmethod
    def _extract_budget(text: str) -> Optional[str]:
        for kw in _BUDGET_LUXURY:
            if kw in text:
                return "luxury"
        for kw in _BUDGET_CHEAP:
            if kw in text:
                return "budget"
        for kw in _BUDGET_MID:
            if kw in text:
                return "mid-range"
        return None

    @staticmethod
    def _extract_hotel_area(text: str) -> str:
        m = _HOTEL_AREA_RE.search(text)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_hotel_budget(text: str) -> tuple[int, int]:
        """Return (min, max) nightly budget in CNY; (0,0) if not specified."""
        m = _HOTEL_BUDGET_RANGE_RE.search(text)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = _HOTEL_BUDGET_MAX_RE.search(text)
        if m:
            return 0, int(m.group(1))
        return 0, 0

    @staticmethod
    def _extract_strategy(text: str) -> str:
        for strategy, keywords in _STRATEGY_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return strategy
        return "balanced"

    # -- LLM fallback -------------------------------------------------------

    async def _llm_parse(self, user_message: str, state: Optional[TourState] = None) -> dict:
        """Use LLM to parse intent; returns a raw dict."""
        content = await self.invoke_llm({"user_message": user_message}, state=state)
        # Strip markdown fences if present
        if "```json" in content:
            content = content.split("```json", 1)[1].rsplit("```", 1)[0]
        elif "```" in content:
            content = content.split("```", 1)[1].rsplit("```", 1)[0]
        return json.loads(content.strip())

    async def _llm_extract_must_visit(self, user_message: str, city: str, state: Optional[TourState] = None) -> list[str]:
        """Lightweight LLM call to extract must_visit places only."""
        prompt = (
            f"\u4ece\u4ee5\u4e0b\u6d88\u606f\u4e2d\u63d0\u53d6\u7528\u6237\u60f3\u53bb\u7684\u666f\u70b9\u540d\u79f0\uff08\u4e0d\u5305\u542b\u57ce\u5e02\u540d\uff09\u3002"
            f"\u57ce\u5e02\u662f{city}\u3002\u53ea\u8fd4\u56deJSON\u6570\u7ec4\uff0c\u5982 [\"\u666f\u70b9A\", \"\u666f\u70b9B\"]\u3002"
            f"\u5982\u679c\u6ca1\u6709\u660e\u786e\u666f\u70b9\uff0c\u8fd4\u56de []\u3002\n"
            f"\u6d88\u606f\uff1a{user_message}"
        )
        content = await self.invoke_llm({"user_message": prompt}, state=state)
        if "```json" in content:
            content = content.split("```json", 1)[1].rsplit("```", 1)[0]
        elif "```" in content:
            content = content.split("```", 1)[1].rsplit("```", 1)[0]
        result = json.loads(content.strip())
        if isinstance(result, list):
            return [s for s in result if isinstance(s, str) and s.strip()]
        return []

    # -- main ----------------------------------------------------------------

    async def execute(self, state: TourState) -> dict:
        user_message = state.get("user_message", "")

        if state.get("trip_intent") and state["trip_intent"].get("city"):
            return {}  # already parsed

        # --- Regex fast-path ---
        city = self._extract_city(user_message)
        days = self._extract_days(user_message)
        must_visit = self._extract_must_visit(user_message)
        interests = self._extract_interests(user_message)
        travelers = self._extract_travelers(user_message)
        budget = self._extract_budget(user_message)
        avoid = self._extract_avoid(user_message)
        pace = self._extract_pace(user_message)

        # --- Hotel / strategy regex ---
        hotel_area = self._extract_hotel_area(user_message)
        hotel_budget_min, hotel_budget_max = self._extract_hotel_budget(user_message)
        strategy = self._extract_strategy(user_message)

        # --- LLM fallback only when city is missing ---
        if not city:
            try:
                data = await self._llm_parse(user_message, state=state)
                llm_city = data.get("city", "")
                # Normalise
                if llm_city in CITY_DIR_MAP:
                    city = llm_city
                elif llm_city in KNOWN_CITIES:
                    city = llm_city
                elif llm_city.lower() in ENGLISH_CITY_MAP:
                    city = ENGLISH_CITY_MAP[llm_city.lower()]
                # Fill gaps from LLM
                if not must_visit:
                    must_visit = data.get("must_visit", [])
                if not interests:
                    interests = data.get("interests", [])
                if travelers == "solo":
                    travelers = data.get("travelers", travelers)
                if budget is None:
                    budget = data.get("budget")
                if not avoid:
                    avoid = data.get("avoid", [])
                if days == 3:
                    days = data.get("days", 3)
                if pace == "balanced":
                    pace = data.get("pace", "balanced")
                # Fill hotel/strategy gaps from LLM
                if not hotel_area:
                    hotel_area = data.get("hotel_area", "")
                if hotel_budget_max == 0:
                    hotel_budget_min = int(data.get("hotel_budget_min", 0) or 0)
                    hotel_budget_max = int(data.get("hotel_budget_max", 0) or 0)
                if strategy == "balanced":
                    strategy = data.get("strategy", "balanced")
            except Exception as e:
                logger.error("LLM parsing failed: %s", e)

        # --- LLM must_visit supplement when city found but must_visit empty ---
        if city and not must_visit:
            has_compound = any(sep in user_message for sep in ("\u3001", "\u548c", "\u8fd8\u6709", "\u4ee5\u53ca"))
            has_visit_kw = any(kw in user_message for kw in ("\u53bb", "\u73a9", "\u901b", "\u6253\u5361"))
            if has_compound and has_visit_kw:
                try:
                    must_visit = await self._llm_extract_must_visit(user_message, city, state=state)
                except Exception as e:
                    logger.warning("LLM must_visit supplement failed: %s", e)

        if not city:
            # Explicit error instead of silent default
            return {"errors": [f"IntentAgent: 无法识别目的地城市，请明确指定城市名称（支持: {', '.join(KNOWN_CITIES[:10])}...）"]}

        intent = TripIntent(
            city=city,
            days=days,
            pace=pace,
            must_visit=must_visit,
            interests=interests,
            travelers=travelers,
            budget=budget,
            avoid=avoid,
            hotel_area=hotel_area,
            hotel_budget_min=hotel_budget_min,
            hotel_budget_max=hotel_budget_max,
            strategy=strategy,
        )
        logger.info("Parsed intent: %s", intent.model_dump())

        return {
            "trip_intent": intent.model_dump(),
            "city": intent.city,
            "days": intent.days,
            "sse_events": [{
                "type": "intent_parsed",
                "content": f"目的地：{intent.city}，{intent.days}天{intent.pace}节奏",
            }],
        }
