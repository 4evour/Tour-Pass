"""Tour Pass Multi-Agent System - API Adapter.

Key improvements:
- Graph is compiled once and reused across requests.
- thread_id is derived from the request (not hardcoded "default").
- LLM instance is created once at startup.
"""

import asyncio
import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv("agent/.env")
except ImportError:
    pass

from graph import build_tour_graph, create_initial_state
from agents.constants import resolve_city_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

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
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY not set")
        logger.info("Initialising LLM: %s @ %s", model, base_url)
        _llm = ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=0.3)
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
    if not raw_url:
        return ""
    if raw_url.startswith("images/"):
        return "/" + raw_url
    return "/" + raw_url


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
    trip_intent = state.get("trip_intent", {})
    daily_plans = state.get("daily_plans", [])
    hotel = state.get("selected_hotel", {})
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
    summary_parts = [f"{city}{days_count}天游"]
    if must_visit:
        summary_parts.append("必去: " + ", ".join(must_visit))

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

    return {
        "city": city,
        "days": days,
        "hotel": hotel_data,
        "summary": " | ".join(summary_parts),
        "variant_name": "AI推荐方案",
        "travel_tips": [],
        "alternatives": [],
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
    # Pre-initialise singletons
    _get_llm()
    _get_graph()
    yield
    logger.info("TourPass Multi-Agent service shutting down...")


app = FastAPI(
    title="TourPass Multi-Agent",
    description="AI-powered travel itinerary planning with multi-agent system",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve data/ directory as static files for images
app.mount("/data", StaticFiles(directory="data"), name="data")


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

            final_state = None
            async for event in graph.astream(initial_state, config, stream_mode="values"):
                final_state = event

                if event.get("trip_intent"):
                    city = event["trip_intent"].get("city", "")
                    yield make_sse_event("intent_parsed", {"type": "intent_parsed", "content": f"目的地: {city}"})

                if event.get("pois"):
                    yield make_sse_event("pois_found", {"type": "pois_found", "content": f"找到 {len(event['pois'])} 个景点"})

                if event.get("selected_hotel"):
                    name = event["selected_hotel"].get("name", "")
                    yield make_sse_event("hotel_selected", {"type": "hotel_selected", "content": f"推荐酒店: {name}"})

                if event.get("daily_plans"):
                    yield make_sse_event("schedule_created", {"type": "schedule_created", "content": f"创建 {len(event['daily_plans'])} 天行程"})

            if final_state:
                itinerary = convert_to_frontend_format(final_state)
                yield make_sse_event("itinerary", {"type": "itinerary", "itinerary": itinerary})
            else:
                yield make_sse_event("error", {"type": "error", "content": "Planning failed"})

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


@app.get("/agent/health")
async def health():
    return {"status": "ok", "version": "2.1.0", "agent": "multi-agent"}


@app.get("/agent/stats")
async def stats():
    return {
        "version": "2.1.0",
        "agent_type": "multi-agent",
        "agents": ["intent", "retrieve", "poi", "hotel", "weather", "restaurant", "scheduler", "reviewer", "ticket"],
        "llm_agents": ["intent", "weather", "reviewer"],
        "deterministic_agents": ["retrieve", "poi", "hotel", "restaurant", "scheduler", "ticket"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
