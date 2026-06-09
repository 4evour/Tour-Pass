"""FastAPI main entry point with SSE streaming endpoints."""
from __future__ import annotations
import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .config import HOST, PORT
from .models import PlanRequest, ChatRequest
try:
    from .graph import run_planning_pipeline
except ImportError:
    from .graph_simple import run_planning_pipeline
from . import cache
from . import tools
from . import rag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("TourPass Agent service starting...")
    rag.init_rag()
    yield
    logger.info("TourPass Agent service shutting down...")
    await tools.close_client()


app = FastAPI(
    title="TourPass Agent",
    description="AI-powered travel itinerary planning agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── SSE streaming endpoint ────────────────────────────────────────────────────

@app.post("/agent/plan")
async def plan_itinerary(req: PlanRequest):
    """Generate a travel itinerary via Agent pipeline. Returns SSE stream."""

    async def event_stream():
        try:
            async for event in run_planning_pipeline(
                user_message=req.message,
                context=req.context,
            ):
                event_type = event.get("type", "message")
                data = json.dumps(event, ensure_ascii=False, default=str)
                yield f"event: {event_type}\ndata: {data}\n\n"
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            error_data = json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"
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


# ── Non-streaming endpoint (for quick requests) ──────────────────────────────

@app.post("/agent/plan-sync")
async def plan_itinerary_sync(req: PlanRequest):
    """Generate itinerary synchronously (for cached results or simple requests)."""
    # Check cache first
    try:
        from .graph import get_llm, _llm_json, PARSE_INTENT_SYSTEM
    except ImportError:
        from .graph_simple import get_llm, _llm_json, PARSE_INTENT_SYSTEM
    from .models import TripIntent, AgentState

    try:
        state = AgentState(user_message=req.message)
        llm = get_llm()
        data = await _llm_json(llm, PARSE_INTENT_SYSTEM, req.message, state)
        intent = TripIntent(**data)

        cached = cache.get_cached_itinerary(
            city=intent.city, days=intent.days, pace=intent.pace,
            strategy=intent.strategy, must_visit=intent.must_visit,
        )
        if cached:
            return {"status": "ok", "source": "cache", "itinerary": cached}
    except Exception:
        pass

    # Fallback: run full pipeline and collect all events
    events = []
    async for event in run_planning_pipeline(req.message, req.context):
        events.append(event)

    # Extract final itinerary from events
    itinerary = None
    for e in reversed(events):
        if e.get("type") in ("itinerary_complete", "cache_hit"):
            itinerary = e.get("itinerary")
            break

    return {
        "status": "ok",
        "source": "agent",
        "itinerary": itinerary,
        "events": events,
    }


# ── Chat endpoint (for modifying existing itinerary) ──────────────────────────

@app.post("/agent/chat")
async def chat_with_agent(req: ChatRequest):
    """Chat with the agent to modify or ask about an itinerary."""
    from .graph import get_llm
    from langchain_core.messages import HumanMessage, SystemMessage
    from .prompts import CHAT_SYSTEM

    # Build context
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
    for msg in req.history[-5:]:  # Last 5 messages
        role = msg.get("role", "user")
        content = msg.get("content", "")
        history_text += f"{role}: {content}\n"

    user_prompt = f"{history_text}\n{chr(10).join(context_parts)}\n\n用户: {req.message}"

    llm = get_llm()
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=CHAT_SYSTEM),
            HumanMessage(content=user_prompt),
        ])
        reply = resp.content.strip()

        # Try to parse as JSON action
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
        logger.error(f"Chat failed: {e}")
        return {"status": "error", "reply": "抱歉，处理失败，请稍后重试。"}


# ── Hot itineraries endpoints ─────────────────────────────────────────────────

@app.get("/agent/hot")
async def list_hot(city: str = "", limit: int = 20):
    """List available hot itineraries."""
    items = cache.list_hot_itineraries(city=city, limit=limit)
    return {"status": "ok", "items": items}


@app.get("/agent/hot/{city}/{days}/{preference}")
async def get_hot(city: str, days: int, preference: str):
    """Get a specific hot itinerary."""
    item = cache.get_hot_itinerary(city, days, preference)
    if item:
        return {"status": "ok", "item": item}
    return {"status": "not_found"}, 404


# ── RAG management endpoints ──────────────────────────────────────────────────

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

        n1 = rag.ingest_city_guide(c, guide_path)
        n2 = rag.ingest_guidebook(c, guidebook_path)
        results[c] = {"guide_chunks": n1, "guidebook_chunks": n2}

    return {"status": "ok", "results": results}


# ── Health and stats ──────────────────────────────────────────────────────────

@app.get("/agent/health")
async def health():
    return {"status": "ok", "service": "tourpass-agent"}


@app.get("/agent/stats")
async def stats():
    return {
        "status": "ok",
        "cache": cache.get_cache_stats(),
    }


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)




