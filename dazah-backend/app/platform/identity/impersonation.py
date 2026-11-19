"""Short-lived browser identity switches with live authorization and revocation."""

import asyncio
import hashlib
import hmac
from collections.abc import Awaitable
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.redis import redis_client
from app.platform.identity.models import User
from app.platform.identity.rbac import is_ordinary_admin
from app.platform.identity.repository import UserRepository

COOKIE = "impersonation_token"
PREFIX = "dazah-impersonation."
DURATION = timedelta(minutes=30)
_AUDIENCE = "dazah-browser-impersonation"


class ImpersonationSession(BaseModel):
    session_id: UUID
    administrator_id: UUID
    administrator_version: int
    target_id: UUID
    target_version: int
    login_digest: str
    exp: int

    @property
    def expires_at(self) -> datetime:
        return datetime.fromtimestamp(self.exp, UTC)

    @property
    def redis_key(self) -> str:
        return f"identity:impersonation:{self.login_digest}"

    def audit_fields(self) -> dict[str, str]:
        return {
            "session_id": str(self.session_id),
            "administrator_id": str(self.administrator_id),
            "target_id": str(self.target_id),
        }


current_impersonation: ContextVar[ImpersonationSession | None] = ContextVar(
    "current_impersonation", default=None
)


def _signing_key(settings: Settings) -> bytes:
    return hmac.digest(settings.SECRET_KEY.encode(), _AUDIENCE.encode(), "sha256")


def bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ") or None


def authentication_token(request: Request, auth_cookie: str | None) -> str | None:
    # A browser's active switch always takes precedence, including when invalid.
    if COOKIE in request.cookies:
        return request.cookies[COOKIE]
    return bearer_token(request) or auth_cookie


def is_impersonating_request(request: Request, token: str | None) -> bool:
    return COOKIE in request.cookies or bool(token and token.startswith(PREFIX))


def decode_login(token: str, settings: Settings) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None


def _decode_switch(
    token: str, settings: Settings, *, verify_exp: bool = True
) -> ImpersonationSession:
    try:
        if not token.startswith(PREFIX):
            raise jwt.InvalidTokenError()
        claims = jwt.decode(
            token.removeprefix(PREFIX),
            _signing_key(settings),
            algorithms=["HS256"],
            audience=_AUDIENCE,
            options={"require": ["exp"], "verify_exp": verify_exp},
        )
        return ImpersonationSession.model_validate(claims)
    except (jwt.InvalidTokenError, ValidationError) as exc:
        raise HTTPException(401, "模拟登录已失效，请返回管理员身份") from exc


async def is_system_administrator(db: AsyncSession, user: User) -> bool:
    return user.role == "admin" and not await is_ordinary_admin(db, user.id)


async def start_impersonation(
    db: AsyncSession,
    settings: Settings,
    *,
    login_token: str,
    administrator: User,
    target_id: UUID,
) -> tuple[ImpersonationSession, str]:
    payload = decode_login(login_token, settings)
    if (
        payload is None
        or payload.get("sub") != str(administrator.id)
        or payload.get("session_version") != administrator.session_version
        or not isinstance(payload.get("exp"), int)
    ):
        raise HTTPException(401, "请重新登录后再开始模拟")
    if target_id == administrator.id:
        raise HTTPException(422, "请选择其他用户")
    target = await UserRepository().get_by_id(db, target_id)
    if target is None or target.status != "active":
        raise HTTPException(404, "该用户已停用或不存在")
    if await is_system_administrator(db, target):
        raise HTTPException(403, "不能模拟系统管理员")

    now = datetime.now(UTC)
    session = ImpersonationSession(
        session_id=uuid4(),
        administrator_id=administrator.id,
        administrator_version=administrator.session_version,
        target_id=target.id,
        target_version=target.session_version,
        login_digest=hashlib.sha256(login_token.encode()).hexdigest(),
        exp=min(payload["exp"], int((now + DURATION).timestamp())),
    )
    ttl = session.exp - int(now.timestamp())
    if ttl <= 0:
        raise HTTPException(401, "请重新登录后再开始模拟")
    token = PREFIX + jwt.encode(
        {**session.model_dump(mode="json"), "aud": _AUDIENCE},
        _signing_key(settings),
        algorithm="HS256",
    )
    try:
        async with asyncio.timeout(0.5):
            reserved = await redis_client.set(
                session.redis_key, str(session.session_id), ex=ttl, nx=True
            )
    except (RedisError, TimeoutError) as exc:
        raise HTTPException(503, "模拟登录暂时不可用，请稍后重试") from exc
    if not reserved:
        raise HTTPException(409, "本次登录已有模拟会话")
    return session, token


async def validate_impersonation(
    db: AsyncSession, session: ImpersonationSession
) -> User:
    try:
        async with asyncio.timeout(0.5):
            active = await redis_client.get(session.redis_key)
    except (RedisError, TimeoutError) as exc:
        raise HTTPException(503, "模拟登录暂时无法验证，请稍后重试") from exc
    if active != str(session.session_id) or session.expires_at <= datetime.now(UTC):
        raise HTTPException(401, "模拟登录已失效，请返回管理员身份")

    repo = UserRepository()
    administrator = await repo.get_by_id(db, session.administrator_id)
    target = await repo.get_by_id(db, session.target_id)
    if (
        administrator is None
        or administrator.status != "active"
        or administrator.session_version != session.administrator_version
        or not await is_system_administrator(db, administrator)
        or target is None
        or target.status != "active"
        or target.session_version != session.target_version
        or await is_system_administrator(db, target)
    ):
        raise HTTPException(401, "模拟登录已失效，请返回管理员身份")
    return target


async def resolve_impersonation(
    request: Request, db: AsyncSession, settings: Settings, token: str
) -> User:
    session = _decode_switch(token, settings)
    user = await validate_impersonation(db, session)
    request.state.impersonation = session
    request.state.audit_user_id = user.id
    current_impersonation.set(session)
    return user


async def revoke_impersonation(session: ImpersonationSession) -> None:
    if session.expires_at <= datetime.now(UTC):
        return
    # Compare and delete atomically so an old switch cannot revoke a newer one.
    try:
        async with asyncio.timeout(0.5):
            await cast(
                Awaitable[int],
                redis_client.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then "
                    "return redis.call('del', KEYS[1]) else return 0 end",
                    1,
                    session.redis_key,
                    str(session.session_id),
                ),
            )
    except (RedisError, TimeoutError) as exc:
        raise HTTPException(503, "暂时无法退出模拟，请稍后重试") from exc


async def end_impersonation(
    db: AsyncSession, settings: Settings, switch: str, login_token: str | None
) -> tuple[ImpersonationSession | None, bool]:
    try:
        session = _decode_switch(switch, settings, verify_exp=False)
    except HTTPException:
        return None, False
    await revoke_impersonation(session)
    payload = decode_login(login_token, settings) if login_token else None
    if payload is None or payload.get("sub") != str(session.administrator_id):
        return session, False
    administrator = await UserRepository().get_by_id(db, session.administrator_id)
    return session, bool(
        administrator is not None
        and administrator.status == "active"
        and administrator.session_version == session.administrator_version
        and administrator.session_version == payload.get("session_version")
        and await is_system_administrator(db, administrator)
    )
