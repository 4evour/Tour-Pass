"""Scheduler for pre-generating hot itineraries."""
from __future__ import annotations
import asyncio
import logging
import os

from .config import HOT_CITIES, HOT_DAY_OPTIONS, HOT_PREFERENCES
from .graph import run_planning_pipeline
from . import cache

logger = logging.getLogger(__name__)


async def generate_hot_itinerary(city: str, days: int, preference: str) -> dict | None:
    """Generate a single hot itinerary and store it."""
    preference_map = {
        "balanced": f"去{city}玩{days}天，标准节奏，综合体验",
        "culture": f"去{city}玩{days}天，重点看历史文化景点和博物馆",
        "food": f"去{city}玩{days}天，重点体验当地美食和小吃",
        "nature": f"去{city}玩{days}天，重点看自然风光和户外景点",
    }
    message = preference_map.get(preference, f"去{city}玩{days}天")

    logger.info(f"Generating hot itinerary: {city} {days}d {preference}")

    itinerary = None
    async for event in run_planning_pipeline(message):
        if event.get("type") in ("itinerary_complete", "cache_hit"):
            itinerary = event.get("itinerary")
            break

    if itinerary:
        cache.store_hot_itinerary(city, days, preference, itinerary)
        logger.info(f"Stored hot itinerary: {city} {days}d {preference}")

    return itinerary


async def generate_all_hot_itineraries():
    """Generate hot itineraries for all configured combinations."""
    total = len(HOT_CITIES) * len(HOT_DAY_OPTIONS) * len(HOT_PREFERENCES)
    logger.info(f"Starting hot itinerary generation: {total} combinations")

    generated = 0
    failed = 0

    for city in HOT_CITIES:
        for days in HOT_DAY_OPTIONS:
            for pref in HOT_PREFERENCES:
                try:
                    result = await generate_hot_itinerary(city, days, pref)
                    if result:
                        generated += 1
                    else:
                        failed += 1
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Failed: {city} {days}d {pref}: {e}")
                    failed += 1

    logger.info(f"Hot itinerary generation complete: {generated} generated, {failed} failed")
    return {"generated": generated, "failed": failed}


async def run_scheduler():
    """Run hot itinerary generation periodically."""
    while True:
        try:
            logger.info("Scheduler: starting hot itinerary generation cycle")
            await generate_all_hot_itineraries()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")

        # Wait 24 hours before next cycle
        await asyncio.sleep(86400)


def has_city_data(city: str) -> bool:
    """Check if we have local data for a city."""
    return os.path.isdir(os.path.join("data", city))
