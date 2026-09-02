"""Single-run Grounded Planner orchestrator."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any


from langchain_core.messages import HumanMessage, SystemMessage

from .errors import (
    EvidenceError,
    LlmBudgetExceeded,
    PlannerError,
    SkeletonError,
    SolverError,
)
from .models import (
    DailyWindow,
    HotelPreference,
    ItineraryPlan,
    PlaceEvidence,
    PlaceQuery,
    PlanSkeleton,
    PlanningResult,
    TripContext,
    ValidationIssue,
    ValidationReport,
)
from .prompts import PROMPT_VERSION, SKELETON_SYSTEM, build_skeleton_user_prompt
from .repair import drop_lowest_optional
from .tools.places import normalize_place_name
from .tools.registry import ToolRegistry
from .tools.validator import validate_itinerary
from .trace import PlanningTrace

logger = logging.getLogger(__name__)


class LlmBudget:
    def __init__(self, default_total: int = 2, absolute_total: int = 3) -> None:
        self.default_total = default_total
        self.absolute_total = absolute_total
        self.used = 0

    def consume(self, purpose: str) -> None:
        if self.used >= self.default_total:
            raise LlmBudgetExceeded(f"LLM budget exhausted before {purpose}")
        self.used += 1

    @property
    def remaining(self) -> int:
        return max(0, self.default_total - self.used)


class GroundedPlanner:
    def __init__(
        self, llm: Any, data_dir: str = "data", tools: ToolRegistry | None = None
    ) -> None:
        self.llm = llm
        self.tools = tools or ToolRegistry(data_dir=data_dir)

    async def close(self) -> None:
        await self.tools.close()

    @staticmethod
    def _optional_list(value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [
                item.strip() for item in re.split(r"[,，;；]", value) if item.strip()
            ]
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _infer_constraints(
        special_requests: str,
        hotel_area: str,
        avoid: list[str],
    ) -> tuple[dict[str, Any], str, list[str], list[str]]:
        text = special_requests.strip()
        assumptions: list[str] = []
        inferred_avoid = list(avoid)
        prefer_low_walking = bool(
            re.search(r"少走|减少步行|不想走|走路少|腿脚|带长辈", text)
        )
        reserve_lunch = 60
        if re.search(r"不需要午餐|跳过午餐", text):
            reserve_lunch = 0
        elif re.search(r"午餐|中午.{0,6}(吃饭|用餐)|正常用餐", text):
            reserve_lunch = 75
        max_stops = None
        match = re.search(
            r"每天(?:最多|不超过)?\\s*([1-8一二三四五六七八])\\s*个?(?:景点|地点|站)",
            text,
        )
        if match:
            digit_map = {
                "一": 1,
                "二": 2,
                "三": 3,
                "四": 4,
                "五": 5,
                "六": 6,
                "七": 7,
                "八": 8,
            }
            max_stops = digit_map.get(
                match.group(1),
                int(match.group(1)) if match.group(1).isdigit() else None,
            )
        if prefer_low_walking and max_stops is None:
            max_stops = 3
        if not hotel_area:
            hotel_match = re.search(
                r"(?:住|住宿|酒店)(?:在|选在|安排在)?\s*([\u4e00-\u9fffA-Za-z0-9·]{2,12}(?:区|附近|广场|商圈))",
                text,
            )
            if hotel_match:
                hotel_area = hotel_match.group(1)
        for avoid_match in re.finditer(
            r"(?:不去|避开|不要安排)\s*([^，,。；;]{2,24})", text
        ):
            value = avoid_match.group(1).strip()
            if value and value not in inferred_avoid:
                inferred_avoid.append(value)
        constraints = {
            "reserve_lunch_minutes": reserve_lunch,
            "lunch_start_minutes": 12 * 60,
            "prefer_low_walking": prefer_low_walking,
            "max_stops_per_day": max_stops,
            "freeform_requirements": [text] if text else [],
        }
        return constraints, hotel_area, inferred_avoid, assumptions

    @staticmethod
    def build_context(payload: dict[str, Any]) -> TripContext:
        assumptions: list[str] = []
        today = date.today()
        raw_date = payload.get("date_start")
        try:
            start_date = (
                date.fromisoformat(str(raw_date))
                if raw_date
                else today + timedelta(days=1)
            )
        except ValueError:
            start_date = today + timedelta(days=1)
            assumptions.append("旅行日期格式无效，暂按明天开始规划")
        if not raw_date:
            assumptions.append(
                "未填写旅行日期，暂按明天开始规划；天气和开放状态需在出发前复核"
            )

        raw_days = payload.get("days")
        try:
            days = int(raw_days) if raw_days not in (None, "") else 3
        except (TypeError, ValueError):
            days = 3
            assumptions.append("游玩天数无效，暂按3天规划")

        modes = payload.get("transport_preferences") or []
        raw_mode = payload.get("transport_mode") or (modes[0] if modes else "")
        mode_aliases = {
            "taxi": "driving",
            "drive": "driving",
            "walk": "walking",
            "metro": "transit",
            "bus": "transit",
        }
        transport_mode = mode_aliases.get(raw_mode, raw_mode)
        if transport_mode not in {"driving", "walking", "transit"}:
            transport_mode = "driving"
            assumptions.append("未指定交通方式，暂按驾车/打车路线核验")

        special_requests = str(payload.get("special_requests", "") or "")
        hotel_area = str(payload.get("hotel_area", "") or "")
        avoid = GroundedPlanner._optional_list(payload.get("avoid"))
        constraints, hotel_area, avoid, inferred_assumptions = (
            GroundedPlanner._infer_constraints(special_requests, hotel_area, avoid)
        )
        if constraints["prefer_low_walking"] and transport_mode == "walking":
            transport_mode = "driving"
            assumptions.append(
                "附加要求希望减少步行，已将步行优先调整为驾车/打车路线核验"
            )
        assumptions.extend(inferred_assumptions)
        if not payload.get("hotel_name") and not hotel_area:
            assumptions.append("未指定酒店或住宿区域，将从候选地点附近选择本地酒店锚点")
        if payload.get("budget") in (None, ""):
            assumptions.append("未指定预算，不使用价格作为硬约束")

        pace = payload.get("pace") or "balanced"
        if pace not in {"relaxed", "balanced", "intense"}:
            pace = "balanced"
            assumptions.append("未明确行程节奏，暂按标准节奏规划")
        if constraints["prefer_low_walking"] and pace == "intense":
            pace = "balanced"
            assumptions.append("附加要求希望减少步行，已将紧凑节奏降为标准节奏")

        strategy = payload.get("strategy") or "balanced"
        if strategy not in {"balanced", "culture", "culinary", "nature"}:
            strategy = "balanced"
            assumptions.append("未明确旅游侧重，暂按均衡方案规划")

        return TripContext(
            request_id=payload.get("request_id") or uuid.uuid4().hex,
            planning_run_id=payload.get("planning_run_id") or uuid.uuid4().hex,
            city=str(payload.get("city", "")).strip(),
            date_start=start_date,
            days=days,
            daily_window=DailyWindow(
                start=payload.get("daily_start")
                or payload.get("start_time")
                or "09:00",
                end=payload.get("daily_end") or payload.get("end_time") or "21:30",
            ),
            hotel=HotelPreference(
                name=str(payload.get("hotel_name", "") or ""),
                area=hotel_area,
                required_anchor=True,
            ),
            travelers=str(payload.get("travelers") or "unspecified"),
            pace=pace,
            strategy=strategy,
            interests=GroundedPlanner._optional_list(payload.get("interests")),
            must_visit=list(
                dict.fromkeys(GroundedPlanner._optional_list(payload.get("must_visit")))
            ),
            avoid=list(dict.fromkeys(avoid)),
            budget_level=payload.get("budget") or None,
            transport_mode=transport_mode,
            special_requests=special_requests,
            constraints=constraints,
            assumptions=list(dict.fromkeys(assumptions)),
        )

    async def _invoke_json(
        self, system: str, user: str, budget: LlmBudget, purpose: str
    ) -> dict:
        budget.consume(purpose)
        response = await self.llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        text = response.content if hasattr(response, "content") else str(response)
        if isinstance(text, list):
            text = "".join(
                str(part.get("text", "") if isinstance(part, dict) else part)
                for part in text
            )
        text = str(text).strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        if not text.startswith("{"):
            match = re.search(r"\{.*\}", text, re.S)
            if match:
                text = match.group(0)
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise SkeletonError("LLM skeleton response must be an object")
        return parsed

    @staticmethod
    def _missing_must_visit(ctx: TripContext, skeleton: PlanSkeleton) -> list[str]:
        queries = [
            normalize_place_name(query.query)
            for day in skeleton.days
            for query in day.place_queries
        ]
        return [
            item
            for item in ctx.must_visit
            if not any(
                normalize_place_name(item) == query
                or normalize_place_name(item) in query
                or query in normalize_place_name(item)
                for query in queries
                if query
            )
        ]

    async def _build_skeleton(
        self, ctx: TripContext, budget: LlmBudget, trace: PlanningTrace
    ) -> PlanSkeleton:
        user_prompt = build_skeleton_user_prompt(ctx)
        last_error = ""
        for attempt in range(2):
            try:
                suffix = (
                    f"\n上次输出错误：{last_error}。请完整重写合法 JSON。"
                    if last_error
                    else ""
                )
                raw = await self._invoke_json(
                    SKELETON_SYSTEM, user_prompt + suffix, budget, "plan_skeleton"
                )
                skeleton = PlanSkeleton.model_validate(raw)
                if len(skeleton.days) != ctx.days or [
                    day.day for day in skeleton.days
                ] != list(range(1, ctx.days + 1)):
                    raise SkeletonError(
                        "skeleton days must be consecutive and match requested days"
                    )
                missing = self._missing_must_visit(ctx, skeleton)
                if missing:
                    raise SkeletonError(
                        "missing must-visit queries: " + ", ".join(missing)
                    )
                trace.record(
                    "skeleton_created",
                    attempt=attempt + 1,
                    prompt_version=PROMPT_VERSION,
                    llm_calls=budget.used,
                )
                return skeleton
            except Exception as exc:
                last_error = str(exc)
                trace.record("skeleton_rejected", attempt=attempt + 1, error=last_error)
                if budget.remaining <= 0:
                    break
        raise SkeletonError(last_error or "unable to create plan skeleton")

    @staticmethod
    def _mark_required(ctx: TripContext, query: PlaceQuery) -> PlaceQuery:
        query_norm = normalize_place_name(query.query)
        required = any(
            query_norm == normalize_place_name(item)
            or query_norm in normalize_place_name(item)
            or normalize_place_name(item) in query_norm
            for item in ctx.must_visit
        )
        if required:
            return query.model_copy(update={"required": True, "role": "must_visit"})
        if query.role == "must_visit":
            return query.model_copy(update={"required": False, "role": "attraction"})
        return query

    @staticmethod
    def _matches_avoid(place: PlaceEvidence, avoid: list[str]) -> str:
        haystack = normalize_place_name(
            " ".join([place.canonical_name, place.category, place.role, *place.tags])
        )
        for item in avoid:
            normalized = normalize_place_name(item)
            if normalized and normalized in haystack:
                return item
        return ""

    async def _resolve_places(
        self,
        ctx: TripContext,
        skeleton: PlanSkeleton,
        trace: PlanningTrace,
    ) -> tuple[dict[int, list[PlaceEvidence]], dict[str, PlaceEvidence]]:
        places_by_day: dict[int, list[PlaceEvidence]] = {}
        evidence: dict[str, PlaceEvidence] = {}
        used_entities: set[str] = set()
        for day in skeleton.days:
            resolved: list[PlaceEvidence] = []
            ordered_queries = sorted(
                (self._mark_required(ctx, query) for query in day.place_queries),
                key=lambda query: not query.required,
            )
            for query in ordered_queries[:4]:
                place = await self.tools.places.resolve(ctx.city, query)
                if not place:
                    trace.record(
                        "place_unresolved",
                        day=day.day,
                        query=query.query,
                        required=query.required,
                    )
                    if query.required:
                        raise EvidenceError(f"必去地点无法唯一解析：{query.query}")
                    continue
                matched_avoid = self._matches_avoid(place, ctx.avoid)
                if matched_avoid:
                    trace.record(
                        "place_avoided",
                        day=day.day,
                        query=query.query,
                        entity_id=place.entity_id,
                        avoid=matched_avoid,
                    )
                    if query.required:
                        raise EvidenceError(
                            f"必去项“{query.query}”与避免项“{matched_avoid}”冲突"
                        )
                    continue
                if place.entity_id in used_entities:
                    continue
                used_entities.add(place.entity_id)
                resolved.append(place)
                evidence[place.entity_id] = place
                trace.record(
                    "place_resolved",
                    day=day.day,
                    query=query.query,
                    entity_id=place.entity_id,
                    provider=place.provider,
                    confidence=place.confidence,
                )
            if not resolved:
                raise EvidenceError(f"第{day.day}天没有可解析地点")
            places_by_day[day.day] = resolved
        return places_by_day, evidence

    def _hotel_anchor(
        self, ctx: TripContext, places_by_day: dict[int, list[PlaceEvidence]]
    ) -> PlaceEvidence:
        now = datetime.now(UTC)
        if ctx.hotel.name:
            item = self.tools.local_places.select_hotel(
                ctx.city, ctx.hotel.name, ctx.hotel.area
            )
        elif not ctx.hotel.area:
            item = self.tools.local_places.select_hotel(ctx.city)
        else:
            item = None
        if item:
            source_id = str(item.get("source_id", ""))
            return PlaceEvidence(
                query=ctx.hotel.name or str(item.get("name", "")),
                entity_id=f"amap:{source_id}"
                if source_id
                else f"local:{item.get('id', '')}",
                local_id=str(item.get("id", "")),
                source_id=source_id,
                canonical_name=str(item.get("name", "住宿锚点")),
                category="hotel",
                role="hotel",
                lat=float(item.get("lat", 0)),
                lng=float(item.get("lng", 0)),
                area=str(item.get("area", "")),
                status="resolved",
                open_status="verified",
                open_windows=[],
                visit_duration_minutes=30,
                popularity=float(item.get("popularity", 0) or 0),
                tags=[str(tag) for tag in item.get("tags", [])],
                provider="local_cache",
                retrieved_at=now,
                confidence=0.85,
                warnings=["住宿点来自本地实体缓存，价格和可订状态未核验"],
                image_url=str(item.get("image_url", "")),
            )
        all_places = [place for places in places_by_day.values() for place in places]
        if not all_places:
            raise EvidenceError("无法建立住宿区域锚点")
        area_places = [
            place
            for place in all_places
            if ctx.hotel.area and ctx.hotel.area in place.area
        ] or all_places
        lat = sum(place.lat for place in area_places) / len(area_places)
        lng = sum(place.lng for place in area_places) / len(area_places)
        area = ctx.hotel.area or area_places[0].area or "规划区域"
        return PlaceEvidence(
            query=area,
            entity_id=f"virtual:hotel-area:{normalize_place_name(area)}",
            canonical_name=f"住宿区域：{area}",
            category="hotel",
            role="hotel",
            lat=lat,
            lng=lng,
            area=area,
            status="resolved",
            open_status="verified",
            open_windows=[],
            visit_duration_minutes=30,
            provider="virtual_anchor",
            retrieved_at=now,
            confidence=0.7,
            warnings=["未指定具体酒店，使用住宿区域中心作为每日往返锚点"],
        )

    async def plan(self, payload: dict[str, Any] | TripContext) -> PlanningResult:
        ctx = (
            payload if isinstance(payload, TripContext) else self.build_context(payload)
        )
        self.tools.begin_request()
        trace = PlanningTrace(ctx.planning_run_id)
        budget = LlmBudget()
        trace.record("planning_started", city=ctx.city, days=ctx.days)
        try:
            skeleton = await self._build_skeleton(ctx, budget, trace)
            places_by_day, evidence = await self._resolve_places(ctx, skeleton, trace)
            hotel = self._hotel_anchor(ctx, places_by_day)
            evidence[hotel.entity_id] = hotel
            weather = await self.tools.weather.get(ctx.city, ctx.date_start, ctx.days)
            trace.record(
                "weather_collected",
                provider=weather[0].provider if weather else "unavailable",
            )

            plan: ItineraryPlan | None = None
            last_error = ""
            for repair_count in range(4):
                matrices = {}
                for day in skeleton.days:
                    candidates = [hotel, *places_by_day.get(day.day, [])]
                    matrices[day.day] = await self.tools.routes.get_day_matrix(
                        ctx.city, candidates, ctx.transport_mode
                    )
                trace.record(
                    "routes_collected",
                    repair_count=repair_count,
                    verified_edges=sum(len(matrix) for matrix in matrices.values()),
                )
                try:
                    plan = await self.tools.solver.solve(
                        ctx, skeleton.days, places_by_day, hotel, matrices, weather
                    )
                    break
                except SolverError as exc:
                    last_error = str(exc)
                    trace.record(
                        "plan_repair_needed",
                        repair_count=repair_count,
                        error=last_error,
                    )
                    if repair_count >= 3 or not drop_lowest_optional(places_by_day):
                        raise
            if plan is None:
                raise SolverError(last_error or "solver did not return a plan")
            report = validate_itinerary(ctx, plan, evidence)
            trace.record(
                "plan_validated",
                passed=report.passed,
                hard_failures=[issue.code for issue in report.hard_failures],
            )
            if not report.passed:
                return PlanningResult(
                    success=False,
                    planning_run_id=ctx.planning_run_id,
                    itinerary=None,
                    validation=report,
                    trace=trace.events,
                    error="；".join(issue.message for issue in report.hard_failures),
                )
            trace.record(
                "planning_completed", llm_calls=budget.used, repair_count=repair_count
            )
            return PlanningResult(
                success=True,
                planning_run_id=ctx.planning_run_id,
                itinerary=plan,
                validation=report,
                trace=trace.events,
            )
        except Exception as exc:
            code = exc.code if isinstance(exc, PlannerError) else "PLANNING_FAILED"
            logger.error(
                "Grounded planning failed run_id=%s code=%s error=%s",
                ctx.planning_run_id,
                code,
                exc,
            )
            trace.record(
                "planning_failed", code=code, error=str(exc), llm_calls=budget.used
            )
            report = ValidationReport(
                passed=False,
                hard_failures=[
                    ValidationIssue(code=code, message=str(exc), repairable=False)
                ],
            )
            return PlanningResult(
                success=False,
                planning_run_id=ctx.planning_run_id,
                validation=report,
                trace=trace.events,
                error=str(exc),
            )

    @staticmethod
    def to_frontend(result: PlanningResult) -> dict:
        if not result.success or not result.itinerary:
            return {
                "success": False,
                "planning_run_id": result.planning_run_id,
                "error": result.error,
                "validation": result.validation.model_dump(mode="json"),
            }
        plan = result.itinerary
        days = []
        for day in plan.days:
            stops = []
            for stop in day.stops:
                stops.append(
                    {
                        "slot": stop.slot,
                        "poi_id": stop.local_id or stop.entity_id,
                        "entity_id": stop.entity_id,
                        "poi_name": stop.poi_name,
                        "poi_type": stop.poi_type,
                        "area": stop.area,
                        "lat": stop.lat,
                        "lng": stop.lng,
                        "start_minutes": stop.start_minutes,
                        "end_minutes": stop.end_minutes,
                        "start_time": f"{stop.start_minutes // 60:02d}:{stop.start_minutes % 60:02d}",
                        "end_time": f"{stop.end_minutes // 60:02d}:{stop.end_minutes % 60:02d}",
                        "reason": stop.reason,
                        "travel_minutes_from_previous": stop.travel_minutes_from_previous,
                        "distance_meters_from_previous": stop.distance_meters_from_previous,
                        "route_source": stop.route_source,
                        "transport_hint": stop.transport_hint,
                        "open_status": stop.open_status,
                        "evidence_provider": stop.evidence_provider,
                        "image_url": stop.image_url,
                    }
                )
            days.append(
                {
                    "day": day.day,
                    "date": day.date,
                    "theme": day.theme,
                    "stops": stops,
                    "summary": day.summary,
                    "route_segments": day.route_segments,
                    "total_travel_minutes": day.total_travel_minutes,
                    "route_quality": {
                        "verified_segments": len(day.route_segments),
                        "estimated_segments": 0,
                        "verified_ratio": 1.0,
                    },
                    "replacement_pool": [],
                    "weather": day.weather.model_dump(mode="json")
                    if day.weather
                    else None,
                    "warnings": day.warnings,
                }
            )
        return {
            "success": True,
            "city": plan.city,
            "days": days,
            "hotel": {
                "name": plan.hotel_anchor.canonical_name,
                "area": plan.hotel_anchor.area,
                "lat": plan.hotel_anchor.lat,
                "lng": plan.hotel_anchor.lng,
            },
            "summary": f"{plan.city}{len(days)}天可信行程；地点与通勤均经过结构化证据链处理。",
            "variant_name": "Grounded Planner",
            "travel_tips": [],
            "alternatives": [],
            "must_visit_coverage": [],
            "weather_available": all(
                day.weather and day.weather.provider != "unavailable"
                for day in plan.days
            ),
            "planning_run_id": result.planning_run_id,
            "validation": result.validation.model_dump(mode="json"),
            "warnings": plan.warnings,
        }
