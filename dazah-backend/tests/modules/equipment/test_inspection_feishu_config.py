"""设备巡检飞书镜像配置服务与 API 测试。"""

from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models.inspection_feishu_config import (
    EquipmentInspectionFeishuConfig,
)
from app.modules.equipment.schemas.inspection import (
    EquipmentInspectionFeishuConfigUpdateRequest,
)
from app.modules.equipment.service import inspection_feishu_config as config_service


@pytest.fixture(autouse=True)
async def _clean_config_table(
    db_session: AsyncSession,
    _equipment_session: AsyncSession,
) -> Any:
    """前后清空配置表：update_config 会 commit，不能依赖回滚隔离。

    同时覆盖服务级会话（db_session）与 API 级共享会话
    （_equipment_session）两条写入路径。
    """
    for session in (db_session, _equipment_session):
        await session.execute(delete(EquipmentInspectionFeishuConfig))
        await session.commit()
    yield
    for session in (db_session, _equipment_session):
        await session.execute(delete(EquipmentInspectionFeishuConfig))
        await session.commit()


def _patch_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    values = {
        "EQUIPMENT_FEISHU_APP_ID": "cli_env",
        "EQUIPMENT_FEISHU_APP_SECRET": "env_secret",
        "EQUIPMENT_FEISHU_BITABLE_APP_TOKEN": "bascn_env",
        "EQUIPMENT_FEISHU_BITABLE_TODAY_TABLE_ID": "tbl_env_today",
        "EQUIPMENT_FEISHU_BITABLE_HISTORY_TABLE_ID": "tbl_env_history",
        "EQUIPMENT_FEISHU_BITABLE_DEVICE_TABLE_ID": "tbl_env_device",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setattr(config_service.settings, key, value)


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


# ---------- 生效配置解析 ----------


async def test_effective_config_falls_back_to_environment(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch)
    config = await config_service.get_effective_config(db_session)
    assert config.source == "environment"
    assert config.app_id == "cli_env"
    assert config.app_secret == "env_secret"
    assert config.app_token == "bascn_env"
    assert config.enabled is True
    assert await config_service.is_mirror_enabled(db_session) is True


async def test_effective_config_env_missing_token_disables_sync(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch, EQUIPMENT_FEISHU_BITABLE_APP_TOKEN="")
    config = await config_service.get_effective_config(db_session)
    assert config.enabled is False


async def test_effective_config_prefers_database_row(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch)
    db_session.add(
        EquipmentInspectionFeishuConfig(
            app_id="cli_db",
            app_secret="db_secret",
            app_token="bascn_db",
            today_table_id="tbl_db_today",
            history_table_id="tbl_db_history",
            device_table_id="tbl_db_device",
            is_enabled=True,
        )
    )
    await db_session.commit()

    config = await config_service.get_effective_config(db_session)
    assert config.source == "database"
    assert config.app_id == "cli_db"
    assert config.app_secret == "db_secret"
    assert config.app_token == "bascn_db"


async def test_effective_config_disabled_switch_stops_sync(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch)
    db_session.add(
        EquipmentInspectionFeishuConfig(
            app_id="cli_db",
            app_secret="db_secret",
            app_token="bascn_db",
            is_enabled=False,
        )
    )
    await db_session.commit()
    assert await config_service.is_mirror_enabled(db_session) is False


async def test_get_config_detail_masks_secret(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch)
    detail = await config_service.get_config_detail(db_session)
    assert detail.source == "environment"
    assert detail.app_secret_configured is True
    assert detail.app_secret_masked == "****"  # 短密钥全掩码，不回传明文
    assert "env_secret" not in detail.model_dump_json()


# ---------- 保存配置 ----------


async def test_update_config_first_save_requires_credentials(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    with pytest.raises(AppException):
        await config_service.update_config(
            db_session,
            EquipmentInspectionFeishuConfigUpdateRequest(
                app_id="", app_secret="", app_token=""
            ),
        )


async def test_update_config_creates_row_and_returns_detail(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    detail = await config_service.update_config(
        db_session,
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_new",
            app_secret="new_secret_value",
            app_token="https://x.feishu.cn/base/bascn_new?table=tbl_a&view=v",
            today_table_id="tbl_today",
            history_table_id="tbl_history",
            device_table_id="tbl_devices",
            is_enabled=True,
        ),
    )
    assert detail.source == "database"
    assert detail.enabled is True
    # URL 粘贴自动归一为裸 token / table id
    assert detail.app_token == "bascn_new"
    assert detail.today_table_id == "tbl_today"
    assert detail.last_test_status is None


async def test_update_config_blank_secret_keeps_stored_value(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    await config_service.update_config(
        db_session,
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_keep",
            app_secret="original_secret",
            app_token="bascn_keep",
        ),
    )
    detail = await config_service.update_config(
        db_session,
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_keep2",
            app_secret=None,
            app_token="bascn_keep",
            today_table_id="tbl_today",
        ),
    )
    assert detail.app_id == "cli_keep2"
    assert detail.app_secret_configured is True
    config = await config_service.get_effective_config(db_session)
    assert config.app_secret == "original_secret"


async def test_update_config_masked_resend_not_treated_as_new_secret(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    await config_service.update_config(
        db_session,
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_mask",
            app_secret="original_secret",
            app_token="bascn_mask",
        ),
    )
    # 前端把掩码原样带回时不得把掩码当新密钥存储
    await config_service.update_config(
        db_session,
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_mask",
            app_secret=config_service.mask_api_key("original_secret"),
            app_token="bascn_mask",
        ),
    )
    config = await config_service.get_effective_config(db_session)
    assert config.app_secret == "original_secret"


async def test_update_config_enable_requires_complete_fields(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    with pytest.raises(AppException):
        await config_service.update_config(
            db_session,
            EquipmentInspectionFeishuConfigUpdateRequest(
                app_id="cli_x",
                app_secret="secret_x",
                app_token="",
                is_enabled=True,
            ),
        )
    # 校验失败不落库
    detail = await config_service.get_config_detail(db_session)
    assert detail.source == "environment"


async def test_update_config_disabled_allows_incomplete_fields(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    detail = await config_service.update_config(
        db_session,
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_partial",
            app_secret="partial_secret",
            app_token="",
            is_enabled=False,
        ),
    )
    assert detail.is_enabled is False
    assert detail.enabled is False


async def test_update_config_resolves_wiki_link(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)

    async def fake_resolve(**kwargs: Any) -> str:
        assert kwargs["app_id"] == "cli_wiki"
        assert kwargs["app_secret"] == "wiki_secret"
        return "bascn_resolved"

    monkeypatch.setattr(
        config_service, "resolve_wiki_bitable_app_token", fake_resolve
    )
    detail = await config_service.update_config(
        db_session,
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_wiki",
            app_secret="wiki_secret",
            app_token="https://x.feishu.cn/wiki/WikiNodeToken123",
        ),
    )
    assert detail.app_token == "bascn_resolved"


async def test_update_config_wiki_requires_credentials(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    db_session.add(
        EquipmentInspectionFeishuConfig(
            app_id="cli_old",
            app_secret="stored_secret",
            app_token="bascn_old",
        )
    )
    await db_session.commit()
    # 数据库行存在但提交的 app_id/secret 为空 → 无法解析 wiki 链接
    with pytest.raises(AppException):
        await config_service.update_config(
            db_session,
            EquipmentInspectionFeishuConfigUpdateRequest(
                app_id="",
                app_secret=None,
                app_token="https://x.feishu.cn/wiki/WikiNodeToken123",
            ),
        )


# ---------- 连接测试 ----------


class _FakeBitableClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def list_tables(self) -> list[dict[str, Any]]:
        return [{"table_id": "tbl1"}, {"table_id": "tbl2"}]


class _BrokenBitableClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def list_tables(self) -> list[dict[str, Any]]:
        raise RuntimeError("request failed for bascn_secret_token")


async def test_test_config_success_records_status(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    await config_service.update_config(
        db_session,
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_ok",
            app_secret="ok_secret",
            app_token="bascn_ok",
        ),
    )
    monkeypatch.setattr(config_service, "BitableClient", _FakeBitableClient)

    result = await config_service.test_config(db_session)
    assert result.success is True
    assert result.table_count == 2
    detail = await config_service.get_config_detail(db_session)
    assert detail.last_test_status == "success"
    assert detail.last_tested_at is not None


async def test_test_config_failure_sanitizes_and_records(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    await config_service.update_config(
        db_session,
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_bad",
            app_secret="bad_secret",
            app_token="bascn_secret_token",
        ),
    )
    monkeypatch.setattr(config_service, "BitableClient", _BrokenBitableClient)

    result = await config_service.test_config(db_session)
    assert result.success is False
    assert "bascn_secret_token" not in result.message
    detail = await config_service.get_config_detail(db_session)
    assert detail.last_test_status == "failed"
    assert detail.last_test_error is not None
    assert "bascn_secret_token" not in detail.last_test_error


async def test_test_config_unconfigured_raises(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    with pytest.raises(AppException):
        await config_service.test_config(db_session)


# ---------- API ----------


async def test_config_api_requires_login(db_session: AsyncSession) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.main import app

    async def _override_get_db() -> Any:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            for method, path in (
                ("GET", "/api/v1/equipment/inspection/feishu/config"),
                ("PUT", "/api/v1/equipment/inspection/feishu/config"),
                ("POST", "/api/v1/equipment/inspection/feishu/config/test"),
            ):
                resp = await ac.request(method, path, json={})
                assert resp.status_code == 401, (method, path, resp.status_code)
    finally:
        app.dependency_overrides.clear()


async def test_config_api_get_put_flow(client: Any) -> None:
    resp = await client.get("/api/v1/equipment/inspection/feishu/config")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["source"] == "environment"

    resp = await client.put(
        "/api/v1/equipment/inspection/feishu/config",
        json={
            "app_id": "cli_api",
            "app_secret": "api_secret",
            "app_token": "bascn_api",
            "today_table_id": "tbl_api_today",
            "history_table_id": "tbl_api_history",
            "device_table_id": "tbl_api_device",
            "is_enabled": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["source"] == "database"
    assert body["enabled"] is True
    assert "app_secret" not in body
    assert body["app_secret_masked"]

    resp = await client.get("/api/v1/equipment/inspection/feishu/config")
    assert resp.status_code == 200
    assert resp.json()["data"]["app_id"] == "cli_api"
