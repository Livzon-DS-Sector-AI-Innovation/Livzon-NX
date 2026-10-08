"""安全模块飞书设置与知识库同步的页面级权限执行测试。

对齐质量模块 test_settings_page_permissions：设置写入与同步端点绑定页面
sensitive_action=sync_config，未获授权的非管理员调用应 403。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.safety.api import feishu_settings as settings_api
from app.modules.safety.api import knowledge as knowledge_api
from app.platform.identity import deps, page_policy
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import (
    EffectivePageGrantOut,
    PageDataScopeInput,
)


def _build_app() -> FastAPI:
    application = FastAPI()
    application.include_router(
        settings_api.feishu_settings_router,
        prefix="/api/v1/safety",
        dependencies=[Depends(deps.require_module_view("safety"))],
    )
    application.include_router(
        knowledge_api.knowledge_router,
        prefix="/api/v1/safety",
        dependencies=[Depends(deps.require_module_view("safety"))],
    )
    application.dependency_overrides[get_db] = lambda: None
    return application


def _install_user(application: FastAPI, monkeypatch, permissions, actions) -> None:
    application.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    application.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(application.routes),
    )
    grant = EffectivePageGrantOut(
        page_key="safety:system-config:safety-feishu-settings",
        module_code="safety",
        permissions=permissions,
        sensitive_actions=actions,
        data_scope=PageDataScopeInput(scope_type="not_applicable"),
        source="user",
    )
    knowledge_grant = EffectivePageGrantOut(
        page_key="safety:regulation-info:knowledge-base",
        module_code="safety",
        permissions=["access", "operate"],
        sensitive_actions=["sync_config"],
        data_scope=PageDataScopeInput(scope_type="not_applicable"),
        source="user",
    )
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(return_value=[grant, knowledge_grant]),
    )


def _mock_services(monkeypatch) -> None:
    from app.modules.safety.schemas.feishu_settings import (
        SafetyFeishuAppSettingsDetail,
    )

    monkeypatch.setattr(
        settings_api.feishu_settings,
        "update_safety_feishu_app_settings",
        AsyncMock(return_value=SafetyFeishuAppSettingsDetail()),
    )
    monkeypatch.setattr(
        settings_api.feishu_settings,
        "get_safety_feishu_app_settings",
        AsyncMock(return_value=SafetyFeishuAppSettingsDetail()),
    )
    monkeypatch.setattr(
        knowledge_api.knowledge_feishu,
        "sync_knowledge_from_feishu",
        AsyncMock(return_value={"created": 0, "updated": 0, "removed": 0, "failed": 0}),
    )


async def _call(
    application: FastAPI, method: str, path: str, page_key: str | None = None
) -> int:
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        resp = await ac.request(
            method,
            path,
            headers={"X-Dazah-Page-Key": page_key} if page_key else {},
            json={"app_id": "cli_x", "app_secret": ""}
            if method == "PUT"
            else None,
        )
        return resp.status_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "permissions,actions,expected",
    [
        # query 权限不足以写配置
        (["access", "query"], [], 403),
        # 仅 operate 不足，必须带 sync_config 敏感动作
        (["access", "operate"], [], 403),
        (["access", "operate"], ["sync_config"], 200),
    ],
)
async def test_settings_write_requires_sync_config_action(
    monkeypatch, permissions, actions, expected
):
    application = _build_app()
    _install_user(application, monkeypatch, permissions, actions)
    _mock_services(monkeypatch)
    status = await _call(
        application,
        "PUT",
        "/api/v1/safety/feishu-settings/app",
        page_key="safety:system-config:safety-feishu-settings",
    )
    assert status == expected


@pytest.mark.asyncio
async def test_knowledge_sync_requires_sync_config_on_knowledge_page(monkeypatch):
    application = _build_app()
    # 设置页无任何授权（permissions 空）也不影响知识库页的同步判定
    _install_user(application, monkeypatch, [], [])
    _mock_services(monkeypatch)
    status = await _call(
        application,
        "POST",
        "/api/v1/safety/knowledge-articles/feishu/sync",
        page_key="safety:regulation-info:knowledge-base",
    )
    assert status == 200


@pytest.mark.asyncio
async def test_admin_bypasses_page_action_check(monkeypatch):
    application = _build_app()
    application.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="admin"
    )
    _mock_services(monkeypatch)
    assert (
        await _call(application, "PUT", "/api/v1/safety/feishu-settings/app") == 200
    )


@pytest.mark.asyncio
async def test_settings_read_requires_query_permission(monkeypatch):
    application = _build_app()
    _install_user(application, monkeypatch, ["access", "query"], [])
    _mock_services(monkeypatch)
    status = await _call(
        application,
        "GET",
        "/api/v1/safety/feishu-settings/app",
        page_key="safety:system-config:safety-feishu-settings",
    )
    assert status == 200
