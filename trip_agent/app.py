from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .contracts import ChatRequest
from .runtime import TripRuntime

runtime: TripRuntime | None = None
STATIC_DIR = Path(__file__).parent / "static"
load_dotenv(os.environ.get("TRIP_AGENT_ENV_FILE", ".env"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global runtime
    runtime = TripRuntime()
    yield
    await runtime.close()
    runtime = None


app = FastAPI(title="Tour Pass Trip Agent", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "trip-agent",
        "version": "0.1.0",
        "runtime": runtime.health() if runtime else {"status": "not_initialized"},
    }


@app.post("/chat")
async def chat(request: ChatRequest) -> dict:
    if runtime is None:
        raise HTTPException(status_code=503, detail="runtime not initialized")
    if not runtime.llm.available:
        raise HTTPException(
            status_code=503, detail="TRIP_AGENT_LLM_KEY is not configured"
        )
    try:
        result = await asyncio.wait_for(
            runtime.agent.run(request.message, request.session_id),
            timeout=runtime.request_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Trip Agent 规划超时") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Trip Agent 规划失败：{exc}"
        ) from exc
    return result.model_dump(mode="json")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "trip_agent.app:app",
        host="127.0.0.1",
        port=int(os.environ.get("TRIP_AGENT_PORT", "8123")),
        reload=False,
    )
