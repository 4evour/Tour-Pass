from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from .models import DailyUsage, User, WebSession

COOKIE_NAME = "tp_session"
CSRF_COOKIE_NAME = "tp_csrf"
USERNAME_PATTERN = re.compile(r"^[\w\-\u4e00-\u9fff]{3,32}$", re.UNICODE)
PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)


@dataclass(frozen=True)
class Identity:
    kind: str
    id: str
    username: str | None = None
    role: str = "guest"

    @property
    def owner(self) -> tuple[str, str]:
        return self.kind, self.id


@dataclass(frozen=True)
class IssuedSession:
    identity: Identity
    token: str
    csrf: str


class AuthManager:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions
        self._secure_cookie = os.environ.get(
            "TRIP_AGENT_SECURE_COOKIES", ""
        ).lower() in {"1", "true", "yes"}
        self._guest_limit = max(
            1, int(os.environ.get("TRIP_AGENT_GUEST_DAILY_LIMIT", "5"))
        )
        self._user_limit = max(
            self._guest_limit, int(os.environ.get("TRIP_AGENT_USER_DAILY_LIMIT", "20"))
        )
        self._ip_key = os.environ.get(
            "TRIP_AGENT_IP_HASH_KEY", "tour-pass-local-ip-key"
        ).encode()
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._attempt_lock = threading.Lock()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def _ip_digest(self, value: str) -> str:
        return hmac.new(self._ip_key, value.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _normalize_username(value: str) -> str:
        return value.strip().casefold()

    @staticmethod
    def client_ip(request: Request) -> str:
        if os.environ.get("TRIP_AGENT_TRUST_PROXY", "").lower() in {"1", "true", "yes"}:
            forwarded = (
                request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
            )
            if forwarded:
                return forwarded
        return request.client.host if request.client else "unknown"

    def resolve(self, request: Request) -> Identity | IssuedSession:
        raw_token = request.cookies.get(COOKIE_NAME, "")
        if raw_token:
            now = datetime.now(UTC)
            with self._sessions.begin() as db:
                web = db.scalar(
                    select(WebSession).where(
                        WebSession.token_hash == self._digest(raw_token)
                    )
                )
                if web and self._aware(web.expires_at) > now:
                    user = db.get(User, web.user_id) if web.user_id else None
                    identity = (
                        Identity("user", user.id, user.username, user.role)
                        if user
                        else Identity("guest", web.id)
                    )
                    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
                    if csrf_cookie and hmac.compare_digest(
                        web.csrf_hash, self._digest(csrf_cookie)
                    ):
                        return identity
                    token = secrets.token_urlsafe(32)
                    csrf = secrets.token_urlsafe(24)
                    web.token_hash = self._digest(token)
                    web.csrf_hash = self._digest(csrf)
                    return IssuedSession(identity, token, csrf)
                if web:
                    db.delete(web)
        return self._issue(None)

    def _issue(self, user_id: str | None) -> IssuedSession:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        web_id = uuid.uuid4().hex
        ttl_days = 30
        with self._sessions.begin() as db:
            db.add(
                WebSession(
                    id=web_id,
                    token_hash=self._digest(token),
                    csrf_hash=self._digest(csrf),
                    user_id=user_id,
                    expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
                )
            )
            user = db.get(User, user_id) if user_id else None
            identity = (
                Identity("user", user.id, user.username, user.role)
                if user
                else Identity("guest", web_id)
            )
        return IssuedSession(identity, token, csrf)

    def set_cookies(self, response: Response, issued: IssuedSession) -> None:
        max_age = 30 * 86400
        response.set_cookie(
            COOKIE_NAME,
            issued.token,
            max_age=max_age,
            httponly=True,
            secure=self._secure_cookie,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            CSRF_COOKIE_NAME,
            issued.csrf,
            max_age=max_age,
            httponly=False,
            secure=self._secure_cookie,
            samesite="lax",
            path="/",
        )

    def require_csrf(self, request: Request) -> None:
        token = request.headers.get("x-csrf-token", "")
        cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
        raw_session = request.cookies.get(COOKIE_NAME, "")
        if (
            not token
            or not cookie
            or not raw_session
            or not hmac.compare_digest(token, cookie)
        ):
            raise HTTPException(
                status_code=403, detail="安全令牌无效，请刷新页面后重试"
            )
        with self._sessions() as db:
            web = db.scalar(
                select(WebSession).where(
                    WebSession.token_hash == self._digest(raw_session)
                )
            )
            if web is None or not hmac.compare_digest(
                web.csrf_hash, self._digest(token)
            ):
                raise HTTPException(
                    status_code=403, detail="安全令牌无效，请刷新页面后重试"
                )

    def register(self, username: str, password: str, guest: Identity) -> IssuedSession:
        clean_name = username.strip()
        if not USERNAME_PATTERN.fullmatch(clean_name):
            raise HTTPException(
                status_code=422,
                detail="用户名需为 3-32 位中文、字母、数字、下划线或连字符",
            )
        if len(password) < 8 or len(password) > 128:
            raise HTTPException(status_code=422, detail="密码长度需为 8-128 位")
        user_id = uuid.uuid4().hex
        try:
            with self._sessions.begin() as db:
                db.add(
                    User(
                        id=user_id,
                        username=clean_name,
                        username_normalized=self._normalize_username(clean_name),
                        password_hash=PASSWORD_HASHER.hash(password),
                    )
                )
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="用户名已被注册") from exc
        issued = self._issue(user_id)
        return issued

    def login(self, username: str, password: str, ip: str) -> IssuedSession:
        self.check_auth_rate(ip)
        normalized = self._normalize_username(username)
        with self._sessions() as db:
            user = db.scalar(select(User).where(User.username_normalized == normalized))
            if user is None:
                PASSWORD_HASHER.hash(password[:128] or "invalid-password")
                raise HTTPException(status_code=401, detail="用户名或密码错误")
            try:
                PASSWORD_HASHER.verify(user.password_hash, password)
            except (VerifyMismatchError, InvalidHashError) as exc:
                raise HTTPException(status_code=401, detail="用户名或密码错误") from exc
            user_id = user.id
        return self._issue(user_id)

    def logout(self, request: Request) -> IssuedSession:
        raw_token = request.cookies.get(COOKIE_NAME, "")
        if raw_token:
            with self._sessions.begin() as db:
                web = db.scalar(
                    select(WebSession).where(
                        WebSession.token_hash == self._digest(raw_token)
                    )
                )
                if web:
                    db.delete(web)
        return self._issue(None)

    def quota(self, identity: Identity) -> tuple[int, int]:
        limit = (
            100000
            if identity.role == "admin"
            else self._user_limit
            if identity.kind == "user"
            else self._guest_limit
        )
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        with self._sessions() as db:
            row = db.scalar(
                select(DailyUsage).where(
                    DailyUsage.subject_type == identity.kind,
                    DailyUsage.subject_hash == identity.id,
                    DailyUsage.usage_date == today,
                )
            )
            used = row.request_count if row else 0
        return max(0, limit - used), limit

    def consume_quota(self, identity: Identity, request: Request) -> tuple[int, int]:
        limit = (
            100000
            if identity.role == "admin"
            else self._user_limit
            if identity.kind == "user"
            else self._guest_limit
        )
        subjects = [(identity.kind, identity.id, limit)]
        if identity.kind == "guest":
            subjects.append(
                ("ip", self._ip_digest(self.client_ip(request)), self._guest_limit)
            )
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        remaining_values: list[int] = []
        with self._sessions.begin() as db:
            for subject_type, subject_hash, subject_limit in subjects:
                row = db.scalar(
                    select(DailyUsage)
                    .where(
                        DailyUsage.subject_type == subject_type,
                        DailyUsage.subject_hash == subject_hash,
                        DailyUsage.usage_date == today,
                    )
                    .with_for_update()
                )
                if row is None:
                    try:
                        with db.begin_nested():
                            db.add(
                                DailyUsage(
                                    subject_type=subject_type,
                                    subject_hash=subject_hash,
                                    usage_date=today,
                                    request_count=0,
                                )
                            )
                            db.flush()
                    except IntegrityError:
                        pass
                    row = db.scalar(
                        select(DailyUsage)
                        .where(
                            DailyUsage.subject_type == subject_type,
                            DailyUsage.subject_hash == subject_hash,
                            DailyUsage.usage_date == today,
                        )
                        .with_for_update()
                    )
                if row is None:
                    raise RuntimeError("无法建立额度记录")
                result = db.execute(
                    update(DailyUsage)
                    .where(
                        DailyUsage.id == row.id,
                        DailyUsage.request_count < subject_limit,
                    )
                    .values(request_count=DailyUsage.request_count + 1)
                    .returning(DailyUsage.request_count)
                )
                updated_count = result.scalar_one_or_none()
                if updated_count is None:
                    raise HTTPException(
                        status_code=429, detail="今日免费规划次数已用完"
                    )
                remaining_values.append(max(0, subject_limit - int(updated_count)))
        return min(remaining_values), limit

    def check_auth_rate(self, ip: str) -> None:
        now = time.monotonic()
        key = self._ip_digest(ip)
        with self._attempt_lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= now - 900:
                attempts.popleft()
            if len(attempts) >= 10:
                raise HTTPException(
                    status_code=429, detail="账号操作过于频繁，请稍后再试"
                )
            attempts.append(now)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )
