import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock
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
        sync_status="success",
        sync_error=None,
        last_synced_at=datetime(2026, 8, 14, tzinfo=UTC),
        last_sync_record_count=2,
        sync_total_records=None,
        sync_fetched_count=0,
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


class _FakeSyncSession:
    def __init__(self) -> None:
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.refresh = AsyncMock()

    async def __aenter__(self) -> "_FakeSyncSession":
        return self

    async def __aexit__(self, *_args) -> bool:
        return False


def _install_fake_sync_session(monkeypatch: pytest.MonkeyPatch) -> _FakeSyncSession:
    fake = _FakeSyncSession()
    monkeypatch.setattr(procurement_api, "async_session_factory", lambda: fake)
    return fake


@pytest.mark.anyio
async def test_material_sync_lock_heartbeat_renews_lock_until_cancelled(
    monkeypatch,
) -> None:
    renew = AsyncMock()
    monkeypatch.setattr(procurement_api, "renew_lock", renew)
    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(procurement_api.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await procurement_api._lock_heartbeat("lock-key")

    assert sleeps == 3
    assert renew.await_count == 2
    renew.assert_awaited_with(
        "lock-key",
        procurement_api.MATERIAL_SYNC_LOCK_TTL_SECONDS,
    )


@pytest.mark.anyio
async def test_admin_can_sync_material_source_and_records_audit(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    result = SimpleNamespace(
        config=_config(),
        synced_count=24,
        deactivated_count=3,
    )

    async def sync(_db, *, user_id):
        assert user_id
        return result

    monkeypatch.setattr(
        procurement_api,
        "get_material_source_config",
        lambda _db: _async_value(config),
    )
    monkeypatch.setattr(procurement_api, "sync_material_source", sync)
    monkeypatch.setattr(
        procurement_api,
        "acquire_lock",
        AsyncMock(return_value=True),
    )
    release = _async_mock()
    monkeypatch.setattr(procurement_api, "release_lock", release)
    audit = AsyncMock()
    monkeypatch.setattr(procurement_api, "record_audit_log", audit)
    fake_session = _install_fake_sync_session(monkeypatch)

    response = await admin_client.post(
        "/api/v1/procurement/material-source-config/sync",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "采购物料数据同步已启动"
    assert response.json()["data"]["synced_count"] == 0
    assert response.json()["data"]["deactivated_count"] == 0
    assert response.json()["data"]["config"]["sync_status"] == "syncing"
    audit.assert_awaited_once_with(
        fake_session,
        action="procurement_material_source_synced",
        user_id=ANY,
        resource_type="procurement_material_source_config",
        resource_id=config.id,
        new_value={
            "synced_count": 24,
            "deactivated_count": 3,
            "sync_status": "success",
        },
    )
    fake_session.commit.assert_awaited_once()
    release.assert_awaited_once()


@pytest.mark.anyio
async def test_sync_conflict_when_sync_already_running(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    config.sync_status = "syncing"
    monkeypatch.setattr(
        procurement_api,
        "get_material_source_config",
        lambda _db: _async_value(config),
    )
    monkeypatch.setattr(
        procurement_api,
        "acquire_lock",
        AsyncMock(return_value=False),
    )
    sync = _async_mock()
    monkeypatch.setattr(procurement_api, "sync_material_source", sync)

    response = await admin_client.post(
        "/api/v1/procurement/material-source-config/sync",
        json={},
    )

    assert response.status_code == 409
    assert response.json()["message"] == "物料数据同步正在进行中，请稍后重试"
    sync.assert_not_awaited()


@pytest.mark.anyio
async def test_sync_recovers_stale_lock_when_status_is_clear(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    monkeypatch.setattr(
        procurement_api,
        "get_material_source_config",
        lambda _db: _async_value(config),
    )
    monkeypatch.setattr(
        procurement_api,
        "acquire_lock",
        AsyncMock(side_effect=[False, True]),
    )
    release = _async_mock()
    monkeypatch.setattr(procurement_api, "release_lock", release)

    async def sync(_db, *, user_id):
        return SimpleNamespace(
            config=_config(),
            synced_count=0,
            deactivated_count=0,
        )

    monkeypatch.setattr(procurement_api, "sync_material_source", sync)
    monkeypatch.setattr(procurement_api, "record_audit_log", _async_mock())
    _install_fake_sync_session(monkeypatch)

    response = await admin_client.post(
        "/api/v1/procurement/material-source-config/sync",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "采购物料数据同步已启动"
    # 陈旧锁释放一次，后台任务结束后释放一次
    assert release.await_count == 2


@pytest.mark.anyio
async def test_clear_stale_material_sync_lock_releases_residual_lock(
    monkeypatch,
) -> None:
    config = _config()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(
        procurement_api,
        "async_session_factory",
        lambda: FakeSession(),
    )
    monkeypatch.setattr(
        procurement_api,
        "get_material_source_config",
        AsyncMock(return_value=config),
    )
    release = AsyncMock()
    monkeypatch.setattr(procurement_api, "release_lock", release)

    await procurement_api.clear_stale_material_sync_lock()

    release.assert_awaited_once_with(
        procurement_api._material_sync_lock_key(config.id)
    )

    monkeypatch.setattr(
        procurement_api,
        "get_material_source_config",
        AsyncMock(return_value=None),
    )
    await procurement_api.clear_stale_material_sync_lock()
    release.assert_awaited_once()


@pytest.mark.anyio
async def test_sync_conflict_when_redis_down_and_status_syncing(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    config.sync_status = "syncing"
    monkeypatch.setattr(
        procurement_api,
        "get_material_source_config",
        lambda _db: _async_value(config),
    )

    async def unavailable(*_args, **_kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(procurement_api, "acquire_lock", unavailable)
    sync = _async_mock()
    monkeypatch.setattr(procurement_api, "sync_material_source", sync)

    response = await admin_client.post(
        "/api/v1/procurement/material-source-config/sync",
        json={},
    )

    assert response.status_code == 409
    assert response.json()["message"] == "同步依赖的 Redis 当前不可用，请稍后重试"
    sync.assert_not_awaited()


@pytest.mark.anyio
async def test_sync_proceeds_when_redis_down_but_status_clear(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        procurement_api,
        "get_material_source_config",
        lambda _db: _async_value(_config()),
    )

    async def unavailable(*_args, **_kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(procurement_api, "acquire_lock", unavailable)
    release = _async_mock()
    monkeypatch.setattr(procurement_api, "release_lock", release)

    async def sync(_db, *, user_id):
        return SimpleNamespace(
            config=_config(),
            synced_count=0,
            deactivated_count=0,
        )

    monkeypatch.setattr(procurement_api, "sync_material_source", sync)
    monkeypatch.setattr(procurement_api, "record_audit_log", _async_mock())
    _install_fake_sync_session(monkeypatch)

    response = await admin_client.post(
        "/api/v1/procurement/material-source-config/sync",
        json={},
    )

    assert response.status_code == 409
    assert response.json()["message"] == "同步依赖的 Redis 当前不可用，请稍后重试"
    release.assert_not_awaited()


@pytest.mark.anyio
async def test_authorized_user_can_list_material_catalog_with_filters(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def list_catalog(_db, **kwargs):
        assert kwargs == {
            "keyword": "MAT",
            "material_code": "MAT-001",
            "material_description": "第一条",
            "rule_model": "A",
            "page": 2,
            "page_size": 20,
        }
        record = SimpleNamespace(
            id=uuid4(),
            feishu_record_id="rec-1",
            material_code="MAT-001",
            material_description="第一条",
            rule_model="A",
            feishu_created_time=None,
            feishu_last_modified_time=None,
            last_synced_at=datetime(2026, 8, 14, tzinfo=UTC),
        )
        return [record], 1, _config()

    monkeypatch.setattr(procurement_api, "list_material_catalog", list_catalog)
    response = await admin_client.get(
        "/api/v1/procurement/material-catalog"
        "?keyword=MAT&material_code=MAT-001&material_description=%E7%AC%AC%E4%B8%80%E6%9D%A1"
        "&rule_model=A&page=2&page_size=20"
    )

    assert response.status_code == 200
    assert response.json()["data"][0]["material_code"] == "MAT-001"
    assert response.json()["meta"] == {
        "page": 2,
        "page_size": 20,
        "total": 1,
        "sync_status": "success",
        "sync_error": None,
        "last_synced_at": "2026-08-14T00:00:00Z",
        "last_sync_record_count": 2,
        "sync_total_records": None,
        "sync_fetched_count": 0,
        "sync_phase": "idle",
        "sync_persisted_count": 0,
        "sync_heartbeat_at": None,
        "last_successful_modified_time": None,
    }


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
        response = await client.get("/api/v1/procurement/material-options?keyword=MAT")

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


@pytest.mark.anyio
async def test_material_options_timeout_returns_504(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def list_options(*_args, **_kwargs):
        raise MaterialSourceTimeoutError("飞书物料数据源请求超时")

    monkeypatch.setattr(procurement_api, "list_material_options", list_options)
    response = await admin_client.get(
        "/api/v1/procurement/material-options?keyword=MAT"
    )

    assert response.status_code == 504
    assert response.json()["message"] == "飞书物料数据源请求超时"


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


async def test_sync_endpoint_serializes_real_orm_config_after_commit(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 ORM 配置在 commit 后序列化不触发异步懒加载（回归 MissingGreenlet）。

    测试配置由数据库生成 updated_at（onupdate），模拟生产数据特征；
    SimpleNamespace mock 无法覆盖此场景。
    """
    from sqlalchemy import delete, select

    from app.core.database import async_session_factory
    from app.modules.procurement.models import (
        MaterialCatalogRecord,
        MaterialSourceConfig,
    )
    from app.platform.identity.deps import get_current_user

    async with async_session_factory() as session:
        async def _override_get_db():
            try:
                yield session
            finally:
                pass

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            role="admin",
            status="active",
            id=uuid4(),
        )
        try:
            await session.execute(
                delete(MaterialCatalogRecord).where(
                    MaterialCatalogRecord.source_config_id.in_(
                        select(MaterialSourceConfig.id).where(
                            MaterialSourceConfig.config_key == "material-master"
                        )
                    )
                )
            )
            await session.execute(
                delete(MaterialSourceConfig).where(
                    MaterialSourceConfig.config_key == "material-master"
                )
            )
            await session.commit()

            session.add(
                MaterialSourceConfig(
                    config_key="material-master",
                    source_url="https://feishu.cn/base/appToken123456?table=tbl123456",
                    app_token="appToken123456",
                    table_id="tbl123456",
                    material_code_field="物料编码",
                    material_description_field="物料说明",
                    rule_model_field="规格型号",
                    last_test_status="success",
                    sync_status="not_synced",
                    sync_phase="idle",
                    last_sync_record_count=0,
                    sync_persisted_count=0,
                )
            )
            await session.commit()

            monkeypatch.setattr(
                procurement_api,
                "acquire_lock",
                AsyncMock(return_value=True),
            )
            monkeypatch.setattr(procurement_api, "release_lock", AsyncMock())
            monkeypatch.setattr(procurement_api, "record_audit_log", AsyncMock())
            monkeypatch.setattr(
                procurement_api,
                "_run_material_source_sync",
                AsyncMock(),
            )

            response = await client.post(
                "/api/v1/procurement/material-source-config/sync",
                json={},
            )
            assert response.status_code == 200
            assert response.json()["message"] == "采购物料数据同步已启动"
            assert response.json()["data"]["config"]["sync_status"] == "syncing"
        finally:
            await session.execute(
                delete(MaterialCatalogRecord).where(
                    MaterialCatalogRecord.source_config_id.in_(
                        select(MaterialSourceConfig.id).where(
                            MaterialSourceConfig.config_key == "material-master"
                        )
                    )
                )
            )
            await session.execute(
                delete(MaterialSourceConfig).where(
                    MaterialSourceConfig.config_key == "material-master"
                )
            )
            await session.commit()
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)

