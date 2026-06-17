"""Itinerary-level cache using Redis (optional) and in-memory fallback.

Migrated from agent/cache.py — only import path changed to agents.config.
"""
from __future__ import annotations
import hashlib
import json
import logging
import time
from typing import Optional

from agents.config import REDIS_URL, CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)

# ── In-memory cache (always available, no Redis dependency) ───────────────────

_memory_cache: dict[str, tuple[float, dict]] = {}
_memory_max = 500


def _cache_key(city: str, days: int, pace: str, strategy: str, must_visit: list[str]) -> str:
    """Generate cache key from trip parameters."""
    must_sorted = sorted(must_visit)
    raw = f"{city}:{days}:{pace}:{strategy}:{'|'.join(must_sorted)}"
    return hashlib.md5(raw.encode()).hexdigest()


def _memory_get(key: str) -> Optional[dict]:
    if key in _memory_cache:
        ts, data = _memory_cache[key]
        if time.time() - ts < CACHE_TTL_SECONDS:
            return data
        del _memory_cache[key]
    return None


def _memory_set(key: str, data: dict):
    global _memory_cache
    if len(_memory_cache) >= _memory_max:
        # Evict oldest
        oldest = min(_memory_cache, key=lambda k: _memory_cache[k][0])
        del _memory_cache[oldest]
    _memory_cache[key] = (time.time(), data)


# ── Redis cache (optional, for multi-instance deployments) ────────────────────

_redis_client = None
_redis_available = False


def _get_redis():
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client if _redis_available else None

    try:
        import redis
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        _redis_available = True
        logger.info("Redis connected for cache")
        return _redis_client
    except Exception as e:
        logger.info("Redis not available (%s), using in-memory cache only", e)
        _redis_available = False
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def get_cached_itinerary(
    city: str, days: int, pace: str, strategy: str, must_visit: list[str],
) -> Optional[dict]:
    """Get cached itinerary. Returns None if not found."""
    key = _cache_key(city, days, pace, strategy, must_visit)

    # Try memory first
    result = _memory_get(key)
    if result is not None:
        return result

    # Try Redis
    r = _get_redis()
    if r:
        try:
            raw = r.get(f"itinerary:{key}")
            if raw:
                data = json.loads(raw)
                _memory_set(key, data)
                return data
        except Exception as e:
            logger.warning("Redis get failed: %s", e)

    return None


def set_cached_itinerary(
    city: str, days: int, pace: str, strategy: str, must_visit: list[str],
    itinerary: dict,
):
    """Store itinerary in cache."""
    key = _cache_key(city, days, pace, strategy, must_visit)

    _memory_set(key, itinerary)

    r = _get_redis()
    if r:
        try:
            r.setex(f"itinerary:{key}", CACHE_TTL_SECONDS, json.dumps(itinerary, ensure_ascii=False))
        except Exception as e:
            logger.warning("Redis set failed: %s", e)


# ── Hot itineraries store ─────────────────────────────────────────────────────

_hot_store: dict[str, dict] = {}  # key -> itinerary dict


def store_hot_itinerary(city: str, days: int, preference: str, itinerary: dict):
    """Store a pre-generated hot itinerary."""
    key = f"{city}:{days}:{preference}"
    _hot_store[key] = {
        "id": key,
        "city": city,
        "days": days,
        "preference": preference,
        "itinerary": itinerary,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hit_count": 0,
    }


def get_hot_itinerary(city: str, days: int, preference: str) -> Optional[dict]:
    """Get a hot itinerary if available."""
    key = f"{city}:{days}:{preference}"
    item = _hot_store.get(key)
    if item:
        item["hit_count"] += 1
        return item
    return None


def list_hot_itineraries(city: str = "", limit: int = 20) -> list[dict]:
    """List available hot itineraries."""
    items = list(_hot_store.values())
    if city:
        items = [i for i in items if i["city"] == city]
    items.sort(key=lambda x: x.get("hit_count", 0), reverse=True)
    return items[:limit]


def get_cache_stats() -> dict:
    """Get cache statistics."""
    r = _get_redis()
    redis_keys = 0
    if r:
        try:
            redis_keys = len(r.keys("itinerary:*"))
        except Exception:
            pass

    return {
        "memory_entries": len(_memory_cache),
        "redis_entries": redis_keys,
        "hot_itineraries": len(_hot_store),
        "redis_available": _redis_available,
    }
