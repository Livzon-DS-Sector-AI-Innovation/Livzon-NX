from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.quality.api import product_quality_feishu as api
from app.platform.identity import deps, page_policy
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
@pytest.mark.parametrize("action,expected", [(None, 403), ("sync_config", 200)])
async def test_supplier_pull_requires_its_own_sensitive_action(
    monkeypatch, action, expected
):
    from app.modules.quality.api import supplier_feishu as supplier_api

    key = "quality:suppliers:supplier-qualification"
    app = FastAPI()
    app.include_router(
        supplier_api.router,
        prefix="/api/v1/quality",
        dependencies=[Depends(deps.require_module_view("quality"))],
    )
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    app.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(app.routes),
    )
    grant = EffectivePageGrantOut(
        page_key=key,
        module_code="quality",
        permissions=["access", "query", "operate"],
        sensitive_actions=[action] if action else [],
        data_scope=PageDataScopeInput(scope_type="not_applicable"),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    pull = AsyncMock(return_value={"synced": 2, "failed": 0})
    monkeypatch.setattr(supplier_api, "pull_supplier_qualification_records", pull)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/quality/supplier-qualification/pull",
            headers={"X-Dazah-Page-Key": key},
        )
    assert response.status_code == expected, response.text
    if expected == 200:
        assert response.json()["data"]["synced"] == 2
    else:
        pull.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "product,method,action,expected",
    [
        ("mfn", "GET", None, 200),
        ("dljs", "GET", None, 403),
        ("mfn", "PUT", None, 200),
        ("dljs", "PUT", None, 403),
        ("mfn", "DELETE", None, 403),
        ("mfn", "DELETE", "delete", 200),
        ("dljs", "DELETE", "delete", 403),
    ],
)
async def test_shared_product_ledger_keeps_product_page_boundary(
    monkeypatch, product, method, action, expected
):
    key = "quality:product-quality:product-quality-mfn"
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/quality",
        dependencies=[Depends(deps.require_module_view("quality"))],
    )
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    app.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(app.routes),
    )
    grant = EffectivePageGrantOut(
        page_key=key,
        module_code="quality",
        permissions=["access", "query", "operate"],
        sensitive_actions=[action] if action else [],
        data_scope=PageDataScopeInput(scope_type="not_applicable"),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    # The ordinary page grant must work without a legacy quality-write role.
    from app.modules.quality.api import deps as quality_deps

    monkeypatch.setattr(
        quality_deps, "resolve_user_permissions", AsyncMock(return_value=[])
    )
    listing = AsyncMock(
        return_value={
            "items": [{"record_id": "record", "customer_name": "全厂共享客户"}],
            "page": 1,
            "page_size": 20,
            "total": 1,
        }
    )
    updating = AsyncMock(
        return_value={"record_id": "record", "customer_name": "新客户"}
    )
    deleting = AsyncMock()
    monkeypatch.setattr(api, "list_product_quality_records", listing)
    monkeypatch.setattr(api, "update_product_quality_record", updating)
    monkeypatch.setattr(api, "delete_product_quality_record", deleting)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            f"/api/v1/quality/product-quality-standards/{product}"
            + ("" if method == "GET" else "/record"),
            headers={"X-Dazah-Page-Key": key},
            json={"customer_name": "新客户"} if method == "PUT" else None,
        )
    assert response.status_code == expected, response.text
    target = {"GET": listing, "PUT": updating, "DELETE": deleting}[method]
    if expected == 200:
        assert target.await_args.args[1] == "product_quality_mfn"
    else:
        target.assert_not_awaited()
