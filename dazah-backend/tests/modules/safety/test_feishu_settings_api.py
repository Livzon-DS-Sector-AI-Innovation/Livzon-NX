"""安全模块飞书设置 API 路由测试。

用子应用 + 依赖覆盖验证 GET/PUT/POST test 三端点的路由、鉴权依赖与
序列化行为；服务层用 mock 隔离（服务本身在 service 测试中用真实会话覆盖）。
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.safety.api import feishu_settings as api
from app.modules.safety.schemas.feishu_settings import (
    SafetyFeishuAppSettingsDetail,
    SafetyFeishuSettingsTestResult,
)


@pytest.fixture
def sub_app(monkeypatch) -> FastAPI:
    application = FastAPI()
    application.include_router(api.feishu_settings_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_db] = lambda: None
    # 模块级 require_module_view 已在全局路由装配处生效；子应用用登录用户直通
    application.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    return application


@pytest.fixture
def client(sub_app: FastAPI):
    return AsyncClient(
        transport=ASGITransport(app=sub_app), base_url="http://test"
    )


async def test_get_app_settings_returns_masked_detail(sub_app, client, monkeypatch):
    detail = SafetyFeishuAppSettingsDetail(
        app_id="cli_x",
        app_secret_masked="cli_****_abcd",
        bitable_app_token="bascnX",
        bitable_hazard_table_id="tblX",
        is_enabled=True,
        last_test_status="success",
        last_tested_at=datetime(2026, 10, 8, 12, 0, tzinfo=UTC),
    )
    fake = AsyncMock(return_value=detail)
    monkeypatch.setattr(api.feishu_settings, "get_safety_feishu_app_settings", fake)

    resp = await client.get("/api/v1/safety/feishu-settings/app")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["app_id"] == "cli_x"
    assert body["data"]["app_secret_masked"] == "cli_****_abcd"
    assert "app_secret" not in body["data"] or body["data"].get("app_secret") is None
    fake.assert_awaited_once()


async def test_put_app_settings_saves_and_returns_detail(client, monkeypatch):
    detail = SafetyFeishuAppSettingsDetail(app_id="cli_x", app_secret_masked="****")
    fake = AsyncMock(return_value=detail)
    monkeypatch.setattr(api.feishu_settings, "update_safety_feishu_app_settings", fake)

    resp = await client.put(
        "/api/v1/safety/feishu-settings/app",
        json={
            "app_id": "cli_x",
            "app_secret": "new-secret",
            "bitable_app_token": "bascnX",
            "bitable_hazard_table_id": "tblX",
            "is_enabled": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["app_id"] == "cli_x"
    request = fake.await_args.args[1]
    assert request.app_id == "cli_x"
    assert request.app_secret == "new-secret"


async def test_put_app_settings_rejects_empty_app_id(client):
    resp = await client.put(
        "/api/v1/safety/feishu-settings/app",
        json={"app_id": "", "app_secret": "s"},
    )
    assert resp.status_code == 422


async def test_test_app_settings_returns_result(client, monkeypatch):
    result = SafetyFeishuSettingsTestResult(
        success=False,
        message="app secret invalid",
        checked_at=datetime(2026, 10, 8, 12, 0, tzinfo=UTC),
    )
    fake = AsyncMock(return_value=result)
    monkeypatch.setattr(api.feishu_settings, "test_safety_feishu_app_settings", fake)

    resp = await client.post("/api/v1/safety/feishu-settings/app/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["success"] is False
    assert body["data"]["message"] == "app secret invalid"
    fake.assert_awaited_once()


