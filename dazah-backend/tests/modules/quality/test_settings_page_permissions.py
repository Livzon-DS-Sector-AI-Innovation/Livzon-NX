from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.quality.api import inspection_feishu as inspection_api
from app.modules.quality.api import quality_feishu_sync as api
from app.modules.quality.schemas import QualityFeishuAppSettingsDetail
from app.platform.identity import deps, page_policy
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,permissions,actions,expected",
    [
        (
            "POST",
            "/items/dashboard/push-low-stock/test",
            ["access", "operate"],
            [],
            403,
        ),
        (
            "POST",
            "/items/dashboard/push-low-stock/test",
            ["access", "operate"],
            ["sync_config"],
            200,
        ),
        ("GET", "/feishu-settings/app", ["access", "query"], [], 200),
        ("PUT", "/feishu-settings/app", ["access", "query"], [], 403),
        ("PUT", "/feishu-settings/app", ["access", "operate"], [], 403),
        ("POST", "/feishu-settings/app/test", ["access", "operate"], [], 403),
        ("POST", "/feishu-sync/pull", ["access", "operate"], [], 403),
        ("PUT", "/feishu-settings/app", ["access", "operate"], ["sync_config"], 200),
        ("POST", "/feishu-sync/pull", ["access", "operate"], ["sync_config"], 200),
    ],
)
async def test_settings_requires_explicit_configuration_action(
    monkeypatch, method, path, permissions, actions, expected
):
    key = "quality:quality-settings"
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/quality",
        dependencies=[Depends(deps.require_module_view("quality"))],
    )
    app.include_router(
        inspection_api.router,
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
        permissions=permissions,
        sensitive_actions=actions,
        data_scope=PageDataScopeInput(scope_type="not_applicable"),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[grant])
    )
    read = AsyncMock(return_value=QualityFeishuAppSettingsDetail())
    save = AsyncMock(return_value=QualityFeishuAppSettingsDetail(is_enabled=True))
    pull = AsyncMock(return_value={"synced": 2, "failed": 0})
    test = AsyncMock()
    push = AsyncMock(
        return_value=SimpleNamespace(model_dump=lambda **kwargs: {"sent": 1})
    )
    monkeypatch.setattr(inspection_api, "push_low_stock_alert", push)
    from app.modules.quality.api import deps as quality_deps

    monkeypatch.setattr(
        quality_deps, "resolve_user_permissions", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(api.service, "get_quality_feishu_app_settings", read)
    monkeypatch.setattr(api.service, "update_quality_feishu_app_settings", save)
    monkeypatch.setattr(api.service, "pull_quality_records_from_feishu", pull)
    monkeypatch.setattr(api.service, "test_quality_feishu_app_settings", test)
    monkeypatch.setattr(api, "try_acquire_action_lock", AsyncMock(return_value=True))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            "/api/v1/quality" + path,
            headers={"X-Dazah-Page-Key": key},
            json={} if method == "PUT" else None,
        )
    assert response.status_code == expected, response.text
    if expected == 403:
        for operation in (read, save, pull, test, push):
            operation.assert_not_awaited()
    elif path == "/items/dashboard/push-low-stock/test":
        assert response.json()["data"]["sent"] == 1
        push.assert_awaited_once_with(None, test=True)
    elif method == "PUT":
        assert response.json()["is_enabled"] is True
        save.assert_awaited_once()
    elif method == "POST":
        assert response.json()["data"]["synced"] == 2
        pull.assert_awaited_once()
    else:
        assert response.json()["app_secret_masked"] is None
        read.assert_awaited_once()
