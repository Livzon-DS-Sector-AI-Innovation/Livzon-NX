from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.platform.identity import api as identity_api
from app.platform.identity.api import (
    create_external_identity_binding,
    get_livzon_feishu_gateway_status,
    list_external_identity_bindings,
    update_external_identity_binding_status,
)
from app.platform.identity.schemas import (
    ExternalIdentityBindingCreate,
    ExternalIdentityBindingStatusUpdate,
)


def _binding():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        tenant_id="tenant",
        platform="feishu",
        app_fingerprint="app",
        external_user_id=None,
        external_open_id="open",
        external_union_id=None,
        local_user_id=uuid4(),
        status="active",
        source="admin",
        verified_at=now,
        last_seen_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_external_identity_binding_admin_endpoints(
    monkeypatch,
) -> None:
    binding = _binding()
    current_user = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(rollback=AsyncMock(), add=lambda _item: None)
    user = SimpleNamespace(name="张三", department="质量部", status="active")

    class BindingRepository:
        async def list_page(self, _db, **_kwargs):
            return [(binding, user)], 1

        async def create(self, _db, **kwargs):
            assert kwargs["actor_id"] == current_user.id
            return binding

        async def get(self, _db, binding_id):
            return binding if binding_id == binding.id else None

        async def set_status(self, _db, item, *, status_value, **kwargs):
            assert kwargs["actor_id"] == current_user.id
            item.status = status_value
            return item

    class UserRepository:
        async def get_by_id(self, _db, user_id):
            return SimpleNamespace(id=user_id)

    monkeypatch.setattr(
        identity_api,
        "ExternalIdentityBindingRepository",
        BindingRepository,
    )
    monkeypatch.setattr(identity_api, "UserRepository", UserRepository)
    payload = ExternalIdentityBindingCreate(
        tenant_id="tenant",
        app_fingerprint="app",
        external_open_id="open",
        local_user_id=binding.local_user_id,
    )

    listed = await list_external_identity_bindings(
        db=db,
        current_user=current_user,
    )
    assert json.loads(listed.body)["data"]["items"][0]["id"] == str(binding.id)
    created = await create_external_identity_binding(payload, db, current_user)
    assert json.loads(created.body)["data"]["external_open_id"] == "open"
    suspended = await update_external_identity_binding_status(
        binding.id,
        ExternalIdentityBindingStatusUpdate(status="suspended"),
        db,
        current_user,
    )
    assert json.loads(suspended.body)["data"]["status"] == "suspended"

    with pytest.raises(HTTPException, match="不存在"):
        await update_external_identity_binding_status(
            uuid4(),
            ExternalIdentityBindingStatusUpdate(status="revoked"),
            db,
            current_user,
        )


@pytest.mark.asyncio
async def test_external_identity_binding_create_maps_expected_errors(
    monkeypatch,
) -> None:
    current_user = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(rollback=AsyncMock())
    payload = ExternalIdentityBindingCreate(
        tenant_id="tenant",
        app_fingerprint="app",
        external_open_id="open",
        local_user_id=uuid4(),
    )

    class MissingUserRepository:
        async def get_by_id(self, _db, _user_id):
            return None

    monkeypatch.setattr(identity_api, "UserRepository", MissingUserRepository)
    with pytest.raises(HTTPException, match="本地用户不存在"):
        await create_external_identity_binding(payload, db, current_user)

    class UserRepository:
        async def get_by_id(self, _db, user_id):
            return SimpleNamespace(id=user_id)

    class DuplicateBindingRepository:
        async def create(self, _db, **_kwargs):
            raise IntegrityError("INSERT", {}, Exception("duplicate"))

    monkeypatch.setattr(identity_api, "UserRepository", UserRepository)
    monkeypatch.setattr(
        identity_api,
        "ExternalIdentityBindingRepository",
        DuplicateBindingRepository,
    )
    with pytest.raises(HTTPException, match="已经绑定"):
        await create_external_identity_binding(payload, db, current_user)
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_gateway_status_maps_configuration_and_upstream_results(
    monkeypatch,
) -> None:
    current_user = SimpleNamespace(id=uuid4())
    missing = SimpleNamespace(HERMES_INTERNAL_URL="", HERMES_INTERNAL_TOKEN="")
    with pytest.raises(HTTPException, match="未配置"):
        await get_livzon_feishu_gateway_status(missing, current_user)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"connected": True}

    class Client:
        def __init__(self, *, timeout):
            assert timeout == 15

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, headers):
            assert url == "http://hermes/internal/feishu/status"
            assert headers["Authorization"] == "Bearer token"
            return Response()

    monkeypatch.setattr(identity_api.httpx, "AsyncClient", Client)
    configured = SimpleNamespace(
        HERMES_INTERNAL_URL="http://hermes/",
        HERMES_INTERNAL_TOKEN="token",
    )
    response = await get_livzon_feishu_gateway_status(configured, current_user)
    assert json.loads(response.body)["data"] == {"connected": True}

    class FailingClient(Client):
        async def get(self, url, *, headers):
            raise httpx.ConnectError("unavailable")

    monkeypatch.setattr(identity_api.httpx, "AsyncClient", FailingClient)
    with pytest.raises(HTTPException, match="状态查询失败"):
        await get_livzon_feishu_gateway_status(configured, current_user)
