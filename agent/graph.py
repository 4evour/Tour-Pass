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
    DayPlan, StopInfo, ItineraryResult, MustVisitStatus,
)
from .prompts import (
    PARSE_INTENT_SYSTEM, HOTEL_SELECTION_SYSTEM,
    DAY_PLANNING_SYSTEM, ITINERARY_SUMMARY_SYSTEM,
)
from . import tools
from . import rag
from . import cache
from .scorer import rank_pois, ScoredPoi, _is_must_visit
from .clustering import cluster_pois_for_days, DayCluster

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


# Allowed fields for TripIntent construction from LLM output
_INTENT_ALLOWED_FIELDS = {
    "city", "days", "pace", "budget", "travelers", "interests",
    "must_visit", "avoid", "hotel_preference", "hotel_area",
    "hotel_budget_min", "hotel_budget_max", "special_requests", "strategy",
}


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

    data = json.loads(text)

    # Whitelist filter: only keep known TripIntent fields to prevent injection
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k in _INTENT_ALLOWED_FIELDS}

    return data


# ── Hotel budget matching helper ──────────────────────────────────────────────

def _matches_budget(hotel: HotelInfo, budget_min: int, budget_max: int) -> bool:
    """Check if a hotel's price range overlaps with the user's budget."""
    if budget_min <= 0 and budget_max <= 0:
        return True

    # Parse price_range string like "200-400元/晚" or "300"
    pr = hotel.price_range
    if not pr:
        # Fallback: use price_level to estimate
        level_ranges = {
            1: (100, 300), 2: (200, 400), 3: (300, 600),
            4: (500, 1000), 5: (800, 2000),
        }
        lo, hi = level_ranges.get(hotel.price_level, (100, 300))
    else:
        import re
        nums = re.findall(r'\d+', pr)
        if len(nums) >= 2:
            lo, hi = int(nums[0]), int(nums[1])
        elif len(nums) == 1:
            lo = hi = int(nums[0])
        else:
            return True  # Can't parse, don't filter out

    # Check overlap: hotel range [lo, hi] vs budget [budget_min, budget_max]
    if budget_max > 0 and lo > budget_max:
        return False
    if budget_min > 0 and hi < budget_min:
        return False
    return True


def _hotel_category_for_budget(budget: str) -> list[str]:
    """Map user budget string to preferred brand categories."""
    if budget == "低":
        return ["经济型"]
    elif budget == "高":
        return ["高端", "豪华"]
    return ["中端"]


# ── Graph nodes ───────────────────────────────────────────────────────────────

async def parse_intent(state: AgentState) -> AgentState:
    """Node 1: Parse user's natural language into structured TripIntent."""
    yield {"type": "status", "content": "正在理解您的需求..."}

    # Skip if intent was already parsed (e.g. from cache pre-check)
    if state.intent and state.intent.city:
        yield {
            "type": "intent_parsed",
            "content": f"目的地：{state.intent.city}，{state.intent.days}天{state.intent.pace}节奏",
            "intent": state.intent.model_dump(),
        }
        return

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
            # Try to extract any known city from the message using substring match
            fallback_city = ""
        state.intent = TripIntent(city=fallback_city or "长沙", days=3)

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
    """Node 4: Select the best hotel as anchor point.
    
    Filtering priority:
    1. Area filter (if user specified hotel_area)
    2. Budget filter (if user specified hotel_budget_min/max or budget level)
    3. Brand category filter (based on user's budget level)
    4. LLM final selection from filtered candidates
    """
    if not state.intent or not state.available_hotels:
        return

    intent = state.intent
    yield {"type": "status", "content": "正在为您选择最佳住宿..."}

    candidates = list(state.available_hotels)

    # 1. Area filter
    if intent.hotel_area:
        area_hotels = [h for h in candidates if intent.hotel_area in h.area]
        if area_hotels:
            candidates = area_hotels

    # 2. Budget filter (by explicit budget range)
    if intent.hotel_budget_max > 0 or intent.hotel_budget_min > 0:
        budget_hotels = [
            h for h in candidates
            if _matches_budget(h, intent.hotel_budget_min, intent.hotel_budget_max)
        ]
        if budget_hotels:
            candidates = budget_hotels
            logger.info(f"Budget filter: {len(candidates)} hotels match "
                        f"{intent.hotel_budget_min}-{intent.hotel_budget_max}元")

    # 3. Brand category filter
    preferred_cats = _hotel_category_for_budget(intent.budget)
    if preferred_cats:
        cat_hotels = [h for h in candidates if h.brand_category in preferred_cats]
        if cat_hotels:
            candidates = cat_hotels
            logger.info(f"Category filter: {len(candidates)} hotels in {preferred_cats}")

    # Build hotel list for LLM (with enriched info)
    hotel_list = "\n".join([
        f"- {h.name} (ID:{h.id}, 区域:{h.area}, 评分:{h.popularity}, "
        f"档次:{h.brand_category or '未知'}, "
        f"价格:{h.price_range or '未知'}, "
        f"描述:{h.description[:60] if h.description else '无'})"
        for h in candidates[:15]
    ])

    # Build context
    must_visit_str = ", ".join(intent.must_visit) if intent.must_visit else "无特殊要求"
    user_context = (
        f"城市: {intent.city}\n"
        f"出行人群: {intent.travelers or '普通'}\n"
        f"预算: {intent.budget}"
    )
    if intent.hotel_budget_min > 0 or intent.hotel_budget_max > 0:
        user_context += f"（每晚{intent.hotel_budget_min}-{intent.hotel_budget_max}元）"
    user_context += (
        f"\n必去景点: {must_visit_str}\n"
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
    """Node 5: Plan each day using multi-dimensional scoring and geographic clustering.
    
    Must-visit guarantee chain:
    1. rank_pois protects must_visit from top_k truncation
    2. cluster_pois_for_days rescues missing must_visit from full POI list
    3. LLM prompt marks must_visit with 【必去】
    4. Per-day post-injection catches LLM omissions
    5. Global post-verification catches any remaining gaps
    """
    if not state.intent:
        return

    intent = state.intent
    hotel = state.selected_hotel

    yield {"type": "status", "content": "正在智能规划行程..."}

    attractions = [p for p in state.available_pois if p.type == "attraction"]
    restaurants = [p for p in state.available_pois if p.type == "restaurant"]
    nightlife = [p for p in state.available_pois if p.type == "nightlife"]

    # Multi-dimensional scoring (must_visit protected from truncation)
    scored = rank_pois(pois=attractions, intent=intent, top_k=intent.days * 10)

    yield {"type": "status", "content": f"已评分 {len(scored)} 个景点，正在聚类分配..."}

    # Geographic clustering (must_visit rescued from full POI list)
    clusters = cluster_pois_for_days(
        scored_attractions=scored, restaurants=restaurants,
        nightlife=nightlife, num_days=intent.days, intent=intent,
        all_available_pois=state.available_pois,
    )

    guide_context = "\n".join(state.city_guides[:3]) if state.city_guides else ""

    for cluster in clusters:
        day_num = cluster.day_num
        yield {"type": "status", "content": f"正在规划第 {day_num} 天（{cluster.theme}）..."}

        # Match must_visit keywords to best POI (shortest name containing keyword)
        must_visit_ids = set()
        for mv in intent.must_visit:
            matches = [a for a in cluster.attractions if mv in a.name or mv == a.id]
            if matches:
                matches.sort(key=lambda p: (p.name != mv, len(p.name), -p.popularity))
                must_visit_ids.add(matches[0].id)

        attr_list = "\n".join([
            f"- {a.name} (ID:{a.id}, 区域:{a.area}, 评分:{a.popularity}, "
            f"游玩时长:{a.visit_duration_minutes}分钟, "
            f"{'【必去】' if a.id in must_visit_ids else ''}"
            f"标签:{','.join(a.tags[:5])}, "
            f"简介:{a.description or '无'})"
            for a in cluster.attractions[:12]
        ])
        rest_list = "\n".join([
            f"- {r.name} (ID:{r.id}, 区域:{r.area}, 简介:{(r.description or '')[:60]})"
            for r in cluster.restaurants[:5]
        ])

        user_context = (
            f"第 {day_num} 天，共 {intent.days} 天\n"
            f"今日主题: {cluster.theme}\n"
            f"节奏: {intent.pace}\n"
            f"出行人群: {intent.travelers or '普通'}\n"
            f"酒店位置: {hotel.area if hotel else '未定'}\n"
            f"兴趣: {', '.join(intent.interests) if intent.interests else '综合'}\n"
            f"策略: {intent.strategy or 'balanced'}\n"
        )
        if must_visit_ids:
            must_names = [a.name for a in cluster.attractions if a.id in must_visit_ids]
            user_context += f"\n用户必去景点（必须安排，不可省略）: {', '.join(must_names)}\n"
        user_context += f"\n候选景点（标有【必去】的必须安排，其余按评分排序）:\n{attr_list}\n"
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

            # Per-day must_visit post-injection
            if must_visit_ids:
                included_ids = {s.poi_id for s in stops}
                missing_ids = must_visit_ids - included_ids
                if missing_ids:
                    for p in cluster.attractions:
                        if p.id in missing_ids:
                            inject_stop = StopInfo(
                                slot="上午" if not any(s.slot == "上午" for s in stops) else "下午",
                                poi_id=p.id, poi_name=p.name, poi_type=p.type,
                                area=p.area, lat=p.lat, lng=p.lng,
                                start_minutes=540, end_minutes=540 + p.visit_duration_minutes,
                                visit_duration_minutes=p.visit_duration_minutes,
                                reason=f"用户必去: {p.name}",
                                recommendation=p.recommendation,
                            )
                            stops.insert(0, inject_stop)
                            logger.info(f"Force-injected must_visit: {p.name}")

            day_plan = DayPlan(
                day=day_num, stops=stops,
                total_travel_minutes=total_travel, total_visit_minutes=total_visit,
                summary=f"第{day_num}天({cluster.theme}): {len(stops)}个行程",
            )
            state.daily_plans.append(day_plan)

            yield {
                "type": "day_planned",
                "content": f"第 {day_num} 天规划完成：{len(stops)} 个行程",
                "day": day_num, "stops_count": len(stops),
                "day_plan": day_plan.model_dump(),
            }
        except Exception as e:
            logger.error(f"plan_each_day day {day_num} failed: {e}")
            state.errors.append(f"第{day_num}天规划失败: {e}")

    # ── Global must_visit post-verification ──
    if intent.must_visit and state.daily_plans:
        all_planned_names = set()
        for dp in state.daily_plans:
            for s in dp.stops:
                all_planned_names.add(s.poi_name)

        still_missing = []
        for mv in intent.must_visit:
            if not any(mv in name for name in all_planned_names):
                still_missing.append(mv)

        if still_missing:
            logger.warning(f"Global verification: missing must_visit: {still_missing}")
            for mv in still_missing:
                # Find the POI in available_pois
                poi = None
                for p in state.available_pois:
                    if mv in p.name or mv == p.id:
                        poi = p
                        break
                if not poi:
                    logger.error(f"Cannot rescue must_visit '{mv}': not in available_pois")
                    continue

                # Find the lightest day
                lightest_day = min(state.daily_plans, key=lambda d: len(d.stops))
                inject_stop = StopInfo(
                    slot="下午" if len(lightest_day.stops) >= 3 else "上午",
                    poi_id=poi.id, poi_name=poi.name, poi_type=poi.type,
                    area=poi.area, lat=poi.lat, lng=poi.lng,
                    start_minutes=840, end_minutes=840 + poi.visit_duration_minutes,
                    visit_duration_minutes=poi.visit_duration_minutes,
                    reason=f"用户必去（全局补救）: {poi.name}",
                    recommendation=poi.recommendation,
                )
                lightest_day.stops.append(inject_stop)
                logger.info(f"Global rescue: injected {poi.name} into day {lightest_day.day}")
                yield {
                    "type": "must_visit_injected",
                    "content": f"已强制安排行程: {mv}",
                }

    return


async def optimize_routes(state: AgentState) -> AgentState:
    """Node 6: Optimize routes using C++ backend's Beam Search."""
    if not state.intent or not state.daily_plans:
        return

    yield {"type": "status", "content": "正在优化路线..."}

    for day_plan in state.daily_plans:
        poi_ids = [s.poi_id for s in day_plan.stops if s.poi_id]
        if len(poi_ids) < 2:
            continue

        result = await tools.optimize_route(
            city=state.intent.city,
            poi_ids=poi_ids,
            hotel_id=state.selected_hotel.id if state.selected_hotel else "",
            pace=state.intent.pace,
        )
        if result and "days" in result:
            optimized = result["days"][0] if result["days"] else {}
            if "stops" in optimized:
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

    alternatives = []
    if state.city_guides:
        alternatives = state.city_guides[:3]

    # Build must_visit coverage report
    must_visit_coverage = []
    if intent.must_visit:
        all_planned_names = set()
        for dp in state.daily_plans:
            for s in dp.stops:
                all_planned_names.add(s.poi_name)

        for mv in intent.must_visit:
            matched = ""
            included = False
            for name in all_planned_names:
                if mv in name:
                    included = True
                    matched = name
                    break
            must_visit_coverage.append(MustVisitStatus(
                name=mv, included=included, matched_poi=matched,
            ))

    state.result = ItineraryResult(
        city=intent.city,
        days=state.daily_plans,
        hotel=state.selected_hotel,
        variant_name=f"{intent.pace}节奏方案",
        strategy=intent.strategy,
        alternatives=alternatives,
        summary=summary,
        must_visit_coverage=must_visit_coverage,
    )

    if state.result:
        cache.set_cached_itinerary(
            city=intent.city,
            days=intent.days,
            pace=intent.pace,
            strategy=intent.strategy,
            must_visit=intent.must_visit,
            itinerary=state.result.model_dump(),
        )

    # Log coverage
    if must_visit_coverage:
        covered = sum(1 for c in must_visit_coverage if c.included)
        logger.info(f"Must-visit coverage: {covered}/{len(must_visit_coverage)}")
        for c in must_visit_coverage:
            if not c.included:
                logger.warning(f"Must-visit NOT covered: {c.name}")

    yield {
        "type": "itinerary_complete",
        "content": summary,
        "itinerary": state.result.model_dump() if state.result else None,
        "llm_calls": state.llm_call_count,
    }

    return



async def run_planning_pipeline(
    user_message: str,
    context: dict | None = None,
) -> AsyncIterator[dict]:
    """Run the full planning pipeline, yielding SSE events."""
    state = AgentState(user_message=user_message)

    # Check cache first
    # (We need intent first, so do a quick parse)
    pre_parsed_intent = None
    llm = get_llm()
    try:
        data = await _llm_json(llm, PARSE_INTENT_SYSTEM, user_message, state)
        intent = TripIntent(**data)
        pre_parsed_intent = intent
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

    # Reset state for full pipeline, but reuse pre-parsed intent if available
    state = AgentState(user_message=user_message)
    if pre_parsed_intent:
        state.intent = pre_parsed_intent

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
