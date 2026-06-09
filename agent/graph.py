"""LangGraph state graph — the core Agent orchestration."""
from __future__ import annotations
import json
import logging
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI

from .config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    LLM_TEMPERATURE, LLM_TIMEOUT_SECONDS, MAX_LLM_CALLS_PER_REQUEST,
)
from .models import (
    AgentState, TripIntent, PoiInfo, HotelInfo,
    DayPlan, StopInfo, ItineraryResult,
)
from .prompts import (
    PARSE_INTENT_SYSTEM, HOTEL_SELECTION_SYSTEM,
    DAY_PLANNING_SYSTEM, ITINERARY_SUMMARY_SYSTEM,
)
from . import tools
from . import rag
from . import cache

logger = logging.getLogger(__name__)


# ── LLM client ────────────────────────────────────────────────────────────────

def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        temperature=LLM_TEMPERATURE,
        timeout=LLM_TIMEOUT_SECONDS,
    )


def get_llm_creative() -> ChatOpenAI:
    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        temperature=0.7,
        timeout=LLM_TIMEOUT_SECONDS,
    )


async def _llm_json(llm: ChatOpenAI, system: str, user: str, state: AgentState) -> Any:
    """Call LLM and parse JSON response. Increments call counter."""
    if state.llm_call_count >= MAX_LLM_CALLS_PER_REQUEST:
        raise RuntimeError(f"Max LLM calls ({MAX_LLM_CALLS_PER_REQUEST}) reached")

    state.llm_call_count += 1
    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    resp = await llm.ainvoke(messages)
    text = resp.content.strip()

    # Extract JSON from response (handle markdown code blocks)
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


# ── Graph nodes ───────────────────────────────────────────────────────────────

async def parse_intent(state: AgentState) -> AgentState:
    """Node 1: Parse user's natural language into structured TripIntent."""
    yield {"type": "status", "content": "正在理解您的需求..."}

    llm = get_llm()
    try:
        data = await _llm_json(llm, PARSE_INTENT_SYSTEM, state.user_message, state)
        intent = TripIntent(**data)
        state.intent = intent
        yield {
            "type": "intent_parsed",
            "content": f"目的地：{intent.city}，{intent.days}天{intent.pace}节奏",
            "intent": intent.model_dump(),
        }
    except Exception as e:
        logger.error(f"parse_intent failed: {e}")
        state.errors.append(f"意图解析失败: {e}")
        # Fallback: try to extract city from message using known cities
        known_cities = [
            "北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "武汉",
            "南京", "西安", "长沙", "昆明", "大理", "丽江", "三亚", "桂林",
            "厦门", "青岛", "哈尔滨", "苏州", "张家界",
        ]
        fallback_city = ""
        for c in known_cities:
            if c in state.user_message:
                fallback_city = c
                break
        if not fallback_city:
            fallback_city = state.user_message[:2]
        state.intent = TripIntent(city=fallback_city, days=3)

    return


async def retrieve_guides(state: AgentState) -> AgentState:
    """Node 2: Retrieve relevant city guides via RAG."""
    if not state.intent:
        return

    yield {"type": "status", "content": f"正在检索{state.intent.city}攻略..."}

    # RAG retrieval
    queries = [
        f"{state.intent.city}旅行攻略",
        f"{state.intent.city}交通建议",
        f"{state.intent.city}美食推荐",
    ]
    if state.intent.travelers:
        queries.append(f"{state.intent.city}{state.intent.travelers}旅行")

    all_guides = []
    for q in queries:
        results = rag.search_guides(state.intent.city, q, top_k=3)
        all_guides.extend(results)

    # Deduplicate
    seen = set()
    unique_guides = []
    for g in all_guides:
        if g not in seen:
            seen.add(g)
            unique_guides.append(g)

    state.city_guides = unique_guides[:10]

    yield {
        "type": "guides_retrieved",
        "content": f"找到 {len(state.city_guides)} 条攻略信息",
        "guides_count": len(state.city_guides),
    }

    return


async def select_pois_and_hotels(state: AgentState) -> AgentState:
    """Node 3: Search local POI and hotel databases."""
    if not state.intent:
        return

    intent = state.intent
    yield {"type": "status", "content": f"正在搜索{intent.city}的景点和酒店..."}

    # Search POIs (all types)
    pois = await tools.search_pois(intent.city, limit=200)
    state.available_pois = pois

    # Search hotels
    hotels = await tools.search_hotels(intent.city, limit=30)
    state.available_hotels = hotels

    # Filter by must_visit: use substring/fuzzy matching
    if intent.must_visit:
        found_names = {p.name for p in pois}
        missing = []
        matched_must_visit = []
        for m in intent.must_visit:
            if any(m in name or name in m for name in found_names):
                matched_must_visit.append(m)
            else:
                missing.append(m)
        if missing:
            yield {
                "type": "warning",
                "content": f"本地数据中未找到: {', '.join(missing)}，将尝试其他方式查找",
            }

    yield {
        "type": "data_loaded",
        "content": f"找到 {len(pois)} 个景点、{len(hotels)} 家酒店",
        "poi_count": len(pois),
        "hotel_count": len(hotels),
    }

    return


async def select_hotel(state: AgentState) -> AgentState:
    """Node 4: Select the best hotel as anchor point."""
    if not state.intent or not state.available_hotels:
        return

    intent = state.intent
    yield {"type": "status", "content": "正在为您选择最佳住宿..."}

    # Pre-filter hotels by area if specified
    candidates = state.available_hotels
    if intent.hotel_area:
        area_hotels = [h for h in candidates if intent.hotel_area in h.area]
        if area_hotels:
            candidates = area_hotels

    # Build hotel list for LLM
    hotel_list = "\n".join([
        f"- {h.name} (ID:{h.id}, 区域:{h.area}, 评分:{h.popularity}, "
        f"描述:{h.description[:60] if h.description else '无'})"
        for h in candidates[:15]
    ])

    # Build context
    must_visit_str = ", ".join(intent.must_visit) if intent.must_visit else "无特殊要求"
    user_context = (
        f"城市: {intent.city}\n"
        f"出行人群: {intent.travelers or '普通'}\n"
        f"预算: {intent.budget}\n"
        f"必去景点: {must_visit_str}\n"
        f"酒店偏好: {intent.hotel_preference or '无特殊要求'}\n"
        f"希望区域: {intent.hotel_area or '不限'}\n\n"
        f"候选酒店:\n{hotel_list}"
    )

    llm = get_llm()
    try:
        data = await _llm_json(llm, HOTEL_SELECTION_SYSTEM, user_context, state)
        hotel_id = data.get("hotel_id", "")
        reason = data.get("reason", "")

        # Find the selected hotel
        for h in candidates:
            if h.id == hotel_id:
                state.selected_hotel = h
                yield {
                    "type": "hotel_selected",
                    "content": f"已选酒店: {h.name}",
                    "hotel": h.model_dump(),
                    "reason": reason,
                }
                return

        # Fallback: pick first candidate
        if candidates:
            state.selected_hotel = candidates[0]
            yield {
                "type": "hotel_selected",
                "content": f"已选酒店: {candidates[0].name}",
                "hotel": candidates[0].model_dump(),
                "reason": "默认选择",
            }
    except Exception as e:
        logger.error(f"select_hotel LLM failed: {e}")
        if candidates:
            state.selected_hotel = candidates[0]

    return


async def plan_each_day(state: AgentState) -> AgentState:
    """Node 5: Plan each day's itinerary."""
    if not state.intent:
        return

    intent = state.intent
    hotel = state.selected_hotel

    # Filter POIs by type for planning
    attractions = [p for p in state.available_pois if p.type == "attraction"]
    restaurants = [p for p in state.available_pois if p.type == "restaurant"]
    nightlife = [p for p in state.available_pois if p.type == "nightlife"]

    # Ensure must_visit POIs are included (one best match per keyword)
    must_visit_pois = []
    if intent.must_visit:
        for mv in intent.must_visit:
            matches = [p for p in state.available_pois if mv in p.name]
            if matches:
                # Prefer: exact name > shorter name > higher popularity
                matches.sort(key=lambda p: (p.name != mv, len(p.name), -p.popularity))
                best = matches[0]
                if best not in must_visit_pois:
                    must_visit_pois.append(best)

    # Prioritize: must_visit first, then by popularity
    other_attractions = [p for p in attractions if p not in must_visit_pois]
    other_attractions.sort(key=lambda x: x.popularity, reverse=True)

    # Split attractions across days
    all_attractions = must_visit_pois + other_attractions

    # Guide context
    guide_context = "\n".join(state.city_guides[:5]) if state.city_guides else ""

    for day_num in range(1, intent.days + 1):
        yield {"type": "status", "content": f"正在规划第 {day_num} 天..."}

        # Assign attractions to this day (round-robin must_visit, then fill)
        day_attractions = []
        for i, attr in enumerate(all_attractions):
            if i % intent.days == (day_num - 1) % intent.days:
                day_attractions.append(attr)

        # Also pick some restaurants for this day
        day_restaurants = []
        for i, rest in enumerate(restaurants):
            if i % intent.days == (day_num - 1) % intent.days:
                day_restaurants.append(rest)

        # Build candidate list for LLM
        must_visit_ids = {p.id for p in must_visit_pois}
        attr_list = "\n".join([
            f"- {a.name} (ID:{a.id}, 区域:{a.area}, 评分:{a.popularity}, "
            f"游玩时长:{a.visit_duration_minutes}分钟, "
            f"{'【必去】' if a.id in must_visit_ids else ''}"
            f"描述:{a.description[:80] if a.description else '无'})"
            for a in day_attractions[:20]
        ])
        rest_list = "\n".join([
            f"- {r.name} (ID:{r.id}, 区域:{r.area}, 类型:{r.meal_type})"
            for r in day_restaurants[:10]
        ])

        user_context = (
            f"第 {day_num} 天，共 {intent.days} 天\n"
            f"节奏: {intent.pace}\n"
            f"出行人群: {intent.travelers or '普通'}\n"
            f"酒店位置: {hotel.area if hotel else '未定'}\n"
            f"兴趣: {', '.join(intent.interests) if intent.interests else '综合'}\n"
        )
        if must_visit_pois:
            must_names = [p.name for p in must_visit_pois]
            user_context += f"\n用户必去景点（必须安排，不可省略）: {', '.join(must_names)}\n"
        user_context += f"\n候选景点（标有【必去】的必须安排）:\n{attr_list}\n"
        user_context += f"\n候选餐厅:\n{rest_list}\n"
        if guide_context:
            user_context += f"\n当地攻略参考:\n{guide_context}\n"

        llm = get_llm()
        try:
            stops_data = await _llm_json(llm, DAY_PLANNING_SYSTEM, user_context, state)

            stops = []
            total_travel = 0
            total_visit = 0
            for s in stops_data:
                stop = StopInfo(
                    slot=s.get("slot", ""),
                    poi_id=s.get("poi_id", ""),
                    poi_name=s.get("poi_name", ""),
                    start_minutes=s.get("start_minutes", 0),
                    end_minutes=s.get("end_minutes", 0),
                    visit_duration_minutes=s.get("visit_duration_minutes", 60),
                    reason=s.get("reason", ""),
                )
                # Find POI info for coordinates
                for p in state.available_pois:
                    if p.id == stop.poi_id:
                        stop.poi_type = p.type
                        stop.area = p.area
                        stop.lat = p.lat
                        stop.lng = p.lng
                        stop.meal_type = p.meal_type
                        stop.recommendation = p.recommendation
                        break
                stops.append(stop)
                total_visit += stop.visit_duration_minutes

            # Validate: ensure must_visit POIs for this day are included
            if must_visit_pois:
                must_visit_ids_today = {
                    a.id for a in day_attractions
                    if a.id in {p.id for p in must_visit_pois}
                }
                included_ids = {s.poi_id for s in stops}
                missing_ids = must_visit_ids_today - included_ids
                if missing_ids:
                    for p in day_attractions:
                        if p.id in missing_ids:
                            inject_stop = StopInfo(
                                slot="上午" if not any(s.slot == "上午" for s in stops) else "下午",
                                poi_id=p.id,
                                poi_name=p.name,
                                poi_type=p.type,
                                area=p.area,
                                lat=p.lat,
                                lng=p.lng,
                                start_minutes=540,
                                end_minutes=540 + p.visit_duration_minutes,
                                visit_duration_minutes=p.visit_duration_minutes,
                                reason=f"用户必去: {p.name}",
                                recommendation=p.recommendation,
                            )
                            stops.insert(0, inject_stop)
                            logger.info(f"Force-injected must_visit: {p.name}")

            day_plan = DayPlan(
                day=day_num,
                stops=stops,
                total_travel_minutes=total_travel,
                total_visit_minutes=total_visit,
                summary=f"第{day_num}天: {len(stops)}个行程",
            )
            state.daily_plans.append(day_plan)

            yield {
                "type": "day_planned",
                "content": f"第 {day_num} 天规划完成：{len(stops)} 个行程",
                "day": day_num,
                "stops_count": len(stops),
                "day_plan": day_plan.model_dump(),
            }

        except Exception as e:
            logger.error(f"plan_each_day day {day_num} failed: {e}")
            state.errors.append(f"第{day_num}天规划失败: {e}")

    return


async def optimize_routes(state: AgentState) -> AgentState:
    """Node 6: Optimize routes using Beam Search (C++ backend)."""
    if not state.intent or not state.daily_plans:
        return

    yield {"type": "status", "content": "正在优化路线..."}

    city = state.intent.city
    hotel_id = state.selected_hotel.id if state.selected_hotel else ""

    for i, day_plan in enumerate(state.daily_plans):
        poi_ids = [s.poi_id for s in day_plan.stops if s.poi_id]
        if len(poi_ids) < 2:
            continue

        result = await tools.optimize_route(
            city=city,
            poi_ids=poi_ids,
            hotel_id=hotel_id,
            pace=state.intent.pace,
        )

        if result and "days" in result:
            optimized = result["days"][0] if result["days"] else {}
            if "stops" in optimized:
                # Update travel times from optimization
                for opt_stop in optimized["stops"]:
                    for stop in day_plan.stops:
                        if stop.poi_id == opt_stop.get("poiId", ""):
                            stop.travel_minutes_from_previous = opt_stop.get(
                                "travelMinutesFromPrevious", 0
                            )
                            break
                day_plan.total_travel_minutes = optimized.get("totalTravelMinutes", 0)

    yield {
        "type": "routes_optimized",
        "content": "路线优化完成",
    }

    return


async def assemble_result(state: AgentState) -> AgentState:
    """Node 7: Assemble final itinerary result and generate summary."""
    if not state.intent:
        return

    yield {"type": "status", "content": "正在生成行程总结..."}

    intent = state.intent

    # Generate summary via LLM
    itinerary_text = ""
    for dp in state.daily_plans:
        itinerary_text += f"\n第{dp.day}天:\n"
        for s in dp.stops:
            itinerary_text += f"  {s.slot} {s.poi_name}"
            if s.reason:
                itinerary_text += f" - {s.reason}"
            itinerary_text += "\n"

    guide_tips = "\n".join(state.city_guides[:3])

    summary_context = (
        f"城市: {intent.city}, {intent.days}天{intent.pace}节奏\n"
        f"出行人群: {intent.travelers or '普通'}\n"
        f"行程安排:{itinerary_text}\n"
    )
    if guide_tips:
        summary_context += f"\n当地贴士:\n{guide_tips}\n"

    llm = get_llm_creative()
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=ITINERARY_SUMMARY_SYSTEM),
            HumanMessage(content=summary_context),
        ])
        summary = resp.content.strip()
        state.llm_call_count += 1
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        summary = f"{intent.city}{intent.days}天行程已生成"

    # Build alternatives
    alternatives = []
    if state.city_guides:
        alternatives = state.city_guides[:3]

    # Build result
    state.result = ItineraryResult(
        city=intent.city,
        days=state.daily_plans,
        hotel=state.selected_hotel,
        variant_name=f"{intent.pace}节奏方案",
        strategy=intent.strategy,
        alternatives=alternatives,
        summary=summary,
    )

    # Cache the result
    if state.result:
        cache.set_cached_itinerary(
            city=intent.city,
            days=intent.days,
            pace=intent.pace,
            strategy=intent.strategy,
            must_visit=intent.must_visit,
            itinerary=state.result.model_dump(),
        )

    yield {
        "type": "itinerary_complete",
        "content": summary,
        "itinerary": state.result.model_dump() if state.result else None,
        "llm_calls": state.llm_call_count,
    }

    return


# ── Main planning pipeline ────────────────────────────────────────────────────

async def run_planning_pipeline(
    user_message: str,
    context: dict | None = None,
) -> AsyncIterator[dict]:
    """Run the full planning pipeline, yielding SSE events."""
    state = AgentState(user_message=user_message)

    # Check cache first
    # (We need intent first, so do a quick parse)
    llm = get_llm()
    try:
        data = await _llm_json(llm, PARSE_INTENT_SYSTEM, user_message, state)
        intent = TripIntent(**data)
        state.intent = intent

        # Check cache
        cached = cache.get_cached_itinerary(
            city=intent.city,
            days=intent.days,
            pace=intent.pace,
            strategy=intent.strategy,
            must_visit=intent.must_visit,
        )
        if cached:
            yield {
                "type": "cache_hit",
                "content": "命中缓存，直接返回",
                "itinerary": cached,
            }
            return
    except Exception:
        pass  # Continue with full pipeline

    # Reset state for full pipeline
    state = AgentState(user_message=user_message)
    state.llm_call_count = 0  # Reset since the above was just a pre-check

    # Run nodes sequentially, yielding events
    nodes = [
        parse_intent,
        retrieve_guides,
        select_pois_and_hotels,
        select_hotel,
        plan_each_day,
        optimize_routes,
        assemble_result,
    ]

    for node in nodes:
        try:
            async for event in node(state):
                if isinstance(event, dict):
                    yield event
                # Also handle AgentState returns (last yield)
        except Exception as e:
            logger.error(f"Node {node.__name__} failed: {e}")
            state.errors.append(f"{node.__name__}: {e}")
            yield {"type": "error", "content": f"处理失败: {e}"}

    if state.errors:
        yield {"type": "warnings", "content": f"有 {len(state.errors)} 个警告", "errors": state.errors}

