"""Hotel price provider boundary.

Real hotel prices require an authorized supplier API (for example a hotel
affiliate/demand API). This module keeps the planning pipeline ready for that
integration while staying inert when no provider is configured.
"""

from __future__ import annotations

import logging
import os
from typing import Mapping

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 8


def get_config_status(env: Mapping[str, str] | None = None) -> dict:
    """Return non-secret hotel price provider configuration status."""
    source = env if env is not None else os.environ
    provider = source.get("HOTEL_PRICE_PROVIDER", "").strip().lower()
    endpoint = source.get("HOTEL_PRICE_ENDPOINT", "").strip()
    api_key = source.get("HOTEL_PRICE_API_KEY", "").strip()

    if not provider and not endpoint:
        return {
            "provider": "unconfigured",
            "available": False,
            "requires": ["HOTEL_PRICE_PROVIDER", "HOTEL_PRICE_ENDPOINT", "HOTEL_PRICE_API_KEY"],
        }

    return {
        "provider": provider or "custom",
        "available": bool(endpoint and api_key),
        "requires": [] if endpoint and api_key else ["HOTEL_PRICE_ENDPOINT", "HOTEL_PRICE_API_KEY"],
    }


async def fetch_hotel_prices(
    city: str,
    hotels: list[dict],
    *,
    check_in: str = "",
    check_out: str = "",
    env: Mapping[str, str] | None = None,
) -> dict:
    """Fetch hotel price quotes from a configured HTTP provider.

    The endpoint contract is intentionally simple for future adapters:
    POST {city, hotels:[{id,name,area}], check_in, check_out}
    → {prices:[{hotel_id?, hotel_name?, price_per_night, currency, provider}]}
    """
    source = env if env is not None else os.environ
    status = get_config_status(source)
    if not status["available"]:
        return {"status": "unavailable", "provider": status["provider"], "prices": []}

    endpoint = source["HOTEL_PRICE_ENDPOINT"].strip()
    api_key = source["HOTEL_PRICE_API_KEY"].strip()
    provider = status["provider"]

    try:
        import httpx

        payload = {
            "city": city,
            "hotels": [
                {"id": h.get("id", ""), "name": h.get("name", ""), "area": h.get("area", "")}
                for h in hotels
            ],
            "check_in": check_in,
            "check_out": check_out,
        }
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("Hotel price provider request failed: %s", exc)
        return {"status": "error", "provider": provider, "prices": []}

    prices = data.get("prices", []) if isinstance(data, dict) else []
    return {"status": "ok", "provider": provider, "prices": prices if isinstance(prices, list) else []}


def merge_price_quotes(hotels: list[dict], prices: list[dict]) -> list[dict]:
    """Return hotels with matching external price quotes merged in."""
    by_id = {
        str(item.get("hotel_id")): item
        for item in prices
        if item.get("hotel_id")
    }
    by_name = {
        str(item.get("hotel_name")): item
        for item in prices
        if item.get("hotel_name")
    }

    merged: list[dict] = []
    for hotel in hotels:
        quote = by_id.get(str(hotel.get("id"))) or by_name.get(str(hotel.get("name")))
        if not quote:
            merged.append(hotel)
            continue

        enriched = dict(hotel)
        try:
            price = int(float(quote.get("price_per_night") or 0))
        except (TypeError, ValueError):
            price = 0

        if price > 0:
            enriched["price_per_night"] = price
            enriched["price_range"] = f"约{price}元/晚"
        enriched["price_currency"] = quote.get("currency", "CNY")
        enriched["price_provider"] = quote.get("provider", "external")
        merged.append(enriched)

    return merged
