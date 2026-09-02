"""Small SQLite cache for raw provider responses and normalized metadata."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any


class ProviderCache:
    def __init__(self, path: str | Path = "trip_agent/runtime-cache.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with closing(self._connect()) as db:
            with db:
                db.execute("""
                    CREATE TABLE IF NOT EXISTS provider_cache (
                        cache_key TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        request_json TEXT NOT NULL,
                        response_json TEXT NOT NULL,
                        fetched_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        latency_ms INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        response_hash TEXT NOT NULL
                    )
                """)
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_provider_cache_expiry ON provider_cache(expires_at)"
                )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def make_key(provider: str, operation: str, request: dict[str, Any]) -> str:
        payload = json.dumps(
            request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(f"{provider}:{operation}:{payload}".encode()).hexdigest()

    def get(
        self, provider: str, operation: str, request: dict[str, Any]
    ) -> dict[str, Any] | None:
        key = self.make_key(provider, operation, request)
        with self._lock, closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM provider_cache WHERE cache_key = ? AND expires_at > ?",
                (key, time.time()),
            ).fetchone()
        if row is None:
            return None
        return {
            "response": json.loads(row["response_json"]),
            "fetched_at": row["fetched_at"],
            "expires_at": row["expires_at"],
            "latency_ms": row["latency_ms"],
            "status": row["status"],
            "response_hash": row["response_hash"],
            "cache_hit": True,
        }

    def put(
        self,
        provider: str,
        operation: str,
        request: dict[str, Any],
        response: Any,
        ttl_seconds: int,
        latency_ms: int,
        status: str = "ok",
    ) -> dict[str, Any]:
        fetched_at = time.time()
        serialized = json.dumps(
            response, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        record = {
            "response": response,
            "fetched_at": fetched_at,
            "expires_at": fetched_at + ttl_seconds,
            "latency_ms": latency_ms,
            "status": status,
            "response_hash": "sha256:"
            + hashlib.sha256(serialized.encode()).hexdigest(),
            "cache_hit": False,
        }
        key = self.make_key(provider, operation, request)
        with self._lock, closing(self._connect()) as db:
            with db:
                db.execute(
                    """INSERT OR REPLACE INTO provider_cache
                    (cache_key, provider, operation, request_json, response_json,
                     fetched_at, expires_at, latency_ms, status, response_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        key,
                        provider,
                        operation,
                        json.dumps(request, ensure_ascii=False, sort_keys=True),
                        serialized,
                        fetched_at,
                        fetched_at + ttl_seconds,
                        latency_ms,
                        status,
                        record["response_hash"],
                    ),
                )
        return record

    def stats(self) -> dict[str, int]:
        with self._lock, closing(self._connect()) as db:
            row = db.execute(
                "SELECT COUNT(*) AS total, SUM(expires_at > ?) AS fresh FROM provider_cache",
                (time.time(),),
            ).fetchone()
        return {
            "entries": int(row["total"] or 0),
            "fresh_entries": int(row["fresh"] or 0),
        }
