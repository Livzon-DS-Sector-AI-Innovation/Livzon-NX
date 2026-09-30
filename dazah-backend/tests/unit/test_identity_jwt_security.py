"""JWT dependency compatibility and algorithm-confusion regression checks."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import Settings
from app.platform.identity import deps, service
from app.platform.identity.models import User

TEST_KEY = "synthetic-jwt-test-key-with-at-least-32-bytes"


@pytest.mark.asyncio
async def test_signed_session_resolves_user_without_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.model_construct(
        SECRET_KEY=TEST_KEY, JWT_EXPIRE_SECONDS=3600
    )
    user = User(
        id=uuid4(), name="JWT test", role="user", status="active",
        auth_source="local", session_version=3,
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    lookup = AsyncMock(return_value=user)
    monkeypatch.setattr(
        deps, "UserRepository", lambda: SimpleNamespace(get_by_id=lookup)
    )
    token = service.generate_jwt(user)
    request = Request({
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    })
    db = cast(AsyncSession, object())
    resolved = await deps.get_current_user(
        request, db=db,
        settings=settings, auth_token=None,
    )
    assert resolved is user
    assert request.state.audit_user_id == user.id
    lookup.assert_awaited_once_with(db, str(user.id))
    payload = jwt.decode(token, TEST_KEY, algorithms=["HS256"])
    assert payload["session_version"] == 3
    assert payload["exp"] > payload["iat"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["wrong-signature", "expired", "unsigned"])
async def test_invalid_session_never_looks_up_user(
    monkeypatch: pytest.MonkeyPatch, invalid: str,
) -> None:
    payload = {
        "sub": str(uuid4()), "session_version": 0,
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    if invalid == "expired":
        payload["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    token = (
        jwt.encode(payload, "", algorithm="none")
        if invalid == "unsigned"
        else jwt.encode(
            payload, TEST_KEY + "different" if invalid == "wrong-signature"
            else TEST_KEY, algorithm="HS256",
        )
    )
    repository = AsyncMock()
    monkeypatch.setattr(deps, "UserRepository", repository)
    request = Request({
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    })
    assert await deps.get_current_user(
        request, db=cast(AsyncSession, object()),
        settings=Settings.model_construct(SECRET_KEY=TEST_KEY), auth_token=None,
    ) is None
    repository.assert_not_called()


def test_der_public_key_cannot_be_used_as_hmac_verification_secret() -> None:
    public_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    ).public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    def segment(value: object) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")

    message = b".".join([
        segment({"alg": "HS256", "typ": "JWT"}),
        segment({"sub": "synthetic-attacker"}),
    ])
    signature = base64.urlsafe_b64encode(
        hmac.new(public_key, message, hashlib.sha256).digest()
    ).rstrip(b"=")
    forged = (message + b"." + signature).decode()
    with pytest.raises(jwt.InvalidKeyError):
        jwt.decode(forged, public_key, algorithms=["HS256"])
