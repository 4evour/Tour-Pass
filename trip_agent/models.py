from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    username_normalized: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
    )


class WebSession(Base):
    __tablename__ = "web_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class DailyUsage(Base):
    __tablename__ = "daily_usage"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "subject_type",
            "subject_hash",
            "usage_date",
            name="uq_daily_usage_subject_date",
        ),
    )


class TripSession(Base):
    __tablename__ = "trip_sessions"

    session_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(8), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    city: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    latest_run_id: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        CheckConstraint(
            "owner_type IN ('guest', 'user')", name="ck_trip_sessions_owner_type"
        ),
        Index("ix_trip_sessions_owner_updated", "owner_type", "owner_id", "updated_at"),
    )


class TripMessage(Base):
    __tablename__ = "trip_messages"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("trip_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_trip_messages_role"),
        UniqueConstraint("run_id", "role", name="uq_trip_messages_run_role"),
        Index("ix_trip_messages_session_id_id", "session_id", "id"),
    )


class ItineraryVersion(Base):
    __tablename__ = "itinerary_versions"

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("trip_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reply: Mapped[str] = mapped_column(Text, nullable=False)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    events_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VALUE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "session_id", "version_number", name="uq_itinerary_versions_session_version"
        ),
        Index("ix_itinerary_versions_session_created", "session_id", "created_at"),
    )


class Publication(Base):
    __tablename__ = "publications"

    public_slug: Mapped[str] = mapped_column(String(24), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("trip_sessions.session_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    owner_type: Mapped[str] = mapped_column(String(8), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(32), nullable=False)
    itinerary_run_id: Mapped[str] = mapped_column(
        ForeignKey("itinerary_versions.run_id", ondelete="CASCADE"), nullable=False
    )
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "visibility IN ('public', 'unlisted')", name="ck_publications_visibility"
        ),
        Index("ix_publications_feed", "visibility", "published_at"),
    )
