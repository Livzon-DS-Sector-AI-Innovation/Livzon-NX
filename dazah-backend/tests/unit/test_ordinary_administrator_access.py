from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.platform.identity import deps, rbac, rbac_api


@pytest.mark.asyncio
async def test_ordinary_administrator_can_use_business_but_not_system_routes(
    monkeypatch,
):
    ordinary = SimpleNamespace(id=uuid4(), role="admin")
    system = SimpleNamespace(id=uuid4(), role="admin")
    current = ordinary
    monkeypatch.setattr(
        rbac,
        "is_ordinary_admin",
        AsyncMock(side_effect=lambda _db, user_id: user_id == ordinary.id),
    )
    monkeypatch.setattr(
        rbac_api,
        "is_ordinary_admin",
        AsyncMock(side_effect=lambda _db, user_id: user_id == ordinary.id),
    )

    app = FastAPI()
    app.dependency_overrides[deps.get_current_user] = lambda: current
    app.dependency_overrides[get_db] = lambda: object()

    @app.get("/business", dependencies=[Depends(deps.require_module_view("hr"))])
    async def business():
        return {"ok": True}

    @app.get("/settings-users", dependencies=[Depends(deps.require_system_admin)])
    async def settings_users():
        return {"ok": True}

    @app.get("/settings-roles", dependencies=[Depends(rbac_api.require_identity_admin)])
    async def settings_roles():
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/business")).status_code == 200
        assert (await client.get("/settings-users")).status_code == 403
        assert (await client.get("/settings-roles")).status_code == 403
        current = system
        assert (await client.get("/settings-users")).status_code == 200
        assert (await client.get("/settings-roles")).status_code == 200
