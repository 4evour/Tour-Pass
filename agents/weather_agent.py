"""Weather Agent - Fetch weather forecast for the trip.

When the real API is unavailable, returns a clearly-marked placeholder
instead of hallucinating weather data via LLM.
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

SUGGESTION_SYSTEM = """You are a travel advisor. Given weather forecasts, generate a one-sentence Chinese travel suggestion per day.

Return a JSON array: [{"suggestion": "..."}]"""


class WeatherAgent(LLMAgent):
    """Fetch weather forecast. LLM is only used for generating human-friendly
    suggestion text from real data — never for fabricating weather numbers."""

    def __init__(self, llm: BaseChatModel):
        super().__init__(llm)

    @property
    def name(self) -> str:
        return "WeatherAgent"

    @property
    def description(self) -> str:
        return "Fetch weather forecast for the trip"

    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", SUGGESTION_SYSTEM),
            ("human", "{context}"),
        ])

    async def _generate_suggestions(self, city: str, weather_data: list[dict]) -> list[str]:
        """Generate travel suggestions using LLM from *real* weather data."""
        try:
            lines = [f"城市: {city}\n天气预报:"]
            for w in weather_data:
                lines.append(f"- {w['date']}: {w['condition']}, {w['temperature_low']}-{w['temperature_high']}°C")
            lines.append("\n请为每天生成一句旅行建议（中文）。返回JSON数组，每项: {\"suggestion\": \"...\"}")
            context = "\n".join(lines)

            content = await self.invoke_llm({"context": context})
            # Strip markdown fences
            if "```json" in content:
                content = content.split("```json", 1)[1].rsplit("```", 1)[0]
            elif "```" in content:
                content = content.split("```", 1)[1].rsplit("```", 1)[0]
            suggestions = json.loads(content.strip())
            return [s.get("suggestion", "适合出行") for s in suggestions]
        except Exception as e:
            logger.warning("Failed to generate suggestions via LLM: %s", e)
            return ["适合出行"] * len(weather_data)

    def _make_placeholder(self, days: int) -> list[dict]:
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
                "humidity": None,
                "wind_speed": None,
                "suggestion": "天气数据暂不可用，建议出行前查看实时天气",
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

        # Try real API
        real_weather = await weather_api.fetch_weather(city, days)

        if real_weather:
            logger.info("Using real weather data for %s", city)
            suggestions = await self._generate_suggestions(city, real_weather)
            for i, s in enumerate(suggestions):
                if i < len(real_weather):
                    real_weather[i]["suggestion"] = s
            return {"weather": real_weather}

        # Fallback: honest placeholder, NOT LLM hallucination
        logger.warning("Weather API unavailable for %s, returning placeholder", city)
        return {"weather": self._make_placeholder(days)}
