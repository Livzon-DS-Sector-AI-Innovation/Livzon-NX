from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.router import api_router
from app.core.database import get_db
from app.modules.dossier_writer import api
from app.platform.identity import deps, permission_middleware, rbac
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
async def test_dossier_grant_controls_real_mounted_read_and_delete(monkeypatch):
    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.dependency_overrides[get_db] = lambda: None
    application.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    list_dossiers = AsyncMock(return_value=([], 0))
    delete_dossier = AsyncMock(return_value=True)
    monkeypatch.setattr(api.DossierService, "list_product_dossiers", list_dossiers)
    monkeypatch.setattr(api.DossierService, "delete_product_dossier", delete_dossier)
    declaration = EffectivePageGrantOut(
        page_key="registration:project:declaration-progress:international-planned-in-progress",
        module_code="registration",
        permissions=["access", "query", "operate"],
        sensitive_actions=["delete"],
        data_scope=PageDataScopeInput(scope_type="all"),
        source="user",
    )
    dossier = declaration.model_copy(
        update={
            "page_key": "registration:dossier-writer",
            "permissions": ["access", "query"],
            "sensitive_actions": [],
        }
    )
    effective = AsyncMock(return_value=[declaration])
    monkeypatch.setattr(PagePermissionService, "effective_grants", effective)
    product_id = uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        path = "/api/v1/dossier-writer/products"
        headers = {"X-Dazah-Page-Path": "/registration/dossier-writer"}
        assert (await client.get(path, headers=headers)).status_code == 403
        list_dossiers.assert_not_awaited()
        effective.return_value = [dossier]
        response = await client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.json()["data"] == {
            "items": [], "total": 0, "skip": 0, "limit": 100
        }
        delete_path = f"{path}/{product_id}"
        assert (await client.delete(delete_path, headers=headers)).status_code == 403
        operator = dossier.model_copy(update={"permissions": declaration.permissions})
        effective.return_value = [operator]
        assert (await client.delete(delete_path, headers=headers)).status_code == 403
        delete_dossier.assert_not_awaited()
        effective.return_value = [
            operator.model_copy(update={"sensitive_actions": ["delete"]})
        ]
        response = await client.delete(delete_path, headers=headers)
        assert response.status_code == 200
        assert response.json()["code"] == 200
        delete_dossier.assert_awaited_once_with(product_id)


def test_dossier_middleware_recognizes_mounted_registration_guard():
    from app.main import app

    path = "/api/v1/dossier-writer/products"
    request = SimpleNamespace(
        app=app, scope={"type": "http", "path": path, "method": "GET"}
    )
    module = rbac.match_module(path)
    assert module == "registration"
    assert permission_middleware._has_module_access_dependency(request, module)
