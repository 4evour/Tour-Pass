"""Tour Pass Multi-Agent System - API Adapter.

Key improvements over the legacy single-agent adapter:
- Graph is compiled once and reused across requests.
- thread_id is derived from the request (not hardcoded "default").
- LLM instance is created once at startup.
- Fine-grained SSE events from each agent via sse_events state field.
- Itinerary-level caching (Redis + in-memory) with cache-hit fast path.
- Chat, hot-itinerary, and RAG management endpoints.
"""

import asyncio
import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv("agent/.env")
except ImportError:
    pass

from graph import build_tour_graph, create_initial_state
from agents.constants import resolve_city_dir
from agents.config import HOST, PORT
from tools.cache import (
    get_cached_itinerary,
    set_cached_itinerary,
    list_hot_itineraries,
    get_hot_itinerary,
    get_cache_stats,
)
from tools import rag as rag_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

_VERSION = "2.0.0"

# ---------------------------------------------------------------------------
# Module-level singletons (initialised at startup)
# ---------------------------------------------------------------------------

_llm = None
_graph = None
_poi_cache: dict[str, dict[str, dict]] = {}
_data_dir = Path("data")


def _get_llm():
    """Get or create the shared LLM instance."""
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI
        from agents.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_TEMPERATURE
        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY not set")
        logger.info("Initialising LLM: %s @ %s", DEEPSEEK_MODEL, DEEPSEEK_BASE_URL)
        _llm = ChatOpenAI(
            model=DEEPSEEK_MODEL,
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            temperature=LLM_TEMPERATURE,
        )
    return _llm


def _get_graph():
    """Get or compile the shared graph (compiled once, reused)."""
    global _graph
    if _graph is None:
        _graph = build_tour_graph(_get_llm(), data_dir="data")
        logger.info("Graph compiled and cached")
    return _graph


# ---------------------------------------------------------------------------
# POI lookup cache
# ---------------------------------------------------------------------------

def _load_city_pois(city: str) -> dict[str, dict]:
    if city in _poi_cache:
        return _poi_cache[city]
    city_dir = resolve_city_dir(_data_dir, city)
    poi_file = city_dir / "pois.json"
    if not poi_file.exists():
        _poi_cache[city] = {}
        return {}
    try:
        with open(poi_file, "r", encoding="utf-8") as f:
            pois = json.load(f)
        name_map = {p.get("name", ""): p for p in pois}
        _poi_cache[city] = name_map
        logger.info("Cached %d POIs for %s", len(name_map), city)
        return name_map
    except Exception as e:
        logger.error("Failed to load POIs for %s: %s", city, e)
        _poi_cache[city] = {}
        return {}


def _resolve_image_path(raw_url: str) -> str:
    """Resolve a stored image path to a web-accessible URL.

    Stored paths look like ``images/beijing/images/amap_xxx/1.jpg``.
    With ``ASSET_BASE_URL`` or ``TOURPASS_ASSET_BASE_URL`` configured,
    the stored relative path is resolved against the CDN/R2 custom domain.

    Without a CDN base URL, returns ``/data/{city}/images/{poi_id}/1.jpg``
    for local paths, or the original URL for external URLs.
    """
    if not raw_url:
        return ""
    if raw_url.startswith(("http://", "https://", "data:")):
        return raw_url

    asset_base = (os.environ.get("ASSET_BASE_URL") or os.environ.get("TOURPASS_ASSET_BASE_URL") or "").rstrip("/")
    path = raw_url.lstrip("/")
    if asset_base:
        return f"{asset_base}/{path}"

    if path.startswith("images/"):
        path = path[len("images/"):]
    return "/data/" + path


def _xhs_route_stats() -> dict:
    stats = {"cities": 0, "routes": 0, "by_city": {}}
    if not _data_dir.exists():
        return stats
    for city_dir in _data_dir.iterdir():
        if not city_dir.is_dir():
            continue
        route_file = city_dir / "xhs_routes.json"
        if not route_file.exists():
            continue
        try:
            with open(route_file, "r", encoding="utf-8") as f:
                routes = json.load(f)
            count = len(routes) if isinstance(routes, list) else 0
        except Exception:
            count = 0
        stats["cities"] += 1
        stats["routes"] += count
        stats["by_city"][city_dir.name] = count
    return stats


def _minutes_to_time(minutes: int) -> str:
    if minutes <= 0:
        return ""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _enrich_stop(stop: dict, city_pois: dict[str, dict]) -> dict:
    name = stop.get("poi_name", "")
    poi = city_pois.get(name, {})
    image_url = ""
    images: list[str] = []
    if poi:
        raw_url = poi.get("image_url", "")
        image_url = _resolve_image_path(raw_url)
        for img in (poi.get("images") or [])[:3]:
            img_url = _resolve_image_path(img.get("url", ""))
            if img_url:
                images.append(img_url)
    if not image_url and images:
        image_url = images[0]

    guide_text = (poi.get("guide_text") or "").strip()
    description = (poi.get("description") or "").strip()
    if not guide_text and description:
        guide_text = description

    return {
        **stop,
        "image_url": image_url,
        "images": images,
        "guide_text": guide_text,
        "recommendation": (poi.get("recommendation") or "").strip(),
        "start_time": _minutes_to_time(stop.get("start_minutes", 0)),
        "end_time": _minutes_to_time(stop.get("end_minutes", 0)),
        "open_time": poi.get("open_time", ""),
        "close_time": poi.get("close_time", ""),
        "visit_duration_minutes": poi.get("visit_duration_minutes", 60),
        "lat": poi.get("lat", 0),
        "lng": poi.get("lng", 0),
        "popularity": poi.get("popularity", 0),
    }


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class PlanRequest(BaseModel):
    message: str
    context: Optional[dict] = None


class PlanResponse(BaseModel):
    success: bool
    itinerary: Optional[dict] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Conversion to frontend format
# ---------------------------------------------------------------------------

def convert_to_frontend_format(state: dict) -> dict:
    trip_intent = state.get("trip_intent") or {}
    daily_plans = state.get("daily_plans", [])
    hotel = state.get("selected_hotel") or {}
    city = trip_intent.get("city", "")
    city_pois = _load_city_pois(city)

    slot_map = {
        "morning": "上午", "lunch": "中午",
        "afternoon": "下午", "dinner": "傍晚", "evening": "晚上",
    }

    days: list[dict] = []
    for day in daily_plans:
        stops: list[dict] = []
        for stop in day.get("stops", []):
            slot = stop.get("slot", "")
            enriched = _enrich_stop({
                "slot": slot_map.get(slot, slot),
                "poi_name": stop.get("poi_name", ""),
                "poi_type": stop.get("poi_type", "attraction"),
                "area": stop.get("area", ""),
                "start_minutes": stop.get("start_minutes", 0),
                "end_minutes": stop.get("end_minutes", 0),
                "reason": stop.get("reason", ""),
            }, city_pois)
            stops.append(enriched)
        days.append({"day": day.get("day", 0), "stops": stops, "summary": day.get("summary", "")})

    days_count = trip_intent.get("days", 3)
    must_visit = trip_intent.get("must_visit", [])
    strategy = trip_intent.get("strategy", "balanced")

    # Use LLM-generated summary if available, otherwise build a fallback
    summary = state.get("summary", "")
    if not summary:
        summary_parts = [f"{city}{days_count}天游"]
        if must_visit:
            summary_parts.append("必去: " + ", ".join(must_visit))
        summary = " | ".join(summary_parts)

    # Strategy → variant name mapping
    variant_names = {
        "balanced": "AI推荐方案",
        "culture": "文化深度方案",
        "culinary": "美食探索方案",
        "nature": "自然风光方案",
    }
    variant_name = variant_names.get(strategy, "AI推荐方案")

    hotel_data = None
    if hotel:
        hotel_name = hotel.get("name", "")
        hotel_poi = city_pois.get(hotel_name, {})
        hotel_data = {
            "name": hotel_name,
            "area": hotel.get("area", ""),
            "image_url": _resolve_image_path(hotel_poi.get("image_url", "")),
            "lat": hotel_poi.get("lat", 0),
            "lng": hotel_poi.get("lng", 0),
        }

    # Travel tips from city_guides
    city_guides = state.get("city_guides", [])
    travel_tips = city_guides[:3] if city_guides else []

    return {
        "city": city,
        "days": days,
        "hotel": hotel_data,
        "summary": summary,
        "variant_name": variant_name,
        "travel_tips": travel_tips,
        "alternatives": [],
        "must_visit_coverage": state.get("must_visit_coverage", []),
    }


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------

def make_sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TourPass Multi-Agent service starting...")
    # Keep startup lightweight on Render free tier. LLM, graph, and RAG are
    # initialised lazily on the first planning request so health checks can
    # come up first.
    logger.info("LLM/Graph will be initialised lazily on first planning request")
    logger.info("RAG will be initialised lazily on first retrieval request")
    yield
    logger.info("TourPass Multi-Agent service shutting down...")


app = FastAPI(
    title="TourPass Multi-Agent",
    description="AI-powered travel itinerary planning with multi-agent system",
    version=_VERSION,
    lifespan=lifespan,
)

def _allowed_origins() -> list[str]:
    raw = os.environ.get("AGENT_ALLOWED_ORIGINS") or os.environ.get("TOURPASS_ALLOWED_ORIGINS") or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


_cors_origins = _allowed_origins()
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials="*" not in _cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}


@app.get("/data/{city}/images/{asset_path:path}")
async def get_data_image(city: str, asset_path: str):
    """Serve only whitelisted image files from data/{city}/images."""
    if not city.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=404, detail="image not found")
    if ".." in asset_path or "\\" in asset_path:
        raise HTTPException(status_code=404, detail="image not found")
    if Path(asset_path).suffix.lower() not in _IMAGE_EXTENSIONS:
        raise HTTPException(status_code=404, detail="image not found")

    root = (_data_dir / city / "images").resolve()
    file_path = (root / asset_path).resolve()
    try:
        file_path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="image not found")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(file_path)


def _make_thread_id(message: str) -> str:
    """Derive a per-request thread ID from the message content.

    This avoids the old bug where all users shared 'default' thread,
    causing state pollution across requests.
    """
    return hashlib.sha256(message.encode()).hexdigest()[:16]


@app.post("/agent/plan")
async def plan_itinerary(req: PlanRequest):
    """Generate a travel itinerary via Multi-Agent pipeline. Returns SSE stream."""

    async def event_stream():
        try:
            graph = _get_graph()
            initial_state = create_initial_state(req.message)
            thread_id = _make_thread_id(req.message)
            config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

            # Immediate startup feedback
            yield make_sse_event("status", {
                "type": "status",
                "content": "正在启动智能规划引擎...",
            })

            final_state = None
            prev_sse_count = 0  # Track how many sse_events we've already emitted
            prev_state_keys: set[str] = set()  # Track which keys changed

            async for event in graph.astream(initial_state, config, stream_mode="values"):
                final_state = event

                # Detect which stage just completed by checking new keys
                current_keys = {k for k, v in event.items() if v}
                new_keys = current_keys - prev_state_keys
                prev_state_keys = current_keys

                # Emit stage-level progress for long-running stages
                if "trip_intent" in new_keys and event.get("trip_intent"):
                    city = event["trip_intent"].get("city", "")
                    days = event["trip_intent"].get("days", 3)
                    est_seconds = max(10, days * 5 + 8)
                    yield make_sse_event("status", {
                        "type": "status",
                        "content": f"已解析需求：{city}{days}天行程，预计需要约{est_seconds}秒...",
                    })

                if "city_guides" in new_keys and event.get("city_guides"):
                    yield make_sse_event("status", {
                        "type": "status",
                        "content": "正在搜索景点、酒店、餐厅和天气信息...",
                    })

                if "pois" in new_keys and "selected_hotel" in new_keys:
                    yield make_sse_event("status", {
                        "type": "status",
                        "content": "数据收集完成，正在智能编排行程...",
                    })

                # Emit new sse_events accumulated by agents
                sse_events = event.get("sse_events", [])
                if sse_events and len(sse_events) > prev_sse_count:
                    for ev in sse_events[prev_sse_count:]:
                        ev_type = ev.get("type", "message")
                        yield make_sse_event(ev_type, ev)
                    prev_sse_count = len(sse_events)

            if final_state:
                # Check for critical errors
                errors = final_state.get("errors", [])
                if errors:
                    yield make_sse_event("warnings", {
                        "type": "warnings",
                        "content": f"规划完成，但有 {len(errors)} 个警告",
                        "errors": errors[:5],
                    })

                itinerary = convert_to_frontend_format(final_state)

                # Write to cache
                intent = final_state.get("trip_intent") or {}
                if intent.get("city"):
                    set_cached_itinerary(
                        city=intent.get("city", ""),
                        days=intent.get("days", 3),
                        pace=intent.get("pace", "balanced"),
                        strategy=intent.get("strategy", "balanced"),
                        must_visit=intent.get("must_visit", []),
                        itinerary=itinerary,
                    )

                yield make_sse_event("itinerary", {"type": "itinerary", "itinerary": itinerary})
            else:
                yield make_sse_event("error", {"type": "error", "content": "Planning failed"})

        except RuntimeError as e:
            # Critical agent failure — surface specific error
            logger.error("Critical pipeline error: %s", e)
            yield make_sse_event("error", {
                "type": "error",
                "content": f"规划失败: {e}",
            })
        except Exception as e:
            logger.error("Pipeline error: %s", e)
            yield make_sse_event("error", {"type": "error", "content": str(e)})
        finally:
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/agent/plan-sync")
async def plan_itinerary_sync(req: PlanRequest):
    """Generate itinerary synchronously."""
    # Cache-first: try to resolve intent and check cache before running full pipeline
    try:
        from agents.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_TEMPERATURE
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        _intent_llm = ChatOpenAI(
            model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL, temperature=LLM_TEMPERATURE,
        )
        intent_resp = await _intent_llm.ainvoke([
            SystemMessage(content="Parse the user's travel request. Reply with JSON only: {\"city\":\"\",\"days\":3,\"pace\":\"balanced\",\"strategy\":\"balanced\",\"must_visit\":[]}"),
            HumanMessage(content=req.message),
        ])
        import json as _json, re as _re
        _text = intent_resp.content.strip()
        _m = _re.search(r'\{.*\}', _text, _re.DOTALL)
        if _m:
            _intent = _json.loads(_m.group())
            _cached = get_cached_itinerary(
                city=_intent.get("city", ""),
                days=_intent.get("days", 3),
                pace=_intent.get("pace", "balanced"),
                strategy=_intent.get("strategy", "balanced"),
                must_visit=_intent.get("must_visit", []),
            )
            if _cached:
                return PlanResponse(success=True, itinerary=_cached)
    except Exception:
        pass  # Cache miss or intent parse failed — fall through to full pipeline

    try:
        graph = _get_graph()
        initial_state = create_initial_state(req.message)
        thread_id = _make_thread_id(req.message)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

        final_state = None
        async for event in graph.astream(initial_state, config, stream_mode="values"):
            final_state = event

        if final_state:
            itinerary = convert_to_frontend_format(final_state)
            return PlanResponse(success=True, itinerary=itinerary)
        return PlanResponse(success=False, error="Planning failed")
    except Exception as e:
        logger.error("Pipeline error: %s", e)
        return PlanResponse(success=False, error=str(e))


@app.get("/agent/ping")
async def ping():
    """Minimal health check — no imports, no dependencies."""
    return {"ok": True, "ts": __import__("time").time()}


@app.get("/agent/health")
async def health():
    result = {
        "status": "ok",
        "version": _VERSION,
        "agent": "multi-agent",
    }
    try:
        result["rag"] = rag_module.get_index_stats()
    except Exception as e:
        result["rag_error"] = str(e)
    try:
        result["xhs"] = _xhs_route_stats()
    except Exception as e:
        result["xhs_error"] = str(e)
    return result


# ---------------------------------------------------------------------------
# Multi-candidate plan generation (parallel strategies)
# ---------------------------------------------------------------------------


async def _run_single_plan(message: str, strategy_override: str = "") -> Optional[dict]:
    """Run the full planning graph for a single strategy. Returns final state or None."""
    graph = _get_graph()
    initial_state = create_initial_state(message)
    if strategy_override:
        # Override strategy in initial state (will be parsed by IntentAgent)
        initial_state["_strategy_hint"] = strategy_override
    thread_id = _make_thread_id(f"{message}:{strategy_override}")
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

    final_state = None
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        final_state = event

    return final_state


class MultiPlanRequest(BaseModel):
    message: str
    strategies: list[str] = ["balanced", "culture", "culinary"]
    context: Optional[dict] = None


@app.post("/agent/plan-multi")
async def plan_multi_itineraries(req: MultiPlanRequest):
    """Generate multiple itinerary candidates with different strategies in parallel.

    Returns SSE stream with each candidate as it completes.
    """

    async def event_stream():
        try:
            yield make_sse_event("status", {
                "type": "status",
                "content": f"正在生成 {len(req.strategies)} 套方案...",
            })

            # Run all strategies in parallel
            tasks = [
                _run_single_plan(req.message, strategy_override=s)
                for s in req.strategies
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            candidates = []
            for strategy, result in zip(req.strategies, results):
                if isinstance(result, Exception):
                    logger.warning("Strategy %s failed: %s", strategy, result)
                    yield make_sse_event("warning", {
                        "type": "warning",
                        "content": f"⚠ {strategy} 方案生成失败: {result}",
                    })
                    continue
                if result is None:
                    continue

                itinerary = convert_to_frontend_format(result)
                itinerary["strategy"] = strategy
                candidates.append(itinerary)

                yield make_sse_event("candidate", {
                    "type": "candidate",
                    "strategy": strategy,
                    "itinerary": itinerary,
                })

            if candidates:
                yield make_sse_event("multi_complete", {
                    "type": "multi_complete",
                    "candidates": candidates,
                    "count": len(candidates),
                })
            else:
                yield make_sse_event("error", {
                    "type": "error",
                    "content": "所有方案生成失败",
                })

        except Exception as e:
            logger.error("Multi-plan error: %s", e)
            yield make_sse_event("error", {"type": "error", "content": str(e)})
        finally:
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/agent/stats")
async def stats():
    return {
        "version": _VERSION,
        "agent_type": "multi-agent",
        "agents": [
            "intent", "retrieve", "poi", "hotel", "weather",
            "restaurant", "scheduler", "reviewer", "ticket", "summary",
        ],
        "llm_agents": ["intent", "hotel", "weather", "reviewer", "summary"],
        "deterministic_agents": ["retrieve", "poi", "restaurant", "scheduler", "ticket"],
        "cache": get_cache_stats(),
        "rag": rag_module.get_index_stats(),
        "xhs": _xhs_route_stats(),
    }


# ── Chat endpoint (migrated from agent/main.py) ────────────────────────────────

CHAT_SYSTEM = """你是 Tour Pass AI 旅行助手。你可以帮用户：
1. 修改当前行程（替换景点、调整时间、增减天数）
2. 回答关于行程的问题（附近有什么好吃的、下午还有空余时间吗）
3. 提供旅行建议（天气、交通、注意事项）

回复要求：
- 简洁自然，像朋友聊天
- 如果用户要修改行程，输出修改后的完整行程 JSON
- 如果是普通问答，直接回答

当需要修改行程时，输出格式：
```json
{"action": "modify", "changes": [{"day": 1, "old_poi_id": "xxx", "new_poi_id": "yyy"}]}
```"""


class ChatRequest(BaseModel):
    message: str
    itinerary: Optional[dict] = None
    history: list[dict] = []


@app.post("/agent/chat")
async def chat_with_agent(req: ChatRequest):
    """Chat with the agent to modify or ask about an itinerary."""
    from langchain_core.messages import HumanMessage, SystemMessage

    context_parts = []
    if req.itinerary:
        city = req.itinerary.get("city", "")
        days = req.itinerary.get("days", [])
        context_parts.append(f"当前行程: {city}, {len(days)}天")
        for d in days:
            stops = d.get("stops", [])
            stop_names = [s.get("poi_name", "") for s in stops]
            context_parts.append(f"  第{d.get('day', '?')}天: {', '.join(stop_names)}")

    history_text = ""
    for msg in req.history[-5:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        history_text += f"{role}: {content}\n"

    user_prompt = f"{history_text}\n{chr(10).join(context_parts)}\n\n用户: {req.message}"

    llm = _get_llm()
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=CHAT_SYSTEM),
            HumanMessage(content=user_prompt),
        ])
        reply = resp.content.strip()

        try:
            if "```json" in reply:
                json_str = reply.split("```json")[1].split("```")[0].strip()
            elif "```" in reply:
                json_str = reply.split("```")[1].split("```")[0].strip()
            else:
                json_str = reply

            action = json.loads(json_str)
            if isinstance(action, dict) and action.get("action") == "modify":
                return {"status": "ok", "reply": reply, "action": action}
        except (json.JSONDecodeError, IndexError):
            pass

        return {"status": "ok", "reply": reply}
    except Exception as e:
        logger.error("Chat failed: %s", e)
        return {"status": "error", "reply": "抱歉，处理失败，请稍后重试。"}


# ── Hot itineraries endpoints (migrated from agent/main.py) ──────────────────

@app.get("/agent/hot")
async def list_hot(city: str = "", limit: int = 20):
    """List available hot itineraries."""
    items = list_hot_itineraries(city=city, limit=limit)
    return {"status": "ok", "items": items}


@app.get("/agent/hot/{city}/{days}/{preference}")
async def get_hot(city: str, days: int, preference: str):
    """Get a specific hot itinerary."""
    item = get_hot_itinerary(city, days, preference)
    if item:
        return {"status": "ok", "item": item}
    return {"status": "not_found"}


# ── RAG management endpoints (migrated from agent/main.py) ─────────────────────

@app.post("/agent/rag/ingest")
async def ingest_guides(city: str = ""):
    """Ingest city guides into RAG. If city is empty, ingest all."""
    import os
    cities_to_ingest = [city] if city else [
        d for d in os.listdir("data")
        if os.path.isdir(os.path.join("data", d))
    ]

    results = {}
    for c in cities_to_ingest:
        guide_path = os.path.join("data", c, "city_guide.json")
        guidebook_path = os.path.join("data", c, "guidebook.json")

        n1 = rag_module.ingest_city_guide(c, guide_path)
        n2 = rag_module.ingest_guidebook(c, guidebook_path)
        results[c] = {"guide_chunks": n1, "guidebook_chunks": n2}

    return {"status": "ok", "results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
