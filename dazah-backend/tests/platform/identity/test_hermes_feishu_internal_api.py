from __future__ import annotations

import hmac
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.platform.identity import hermes_api
from app.platform.identity.hermes_api import _require_internal


class FakeIdentityDb:
    def __init__(self, user) -> None:
        self.user = user
        self.flush_count = 0

    async def get(self, model, key):
        return self.user if key == self.user.id else None

    async def flush(self) -> None:
        self.flush_count += 1


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


@pytest.mark.anyio
async def test_resolved_subject_uses_local_user_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        name="测试用户",
        tenant_key="local-tenant",
        is_deleted=False,
        status="active",
    )
    binding = SimpleNamespace(
        id=uuid4(),
        local_user_id=user.id,
        tenant_id="gateway-alias",
        last_seen_at=None,
    )
    config = SimpleNamespace(
        app_id="cli_test",
        allowed_group_chat_ids=[],
    )

    async def fake_get_active(self, db):
        return config

    async def fake_resolve(self, db, **kwargs):
        assert kwargs["tenant_id"] == "gateway-alias"
        return binding

    monkeypatch.setattr(
        hermes_api.FeishuConfigRepository,
        "get_active",
        fake_get_active,
    )
    monkeypatch.setattr(
        hermes_api.ExternalIdentityBindingRepository,
        "resolve",
        fake_resolve,
    )
    db = FakeIdentityDb(user)
    payload = hermes_api.ExternalIdentityResolveRequest(
        tenant_id="gateway-alias",
        app_fingerprint="cli_test",
        external_open_id="ou_test",
    )

    result = await hermes_api.resolve_external_identity(
        payload,
        db,
        Settings(LIVZON_FEISHU_ALLOWED_GROUPS=""),
    )

    assert result["subject"]["tenant_id"] == "local-tenant"
    assert db.flush_count == 1
