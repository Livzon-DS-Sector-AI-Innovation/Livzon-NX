"""Short-lived, purpose-bound user delegation issued only by trusted ingress."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.platform.identity.impersonation import (
    ImpersonationSession,
    current_impersonation,
    validate_impersonation,
)
from app.platform.identity.models import ExternalIdentityBinding, User

_AUDIENCE = "dazah-agent-tools"
_ISSUER = "dazah-identity"


def _signing_key(settings: Settings) -> bytes:
    return hmac.new(
        settings.SECRET_KEY.encode(), b"agent-user-delegation:v1", hashlib.sha256
    ).digest()


def issue_agent_delegation(
    settings: Settings,
    user: User,
    *,
    source: str,
    external_binding_id: UUID | None = None,
) -> str:
    """Called after web authentication or verified external identity resolution."""
    now = datetime.now(UTC)
    switch = current_impersonation.get() if source == "web" else None
    if switch is not None and switch.target_id != user.id:
        raise HTTPException(403, "Agent 用户与模拟登录身份不一致")
    expires_at = now + timedelta(minutes=10)
    if switch is not None:
        expires_at = min(expires_at, switch.expires_at)
    return jwt.encode(
        {
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "sub": str(user.id),
            "tenant": user.tenant_key or "default",
            "source": source,
            "binding": str(external_binding_id) if external_binding_id else None,
            "session_version": user.session_version or 0,
            "iat": now,
            "exp": expires_at,
            "jti": str(uuid4()),
            **({"impersonation": switch.model_dump(mode="json")} if switch else {}),
        },
        _signing_key(settings),
        algorithm="HS256",
    )


async def require_agent_delegation(
    db: AsyncSession,
    settings: Settings,
    token: str | None,
    *,
    user_id: UUID,
    tenant_id: str,
    source: str | None = None,
    external_binding_id: UUID | None = None,
    request: Request | None = None,
) -> User:
    """Check signed identity and current revocation state before any business call."""
    try:
        if not token or len(token) > 4096:
            raise jwt.InvalidTokenError()
        claims = jwt.decode(
            token,
            _signing_key(settings),
            algorithms=["HS256"],
            audience=_AUDIENCE,
            issuer=_ISSUER,
            options={
                "require": [
                    "sub",
                    "tenant",
                    "source",
                    "session_version",
                    "iat",
                    "exp",
                    "jti",
                    "aud",
                    "iss",
                ]
            },
        )
        if (
            claims["sub"] != str(user_id)
            or claims["tenant"] != tenant_id
            or (source is not None and claims["source"] != source)
            or (
                source is not None
                and claims.get("binding")
                != (str(external_binding_id) if external_binding_id else None)
            )
        ):
            raise jwt.InvalidTokenError()
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, "Invalid or expired Agent user delegation") from exc
    user = await db.get(User, user_id)
    if (
        user is None
        or user.is_deleted
        or user.status != "active"
        or (user.tenant_key or "default") != tenant_id
        or (user.session_version or 0) != claims["session_version"]
    ):
        raise HTTPException(403, "Agent user delegation is no longer valid")
    if claims["source"] == "feishu":
        try:
            binding_id = UUID(claims.get("binding") or "")
        except ValueError as exc:
            raise HTTPException(
                401, "Invalid Agent external identity delegation"
            ) from exc
        binding = await db.get(ExternalIdentityBinding, binding_id)
        if (
            binding is None
            or binding.is_deleted
            or binding.status != "active"
            or binding.local_user_id != user.id
        ):
            raise HTTPException(
                403, "Agent external identity binding is no longer valid"
            )
    if "impersonation" in claims:
        try:
            switch = ImpersonationSession.model_validate(claims["impersonation"])
        except ValidationError as exc:
            raise HTTPException(401, "Invalid Agent impersonation delegation") from exc
        if claims["source"] != "web" or switch.target_id != user.id:
            raise HTTPException(403, "Agent 用户与模拟登录身份不一致")
        await validate_impersonation(db, switch)
        current_impersonation.set(switch)
        if request is not None:
            request.state.impersonation = switch
            request.state.audit_user_id = user.id
    return user
