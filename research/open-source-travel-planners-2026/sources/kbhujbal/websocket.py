"""
WebSocket connection manager and handler for real-time progress updates.
"""

import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict
from fastapi import WebSocket, WebSocketDisconnect

from backend.crew.orchestrator import run_travel_pipeline
from backend.config.settings import settings

logger = logging.getLogger(__name__)

# In-memory store (would be a DB in production)
itinerary_store: dict = {}

AGENT_STEPS = [
    {"key": "planning", "label": "Travel Planning Manager", "description": "Analyzing your request..."},
    {"key": "data_fetch", "label": "Fetching Real-Time Data", "description": "Searching flights, hotels, activities..."},
    {"key": "knowledge", "label": "Travel Knowledge Expert", "description": "Gathering travel tips..."},
    {"key": "compilation", "label": "Itinerary Compiler & Optimizer", "description": "Building your itinerary..."},
]


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        self.active_connections.pop(session_id, None)

    async def send_message(self, session_id: str, message: dict):
        ws = self.active_connections.get(session_id)
        if ws:
            await ws.send_json(message)


manager = ConnectionManager()


async def run_with_progress(session_id: str, user_request: str):
    """Run the travel pipeline while sending progress updates via WebSocket."""
    itinerary_id = str(uuid.uuid4())

    itinerary_store[itinerary_id] = {
        "id": itinerary_id,
        "request": user_request,
        "itinerary": "",
        "created_at": datetime.now().isoformat(),
        "status": "processing",
    }

    await manager.send_message(session_id, {
        "type": "started",
        "itinerary_id": itinerary_id,
        "agents": AGENT_STEPS,
    })

    try:
        async def progress_callback(step_key: str, label: str, status: str):
            step_index = next(
                (i for i, s in enumerate(AGENT_STEPS) if s["key"] == step_key),
                0,
            )
            step_info = AGENT_STEPS[step_index] if step_index < len(AGENT_STEPS) else {}

            await manager.send_message(session_id, {
                "type": "agent_progress",
                "agent_key": step_key,
                "agent_label": label,
                "description": step_info.get("description", ""),
                "step": step_index + 1,
                "total_steps": len(AGENT_STEPS),
                "status": status,
            })
            logger.info(f"[{session_id}] {label}: {status}")

        # Run the pipeline in a thread (CrewAI is sync internally)
        loop = asyncio.get_event_loop()
        result = await run_travel_pipeline(
            user_request=user_request,
            progress_callback=progress_callback,
        )

        itinerary_store[itinerary_id]["itinerary"] = result
        itinerary_store[itinerary_id]["status"] = "completed"

        await manager.send_message(session_id, {
            "type": "completed",
            "itinerary_id": itinerary_id,
            "itinerary": result,
        })
        logger.info(f"[{session_id}] Pipeline completed")

    except Exception as e:
        logger.error(f"[{session_id}] Pipeline failed: {e}", exc_info=True)
        itinerary_store[itinerary_id]["status"] = "failed"
        await manager.send_message(session_id, {
            "type": "error",
            "message": str(e),
        })


async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint handler for real-time travel planning."""
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "plan_request":
                user_message = data.get("message", "")
                if not user_message.strip():
                    await manager.send_message(session_id, {
                        "type": "error",
                        "message": "Please provide a travel request.",
                    })
                    continue

                if not settings.gemini_api_key:
                    await manager.send_message(session_id, {
                        "type": "error",
                        "message": "GEMINI_API_KEY not configured on the server.",
                    })
                    continue

                asyncio.create_task(run_with_progress(session_id, user_message))

    except WebSocketDisconnect:
        manager.disconnect(session_id)

