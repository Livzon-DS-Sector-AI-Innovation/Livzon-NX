"""飞书自建应用凭据库：CRUD 与巡检配置引用解析测试。"""

from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models.feishu_app import EquipmentFeishuApp
from app.modules.equipment.models.inspection_feishu_config import (
    EquipmentInspectionFeishuConfig,
)
from app.modules.equipment.schemas.inspection import (
    EquipmentFeishuAppCreateRequest,
    EquipmentFeishuAppUpdateRequest,
    EquipmentInspectionFeishuConfigUpdateRequest,
)
from app.modules.equipment.service import feishu_app as app_service
from app.modules.equipment.service import inspection_feishu_config as config_service


@pytest.fixture(autouse=True)
async def _clean_tables(
    db_session: AsyncSession, _equipment_session: AsyncSession
) -> Any:
    """前后清空应用库与配置表：服务内 commit，不能依赖回滚隔离。"""
    for session in (db_session, _equipment_session):
        await session.execute(delete(EquipmentInspectionFeishuConfig))
        await session.execute(delete(EquipmentFeishuApp))
        await session.commit()
    yield
    for session in (db_session, _equipment_session):
        await session.execute(delete(EquipmentInspectionFeishuConfig))
        await session.execute(delete(EquipmentFeishuApp))
        await session.commit()


def _patch_env_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "EQUIPMENT_FEISHU_APP_ID",
        "EQUIPMENT_FEISHU_APP_SECRET",
        "EQUIPMENT_FEISHU_BITABLE_APP_TOKEN",
        "EQUIPMENT_FEISHU_BITABLE_TODAY_TABLE_ID",
        "EQUIPMENT_FEISHU_BITABLE_HISTORY_TABLE_ID",
        "EQUIPMENT_FEISHU_BITABLE_DEVICE_TABLE_ID",
    ):
        monkeypatch.setattr(config_service.settings, key, "")


async def _create_app(
    db_session: AsyncSession,
    name: str = "设备巡检应用",
    app_id: str = "cli_app1",
    secret: str = "app_secret_value",
) -> EquipmentFeishuApp:
    item = await app_service.create_app(
        db_session,
        EquipmentFeishuAppCreateRequest(name=name, app_id=app_id, app_secret=secret),
    )
    return await _get_app_row(db_session, item.id)


async def _get_app_row(db_session: AsyncSession, app_row_id: Any) -> EquipmentFeishuApp:
    return (
        await db_session.execute(
            select(EquipmentFeishuApp).where(EquipmentFeishuApp.id == app_row_id)
        )
    ).scalars().one()


# ---------- 应用库 CRUD ----------


async def test_create_app_encrypts_secret_and_masks_response(
    db_session: AsyncSession,
) -> None:
    item = await app_service.create_app(
        db_session,
        EquipmentFeishuAppCreateRequest(
            name="巡检应用", app_id="cli_new", app_secret="plain_secret"
        ),
    )
    assert item.app_id == "cli_new"
    assert item.app_secret_configured is True
    # Secret 明文不出现在响应序列化里
    assert "plain_secret" not in item.model_dump_json()

    # 测试环境未配置加密密钥时 encrypt/decrypt 为直通存储；
    # 生产配置密钥后此处为密文（与巡检配置 Secret 同一机制）
    row = await _get_app_row(db_session, item.id)
    assert row.app_secret
    assert app_service.decrypt_app_secret(row.app_secret) == "plain_secret"


async def test_create_app_rejects_duplicate_app_id(db_session: AsyncSession) -> None:
    await _create_app(db_session)
    with pytest.raises(AppException, match="已存在"):
        await app_service.create_app(
            db_session,
            EquipmentFeishuAppCreateRequest(
                name="另一个应用", app_id="cli_app1", app_secret="x"
            ),
        )


async def test_update_app_blank_secret_keeps_stored(
    db_session: AsyncSession,
) -> None:
    item = await _create_app(db_session)
    updated = await app_service.update_app(
        db_session,
        item.id,
        EquipmentFeishuAppUpdateRequest(name="改名", app_id="cli_app1", app_secret=None),
    )
    assert updated.name == "改名"
    config = app_service.decrypt_app_secret((await _get_app_row(db_session, item.id)).app_secret)
    assert config == "app_secret_value"


async def test_update_app_new_secret_takes_effect(
    db_session: AsyncSession,
) -> None:
    item = await _create_app(db_session)
    await app_service.update_app(
        db_session,
        item.id,
        EquipmentFeishuAppUpdateRequest(name="巡检应用", app_id="cli_app1", app_secret="rotated"),
    )
    row = await _get_app_row(db_session, item.id)
    assert app_service.decrypt_app_secret(row.app_secret) == "rotated"


async def test_delete_app_blocked_while_referenced(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    item = await _create_app(db_session)
    await config_service.update_config(
        db_session,
        "101-2",
        EquipmentInspectionFeishuConfigUpdateRequest(
            feishu_app_id=item.id,
            app_id="",
            app_secret=None,
            app_token="bascn_ref",
        ),
    )
    with pytest.raises(AppException, match="仍被.*巡检配置引用"):
        await app_service.delete_app(db_session, item.id)

    # 改回手动凭据后可删除
    await config_service.update_config(
        db_session,
        "101-2",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_manual",
            app_secret="manual_secret",
            app_token="bascn_ref",
        ),
    )
    await app_service.delete_app(db_session, item.id)
    apps = await app_service.list_apps(db_session)
    assert apps == []


# ---------- 巡检配置引用应用库 ----------


async def test_update_config_with_app_reference_resolves_credentials(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """凭据来源选应用库：免填 App ID/Secret，凭据按应用库解析。"""
    _patch_env_empty(monkeypatch)
    item = await _create_app(db_session)
    detail = await config_service.update_config(
        db_session,
        "201-2-DR",
        EquipmentInspectionFeishuConfigUpdateRequest(
            feishu_app_id=item.id,
            app_id="",
            app_secret=None,
            app_token="bascn_dr",
            today_table_id="tbl_today",
            history_table_id="tbl_history",
            device_table_id="tbl_devices",
            is_enabled=True,
        ),
    )
    assert detail.feishu_app_id == item.id
    assert detail.feishu_app_name == "设备巡检应用"
    assert detail.app_id == "cli_app1"
    assert detail.app_secret_configured is True
    assert detail.enabled is True

    config = await config_service.get_effective_config(db_session, "201-2-DR")
    assert config.app_id == "cli_app1"
    assert config.app_secret == "app_secret_value"


async def test_app_secret_rotation_propagates_to_referencing_config(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """应用库 Secret 轮换后引用它的车间配置即时生效（改一处全车间生效）。"""
    _patch_env_empty(monkeypatch)
    item = await _create_app(db_session)
    await config_service.update_config(
        db_session,
        "101-2",
        EquipmentInspectionFeishuConfigUpdateRequest(
            feishu_app_id=item.id, app_id="", app_secret=None, app_token="bascn_x"
        ),
    )
    await app_service.update_app(
        db_session,
        item.id,
        EquipmentFeishuAppUpdateRequest(
            name="设备巡检应用", app_id="cli_app1", app_secret="rotated_secret"
        ),
    )
    config = await config_service.get_effective_config(db_session, "101-2")
    assert config.app_secret == "rotated_secret"


async def test_update_config_rejects_missing_app_reference(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    import uuid

    with pytest.raises(AppException, match="不存在"):
        await config_service.update_config(
            db_session,
            "101-2",
            EquipmentInspectionFeishuConfigUpdateRequest(
                feishu_app_id=uuid.uuid4(),
                app_id="",
                app_secret=None,
                app_token="bascn_x",
            ),
        )


async def test_deleted_app_reference_disables_credentials(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """引用的应用被直接删除后凭据视为未配置（镜像停用），不回退脏数据。"""
    _patch_env_empty(monkeypatch)
    item = await _create_app(db_session)
    await config_service.update_config(
        db_session,
        "101-2",
        EquipmentInspectionFeishuConfigUpdateRequest(
            feishu_app_id=item.id, app_id="", app_secret=None, app_token="bascn_x"
        ),
    )
    # 绕过引用校验直接软删应用
    row = await _get_app_row(db_session, item.id)
    row.is_deleted = True
    await db_session.commit()

    config = await config_service.get_effective_config(db_session, "101-2")
    assert config.app_id == ""
    assert config.app_secret == ""
    assert config.enabled is False


async def test_switch_back_to_manual_clears_app_reference(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    item = await _create_app(db_session)
    await config_service.update_config(
        db_session,
        "101-2",
        EquipmentInspectionFeishuConfigUpdateRequest(
            feishu_app_id=item.id, app_id="", app_secret=None, app_token="bascn_x"
        ),
    )
    detail = await config_service.update_config(
        db_session,
        "101-2",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_manual", app_secret="manual_secret", app_token="bascn_x"
        ),
    )
    assert detail.feishu_app_id is None
    assert detail.app_id == "cli_manual"


# ---------- API ----------


async def test_apps_api_requires_login(db_session: AsyncSession) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.main import app

    async def _override_get_db() -> Any:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/v1/equipment/inspection/feishu/apps")
            assert resp.status_code == 401
            resp = await ac.post(
                "/api/v1/equipment/inspection/feishu/apps",
                json={"name": "x", "app_id": "cli_x", "app_secret": "s"},
            )
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


async def test_apps_api_create_list_update_flow(client: Any) -> None:
    resp = await client.post(
        "/api/v1/equipment/inspection/feishu/apps",
        json={"name": "巡检应用", "app_id": "cli_api", "app_secret": "secret_value"},
    )
    assert resp.status_code == 200
    created = resp.json()["data"]
    assert created["app_secret_configured"] is True
    assert "app_secret" not in created

    resp = await client.get("/api/v1/equipment/inspection/feishu/apps")
    assert resp.status_code == 200
    apps = resp.json()["data"]
    assert [a["app_id"] for a in apps] == ["cli_api"]

    resp = await client.put(
        f"/api/v1/equipment/inspection/feishu/apps/{created['id']}",
        json={"name": "巡检应用改名", "app_id": "cli_api", "app_secret": None},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "巡检应用改名"

    resp = await client.delete(
        f"/api/v1/equipment/inspection/feishu/apps/{created['id']}"
    )
    assert resp.status_code == 200
    resp = await client.get("/api/v1/equipment/inspection/feishu/apps")
    assert resp.json()["data"] == []
