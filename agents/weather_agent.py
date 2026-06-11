"""Weather Agent - Fetch weather forecast for the trip."""

import json
import logging
from datetime import datetime, timedelta

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseTourAgent
from agents.state import TourState

logger = logging.getLogger(__name__)

WEATHER_SYSTEM = """You are a weather forecast assistant.

Given a city and date range, provide a weather forecast with activity suggestions.

Output format (JSON array, one per day):
```json
[
  {{
    "date": "2024-01-15",
    "temperature_high": 15,
    "temperature_low": 5,
    "condition": "晴",
    "humidity": 40,
    "wind_speed": 10,
    "suggestion": "适合户外活动，建议穿外套"
  }}
]
```

Weather conditions: 晴, 多云, 阴, 小雨, 中雨, 大雨, 雪, 雾"""


class WeatherAgent(BaseTourAgent):
    """Agent that fetches weather forecast."""
    
    @property
    def name(self) -> str:
        return "WeatherAgent"
    
    @property
    def description(self) -> str:
        return "Fetch weather forecast for the trip"
    
    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", WEATHER_SYSTEM),
            ("human", "{context}"),
        ])
    
    async def execute(self, state: TourState) -> dict:
        """Fetch weather forecast."""
        intent = state.get("trip_intent", {})
        city = intent.get("city", state.get("city", ""))
        days = intent.get("days", 3)
        
        if not city:
            return {"weather": []}
        
        # Generate date range
        start_date = datetime.now() + timedelta(days=1)
        dates = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        
        context = "City: " + city + "\nDate range: " + dates[0] + " to " + dates[-1] + " (" + str(days) + " days)\n\nPlease provide weather forecast."
        
        runnable = self.get_runnable()
        response = await runnable.ainvoke({"context": context})
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            weather_data = json.loads(content.strip())
            logger.info("Got weather forecast for " + str(days) + " days")
            return {"weather": weather_data}
        
        except Exception as e:
            logger.error("Failed to parse weather: " + str(e))
            fallback = [
                {
                    "date": d,
                    "temperature_high": 25,
                    "temperature_low": 15,
                    "condition": "多云",
                    "humidity": 50,
                    "wind_speed": 10,
                    "suggestion": "适合出行"
                }
                for d in dates
            ]
            return {"weather": fallback}
