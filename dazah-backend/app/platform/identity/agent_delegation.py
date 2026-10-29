"""Short-lived, purpose-bound user delegation issued only by trusted ingress."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
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
            "exp": now + timedelta(minutes=10),
            "jti": str(uuid4()),
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
    return user
