"""Weather provider chain: QWeather (和风天气) then AMap fallback."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from planner.models import WeatherDay
from tools import weather_api

from .amap import AmapClient


def _suggest(
    condition: str, temperature_high: int | None, uv_index: int, warnings: list[dict]
) -> str:
    parts: list[str] = []
    if warnings:
        parts.append("注意当前灾害预警")
    if any(term in condition for term in ("雨", "雪", "雹")):
        parts.append("优先安排室内活动并携带雨具")
    if temperature_high is not None and temperature_high >= 35:
        parts.append("避开午后暴晒并注意补水")
    if uv_index >= 4:
        parts.append("注意防晒")
    return "，".join(parts) + "。" if parts else "天气条件对基础行程无明显限制。"


class WeatherProvider:
    def __init__(self, amap: AmapClient) -> None:
        self.amap = amap

    async def get(self, city: str, start_date: date, days: int) -> list[WeatherDay]:
        forecast, indices, warnings = await asyncio.gather(
            weather_api.fetch_weather(city, days),
            weather_api.fetch_weather_indices(city, days),
            weather_api.fetch_weather_warnings(city),
            return_exceptions=True,
        )
        if isinstance(forecast, Exception):
            forecast = []
        if isinstance(indices, Exception):
            indices = {}
        if isinstance(warnings, Exception):
            warnings = []
        if forecast:
            result: list[WeatherDay] = []
            for item in forecast:
                item_date = str(item.get("date", ""))
                day_indices = (
                    indices.get(item_date, {}) if isinstance(indices, dict) else {}
                )
                uv_detail = (
                    day_indices.get("uv_index_detail", {})
                    if isinstance(day_indices, dict)
                    else {}
                )
                uv_index = int(
                    item.get("uv_index", 0) or uv_detail.get("level", 0) or 0
                )
                result.append(
                    WeatherDay(
                        date=item_date,
                        condition=str(item.get("condition", "")),
                        condition_night=str(item.get("condition_night", "")),
                        temperature_high=item.get("temperature_high"),
                        temperature_low=item.get("temperature_low"),
                        humidity=item.get("humidity"),
                        sunrise=str(item.get("sunrise", "")),
                        sunset=str(item.get("sunset", "")),
                        uv_index=uv_index,
                        precip=float(item.get("precip", 0) or 0),
                        suggestion=_suggest(
                            str(item.get("condition", "")),
                            item.get("temperature_high"),
                            uv_index,
                            warnings,
                        ),
                        warnings=warnings,
                        provider="qweather",
                    )
                )
            return result[:days]

        if self.amap.available:
            try:
                casts = await self.amap.weather(city)
            except Exception:
                casts = []
            result = []
            for item in casts[:days]:
                high = (
                    int(item["daytemp"])
                    if str(item.get("daytemp", "")).lstrip("-").isdigit()
                    else None
                )
                low = (
                    int(item["nighttemp"])
                    if str(item.get("nighttemp", "")).lstrip("-").isdigit()
                    else None
                )
                condition = str(item.get("dayweather", ""))
                result.append(
                    WeatherDay(
                        date=str(item.get("date", "")),
                        condition=condition,
                        condition_night=str(item.get("nightweather", "")),
                        temperature_high=high,
                        temperature_low=low,
                        suggestion=_suggest(condition, high, 0, []),
                        provider="amap",
                    )
                )
            if result:
                return result

        return [
            WeatherDay(
                date=(start_date + timedelta(days=index)).isoformat(),
                suggestion="天气数据暂不可用，请在出发前复核。",
                provider="unavailable",
            )
            for index in range(days)
        ]
