from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url(value: str | Path | None = None) -> str:
    configured = str(value or os.environ.get("DATABASE_URL") or "").strip()
    if not configured:
        configured = os.environ.get("TRIP_AGENT_STORE", "trip_agent/trips.sqlite")
    if configured.startswith("postgres://"):
        return "postgresql+psycopg://" + configured[len("postgres://") :]
    if configured.startswith("postgresql://"):
        return "postgresql+psycopg://" + configured[len("postgresql://") :]
    if "://" in configured:
        return configured
    path = Path(configured).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def create_database_engine(value: str | Path | None = None) -> Engine:
    url = database_url(value)
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 10}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite)
    return engine


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
