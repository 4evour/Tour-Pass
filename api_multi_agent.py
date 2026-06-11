"""Tour Pass Multi-Agent System - API Adapter."""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv('agent/.env')
except ImportError:
    pass

from graph import build_tour_graph, create_initial_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


class PlanRequest(BaseModel):
    message: str
    context: Optional[dict] = None


class PlanResponse(BaseModel):
    success: bool
    itinerary: Optional[dict] = None
    error: Optional[str] = None


def get_llm():
    """Get LLM instance using DeepSeek API."""
    from langchain_openai import ChatOpenAI
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY not set")
    
    logger.info("Using DeepSeek API: " + base_url)
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.3,
    )


def convert_to_frontend_format(state: dict) -> dict:
    """Convert multi-agent state to frontend-compatible format."""
    trip_intent = state.get("trip_intent", {})
    daily_plans = state.get("daily_plans", [])
    hotel = state.get("selected_hotel", {})
    
    slot_map = {
        "morning": "上午",
        "lunch": "中午",
        "afternoon": "下午",
        "dinner": "傍晚",
        "evening": "晚上",
    }
    
    days = []
    for day in daily_plans:
        stops = []
        for stop in day.get("stops", []):
            slot = stop.get("slot", "")
            stops.append({
                "slot": slot_map.get(slot, slot),
                "poi_name": stop.get("poi_name", ""),
                "poi_type": stop.get("poi_type", "attraction"),
                "area": stop.get("area", ""),
                "start_minutes": stop.get("start_minutes", 0),
                "end_minutes": stop.get("end_minutes", 0),
                "reason": stop.get("reason", ""),
            })
        
        days.append({
            "day": day.get("day", 0),
            "stops": stops,
            "summary": day.get("summary", ""),
        })
    
    city = trip_intent.get("city", "")
    days_count = trip_intent.get("days", 3)
    must_visit = trip_intent.get("must_visit", [])
    
    summary_parts = [city + str(days_count) + "天游"]
    if must_visit:
        summary_parts.append("必去: " + ", ".join(must_visit))
    
    return {
        "city": city,
        "days": days,
        "hotel": {
            "name": hotel.get("name", ""),
            "area": hotel.get("area", ""),
        } if hotel else None,
        "summary": " | ".join(summary_parts),
        "variant_name": "AI推荐方案",
        "travel_tips": [],
        "alternatives": [],
    }


def make_sse_event(event_type: str, data: dict) -> str:
    """Create SSE event string."""
    return "event: " + event_type + "\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("TourPass Multi-Agent service starting...")
    yield
    logger.info("TourPass Multi-Agent service shutting down...")


app = FastAPI(
    title="TourPass Multi-Agent",
    description="AI-powered travel itinerary planning with multi-agent system",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/agent/plan")
async def plan_itinerary(req: PlanRequest):
    """Generate a travel itinerary via Multi-Agent pipeline. Returns SSE stream."""
    
    async def event_stream():
        try:
            llm = get_llm()
            graph = build_tour_graph(llm, data_dir="data")
            initial_state = create_initial_state(req.message)
            config = {"configurable": {"thread_id": "default"}, "recursion_limit": 50}
            
            final_state = None
            async for event in graph.astream(initial_state, config, stream_mode="values"):
                final_state = event
                
                if "trip_intent" in event and event["trip_intent"]:
                    city = event["trip_intent"].get("city", "")
                    yield make_sse_event("intent_parsed", {"type": "intent_parsed", "content": "目的地: " + city})
                
                if "pois" in event and event["pois"]:
                    count = len(event["pois"])
                    yield make_sse_event("pois_found", {"type": "pois_found", "content": "找到 " + str(count) + " 个景点"})
                
                if "selected_hotel" in event and event["selected_hotel"]:
                    name = event["selected_hotel"].get("name", "")
                    yield make_sse_event("hotel_selected", {"type": "hotel_selected", "content": "推荐酒店: " + name})
                
                if "daily_plans" in event and event["daily_plans"]:
                    count = len(event["daily_plans"])
                    yield make_sse_event("schedule_created", {"type": "schedule_created", "content": "创建 " + str(count) + " 天行程"})
            
            if final_state:
                itinerary = convert_to_frontend_format(final_state)
                yield make_sse_event("itinerary", {"type": "itinerary", "itinerary": itinerary})
            else:
                yield make_sse_event("error", {"type": "error", "content": "Planning failed"})
        
        except Exception as e:
            logger.error("Pipeline error: " + str(e))
            yield make_sse_event("error", {"type": "error", "content": str(e)})
        
        finally:
            yield "event: done\ndata: {}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/agent/plan-sync")
async def plan_itinerary_sync(req: PlanRequest):
    """Generate itinerary synchronously."""
    try:
        llm = get_llm()
        graph = build_tour_graph(llm, data_dir="data")
        initial_state = create_initial_state(req.message)
        config = {"configurable": {"thread_id": "default"}, "recursion_limit": 50}
        
        final_state = None
        async for event in graph.astream(initial_state, config, stream_mode="values"):
            final_state = event
        
        if final_state:
            itinerary = convert_to_frontend_format(final_state)
            return PlanResponse(success=True, itinerary=itinerary)
        else:
            return PlanResponse(success=False, error="Planning failed")
    
    except Exception as e:
        logger.error("Pipeline error: " + str(e))
        return PlanResponse(success=False, error=str(e))


@app.get("/agent/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.0.0", "agent": "multi-agent"}


@app.get("/agent/stats")
async def stats():
    """Get agent statistics."""
    return {
        "version": "2.0.0",
        "agent_type": "multi-agent",
        "agents": ["intent", "poi", "hotel", "weather", "restaurant", "scheduler", "reviewer", "ticket"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
