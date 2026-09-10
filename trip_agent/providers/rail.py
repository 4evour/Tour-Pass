"""Minimal read-only 12306 timetable adapter.

The request flow follows the publicly inspectable web client patterns used by
Joooook/12306-mcp (MIT). It intentionally excludes login, passenger, order,
seat inventory, and booking operations.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx

from ..cache import ProviderCache

_API_BASE = "https://kyfw.12306.cn"
_WEB_URL = "https://www.12306.cn/index/"
_TICKET_INIT_URL = f"{_API_BASE}/otn/leftTicket/init"
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_STATION_SCRIPT = re.compile(
    r"""["'](\.?/script/core/common/station_name[^"']+?\.js)["']"""
)
_QUERY_PATH = re.compile(r"var CLeftTicketUrl = '([^']+)'")
_SEAT_NAMES = {
    "9": "商务座",
    "P": "特等座",
    "M": "一等座",
    "D": "优选一等座",
    "O": "二等座",
    "S": "二等包座",
    "6": "高级软卧",
    "A": "高级动卧",
    "4": "软卧",
    "I": "一等卧",
    "F": "动卧",
    "3": "硬卧",
    "J": "二等卧",
    "2": "软座",
    "1": "硬座",
    "W": "无座",
    "H": "其他",
}
_SEAT_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "二等座",
            "硬座",
            "软座",
            "一等座",
            "软卧",
            "硬卧",
            "无座",
            "商务座",
            "特等座",
            "其他",
        )
    )
}


def _duration_minutes(value: str) -> int:
    try:
        hours, minutes = value.split(":", 1)
        return int(hours) * 60 + int(minutes)
    except (AttributeError, TypeError, ValueError):
        return 0


def _service_datetime(service_date: str, departure_time: str) -> datetime:
    if departure_time == "24:00":
        return datetime.strptime(service_date, "%Y%m%d") + timedelta(days=1)
    return datetime.strptime(
        f"{service_date} {departure_time}",
        "%Y%m%d %H:%M",
    )


def _parse_prices(value: str) -> list[dict[str, Any]]:
    prices: dict[str, dict[str, Any]] = {}
    for offset in range(0, len(value), 10):
        chunk = value[offset : offset + 10]
        if len(chunk) != 10 or not chunk[1:6].isdigit():
            continue
        code = chunk[0]
        if chunk[6:10].isdigit() and int(chunk[6:10]) >= 3000:
            code = "W"
        name = _SEAT_NAMES.get(code, "其他")
        price = int(chunk[1:6]) / 10
        if price <= 0:
            continue
        current = prices.get(name)
        if current is None or price < current["amount"]:
            prices[name] = {
                "seat_type": name,
                "seat_code": code,
                "amount": price,
                "currency": "CNY",
            }
    return sorted(
        prices.values(),
        key=lambda item: (_SEAT_ORDER.get(item["seat_type"], 99), item["amount"]),
    )


def _parse_station_script(value: str) -> dict[str, dict[str, str]]:
    start = value.find("@")
    if start < 0:
        raise RuntimeError("12306 station data is unavailable")
    names: dict[str, str] = {}
    cities: dict[str, str] = {}
    code_to_name: dict[str, str] = {}
    for raw in value[start + 1 :].split("@"):
        fields = raw.split("|")
        if len(fields) < 8:
            continue
        name, code, city = fields[1].strip(), fields[2].strip(), fields[7].strip()
        if not name or not code:
            continue
        names[name] = code
        names[f"{name}站"] = code
        code_to_name[code] = name
        if city and name == city:
            cities[city] = code
    return {"names": names, "cities": cities, "code_to_name": code_to_name}


def _station_code(value: str, stations: dict[str, dict[str, str]]) -> str | None:
    clean = "".join(str(value or "").split())
    if re.fullmatch(r"[A-Z]{3}", clean):
        return clean
    without_suffix = clean[:-1] if clean.endswith("站") else clean
    return (
        stations["names"].get(clean)
        or stations["names"].get(without_suffix)
        or stations["cities"].get(without_suffix)
    )


def _departure_score(
    value: str, preferred: str | None, duration: int
) -> tuple[int, int, str]:
    target = _duration_minutes(preferred or "09:00")
    departure = _duration_minutes(value)
    return abs(departure - target), duration, value


class Rail12306Provider:
    """Low-volume, anonymous timetable and fare lookup against the 12306 web API."""

    def __init__(self, cache: ProviderCache | None = None) -> None:
        self.cache = cache or ProviderCache()
        self.enabled = os.environ.get(
            "TRIP_AGENT_RAIL_ENABLED", "true"
        ).lower() not in {
            "0",
            "false",
            "no",
        }
        self.timeout = max(
            3.0,
            min(float(os.environ.get("TRIP_AGENT_RAIL_TIMEOUT_SECONDS", "10")), 20.0),
        )
        self.min_interval = max(
            0.5,
            float(os.environ.get("TRIP_AGENT_RAIL_MIN_INTERVAL_SECONDS", "1")),
        )
        self.cache_ttl = max(
            300, int(os.environ.get("TRIP_AGENT_RAIL_CACHE_TTL_SECONDS", "21600"))
        )
        self._client: httpx.AsyncClient | None = None
        self._rate_lock = asyncio.Lock()
        self._last_request = 0.0
        self._stations: dict[str, dict[str, str]] | None = None
        self._query_path: str | None = None

    @property
    def available(self) -> bool:
        return self.enabled

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 TourPass/0.2 read-only timetable",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Referer": _TICKET_INIT_URL,
                },
            )
        return self._client

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        async with self._rate_lock:
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()
        response = await self._http().get(url, **kwargs)
        response.raise_for_status()
        return response

    async def _load_stations(self) -> dict[str, dict[str, str]]:
        if self._stations is not None:
            return self._stations
        request: dict[str, Any] = {}
        cached = self.cache.get("rail12306", "stations", request)
        if cached:
            self._stations = cached["response"]
            return self._stations
        homepage = (await self._get(_WEB_URL)).text
        match = _STATION_SCRIPT.search(homepage)
        if match is None:
            raise RuntimeError("12306 station script path was not found")
        station_script = (await self._get(urljoin(_WEB_URL, match.group(1)))).text
        stations = _parse_station_script(station_script)
        self.cache.put(
            "rail12306",
            "stations",
            request,
            stations,
            ttl_seconds=30 * 86400,
            latency_ms=0,
        )
        self._stations = stations
        return stations

    async def _load_query_path(self, *, refresh: bool = False) -> str:
        if self._query_path and not refresh:
            return self._query_path
        html = (await self._get(_TICKET_INIT_URL)).text
        match = _QUERY_PATH.search(html)
        if match is None:
            raise RuntimeError("12306 ticket query path was not found")
        self._query_path = match.group(1)
        return self._query_path

    @staticmethod
    def _with_record_metadata(record: dict[str, Any]) -> dict[str, Any]:
        fetched = datetime.fromtimestamp(record["fetched_at"], tz=_SHANGHAI).isoformat()
        return {
            **record["response"],
            "cache_hit": bool(record.get("cache_hit")),
            "stale": bool(record.get("stale")),
            "fetched_at": fetched,
            "response_hash": record.get("response_hash", ""),
        }

    async def search_trains(
        self,
        *,
        travel_date: str,
        from_station: str,
        to_station: str,
        preferred_departure: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        if not self.available:
            return {"provider": "rail12306", "available": False, "trains": []}
        parsed_date = date.fromisoformat(travel_date)
        if parsed_date < datetime.now(_SHANGHAI).date():
            raise ValueError("12306 only supports current or future travel dates")
        stations = await self._load_stations()
        from_code = _station_code(from_station, stations)
        to_code = _station_code(to_station, stations)
        if from_code is None or to_code is None:
            raise ValueError(f"Unknown railway station: {from_station} -> {to_station}")
        request = {
            "parser_version": 2,
            "travel_date": parsed_date.isoformat(),
            "from_code": from_code,
            "to_code": to_code,
            "preferred_departure": preferred_departure or "",
            "limit": min(max(int(limit), 1), 10),
        }
        cached = self.cache.get("rail12306", "search_trains", request)
        if cached:
            return self._with_record_metadata(cached)
        stale = self.cache.get_stale("rail12306", "search_trains", request)
        started = time.perf_counter()
        try:
            query_path = await self._load_query_path()
            response = await self._get(
                f"{_API_BASE}/otn/{query_path}",
                params={
                    "leftTicketDTO.train_date": parsed_date.isoformat(),
                    "leftTicketDTO.from_station": from_code,
                    "leftTicketDTO.to_station": to_code,
                    "purpose_codes": "ADULT",
                },
            )
            body = response.json()
            data = body.get("data") if isinstance(body, dict) else None
            if not body.get("status") or not isinstance(data, dict):
                raise RuntimeError("12306 returned an unsuccessful timetable response")
            station_map = data.get("map") if isinstance(data.get("map"), dict) else {}
            trains: list[dict[str, Any]] = []
            for raw in data.get("result") or []:
                values = raw.split("|")
                if len(values) <= 39:
                    continue
                duration = _duration_minutes(values[10])
                if (
                    not values[3]
                    or duration <= 0
                    or values[6] != from_code
                    or values[7] != to_code
                ):
                    continue
                start = _service_datetime(parsed_date.strftime("%Y%m%d"), values[8])
                arrival_date = (start + timedelta(minutes=duration)).date().isoformat()
                prices = _parse_prices(values[39])
                preferred_price = prices[0] if prices else None
                trains.append(
                    {
                        "train_code": values[3],
                        "from_station": station_map.get(values[6])
                        or stations["code_to_name"].get(values[6], from_station),
                        "to_station": station_map.get(values[7])
                        or stations["code_to_name"].get(values[7], to_station),
                        "departure_time": values[8],
                        "arrival_time": values[9],
                        "arrival_date": arrival_date,
                        "duration_minutes": duration,
                        "price": preferred_price,
                        "prices": prices,
                    }
                )
            trains.sort(
                key=lambda item: _departure_score(
                    item["departure_time"],
                    preferred_departure,
                    item["duration_minutes"],
                )
            )
            normalized = {
                "provider": "rail12306",
                "available": True,
                "query_date": parsed_date.isoformat(),
                "from": from_station,
                "to": to_station,
                "source_url": _WEB_URL,
                "trains": trains[: request["limit"]],
            }
            record = self.cache.put(
                "rail12306",
                "search_trains",
                request,
                normalized,
                ttl_seconds=self.cache_ttl,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
            return self._with_record_metadata(record)
        except Exception:
            if stale is not None:
                return self._with_record_metadata(stale)
            raise
