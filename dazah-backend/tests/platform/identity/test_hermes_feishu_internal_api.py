from __future__ import annotations

import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import Settings
from app.platform.identity import hermes_api
from app.platform.identity.hermes_api import (
    ExternalIdentityResolveRequest,
    _require_internal,
    resolve_external_identity,
)


def test_internal_token_is_required() -> None:
    settings = Settings(HERMES_INTERNAL_TOKEN="internal-test-token")
    with pytest.raises(HTTPException) as exc:
        _require_internal("Bearer wrong", settings)
    assert exc.value.status_code == 401


def test_internal_token_accepts_exact_bearer() -> None:
    settings = Settings(HERMES_INTERNAL_TOKEN="internal-test-token")
    assert _require_internal("Bearer internal-test-token", settings) is None


def test_internal_token_comparison_has_no_prefix_match() -> None:
    settings = Settings(HERMES_INTERNAL_TOKEN="internal-test-token")
    assert not hmac.compare_digest("internal-test", settings.HERMES_INTERNAL_TOKEN)
    with pytest.raises(HTTPException):
        _require_internal("Bearer internal-test", settings)


def test_external_identity_request_requires_a_platform_identifier() -> None:
    with pytest.raises(ValidationError, match="identifier is required"):
        ExternalIdentityResolveRequest(
            tenant_id="tenant",
            app_fingerprint="app",
        )


@pytest.mark.asyncio
async def test_external_identity_resolution_rejects_untrusted_states(
    monkeypatch,
) -> None:
    payload = ExternalIdentityResolveRequest(
        tenant_id="tenant",
        app_fingerprint="app",
        external_open_id="open",
        chat_id="group",
    )
    db = SimpleNamespace(get=AsyncMock(), flush=AsyncMock())
    settings = SimpleNamespace(LIVZON_FEISHU_ALLOWED_GROUPS="allowed")

    class ConfigRepository:
        async def get_active(self, _db):
            return SimpleNamespace(app_id="other")

    monkeypatch.setattr(hermes_api, "FeishuConfigRepository", ConfigRepository)
    with pytest.raises(HTTPException, match="active Hermes Gateway"):
        await resolve_external_identity(payload, db, settings)

    class ActiveConfigRepository:
        async def get_active(self, _db):
            return SimpleNamespace(app_id="app")

    class MissingBindingRepository:
        async def resolve(self, _db, **_kwargs):
            return None

    monkeypatch.setattr(
        hermes_api,
        "FeishuConfigRepository",
        ActiveConfigRepository,
    )
    monkeypatch.setattr(
        hermes_api,
        "ExternalIdentityBindingRepository",
        MissingBindingRepository,
    )
    with pytest.raises(HTTPException, match="not bound"):
        await resolve_external_identity(payload, db, settings)

    binding = SimpleNamespace(local_user_id=uuid4())

    class BindingRepository:
        async def resolve(self, _db, **_kwargs):
            return binding

    monkeypatch.setattr(
        hermes_api,
        "ExternalIdentityBindingRepository",
        BindingRepository,
    )
    db.get.return_value = SimpleNamespace(is_deleted=False, status="disabled")
    with pytest.raises(HTTPException, match="not active"):
        await resolve_external_identity(payload, db, settings)

    db.get.return_value = SimpleNamespace(is_deleted=False, status="active")
    with pytest.raises(HTTPException, match="not admitted"):
        await resolve_external_identity(payload, db, settings)


@pytest.mark.asyncio
async def test_external_identity_resolution_returns_trusted_subject(
    monkeypatch,
) -> None:
    user_id = uuid4()
    binding = SimpleNamespace(
        id=uuid4(),
        tenant_id="tenant",
        local_user_id=user_id,
        last_seen_at=None,
    )
    user = SimpleNamespace(
        id=user_id,
        name="张三",
        is_deleted=False,
        status="active",
    )

    class ConfigRepository:
        async def get_active(self, _db):
            return SimpleNamespace(app_id="app")

    class BindingRepository:
        async def resolve(self, _db, **kwargs):
            assert kwargs["external_open_id"] == "open"
            return binding

    monkeypatch.setattr(hermes_api, "FeishuConfigRepository", ConfigRepository)
    monkeypatch.setattr(
        hermes_api,
        "ExternalIdentityBindingRepository",
        BindingRepository,
    )
    db = SimpleNamespace(get=AsyncMock(return_value=user), flush=AsyncMock())
    payload = ExternalIdentityResolveRequest(
        tenant_id="tenant",
        app_fingerprint="app",
        external_open_id="open",
        chat_id="allowed",
    )

    result = await resolve_external_identity(
        payload,
        db,
        SimpleNamespace(LIVZON_FEISHU_ALLOWED_GROUPS="allowed, other"),
    )

    assert result["subject"] == {
        "tenant_id": "tenant",
        "user_id": str(user_id),
        "display_name": "张三",
        "source": "feishu",
        "external_binding_id": str(binding.id),
    }
    assert binding.last_seen_at is not None
    db.flush.assert_awaited_once()
