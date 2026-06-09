"""Simplified graph implementation that works without langgraph.
Uses basic async/await sequential execution.
Falls back to this if langgraph is not installed."""
from __future__ import annotations
import json
import logging
from typing import Any, AsyncIterator

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

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

def get_llm():
    if not LANGCHAIN_AVAILABLE:
        raise RuntimeError("langchain-openai not installed")
    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        temperature=LLM_TEMPERATURE,
        timeout=LLM_TIMEOUT_SECONDS,
    )


def get_llm_creative():
    if not LANGCHAIN_AVAILABLE:
        raise RuntimeError("langchain-openai not installed")
    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        temperature=0.7,
        timeout=LLM_TIMEOUT_SECONDS,
    )


async def _llm_json(llm, system: str, user: str, state: AgentState) -> Any:
    """Call LLM and parse JSON response."""
    if state.llm_call_count >= MAX_LLM_CALLS_PER_REQUEST:
        raise RuntimeError(f"Max LLM calls ({MAX_LLM_CALLS_PER_REQUEST}) reached")

    state.llm_call_count += 1
    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    resp = await llm.ainvoke(messages)
    text = resp.content.strip()

    # Extract JSON from response
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


# ── Direct HTTP fallback (no langchain needed) ────────────────────────────────

async def _direct_llm_json(system: str, user: str, state: AgentState) -> Any:
    """Call DeepSeek API directly via httpx, no langchain needed."""
    import httpx

    if state.llm_call_count >= MAX_LLM_CALLS_PER_REQUEST:
        raise RuntimeError(f"Max LLM calls ({MAX_LLM_CALLS_PER_REQUEST}) reached")

    state.llm_call_count += 1

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": LLM_TEMPERATURE,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()

    # Extract JSON
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


async def _direct_llm_chat(system: str, user: str, temperature: float = 0.7) -> str:
    """Call DeepSeek API directly for chat/text generation."""
    import httpx

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


# Helper: choose JSON caller based on availability
async def call_json(system: str, user: str, state: AgentState) -> Any:
    if LANGCHAIN_AVAILABLE:
        llm = get_llm()
        return await _llm_json(llm, system, user, state)
    else:
        return await _direct_llm_json(system, user, state)


# ── Pipeline nodes ────────────────────────────────────────────────────────────

async def parse_intent(state: AgentState) -> AsyncIterator[dict]:
    yield {"type": "status", "content": "正在理解您的需求..."}

    try:
        data = await call_json(PARSE_INTENT_SYSTEM, state.user_message, state)
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
        known_cities = ["北京","上海","广州","深圳","成都","重庆","杭州","武汉","南京","西安","长沙","昆明","大理","丽江","三亚","桂林","厦门","青岛","哈尔滨","苏州","张家界"]
        fallback_city = next((c for c in known_cities if c in state.user_message), state.user_message[:2])
        state.intent = TripIntent(city=fallback_city, days=3)


async def retrieve_guides(state: AgentState) -> AsyncIterator[dict]:
    if not state.intent:
        return

    yield {"type": "status", "content": f"正在检索{state.intent.city}攻略..."}

    # Check if RAG index is ready
    if not rag.is_rag_ready():
        yield {"type": "guides_retrieved", "content": "攻略库初始化中，跳过检索"}
        return

    queries = [f"{state.intent.city}旅行攻略", f"{state.intent.city}交通建议"]
    if state.intent.travelers:
        queries.append(f"{state.intent.city}{state.intent.travelers}旅行")

    all_guides = []
    for q in queries:
        results = rag.search_guides(state.intent.city, q, top_k=3)
        all_guides.extend(results)

    seen = set()
    state.city_guides = [g for g in all_guides if g not in seen and not seen.add(g)][:10]

    yield {"type": "guides_retrieved", "content": f"找到 {len(state.city_guides)} 条攻略"}


async def select_pois_and_hotels(state: AgentState) -> AsyncIterator[dict]:
    if not state.intent:
        return

    intent = state.intent
    yield {"type": "status", "content": f"正在搜索{intent.city}的景点和酒店..."}

    pois = await tools.search_pois(intent.city, limit=200)
    state.available_pois = pois

    hotels = await tools.search_hotels(intent.city, limit=30)
    state.available_hotels = hotels

    yield {"type": "data_loaded", "content": f"找到 {len(pois)} 个景点、{len(hotels)} 家酒店"}


async def select_hotel(state: AgentState) -> AsyncIterator[dict]:
    if not state.intent or not state.available_hotels:
        return

    intent = state.intent
    yield {"type": "status", "content": "正在为您选择最佳住宿..."}

    candidates = state.available_hotels
    if intent.hotel_area:
        area_hotels = [h for h in candidates if intent.hotel_area in h.area]
        if area_hotels:
            candidates = area_hotels

    hotel_list = "\n".join([
        f"- {h.name} (ID:{h.id}, 区域:{h.area}, 评分:{h.popularity})"
        for h in candidates[:15]
    ])

    must_visit_str = ", ".join(intent.must_visit) if intent.must_visit else "无"
    user_context = (
        f"城市: {intent.city}\n人群: {intent.travelers or '普通'}\n"
        f"预算: {intent.budget}\n必去: {must_visit_str}\n"
        f"酒店偏好: {intent.hotel_preference or '无'}\n区域: {intent.hotel_area or '不限'}\n\n"
        f"候选酒店:\n{hotel_list}"
    )

    try:
        data = await call_json(HOTEL_SELECTION_SYSTEM, user_context, state)
        hotel_id = data.get("hotel_id", "")
        reason = data.get("reason", "")

        for h in candidates:
            if h.id == hotel_id:
                state.selected_hotel = h
                yield {"type": "hotel_selected", "content": f"已选酒店: {h.name}", "reason": reason}
                return

        if candidates:
            state.selected_hotel = candidates[0]
            yield {"type": "hotel_selected", "content": f"已选酒店: {candidates[0].name}"}
    except Exception as e:
        logger.error(f"select_hotel failed: {e}")
        if candidates:
            state.selected_hotel = candidates[0]


async def plan_each_day(state: AgentState) -> AsyncIterator[dict]:
    if not state.intent:
        return

    intent = state.intent
    attractions = [p for p in state.available_pois if p.type == "attraction"]
    restaurants = [p for p in state.available_pois if p.type == "restaurant"]

    must_visit_pois = []
    if intent.must_visit:
        for mv in intent.must_visit:
            matches = [p for p in state.available_pois if mv in p.name]
            if matches:
                matches.sort(key=lambda p: (p.name != mv, len(p.name), -p.popularity))
                best = matches[0]
                if best not in must_visit_pois:
                    must_visit_pois.append(best)

    other = [p for p in attractions if p not in must_visit_pois]
    other.sort(key=lambda x: x.popularity, reverse=True)
    all_attractions = must_visit_pois + other

    guide_context = "\n".join(state.city_guides[:5]) if state.city_guides else ""

    for day_num in range(1, intent.days + 1):
        yield {"type": "status", "content": f"正在规划第 {day_num} 天..."}

        day_attractions = [a for i, a in enumerate(all_attractions) if i % intent.days == (day_num - 1) % intent.days]
        day_restaurants = [r for i, r in enumerate(restaurants) if i % intent.days == (day_num - 1) % intent.days]

        must_visit_ids = {p.id for p in must_visit_pois}
        attr_list = "\n".join([
            f"- {a.name} (ID:{a.id}, 区域:{a.area}, 评分:{a.popularity}, 时长:{a.visit_duration_minutes}分钟, {'【必去】' if a.id in must_visit_ids else ''}{a.description[:60] if a.description else ''})"
            for a in day_attractions[:20]
        ])
        rest_list = "\n".join([
            f"- {r.name} (ID:{r.id}, 区域:{r.area}, 类型:{r.meal_type})"
            for r in day_restaurants[:10]
        ])

        user_context = (
              f"第 {day_num} 天/{intent.days}天，节奏:{intent.pace}，人群:{intent.travelers or '普通'}\n"
              f"酒店:{state.selected_hotel.area if state.selected_hotel else '未定'}\n"
        )
        if must_visit_pois:
              must_names = [p.name for p in must_visit_pois]
              user_context += f"\n用户必去景点（必须安排，不可省略）: {chr(44).join(must_names)}\n"
        user_context += f"\n候选景点（标有【必去】的必须安排）:\n{attr_list}\n\n候选餐厅:\n{rest_list}\n"
        if guide_context:
            user_context += f"\n攻略参考:\n{guide_context}\n"

        try:
            stops_data = await call_json(DAY_PLANNING_SYSTEM, user_context, state)

            stops = []
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
                        break
                stops.append(stop)

            # Validate must_visit
            if must_visit_pois:
                must_visit_ids_today = {a.id for a in day_attractions if a.id in {p.id for p in must_visit_pois}}
                included_ids = {s.poi_id for s in stops}
                missing_ids = must_visit_ids_today - included_ids
                if missing_ids:
                    for p in day_attractions:
                        if p.id in missing_ids:
                            inject_stop = StopInfo(
                                slot="上午" if not any(s.slot == "上午" for s in stops) else "下午",
                                poi_id=p.id, poi_name=p.name, poi_type=p.type,
                                area=p.area, lat=p.lat, lng=p.lng,
                                start_minutes=540, end_minutes=540 + p.visit_duration_minutes,
                                visit_duration_minutes=p.visit_duration_minutes,
                                reason=f"用户必去: {p.name}", recommendation=p.recommendation,
                              )
                            stops.insert(0, inject_stop)
                            logger.info(f"Force-injected must_visit: {p.name}")

            day_plan = DayPlan(day=day_num, stops=stops, summary=f"第{day_num}天: {len(stops)}个行程")
            state.daily_plans.append(day_plan)
            yield {"type": "day_planned", "content": f"第 {day_num} 天: {len(stops)} 个行程", "day": day_num, "day_plan": day_plan.model_dump()}

        except Exception as e:
            logger.error(f"plan day {day_num} failed: {e}")
            state.errors.append(f"第{day_num}天规划失败: {e}")


async def optimize_routes(state: AgentState) -> AsyncIterator[dict]:
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
                            stop.travel_minutes_from_previous = opt_stop.get("travelMinutesFromPrevious", 0)
                            break
                day_plan.total_travel_minutes = optimized.get("totalTravelMinutes", 0)

    yield {"type": "routes_optimized", "content": "路线优化完成"}


async def assemble_result(state: AgentState) -> AsyncIterator[dict]:
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

    summary_context = f"城市:{intent.city}, {intent.days}天{intent.pace}节奏, 人群:{intent.travelers or '普通'}\n行程:{itinerary_text}\n"

    try:
        if LANGCHAIN_AVAILABLE:
            llm = get_llm_creative()
            resp = await llm.ainvoke([
                SystemMessage(content=ITINERARY_SUMMARY_SYSTEM),
                HumanMessage(content=summary_context),
            ])
            summary = resp.content.strip()
        else:
            summary = await _direct_llm_chat(ITINERARY_SUMMARY_SYSTEM, summary_context)
        state.llm_call_count += 1
    except Exception as e:
        logger.error(f"Summary failed: {e}")
        summary = f"{intent.city}{intent.days}天行程已生成"

    state.result = ItineraryResult(
        city=intent.city,
        days=state.daily_plans,
        hotel=state.selected_hotel,
        variant_name=f"{intent.pace}节奏方案",
        strategy=intent.strategy,
        alternatives=state.city_guides[:3],
        summary=summary,
    )

    cache.set_cached_itinerary(
        city=intent.city, days=intent.days, pace=intent.pace,
        strategy=intent.strategy, must_visit=intent.must_visit,
        itinerary=state.result.model_dump(),
    )

    yield {
        "type": "itinerary_complete",
        "content": summary,
        "itinerary": state.result.model_dump(),
        "llm_calls": state.llm_call_count,
    }


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_planning_pipeline(
    user_message: str,
    context: dict | None = None,
) -> AsyncIterator[dict]:
    """Run the full planning pipeline, yielding SSE events."""
    state = AgentState(user_message=user_message)

    # Quick intent parse for cache check
    try:
        data = await call_json(PARSE_INTENT_SYSTEM, user_message, state)
        intent = TripIntent(**data)
        cached = cache.get_cached_itinerary(
            intent.city, intent.days, intent.pace, intent.strategy, intent.must_visit,
        )
        if cached:
            yield {"type": "cache_hit", "content": "命中缓存", "itinerary": cached}
            return
    except Exception:
        pass

    # Full pipeline
    state = AgentState(user_message=user_message)

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
        except Exception as e:
            logger.error(f"Node {node.__name__} failed: {e}")
            state.errors.append(f"{node.__name__}: {e}")
            yield {"type": "error", "content": f"处理失败: {e}"}
