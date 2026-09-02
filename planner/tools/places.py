"""POI recall and deterministic entity resolution."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agents.constants import resolve_city_dir
from planner.models import OpenWindow, PlaceEvidence, PlaceQuery

from .amap import AmapClient

_TRAVEL_TYPE_TERMS = (
    "风景名胜",
    "博物馆",
    "美术馆",
    "公园",
    "海滨浴场",
    "特色商业街",
    "体育休闲",
    "学校",
    "热点地名",
    "教堂",
    "寺庙",
)
_LOW_VALUE_TERMS = ("停车场", "洗手间", "厕所", "售票处", "出入口", "入口", "办公室")
_SUFFIXES = (
    "风景名胜区",
    "风景区",
    "景区",
    "旅游区",
    "公园",
    "博物馆",
    "博物院",
    "文创园",
    "文创街区",
)


def normalize_place_name(value: str) -> str:
    text = re.sub(r"[\s·•（）()\-—_，,。.]", "", value or "").lower()
    text = text.replace("博物院", "博物馆").replace("park", "公园")
    for suffix in _SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            text = text[: -len(suffix)]
            break
    return text


def _parse_location(raw: object) -> tuple[float, float] | None:
    try:
        lng_text, lat_text = str(raw).split(",", 1)
        lng, lat = float(lng_text), float(lat_text)
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    except (TypeError, ValueError):
        return None
    return None


def _parse_hours(raw: object) -> list[OpenWindow]:
    text = str(raw or "")
    match = re.search(r"(\d{1,2}:\d{2})\s*[-–—至]\s*(\d{1,2}:\d{2})", text)
    if not match:
        return []
    return [OpenWindow(start=match.group(1).zfill(5), end=match.group(2).zfill(5))]


def _category_for(raw_type: str, role: str) -> str:
    if role and role not in {"must_visit", "attraction"}:
        return role
    if "博物馆" in raw_type:
        return "museum"
    if "美术馆" in raw_type:
        return "gallery"
    if "海滨浴场" in raw_type or "海滩" in raw_type:
        return "beach"
    if "学校" in raw_type:
        return "campus"
    if "特色商业街" in raw_type or "热点地名" in raw_type:
        return "urban_walk"
    if "住宅" in raw_type:
        return "neighborhood"
    if "餐饮" in raw_type:
        return "restaurant"
    return "attraction"


class LocalPlaceStore:
    def __init__(
        self,
        data_dir: str | Path = "data",
        aliases_path: str | Path = "tests/fixtures/grounded-planner/core_places.json",
    ) -> None:
        self.data_dir = Path(data_dir)
        self.aliases_path = Path(aliases_path)
        self._cache: dict[str, list[dict]] = {}
        self._aliases = self._load_aliases()

    def _load_aliases(self) -> dict[str, dict[str, str]]:
        if not self.aliases_path.exists():
            return {}
        try:
            data = json.loads(self.aliases_path.read_text(encoding="utf-8"))
            result: dict[str, dict[str, str]] = {}
            for city, entries in data.get("cities", {}).items():
                result[city] = {}
                for entry in entries:
                    canonical = entry.get("canonical_name", "")
                    for alias in [canonical, *entry.get("aliases", [])]:
                        if alias:
                            result[city][normalize_place_name(alias)] = canonical
            return result
        except Exception:
            return {}

    def load(self, city: str) -> list[dict]:
        city_dir = resolve_city_dir(self.data_dir, city)
        key = city_dir.name
        if key not in self._cache:
            path = city_dir / "pois.json"
            if not path.exists():
                self._cache[key] = []
            else:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._cache[key] = data if isinstance(data, list) else []
        return self._cache[key]

    def search(
        self, city: str, query: str, role: str, limit: int = 8
    ) -> list[tuple[float, dict]]:
        query_norm = normalize_place_name(query)
        canonical = self._aliases.get(
            resolve_city_dir(self.data_dir, city).name, {}
        ).get(query_norm, "")
        canonical_norm = normalize_place_name(canonical)
        ranked: list[tuple[float, dict]] = []
        for item in self.load(city):
            name = str(item.get("name", ""))
            name_norm = normalize_place_name(name)
            score = 0.0
            if canonical_norm and name_norm == canonical_norm:
                score = 1.0
            elif name == query:
                score = 1.0
            elif name_norm == query_norm:
                score = 0.96
            elif query_norm and (query_norm in name_norm or name_norm in query_norm):
                score = 0.78
            elif query_norm and query_norm in normalize_place_name(
                " ".join(item.get("tags", []))
            ):
                score = 0.55
            if role == "restaurant" and item.get("type") != "restaurant":
                score -= 0.3
            elif role != "restaurant" and item.get("type") in {"hotel", "transit"}:
                score -= 0.5
            if score > 0.35:
                ranked.append((score, item))
        ranked.sort(
            key=lambda pair: (pair[0], float(pair[1].get("popularity", 0) or 0)),
            reverse=True,
        )
        return ranked[:limit]

    def select_hotel(self, city: str, name: str = "", area: str = "") -> dict | None:
        hotels = [item for item in self.load(city) if item.get("type") == "hotel"]
        if name:
            matches = self.search(city, name, "hotel", 5)
            hotel_matches = [item for _, item in matches if item.get("type") == "hotel"]
            if hotel_matches:
                return hotel_matches[0]
        if area:
            area_hotels = [
                item
                for item in hotels
                if area in str(item.get("area", ""))
                or area in str(item.get("name", ""))
            ]
            if area_hotels:
                hotels = area_hotels
        return max(
            hotels, key=lambda item: float(item.get("popularity", 0) or 0), default=None
        )


class PlaceResolver:
    def __init__(self, local: LocalPlaceStore, amap: AmapClient) -> None:
        self.local = local
        self.amap = amap

    @staticmethod
    def _online_score(query: str, raw: dict, role: str) -> float:
        name = str(raw.get("name", ""))
        name_norm = normalize_place_name(name)
        query_norm = normalize_place_name(query)
        score = 0.0
        if name == query:
            score += 1.0
        elif name_norm == query_norm:
            score += 0.95
        elif query_norm and (query_norm in name_norm or name_norm in query_norm):
            score += 0.65
        raw_type = str(raw.get("type", ""))
        if any(term in raw_type for term in _TRAVEL_TYPE_TERMS):
            score += 0.15
        if role == "restaurant" and "餐饮" in raw_type:
            score += 0.2
        if any(term in name for term in _LOW_VALUE_TERMS):
            score -= 0.6
        return score

    async def resolve(self, city: str, place_query: PlaceQuery) -> PlaceEvidence | None:
        local_matches = self.local.search(city, place_query.query, place_query.role)
        best_local = local_matches[0] if local_matches else None
        online_matches: list[dict] = []
        if self.amap.available and (
            place_query.required or not best_local or best_local[0] < 0.94
        ):
            try:
                online_matches = await self.amap.search_text(city, place_query.query)
            except Exception:
                online_matches = []

        best_online = max(
            online_matches,
            key=lambda raw: self._online_score(
                place_query.query, raw, place_query.role
            ),
            default=None,
        )
        online_score = (
            self._online_score(place_query.query, best_online, place_query.role)
            if best_online
            else 0.0
        )

        if (
            best_online
            and online_score >= 0.72
            and (not best_local or online_score >= best_local[0])
        ):
            evidence = self._from_amap(place_query, best_online, online_score)
            detail = None
            try:
                detail = await self.amap.place_detail(evidence.source_id)
            except Exception:
                pass
            if detail:
                evidence = self._from_amap(
                    place_query, detail, min(1.0, online_score + 0.08)
                )
            return (
                evidence
                if evidence.status != "closed" or place_query.required
                else None
            )

        if best_local:
            score, item = best_local
            evidence = self._from_local(place_query, item, score)
            if self.amap.available and item.get("source_id") and place_query.required:
                try:
                    detail = await self.amap.place_detail(str(item["source_id"]))
                    if detail:
                        confirmed = self._from_amap(
                            place_query, detail, max(score, 0.97), local_item=item
                        )
                        return (
                            confirmed
                            if confirmed.status != "closed" or place_query.required
                            else None
                        )
                except Exception:
                    evidence.warnings.append("高德详情复核失败，使用本地实体缓存")
            return (
                evidence
                if evidence.status != "closed" or place_query.required
                else None
            )
        return None

    def _from_local(
        self, query: PlaceQuery, item: dict, confidence: float
    ) -> PlaceEvidence:
        now = datetime.now(UTC)
        source_id = str(item.get("source_id", ""))
        entity_id = f"amap:{source_id}" if source_id else f"local:{item.get('id', '')}"
        is_closed = any(
            term in str(item.get("name", ""))
            for term in ("暂停开放", "暂停营业", "已关闭")
        )
        return PlaceEvidence(
            query=query.query,
            entity_id=entity_id,
            local_id=str(item.get("id", "")),
            source_id=source_id,
            canonical_name=str(item.get("name", query.query)),
            aliases=[query.query] if query.query != item.get("name") else [],
            category=_category_for(" ".join(item.get("tags", [])), query.role),
            role=query.role,
            lat=float(item.get("lat", 0)),
            lng=float(item.get("lng", 0)),
            area=str(item.get("area", "")),
            status="closed" if is_closed else "resolved",
            open_status="closed" if is_closed else "unknown",
            open_windows=[],
            visit_duration_minutes=int(item.get("visit_duration_minutes", 90) or 90),
            popularity=float(item.get("popularity", 0) or 0),
            tags=[str(tag) for tag in item.get("tags", [])],
            provider="local_cache",
            retrieved_at=now,
            valid_until=None,
            confidence=min(confidence, 0.9),
            warnings=["地点名称标记为暂停开放或已关闭"]
            if is_closed
            else ["本地开放时间为默认值，未作为开放硬证据"],
            image_url=str(item.get("image_url", "")),
        )

    def _from_amap(
        self,
        query: PlaceQuery,
        raw: dict,
        confidence: float,
        local_item: dict | None = None,
    ) -> PlaceEvidence:
        location = _parse_location(raw.get("location"))
        if not location and local_item:
            location = (
                float(local_item.get("lat", 0)),
                float(local_item.get("lng", 0)),
            )
        if not location:
            raise ValueError("AMap place has no valid location")
        now = datetime.now(UTC)
        business = raw.get("business") if isinstance(raw.get("business"), dict) else {}
        biz_ext = raw.get("biz_ext") if isinstance(raw.get("biz_ext"), dict) else {}
        hours = _parse_hours(
            business.get("opentime_week")
            or business.get("opentime_today")
            or biz_ext.get("opentime2")
            or biz_ext.get("open_time")
            or raw.get("opentime")
        )
        source_id = str(raw.get("id") or (local_item or {}).get("source_id", ""))
        raw_type = str(raw.get("type", ""))
        canonical_name = str(
            raw.get("name") or (local_item or {}).get("name") or query.query
        )
        is_closed = any(
            term in canonical_name for term in ("暂停开放", "暂停营业", "已关闭")
        )
        warnings = (
            ["地点名称标记为暂停开放或已关闭"]
            if is_closed
            else ([] if hours else ["未取得日期化开放时间"])
        )
        return PlaceEvidence(
            query=query.query,
            entity_id=f"amap:{source_id}",
            local_id=str((local_item or {}).get("id", "")),
            source_id=source_id,
            canonical_name=canonical_name,
            aliases=[query.query] if query.query != raw.get("name") else [],
            category=_category_for(raw_type, query.role),
            role=query.role,
            lat=location[0],
            lng=location[1],
            area=str(
                raw.get("adname")
                or raw.get("business_area")
                or (local_item or {}).get("area", "")
            ),
            status="closed" if is_closed else "resolved",
            open_status="closed" if is_closed else ("verified" if hours else "unknown"),
            open_windows=[] if is_closed else hours,
            visit_duration_minutes=int(
                (local_item or {}).get("visit_duration_minutes", 90) or 90
            ),
            popularity=float((local_item or {}).get("popularity", 0) or 0),
            tags=[part for part in re.split(r"[|;]", raw_type) if part],
            provider="amap",
            retrieved_at=now,
            valid_until=now + timedelta(days=7 if hours else 30),
            confidence=min(confidence, 1.0),
            warnings=warnings,
            image_url=str((local_item or {}).get("image_url", "")),
        )
