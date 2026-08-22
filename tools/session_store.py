"""Session store with Redis backend and in-memory fallback.

Provides persistent session storage for multi-turn chat with TTL-based expiry.
Falls back to in-memory dict with asyncio.Lock when Redis is unavailable.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from tools.cache import _get_redis

logger = logging.getLogger(__name__)

_SESSION_TTL_SECONDS = 1800  # 30 minutes


class SessionStore:
    """Hybrid session store: Redis (preferred) + in-memory fallback."""

    def __init__(self, ttl: int = _SESSION_TTL_SECONDS):
        self.ttl = ttl
        self._memory: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._redis_checked = False
        self._redis = None

    def _get_redis_client(self):
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        try:
            self._redis = _get_redis()
        except Exception:
            self._redis = None
        return self._redis

    async def get_or_create(self, session_id: str) -> dict:
        """Get existing session or create a new one."""
        r = self._get_redis_client()

        if r:
            try:
                key = f"session:{session_id}" if session_id else ""
                if session_id and key:
                    raw = r.get(key)
                    if raw:
                        session = json.loads(raw)
                        if time.time() - session.get("ts", 0) < self.ttl:
                            session["ts"] = time.time()
                            r.setex(key, self.ttl, json.dumps(session, ensure_ascii=False))
                            return session
                # Create new
                new_id = session_id or uuid.uuid4().hex[:12]
                session = {
                    "session_id": new_id,
                    "history": [],
                    "itinerary": None,
                    "state": None,
                    "intent": None,
                    "ts": time.time(),
                }
                r.setex(f"session:{new_id}", self.ttl, json.dumps(session, ensure_ascii=False))
                return session
            except Exception as e:
                logger.warning("Redis session get failed: %s, falling back to memory", e)

        # In-memory fallback
        async with self._lock:
            if session_id and session_id in self._memory:
                session = self._memory[session_id]
                if time.time() - session.get("ts", 0) < self.ttl:
                    session["ts"] = time.time()
                    return session
            new_id = session_id or uuid.uuid4().hex[:12]
            session = {
                "session_id": new_id,
                "history": [],
                "itinerary": None,
                "state": None,
                "intent": None,
                "ts": time.time(),
            }
            self._memory[new_id] = session
            return session

    async def get(self, session_id: str) -> Optional[dict]:
        """Return an existing non-expired session without creating one."""
        if not session_id:
            return None
        r = self._get_redis_client()
        if r:
            try:
                raw = r.get(f"session:{session_id}")
                if not raw:
                    return None
                session = json.loads(raw)
                if time.time() - session.get("ts", 0) >= self.ttl:
                    r.delete(f"session:{session_id}")
                    return None
                return session
            except Exception as e:
                logger.warning("Redis session get failed: %s, falling back to memory", e)

        async with self._lock:
            session = self._memory.get(session_id)
            if not session:
                return None
            if time.time() - session.get("ts", 0) >= self.ttl:
                del self._memory[session_id]
                return None
            return session

    async def save(self, session: dict):
        """Persist session state."""
        session["ts"] = time.time()
        sid = session.get("session_id", "")
        r = self._get_redis_client()

        if r and sid:
            try:
                r.setex(f"session:{sid}", self.ttl, json.dumps(session, ensure_ascii=False))
                return
            except Exception as e:
                logger.warning("Redis session save failed: %s", e)

        # In-memory fallback
        async with self._lock:
            if sid:
                self._memory[sid] = session

    async def list_sessions(self, limit: int = 100) -> list[dict]:
        """List active sessions for the debug endpoint."""
        r = self._get_redis_client()
        if r:
            sessions = []
            try:
                for key in r.scan_iter(match="session:*", count=min(limit, 100)):
                    raw = r.get(key)
                    if raw:
                        sessions.append(json.loads(raw))
                    if len(sessions) >= limit:
                        break
                return sessions
            except Exception as e:
                logger.warning("Redis session list failed: %s, falling back to memory", e)

        await self.cleanup()
        async with self._lock:
            return list(self._memory.values())[:limit]

    async def cleanup(self):
        """Remove expired sessions."""
        r = self._get_redis_client()
        if r:
            # Redis handles TTL-based expiry automatically
            return

        async with self._lock:
            now = time.time()
            expired = [
                sid for sid, s in self._memory.items()
                if now - s.get("ts", 0) >= self.ttl
            ]
            for sid in expired:
                del self._memory[sid]
            if expired:
                logger.info("Cleaned up %d expired chat sessions", len(expired))


# Global singleton
_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """Get or create the global SessionStore instance."""
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
