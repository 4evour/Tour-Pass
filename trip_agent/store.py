from __future__ import annotations

import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update

from .contracts import ChatResponse
from .db import Base, create_database_engine, session_factory
from .models import ItineraryVersion, Publication, TripMessage, TripSession

OwnerKey = tuple[str, str]


class TripStore:
    """Small SQLAlchemy store shared by local SQLite and production PostgreSQL."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.engine = create_database_engine(path)
        Base.metadata.create_all(self.engine)
        self._sessions = session_factory(self.engine)

    @staticmethod
    def _timestamp(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat(timespec="seconds")

    @staticmethod
    def _title(message: str, plan: dict[str, Any] | None) -> str:
        if plan:
            title = str(plan.get("title") or "").strip()
            if title:
                return title[:80]
            city = str(plan.get("city") or "").strip()
            if city:
                return f"{city}行程"
        return " ".join(message.split())[:30] or "未命名行程"

    @staticmethod
    def _owned(session: TripSession, owner: OwnerKey) -> bool:
        return session.owner_type == owner[0] and session.owner_id == owner[1]

    def save_exchange(
        self,
        *,
        owner: OwnerKey = ("guest", "local"),
        session_id: str,
        run_id: str,
        user_message: str,
        reply: str,
        plan: dict[str, Any] | None,
        events: list[dict[str, Any]],
    ) -> None:
        now = datetime.now(UTC)
        with self._sessions.begin() as db:
            trip = db.get(TripSession, session_id)
            if trip is None:
                trip = TripSession(
                    session_id=session_id,
                    owner_type=owner[0],
                    owner_id=owner[1],
                    title=self._title(user_message, plan),
                    city=str(plan.get("city") or "").strip() or None if plan else None,
                    created_at=now,
                    updated_at=now,
                    latest_run_id=run_id if plan else None,
                )
                db.add(trip)
                db.flush()
            elif not self._owned(trip, owner):
                raise PermissionError("行程不存在或无权访问")
            else:
                trip.updated_at = now
                if plan is not None:
                    trip.title = self._title(user_message, plan)
                    trip.city = str(plan.get("city") or "").strip() or trip.city
                    trip.latest_run_id = run_id

            for role, content in (("user", user_message), ("assistant", reply)):
                db.add(
                    TripMessage(
                        session_id=session_id,
                        run_id=run_id,
                        role=role,
                        content=content,
                        created_at=now,
                    )
                )
            if plan is not None:
                version = db.scalar(
                    select(
                        func.coalesce(func.max(ItineraryVersion.version_number), 0)
                    ).where(ItineraryVersion.session_id == session_id)
                )
                db.add(
                    ItineraryVersion(
                        run_id=run_id,
                        session_id=session_id,
                        version_number=int(version or 0) + 1,
                        reply=reply,
                        plan_json=plan,
                        events_json=events,
                        created_at=now,
                    )
                )

    def update_events(self, run_id: str, events: list[dict[str, Any]]) -> None:
        with self._sessions.begin() as db:
            db.execute(
                update(ItineraryVersion)
                .where(ItineraryVersion.run_id == run_id)
                .values(events_json=events)
            )

    def history(
        self, session_id: str, owner: OwnerKey = ("guest", "local"), limit: int = 12
    ) -> list[dict[str, str]]:
        limit = max(1, min(limit, 40))
        with self._sessions() as db:
            trip = db.get(TripSession, session_id)
            if trip is None or not self._owned(trip, owner):
                return []
            rows = list(
                db.scalars(
                    select(TripMessage)
                    .where(TripMessage.session_id == session_id)
                    .order_by(TripMessage.id.desc())
                    .limit(limit)
                )
            )
        rows.reverse()
        return [{"role": row.role, "content": row.content} for row in rows]

    def latest_plan(
        self, session_id: str, owner: OwnerKey = ("guest", "local")
    ) -> dict[str, Any] | None:
        with self._sessions() as db:
            trip = db.get(TripSession, session_id)
            if trip is None or not self._owned(trip, owner) or not trip.latest_run_id:
                return None
            itinerary = db.get(ItineraryVersion, trip.latest_run_id)
            return dict(itinerary.plan_json) if itinerary else None

    def list_sessions(
        self, owner: OwnerKey = ("guest", "local"), limit: int = 50
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        with self._sessions() as db:
            rows = list(
                db.scalars(
                    select(TripSession)
                    .where(
                        TripSession.owner_type == owner[0],
                        TripSession.owner_id == owner[1],
                        TripSession.latest_run_id.is_not(None),
                    )
                    .order_by(TripSession.updated_at.desc())
                    .limit(limit)
                )
            )
        return [self._session_summary(row) for row in rows]

    def get_session(
        self, session_id: str, owner: OwnerKey = ("guest", "local")
    ) -> dict[str, Any] | None:
        with self._sessions() as db:
            trip = db.get(TripSession, session_id)
            if trip is None or not self._owned(trip, owner):
                return None
            messages = list(
                db.scalars(
                    select(TripMessage)
                    .where(TripMessage.session_id == session_id)
                    .order_by(TripMessage.id.asc())
                )
            )
            itinerary = (
                db.get(ItineraryVersion, trip.latest_run_id)
                if trip.latest_run_id
                else None
            )
            summary = self._session_summary(trip)
            latest = None
            if itinerary:
                latest = ChatResponse(
                    session_id=session_id,
                    run_id=itinerary.run_id,
                    reply=itinerary.reply,
                    plan=itinerary.plan_json,
                    events=itinerary.events_json,
                ).model_dump(mode="json")
        return {
            "session": summary,
            "messages": [
                {
                    "role": row.role,
                    "content": row.content,
                    "created_at": self._timestamp(row.created_at),
                }
                for row in messages
            ],
            "latest": latest,
        }

    def claim_guest_trips(self, guest_id: str, user_id: str) -> None:
        with self._sessions.begin() as db:
            db.execute(
                update(TripSession)
                .where(
                    TripSession.owner_type == "guest", TripSession.owner_id == guest_id
                )
                .values(owner_type="user", owner_id=user_id)
            )
            db.execute(
                update(Publication)
                .where(
                    Publication.owner_type == "guest", Publication.owner_id == guest_id
                )
                .values(owner_type="user", owner_id=user_id, visibility="public")
            )

    def publish(self, session_id: str, owner: OwnerKey) -> dict[str, Any]:
        with self._sessions.begin() as db:
            trip = db.get(TripSession, session_id)
            if trip is None or not self._owned(trip, owner) or not trip.latest_run_id:
                raise LookupError("行程不存在")
            itinerary = db.get(ItineraryVersion, trip.latest_run_id)
            if itinerary is None:
                raise LookupError("行程版本不存在")
            plan = dict(itinerary.plan_json)
            existing = db.scalar(
                select(Publication).where(Publication.session_id == session_id)
            )
            visibility = "public" if owner[0] == "user" else "unlisted"
            if existing is None:
                existing = Publication(
                    public_slug=secrets.token_hex(10),
                    session_id=session_id,
                    owner_type=owner[0],
                    owner_id=owner[1],
                    itinerary_run_id=itinerary.run_id,
                    visibility=visibility,
                    title=trip.title,
                    city=trip.city or str(plan.get("city") or "旅行目的地"),
                    days=len(plan.get("days") or []),
                    snapshot_json=plan,
                    published_at=datetime.now(UTC),
                )
                db.add(existing)
            else:
                existing.itinerary_run_id = itinerary.run_id
                existing.visibility = visibility
                existing.title = trip.title
                existing.city = trip.city or str(plan.get("city") or "旅行目的地")
                existing.days = len(plan.get("days") or [])
                existing.snapshot_json = plan
                existing.published_at = datetime.now(UTC)
            return self._publication(existing)

    def unpublish(self, session_id: str, owner: OwnerKey) -> bool:
        with self._sessions.begin() as db:
            result = db.execute(
                delete(Publication).where(
                    Publication.session_id == session_id,
                    Publication.owner_type == owner[0],
                    Publication.owner_id == owner[1],
                )
            )
            return bool(result.rowcount)

    def get_public(self, slug: str) -> dict[str, Any] | None:
        with self._sessions() as db:
            row = db.get(Publication, slug)
            return self._publication(row) if row else None

    def list_public(
        self, *, city: str | None = None, days: int | None = None, limit: int = 30
    ) -> list[dict[str, Any]]:
        query = select(Publication).where(Publication.visibility == "public")
        if city:
            query = query.where(Publication.city == city.strip())
        if days:
            query = query.where(Publication.days == days)
        with self._sessions() as db:
            rows = list(
                db.scalars(
                    query.order_by(Publication.published_at.desc()).limit(
                        max(1, min(limit, 50))
                    )
                )
            )
        return [self._publication(row, include_plan=False) for row in rows]

    def stats(self) -> dict[str, int]:
        with self._sessions() as db:
            sessions = db.scalar(select(func.count()).select_from(TripSession)) or 0
            itineraries = (
                db.scalar(select(func.count()).select_from(ItineraryVersion)) or 0
            )
        return {"sessions": int(sessions), "itineraries": int(itineraries)}

    def close(self) -> None:
        self.engine.dispose()

    def _session_summary(self, row: TripSession) -> dict[str, Any]:
        return {
            "session_id": row.session_id,
            "title": row.title,
            "city": row.city,
            "created_at": self._timestamp(row.created_at),
            "updated_at": self._timestamp(row.updated_at),
            "latest_run_id": row.latest_run_id,
        }

    def _publication(
        self, row: Publication, *, include_plan: bool = True
    ) -> dict[str, Any]:
        result = {
            "slug": row.public_slug,
            "title": row.title,
            "city": row.city,
            "days": row.days,
            "visibility": row.visibility,
            "run_id": row.itinerary_run_id,
            "published_at": self._timestamp(row.published_at),
        }
        if include_plan:
            result["plan"] = row.snapshot_json
        return result
