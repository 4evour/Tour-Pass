from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .auth import Identity, IssuedSession
from .contracts import (
    ChatRequest,
    LoginRequest,
    RegisterRequest,
    SessionDetailResponse,
    SessionListResponse,
    StreamError,
    StreamErrorDetail,
    StreamProgress,
    StreamResult,
)
from .observability import log_event
from .runtime import TripRuntime

runtime: TripRuntime | None = None
STATIC_DIR = Path(__file__).parent / "static"
load_dotenv(os.environ.get("TRIP_AGENT_ENV_FILE", ".env"))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global runtime
    runtime = TripRuntime()
    yield
    await runtime.close()
    runtime = None


app = FastAPI(title="Tour Pass Trip Agent", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if os.environ.get("TRIP_AGENT_SECURE_COOKIES", "").lower() in {"1", "true", "yes"}:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    response.headers["X-Request-Id"] = uuid.uuid4().hex
    return response


def active_runtime() -> TripRuntime:
    if runtime is None:
        raise HTTPException(status_code=503, detail="runtime not initialized")
    return runtime


def resolve_identity(request: Request) -> tuple[Identity, IssuedSession | None]:
    resolved = active_runtime().auth.resolve(request)
    if isinstance(resolved, IssuedSession):
        return resolved.identity, resolved
    return resolved, None


def identity_payload(identity: Identity) -> dict:
    current = active_runtime()
    remaining, limit = current.auth.quota(identity)
    return {
        "authenticated": identity.kind == "user",
        "user": {"username": identity.username, "role": identity.role}
        if identity.kind == "user"
        else None,
        "quota": {"remaining": remaining, "limit": limit},
    }


def attach_issued(response: Response, issued: IssuedSession | None) -> None:
    if issued:
        active_runtime().auth.set_cookies(response, issued)


@app.get("/")
@app.get("/explore")
@app.get("/p/{public_slug}")
async def index(public_slug: str | None = None) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "trip-agent",
        "version": "0.2.0",
        "runtime": runtime.health() if runtime else {"status": "not_initialized"},
    }


@app.get("/api/auth/session")
async def auth_session(request: Request, response: Response) -> dict:
    identity, issued = resolve_identity(request)
    attach_issued(response, issued)
    return identity_payload(identity)


@app.post("/api/auth/register", status_code=201)
async def register(
    payload: RegisterRequest, request: Request, response: Response
) -> dict:
    current = active_runtime()
    current.auth.require_csrf(request)
    current.auth.check_auth_rate(current.auth.client_ip(request))
    identity, _ = resolve_identity(request)
    issued = current.auth.register(payload.username, payload.password, identity)
    if identity.kind == "guest":
        current.store.claim_guest_trips(identity.id, issued.identity.id)
    current.auth.set_cookies(response, issued)
    return identity_payload(issued.identity)


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    current = active_runtime()
    current.auth.require_csrf(request)
    identity, _ = resolve_identity(request)
    issued = current.auth.login(
        payload.username, payload.password, current.auth.client_ip(request)
    )
    if identity.kind == "guest":
        current.store.claim_guest_trips(identity.id, issued.identity.id)
    current.auth.set_cookies(response, issued)
    return identity_payload(issued.identity)


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response) -> dict:
    current = active_runtime()
    current.auth.require_csrf(request)
    issued = current.auth.logout(request)
    current.auth.set_cookies(response, issued)
    return identity_payload(issued.identity)


@app.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions(
    request: Request, response: Response, limit: int = Query(default=50, ge=1, le=100)
) -> SessionListResponse:
    identity, issued = resolve_identity(request)
    attach_issued(response, issued)
    return SessionListResponse(
        sessions=active_runtime().store.list_sessions(identity.owner, limit)
    )


@app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str, request: Request, response: Response
) -> SessionDetailResponse:
    identity, issued = resolve_identity(request)
    attach_issued(response, issued)
    if len(session_id) > 80:
        raise HTTPException(status_code=404, detail="行程不存在")
    session = active_runtime().store.get_session(session_id, identity.owner)
    if session is None:
        raise HTTPException(status_code=404, detail="行程不存在")
    log_event("session_loaded", session_id=session_id, owner_type=identity.kind)
    return SessionDetailResponse.model_validate(session)


@app.post("/api/sessions/{session_id}/publish")
async def publish_session(session_id: str, request: Request) -> dict:
    current = active_runtime()
    current.auth.require_csrf(request)
    identity, _ = resolve_identity(request)
    try:
        return current.store.publish(session_id, identity.owner)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/sessions/{session_id}/publish", status_code=204)
async def unpublish_session(session_id: str, request: Request) -> Response:
    current = active_runtime()
    current.auth.require_csrf(request)
    identity, _ = resolve_identity(request)
    if not current.store.unpublish(session_id, identity.owner):
        raise HTTPException(status_code=404, detail="分享不存在")
    return Response(status_code=204)


@app.get("/api/public/itineraries")
async def public_itineraries(
    city: str | None = Query(default=None, max_length=80),
    days: int | None = Query(default=None, ge=1, le=30),
    limit: int = Query(default=30, ge=1, le=50),
) -> dict:
    return {
        "items": active_runtime().store.list_public(city=city, days=days, limit=limit)
    }


@app.get("/api/public/itineraries/{public_slug}")
async def public_itinerary(public_slug: str) -> dict:
    if len(public_slug) != 20:
        raise HTTPException(status_code=404, detail="公开行程不存在")
    item = active_runtime().store.get_public(public_slug)
    if item is None:
        raise HTTPException(status_code=404, detail="公开行程不存在")
    return item


@app.post("/chat")
async def chat(payload: ChatRequest, request: Request, response: Response) -> dict:
    current = active_runtime()
    current.auth.require_csrf(request)
    identity, issued = resolve_identity(request)
    attach_issued(response, issued)
    if not current.llm.available:
        raise HTTPException(
            status_code=503, detail="TRIP_AGENT_LLM_KEY is not configured"
        )
    remaining, _ = current.auth.consume_quota(identity, request)
    response.headers["X-Query-Remaining"] = str(remaining)
    try:
        result = await asyncio.wait_for(
            current.agent.run(
                payload.message, payload.session_id, owner=identity.owner
            ),
            timeout=current.request_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Trip Agent 规划超时") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="行程不存在") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Trip Agent 规划失败：{type(exc).__name__}"
        ) from exc
    return result.model_dump(mode="json")


async def stream_chat_events(
    payload: ChatRequest,
    current: TripRuntime,
    owner: tuple[str, str] = ("guest", "local"),
) -> AsyncIterator[str]:
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
    trace_context: dict[str, object] = {}

    def publish_progress(event: dict) -> None:
        if event.get("type") == "run_started":
            trace_context["run_id"] = event.get("run_id")
            trace_context["session_id"] = event.get("session_id")
        queue.put_nowait(("progress", event))

    async def produce() -> None:
        try:
            result = await asyncio.wait_for(
                current.agent.run(
                    payload.message,
                    payload.session_id,
                    on_event=publish_progress,
                    **({} if owner == ("guest", "local") else {"owner": owner}),
                ),
                timeout=current.request_timeout_seconds,
            )
            queue.put_nowait(("result", result))
        except TimeoutError:
            log_event("planning_request_timeout", **trace_context)
            queue.put_nowait(
                (
                    "error",
                    StreamErrorDetail(
                        code="planning_timeout", message="规划超时，请缩小范围后重试。"
                    ),
                )
            )
        except PermissionError:
            queue.put_nowait(
                (
                    "error",
                    StreamErrorDetail(
                        code="planning_failed", message="行程不存在或无权访问。"
                    ),
                )
            )
        except Exception as exc:
            log_event(
                "planning_request_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                **trace_context,
            )
            queue.put_nowait(
                (
                    "error",
                    StreamErrorDetail(
                        code="planning_failed",
                        message=f"规划未完成：{type(exc).__name__}",
                    ),
                )
            )
        finally:
            queue.put_nowait(("done", None))

    producer = asyncio.create_task(produce())
    try:
        while True:
            try:
                kind, result = await asyncio.wait_for(queue.get(), timeout=10)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if kind == "done":
                break
            message = (
                StreamProgress(event=result)
                if kind == "progress"
                else StreamResult(result=result)
                if kind == "result"
                else StreamError(error=result)
            )
            yield f"event: {kind}\ndata: {message.model_dump_json()}\n\n"
    finally:
        if not producer.done():
            producer.cancel()
            try:
                await producer
            except asyncio.CancelledError:
                pass


@app.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    current = active_runtime()
    current.auth.require_csrf(request)
    identity, issued = resolve_identity(request)
    if not current.llm.available:
        raise HTTPException(
            status_code=503, detail="TRIP_AGENT_LLM_KEY is not configured"
        )
    remaining, _ = current.auth.consume_quota(identity, request)
    response = StreamingResponse(
        stream_chat_events(payload, current, identity.owner),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Query-Remaining": str(remaining),
        },
    )
    attach_issued(response, issued)
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "trip_agent.app:app",
        host="127.0.0.1",
        port=int(os.environ.get("TRIP_AGENT_PORT", "8123")),
        reload=False,
    )
