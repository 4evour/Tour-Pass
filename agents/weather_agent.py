"""Weather Agent - Fetch weather forecast with indices and warnings.

Integrates three QWeather data sources:
1. Daily forecast (temperature, humidity, UV, sunrise/sunset, etc.)
2. Weather indices (travel, clothing, UV, sports, cold-risk)
3. Severe weather warnings (暴雨, 台风, 高温 alerts)

LLM is used ONLY for generating human-friendly suggestion text from
real data — never for fabricating weather numbers.
"""

import json
import logging
from datetime import datetime, timedelta

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import LLMAgent
from agents.state import TourState
from tools import weather_api

logger = logging.getLogger(__name__)

SUGGESTION_SYSTEM = """You are a travel advisor. Given weather forecasts, life indices, and any active warnings, generate a one-sentence Chinese travel suggestion per day.

Suggestions should be practical and specific:
- Mention UV protection when UV index is high (≥4)
- Recommend indoor activities on rainy days or when travel index is poor (≥4)
- Suggest appropriate clothing based on temperature and clothing index
- Alert about severe weather warnings if present
- Mention sunrise/sunset times if relevant for planning

Return a JSON array: [{"suggestion": "..."}]"""


class WeatherAgent(LLMAgent):
    """Fetch weather forecast with indices and warnings. LLM is only used for
    generating human-friendly suggestion text from real data."""

    def __init__(self, llm: BaseChatModel):
        super().__init__(llm)

    @property
    def name(self) -> str:
        return "WeatherAgent"

    @property
    def description(self) -> str:
        return "Fetch weather forecast with indices and warnings"

    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", SUGGESTION_SYSTEM),
            ("human", "{context}"),
        ])

    async def _generate_suggestions(
        self, city: str, weather_data: list[dict], warnings: list[dict],
        state=None,
    ) -> list[str]:
        """Generate travel suggestions using LLM from *real* weather data,
        enriched with indices and warnings."""
        try:
            lines = [f"城市: {city}\n天气预报:"]
            for w in weather_data:
                day_line = (
                    f"- {w['date']}: {w['condition']}"
                    f", {w['temperature_low']}-{w['temperature_high']}°C"
                    f", 湿度{w['humidity']}%"
                )
                if w.get("wind_dir"):
                    day_line += f", {w['wind_dir']}{w.get('wind_scale', '')}级"
                if w.get("uv_index", 0) >= 4:
                    day_line += f", 紫外线{w['uv_index']}(强)"
                if w.get("sunrise"):
                    day_line += f", 日出{w['sunrise']}/日落{w['sunset']}"

                # Append indices if available
                idx_parts = []
                if w.get("travel_index"):
                    ti = w["travel_index"]
                    idx_parts.append(f"旅游指数:{ti.get('category', '')}")
                if w.get("clothing_index"):
                    ci = w["clothing_index"]
                    idx_parts.append(f"穿衣:{ci.get('category', '')}")
                if idx_parts:
                    day_line += f" [{', '.join(idx_parts)}]"

                lines.append(day_line)

            if warnings:
                lines.append(f"\n⚠ 活跃灾害预警:")
                for w in warnings:
                    lines.append(f"- {w.get('title', '')} ({w.get('type_name', '')}, {w.get('level', '')}级)")
                    if w.get("text"):
                        lines.append(f"  {w['text'][:80]}")

            lines.append("\n请为每天生成一句旅行建议（中文），包含天气对行程的具体影响。返回JSON数组，每项: {\"suggestion\": \"...\"}")
            context = "\n".join(lines)

            content = await self.invoke_llm({"context": context}, state=state)
            # Strip markdown fences
            if "```json" in content:
                content = content.split("```json", 1)[1].rsplit("```", 1)[0]
            elif "```" in content:
                content = content.split("```", 1)[1].rsplit("```", 1)[0]
            suggestions = json.loads(content.strip())
            return [s.get("suggestion", "适合出行") for s in suggestions]
        except Exception as e:
            logger.warning("Failed to generate suggestions via LLM: %s", e)
            return self._fallback_suggestions(weather_data)

    @staticmethod
    def _fallback_suggestions(weather_data: list[dict]) -> list[str]:
        """Generate rule-based suggestions when LLM is unavailable."""
        suggestions = []
        for w in weather_data:
            parts = []
            condition = w.get("condition", "")
            if "雨" in condition:
                parts.append("记得带伞")
            uv_index = w.get("uv_index") or 0
            if uv_index >= 4:
                parts.append("注意防晒")
            temp_hi = w.get("temperature_high")
            if not isinstance(temp_hi, (int, float)):
                temp_hi = 25
            if temp_hi >= 35:
                parts.append("注意防暑降温")
            elif temp_hi <= 5:
                parts.append("注意保暖")
            if w.get("travel_index"):
                ti = w["travel_index"]
                level = int(ti.get("level", "1"))
                if level >= 4:
                    parts.append("建议安排室内活动")
            suggestions.append("，".join(parts) + "。" if parts else "适合出行")
        return suggestions

    @staticmethod
    def _make_placeholder(days: int) -> list[dict]:
        """Create clearly-marked placeholder weather when API is unavailable.

        We do NOT fabricate temperatures via LLM. Instead we provide
        generic guidance and flag the data as estimated.
        """
        start = datetime.now() + timedelta(days=1)
        return [
            {
                "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
                "temperature_high": None,
                "temperature_low": None,
                "condition": "未知",
                "condition_night": "",
                "humidity": None,
                "wind_speed": None,
                "wind_dir": "",
                "wind_scale": "",
                "sunrise": "",
                "sunset": "",
                "uv_index": 0,
                "precip": 0.0,
                "vis": 0,
                "pressure": 0,
                "cloud": 0,
                "suggestion": "天气数据暂不可用，建议出行前查看实时天气",
                "travel_index": None,
                "clothing_index": None,
                "sports_index": None,
                "uv_index_detail": None,
                "cold_risk_index": None,
                "warnings": [],
                "_placeholder": True,
            }
            for i in range(days)
        ]

    async def execute(self, state: TourState) -> dict:
        intent = state.get("trip_intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)

        if not city:
            return {"weather": []}

        # Fetch all three data sources concurrently
        import asyncio
        real_weather, indices_by_date, warnings = await asyncio.gather(
            weather_api.fetch_weather(city, days),
            weather_api.fetch_weather_indices(city, days),
            weather_api.fetch_weather_warnings(city),
            return_exceptions=True,
        )

        # Handle exceptions from gather
        if isinstance(real_weather, Exception):
            logger.warning("fetch_weather failed: %s", real_weather)
            real_weather = []
        if isinstance(indices_by_date, Exception):
            logger.warning("fetch_weather_indices failed: %s", indices_by_date)
            indices_by_date = {}
        if isinstance(warnings, Exception):
            logger.warning("fetch_weather_warnings failed: %s", warnings)
            warnings = []

        if real_weather:
            logger.info("Using real weather data for %s (%d days)", city, len(real_weather))

            # Merge indices into each day's weather data
            for day_data in real_weather:
                date = day_data.get("date", "")
                day_indices = indices_by_date.get(date, {})
                for index_key, index_value in day_indices.items():
                    day_data[index_key] = index_value
                # Attach warnings (same for all days since they're current)
                day_data["warnings"] = warnings

            # Generate LLM-enhanced suggestions
            suggestions = await self._generate_suggestions(
                city, real_weather, warnings, state=state,
            )
            for i, s in enumerate(suggestions):
                if i < len(real_weather):
                    real_weather[i]["suggestion"] = s

            # Build rich SSE event
            sse_content = f"已获取 {city} {len(real_weather)}天天气预报"
            if warnings:
                sse_content += f"（含{len(warnings)}条灾害预警）"

            return {
                "weather": real_weather,
                "sse_events": [{
                    "type": "weather_loaded",
                    "content": sse_content,
                }],
            }

        # Fallback: honest placeholder, NOT LLM hallucination
        logger.warning("Weather API unavailable for %s, returning placeholder", city)
        placeholder = self._make_placeholder(days)
        return {
            "weather": placeholder,
            "sse_events": [{
                "type": "weather_loaded",
                "content": "天气数据暂不可用",
            }],
        }
