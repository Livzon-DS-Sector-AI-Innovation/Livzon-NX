from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.modules.procurement import api as procurement_api
from app.modules.procurement.material_source import (
    MaterialSourcePermissionError,
    MaterialSourceTimeoutError,
)
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User, UserModuleGrant


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        source_url="https://feishu.cn/base/appToken123456?table=tbl123456&view=vew123456",
        app_token="appToken123456",
        table_id="tbl123456",
        view_id="vew123456",
        material_code_field="物料编码",
        material_description_field="物料说明",
        rule_model_field="规格型号",
        last_test_status="success",
        last_test_error=None,
        last_tested_at=datetime(2026, 8, 14, tzinfo=UTC),
        updated_at=datetime(2026, 8, 14, tzinfo=UTC),
    )


@pytest.fixture
async def admin_client(client: AsyncClient):
    async def _override_current_user():
        return SimpleNamespace(role="admin", status="active", id=uuid4())

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def regular_client(client: AsyncClient):
    async def _override_current_user():
        return SimpleNamespace(role="user", status="active", id=uuid4())

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_admin_can_get_and_save_material_source_config(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    monkeypatch.setattr(
        procurement_api,
        "get_material_source_config",
        lambda _db: _async_value(config),
    )

    response = await admin_client.get("/api/v1/procurement/material-source-config")

    assert response.status_code == 200
    assert response.json()["data"]["table_id"] == "tbl123456"

    async def save(_db, payload, *, user_id):
        assert payload.source_url.startswith("https://feishu.cn/base/")
        assert user_id
        return config

    monkeypatch.setattr(procurement_api, "save_material_source_config", save)
    audit = _async_mock()
    monkeypatch.setattr(procurement_api, "record_audit_log", audit)
    response = await admin_client.put(
        "/api/v1/procurement/material-source-config",
        json={"source_url": config.source_url},
    )

    assert response.status_code == 200
    assert response.json()["data"]["rule_model_field"] == "规格型号"
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_non_admin_cannot_save_material_source_config(
    regular_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save = _async_mock()
    monkeypatch.setattr(procurement_api, "save_material_source_config", save)

    response = await regular_client.put(
        "/api/v1/procurement/material-source-config",
        json={"source_url": "https://feishu.cn/base/appToken123456?table=tbl123456"},
    )

    assert response.status_code == 403
    save.assert_not_awaited()


@pytest.mark.anyio
async def test_admin_config_endpoints_map_material_source_errors(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def test_config(*_args, **_kwargs):
        raise MaterialSourcePermissionError("飞书多维表格访问失败")

    monkeypatch.setattr(
        procurement_api,
        "test_material_source_config",
        test_config,
    )
    response = await admin_client.post(
        "/api/v1/procurement/material-source-config/test",
        json={"source_url": _config().source_url},
    )

    assert response.status_code == 502
    assert response.json()["message"] == "飞书多维表格访问失败"

    async def save_config(*_args, **_kwargs):
        raise MaterialSourceTimeoutError("飞书多维表格请求超时")

    monkeypatch.setattr(
        procurement_api,
        "save_material_source_config",
        save_config,
    )
    response = await admin_client.put(
        "/api/v1/procurement/material-source-config",
        json={"source_url": _config().source_url},
    )

    assert response.status_code == 504
    assert response.json()["message"] == "飞书多维表格请求超时"


@pytest.mark.anyio
async def test_regular_user_can_query_duplicate_material_options(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def override_db():
        yield db_session

    original_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    user = User(
        name="采购物料联想测试用户",
        username=f"material-options-{uuid4().hex[:12]}",
        role="user",
        status="active",
        auth_source="local",
    )
    db_session.add(user)
    await db_session.flush()

    async def override_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    db_session.add(
        UserModuleGrant(
            user_id=user.id,
            module_code="procurement",
            permissions=["module.view"],
            data_scope={},
            grant_version=1,
            granted_by=user.id,
            status="active",
        )
    )
    await db_session.flush()

    async def list_options(_db, *, keyword, limit):
        assert keyword == "MAT"
        assert limit == 20
        return [
            {
                "record_id": "rec-1",
                "material_code": "MAT-001",
                "material_description": "第一条",
                "rule_model": "A",
            },
            {
                "record_id": "rec-2",
                "material_code": "MAT-001",
                "material_description": "第二条",
                "rule_model": "B",
            },
        ]

    monkeypatch.setattr(procurement_api, "list_material_options", list_options)
    try:
        response = await client.get(
            "/api/v1/procurement/material-options?keyword=MAT"
        )

        assert response.status_code == 200
        assert [item["record_id"] for item in response.json()["data"]] == [
            "rec-1",
            "rec-2",
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if original_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original_db_override


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (MaterialSourcePermissionError("飞书多维表格访问失败"), 502),
        (MaterialSourceTimeoutError("飞书多维表格请求超时"), 504),
    ],
)
async def test_material_option_external_failures_have_stable_status(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
) -> None:
    async def list_options(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(procurement_api, "list_material_options", list_options)
    response = await admin_client.get(
        "/api/v1/procurement/material-options?keyword=MAT"
    )

    assert response.status_code == status_code
    assert response.json()["message"] in {
        "飞书多维表格访问失败",
        "飞书多维表格请求超时",
    }


class _AsyncMock:
    def __init__(self) -> None:
        self.await_count = 0

    def assert_awaited_once(self) -> None:
        assert self.await_count == 1

    def assert_not_awaited(self) -> None:
        assert self.await_count == 0

    async def __call__(self, *_args, **_kwargs):
        self.await_count += 1


def _async_mock() -> _AsyncMock:
    return _AsyncMock()


async def _async_value(value):
    return value
