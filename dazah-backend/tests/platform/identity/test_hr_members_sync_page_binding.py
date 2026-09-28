"""飞书联系人同步接口的页面契约回归测试。

生产曾因 POST /hr-settings/hr-members/sync 仅登记人事飞书设置页，联系人页
顶部的「从飞书同步」（该端点唯一前端入口，携带联系人页 page key）被页面
上下文校验拒绝（403「当前页面不能调用此业务接口」，超管同样被拦），前端
表现为「同步飞书联系人失败」；生产构建下 Server Action 报错被脱敏，用户
看到的是 Minified React error #441。回归锁定：同步端点对设置页与联系人页
开放，飞书连通性测试端点仍限设置页，并通过 HTTP 层覆盖超管与普通授权
用户的放行/拒绝路径。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.hr import api
from app.platform.identity.data_scope import (
    current_page_actor,
    current_page_data_scope,
    current_page_key,
)
from app.platform.identity.deps import get_current_user, require_module_view
from app.platform.identity.models import User
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import api_binding_for_route
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput

CONTACTS_PAGE_KEY = "hr:employee-management:feishu-contacts"
SETTINGS_PAGE_KEY = "hr:hr-settings:hr-settings-feishu"
PROFILE_PAGE_KEY = "hr:employee-management:profile"

_SYNC = "/api/v1/hr/hr-settings/hr-members/sync"
_SYNC_STATUS = "/api/v1/hr/hr-settings/hr-members/sync-status"
_APP_TEST = "/api/v1/hr/feishu-settings/app/test"


@pytest.fixture(autouse=True)
def page_context():
    key = current_page_key.set(None)
    actor = current_page_actor.set(None)
    scope = current_page_data_scope.set(None)
    yield
    current_page_key.reset(key)
    current_page_actor.reset(actor)
    current_page_data_scope.reset(scope)


def _binding_pages(method: str, path: str) -> tuple[str, ...]:
    binding = api_binding_for_route(method, path)
    assert binding is not None, f"{method} {path} 绑定缺失或契约校验未通过"
    return binding.page_keys


def test_members_sync_open_to_settings_and_contacts_pages():
    assert _binding_pages("POST", _SYNC) == (
        SETTINGS_PAGE_KEY,
        CONTACTS_PAGE_KEY,
    )


def test_members_sync_status_get_keeps_contacts_page():
    pages = _binding_pages("GET", _SYNC_STATUS)
    assert CONTACTS_PAGE_KEY in pages
    assert SETTINGS_PAGE_KEY in pages


def test_feishu_connectivity_test_stays_settings_only():
    assert _binding_pages("POST", _APP_TEST) == (
        SETTINGS_PAGE_KEY,
    )


def _app(db, user):
    app = FastAPI()
    app.include_router(
        api.router,
        prefix="/api/v1/hr",
        dependencies=[Depends(require_module_view("hr"))],
    )
    app.dependency_overrides[get_db] = lambda: db
    # 模块访问模式由身份测试套件覆盖；此处隔离页面授权链路。
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _contacts_grant(*, actions: list[str]) -> EffectivePageGrantOut:
    return EffectivePageGrantOut(
        page_key=CONTACTS_PAGE_KEY,
        module_code="hr",
        permissions=["access", "query", "operate"],
        sensitive_actions=actions,
        data_scope=PageDataScopeInput(scope_type="all", department_ids=[]),
        source="user",
    )


@pytest.mark.asyncio
async def test_super_admin_can_sync_from_contacts_page(db_session, monkeypatch):
    import app.core.jobs as jobs

    monkeypatch.setattr(jobs, "is_job_running", AsyncMock(return_value=False))
    monkeypatch.setattr(jobs, "submit_job", AsyncMock())
    admin = User(
        name="超管", username="hr-sync-admin", role="admin", status="active"
    )
    app = _app(db_session, admin)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            _SYNC, headers={"X-Dazah-Page-Key": CONTACTS_PAGE_KEY}
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["state"] == "running"


@pytest.mark.asyncio
async def test_sync_from_unregistered_page_is_rejected(db_session, monkeypatch):
    admin = User(
        name="超管", username="hr-sync-admin-2", role="admin", status="active"
    )
    app = _app(db_session, admin)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            _SYNC, headers={"X-Dazah-Page-Key": PROFILE_PAGE_KEY}
        )
        assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_granted_user_can_sync_from_contacts_page(db_session, monkeypatch):
    import app.core.jobs as jobs

    monkeypatch.setattr(jobs, "is_job_running", AsyncMock(return_value=False))
    monkeypatch.setattr(jobs, "submit_job", AsyncMock())
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(return_value=[_contacts_grant(actions=["sync_config"])]),
    )
    actor = User(
        name="授权用户", username="hr-sync-user", role="user", status="active"
    )
    app = _app(db_session, actor)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            _SYNC, headers={"X-Dazah-Page-Key": CONTACTS_PAGE_KEY}
        )
        assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_granted_user_without_sensitive_action_is_rejected(
    db_session, monkeypatch
):
    monkeypatch.setattr(
        PagePermissionService,
        "effective_grants",
        AsyncMock(
            return_value=[_contacts_grant(actions=["delete"])]
        ),
    )
    actor = User(
        name="缺动作用户", username="hr-sync-user-2", role="user", status="active"
    )
    app = _app(db_session, actor)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            _SYNC, headers={"X-Dazah-Page-Key": CONTACTS_PAGE_KEY}
        )
        assert response.status_code == 403, response.text
