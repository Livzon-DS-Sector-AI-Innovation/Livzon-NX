"""设备巡检飞书镜像配置服务与 API 测试。"""

from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.llm.encryption import encrypt_api_key
from app.modules.equipment.models.inspection_feishu_config import (
    EquipmentInspectionFeishuConfig,
)
from app.modules.equipment.schemas.inspection import (
    EquipmentInspectionFeishuConfigUpdateRequest,
)
from app.modules.equipment.service import inspection_feishu_config as config_service


@pytest.fixture(autouse=True)
def _test_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config_service.settings, "LLM_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )


@pytest.fixture(autouse=True)
async def _clean_config_table(
    db_session: AsyncSession,
    _equipment_session: AsyncSession,
) -> Any:
    """前后清空配置表：update_config 会 commit，不能依赖回滚隔离。

    同时覆盖服务级会话（db_session）与 API 级共享会话
    （_equipment_session）两条写入路径。
    """
    from app.modules.equipment.models.inspection_feishu_mirror import (
        EquipmentInspectionFeishuDevice,
        EquipmentInspectionFeishuRecord,
    )
    for session in (db_session, _equipment_session):
        await session.execute(delete(EquipmentInspectionFeishuConfig))
        await session.execute(delete(EquipmentInspectionFeishuRecord))
        await session.execute(delete(EquipmentInspectionFeishuDevice))
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
    config = await config_service.get_effective_config(db_session, "201-1")
    assert config.source == "environment"
    assert config.app_id == "cli_env"
    assert config.app_secret == "env_secret"
    assert config.app_token == "bascn_env"
    assert config.enabled is True
    assert await config_service.is_mirror_enabled(db_session, "201-1") is True


async def test_effective_config_env_missing_token_disables_sync(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch, EQUIPMENT_FEISHU_BITABLE_APP_TOKEN="")
    config = await config_service.get_effective_config(db_session, "201-1")
    assert config.enabled is False


async def test_effective_config_prefers_database_row(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch)
    db_session.add(
        EquipmentInspectionFeishuConfig(
            app_id="cli_db",
            app_secret=encrypt_api_key("db_secret"),
            app_token="bascn_db",
            today_table_id="tbl_db_today",
            history_table_id="tbl_db_history",
            device_table_id="tbl_db_device",
            is_enabled=True,
        )
    )
    await db_session.commit()

    config = await config_service.get_effective_config(db_session, "201-1")
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
            app_secret=encrypt_api_key("db_secret"),
            app_token="bascn_db",
            is_enabled=False,
        )
    )
    await db_session.commit()
    assert await config_service.is_mirror_enabled(db_session, "201-1") is False


async def test_get_config_detail_masks_secret(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch)
    detail = await config_service.get_config_detail(db_session, "201-1")
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
            "201-1",
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
        "201-1",
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
        "201-1",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_keep",
            app_secret="original_secret",
            app_token="bascn_keep",
        ),
    )
    detail = await config_service.update_config(
        db_session,
        "201-1",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_keep2",
            app_secret=None,
            app_token="bascn_keep",
            today_table_id="tbl_today",
        ),
    )
    assert detail.app_id == "cli_keep2"
    assert detail.app_secret_configured is True
    config = await config_service.get_effective_config(db_session, "201-1")
    assert config.app_secret == "original_secret"


async def test_update_config_masked_resend_not_treated_as_new_secret(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    await config_service.update_config(
        db_session,
        "201-1",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_mask",
            app_secret="original_secret",
            app_token="bascn_mask",
        ),
    )
    # 前端把掩码原样带回时不得把掩码当新密钥存储
    await config_service.update_config(
        db_session,
        "201-1",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_mask",
            app_secret=config_service.mask_api_key("original_secret"),
            app_token="bascn_mask",
        ),
    )
    config = await config_service.get_effective_config(db_session, "201-1")
    assert config.app_secret == "original_secret"


async def test_update_config_enable_requires_complete_fields(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    with pytest.raises(AppException):
        await config_service.update_config(
            db_session,
            "201-1",
            EquipmentInspectionFeishuConfigUpdateRequest(
                app_id="cli_x",
                app_secret="secret_x",
                app_token="",
                is_enabled=True,
            ),
        )
    # 校验失败不落库
    detail = await config_service.get_config_detail(db_session, "201-1")
    assert detail.source == "environment"


async def test_update_config_disabled_allows_incomplete_fields(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    detail = await config_service.update_config(
        db_session,
        "201-1",
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
        "201-1",
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
            "201-1",
            EquipmentInspectionFeishuConfigUpdateRequest(
                app_id="",
                app_secret=None,
                app_token="https://x.feishu.cn/wiki/WikiNodeToken123",
            ),
        )


# ---------- 视图 ID 自动解析 ----------


class _ViewResolvingClient:
    """模拟 BitableClient：列出数据表并按表返回视图，用于 vew→tbl 解析。"""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.app_token = kwargs.get("app_token")
        self.client = self

    async def list_tables(self) -> list[dict[str, Any]]:
        return [
            {"table_id": "tbl_today"},
            {"table_id": "tbl_history"},
            {"table_id": "tbl_devices"},
        ]

    async def request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        views = {
            "tbl_today": [{"view_id": "vew_today"}],
            "tbl_history": [{"view_id": "vew_history"}],
            "tbl_devices": [{"view_id": "vew_devices"}],
        }
        for table_id, items in views.items():
            if path.endswith(f"/tables/{table_id}/views"):
                return {"items": items, "has_more": False}
        return {"items": [], "has_more": False}


async def test_update_config_resolves_view_ids_to_table_ids(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """误填视图 ID（vew…）保存时自动解析为所属数据表 ID（tbl…）。

    回归：用户从链接复制了 view= 参数，同步报 WrongTableId。
    """
    _patch_env_empty(monkeypatch)
    monkeypatch.setattr(config_service, "BitableClient", _ViewResolvingClient)
    detail = await config_service.update_config(
        db_session,
        "101-2",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_vw",
            app_secret="vw_secret",
            app_token="bascn_vw",
            today_table_id="vew_today",
            history_table_id="vew_history",
            device_table_id="vew_devices",
        ),
    )
    assert detail.today_table_id == "tbl_today"
    assert detail.history_table_id == "tbl_history"
    assert detail.device_table_id == "tbl_devices"


async def test_update_config_unresolvable_view_id_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """视图 ID 无法定位所属数据表时保存失败，提示改用 tbl 数据表 ID。"""

    class _NoViewClient(_ViewResolvingClient):
        async def request(
            self, method: str, path: str, params: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            return {"items": [{"view_id": "vew_other"}], "has_more": False}

    _patch_env_empty(monkeypatch)
    monkeypatch.setattr(config_service, "BitableClient", _NoViewClient)
    with pytest.raises(AppException, match="数据表 ID"):
        await config_service.update_config(
            db_session,
            "101-2",
            EquipmentInspectionFeishuConfigUpdateRequest(
                app_id="cli_vw",
                app_secret="vw_secret",
                app_token="bascn_vw",
                today_table_id="vew_today",
            ),
        )


async def test_update_config_view_id_requires_credentials(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """凭据不完整时无法自动解析视图 ID，保存失败并说明原因。"""
    _patch_env_empty(monkeypatch)
    db_session.add(
        EquipmentInspectionFeishuConfig(
            app_id="cli_old",
            app_secret="stored_secret",
            app_token="bascn_old",
        )
    )
    await db_session.commit()
    with pytest.raises(AppException, match="自动解析"):
        await config_service.update_config(
            db_session,
            "201-1",
            EquipmentInspectionFeishuConfigUpdateRequest(
                app_id="",
                app_secret=None,
                app_token="bascn_old",
                today_table_id="vew_today",
                is_enabled=False,
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
        "201-1",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_ok",
            app_secret="ok_secret",
            app_token="bascn_ok",
        ),
    )
    monkeypatch.setattr(config_service, "BitableClient", _FakeBitableClient)

    result = await config_service.test_config(db_session, "201-1")
    assert result.success is True
    assert result.table_count == 2
    detail = await config_service.get_config_detail(db_session, "201-1")
    assert detail.last_test_status == "success"
    assert detail.last_tested_at is not None


async def test_test_config_failure_sanitizes_and_records(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    await config_service.update_config(
        db_session,
        "201-1",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_bad",
            app_secret="bad_secret",
            app_token="bascn_secret_token",
        ),
    )
    monkeypatch.setattr(config_service, "BitableClient", _BrokenBitableClient)

    result = await config_service.test_config(db_session, "201-1")
    assert result.success is False
    assert "bascn_secret_token" not in result.message
    detail = await config_service.get_config_detail(db_session, "201-1")
    assert detail.last_test_status == "failed"
    assert detail.last_test_error is not None
    assert "bascn_secret_token" not in detail.last_test_error


async def test_test_config_unconfigured_raises(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    with pytest.raises(AppException):
        await config_service.test_config(db_session, "201-1")


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
                resp = await ac.request(
                    method, path, json={}, params={"workshop": "201-1"}
                )
                assert resp.status_code == 401, (method, path, resp.status_code)
    finally:
        app.dependency_overrides.clear()


async def test_config_api_get_put_flow(client: Any) -> None:
    resp = await client.get(
        "/api/v1/equipment/inspection/feishu/config",
        params={"workshop": "201-1"},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["source"] == "environment"

    resp = await client.put(
        "/api/v1/equipment/inspection/feishu/config",
        params={"workshop": "201-1"},
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

    resp = await client.get(
        "/api/v1/equipment/inspection/feishu/config",
        params={"workshop": "201-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["app_id"] == "cli_api"


# ---------- 镜像查询与手动同步端点 ----------


async def _seed_mirror_rows(db_session: AsyncSession) -> None:
    from datetime import date as date_type

    from app.modules.equipment.models.inspection_feishu_mirror import (
        EquipmentInspectionFeishuDevice,
        EquipmentInspectionFeishuRecord,
    )

    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="history",
            record_id="rec_api_1",
            record_date=date_type(2026, 10, 9),
            equipment_name="方锥混合机",
            equipment_no="XT1-1-1-129",
            am_clean="√",
            pm_clean="×",
            has_abnormal=True,
        )
    )
    db_session.add(
        EquipmentInspectionFeishuDevice(
            record_id="dev_api_1",
            equipment_name="方锥混合机",
            equipment_no="XT1-1-1-129",
        )
    )
    await db_session.commit()


async def test_mirror_read_endpoints(client: Any, db_session: AsyncSession) -> None:
    await _seed_mirror_rows(db_session)

    resp = await client.get(
        "/api/v1/equipment/inspection/feishu/records",
        params={"workshop": "201-1", "source": "history", "abnormal_only": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"][0]["equipment_name"] == "方锥混合机"
    assert body["data"][0]["has_abnormal"] is True
    assert body["meta"]["total"] == 1

    resp = await client.get(
        "/api/v1/equipment/inspection/feishu/devices",
        params={"workshop": "201-1", "keyword": "方锥"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["items"][0]["equipment_no"] == "XT1-1-1-129"
    assert "last_inspected_date" in resp.json()["data"]["items"][0]

    resp = await client.get(
        "/api/v1/equipment/inspection/feishu/today-summary",
        params={"workshop": "201-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["total_devices"] >= 1


async def test_mirror_records_rejects_unknown_source(client: Any) -> None:
    resp = await client.get(
        "/api/v1/equipment/inspection/feishu/records",
        params={"source": "bogus"},
    )
    assert resp.status_code == 400
    assert "source 仅支持" in resp.json()["message"]


async def test_today_summaries_lists_enabled_workshops(
    client: Any,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """汇总接口返回已启用车间的今日进度，未启用车间不出现。"""
    from datetime import date as date_type

    from app.modules.equipment.models.inspection_feishu_mirror import (
        EquipmentInspectionFeishuDevice,
        EquipmentInspectionFeishuRecord,
    )
    from app.modules.equipment.service import inspection_feishu_mirror as mirror_svc

    _patch_env(monkeypatch)  # 默认车间 201-1 走环境变量配置启用
    monkeypatch.setattr(mirror_svc, "_cst_today", lambda: date_type(2026, 10, 12))
    db_session.add(
        EquipmentInspectionFeishuDevice(record_id="dev_sum_1", equipment_no="XT-A")
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_sum_1",
            record_date=date_type(2026, 10, 12),
            equipment_no="XT-A",
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/equipment/inspection/feishu/today-summaries")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [item["workshop_code"] for item in data] == ["201-1"]
    assert data[0]["date"] == "2026-10-12"
    assert data[0]["inspected"] == 1
    assert data[0]["total_devices"] == 1
    assert data[0]["abnormal"] == 0


async def test_today_summaries_empty_when_no_workshop_enabled(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    resp = await client.get("/api/v1/equipment/inspection/feishu/today-summaries")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_mirror_sync_status_and_manual_sync(
    client: Any,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_env(monkeypatch)
    from app.modules.equipment.service import inspection_feishu_mirror as mirror_svc

    resp = await client.get(
        "/api/v1/equipment/inspection/feishu/sync-status",
        params={"workshop": "201-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["enabled"] is True

    async def fake_sync(
        db: Any, workshop: str, *, incremental: bool
    ) -> dict[str, dict[str, Any]]:
        assert workshop == "201-1"
        return {"today": {"synced": 1, "total": 1}}

    monkeypatch.setattr(mirror_svc, "sync_all", fake_sync)
    resp = await client.post(
        "/api/v1/equipment/inspection/feishu/sync",
        params={"workshop": "201-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["today"] == {"synced": 1, "total": 1}


async def test_config_test_endpoint_reports_unconfigured(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    resp = await client.post(
        "/api/v1/equipment/inspection/feishu/config/test",
        params={"workshop": "201-1"},
    )
    assert resp.status_code == 400
    assert "请先完整配置" in resp.json()["message"]


# ---------- 加密与更新分支 ----------


def test_decrypt_stored_secret_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    assert config_service._decrypt_stored_secret(None) == ""
    assert config_service._decrypt_stored_secret("") == ""

    def broken(_value: str) -> str:
        raise config_service.LLMConfigError("no key")

    monkeypatch.setattr(config_service, "decrypt_api_key", broken)
    assert config_service._decrypt_stored_secret("bad-cipher") == ""


def test_mask_short_identifier() -> None:
    assert config_service._mask_feishu_identifier("short") == "****"
    masked = config_service._mask_feishu_identifier("tblVeryLong123456")
    assert masked.startswith("tblV")


async def test_update_config_replaces_secret_on_existing_row(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)
    await config_service.update_config(
        db_session,
        "201-1",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_rotate",
            app_secret="old_secret",
            app_token="bascn_r",
        ),
    )
    detail = await config_service.update_config(
        db_session,
        "201-1",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_rotate",
            app_secret="new_secret",
            app_token="bascn_r",
        ),
    )
    assert detail.app_secret_configured is True
    config = await config_service.get_effective_config(db_session, "201-1")
    assert config.app_secret == "new_secret"


async def test_update_config_wraps_wiki_resolve_errors(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env_empty(monkeypatch)

    async def broken_resolve(**_kwargs: Any) -> str:
        raise RuntimeError("wiki node not found: bascnXYZ")

    monkeypatch.setattr(
        config_service, "resolve_wiki_bitable_app_token", broken_resolve
    )
    with pytest.raises(AppException, match="解析知识库多维表格失败"):
        await config_service.update_config(
            db_session,
            "201-1",
            EquipmentInspectionFeishuConfigUpdateRequest(
                app_id="cli_w",
                app_secret="s",
                app_token="https://x.feishu.cn/wiki/WikiNodeError",
            ),
        )


async def test_update_config_persists_base_url(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """飞书配置页：多维表格完整链接（含租户域名）随配置保存并可回读。"""
    _patch_env_empty(monkeypatch)
    link = "https://j0eukrlohu.feishu.cn/base/WehRbElQcaxkqRsvvehc7oxrnNf"
    detail = await config_service.update_config(
        db_session,
        "101-2",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_ws",
            app_secret="secret_value",
            app_token="bascn_1012",
            base_url=link,
            today_table_id="tbl_today",
            history_table_id="tbl_history",
            device_table_id="tbl_devices",
            is_enabled=True,
        ),
    )
    assert detail.base_url == link

    # 非 https 链接拒绝保存
    with pytest.raises(AppException):
        await config_service.update_config(
            db_session,
            "101-2",
            EquipmentInspectionFeishuConfigUpdateRequest(
                app_id="cli_ws",
                app_secret="",
                app_token="bascn_1012",
                base_url="http://insecure.example/base/x",
                today_table_id="tbl_today",
                history_table_id="tbl_history",
                device_table_id="tbl_devices",
                is_enabled=True,
            ),
        )


async def test_list_config_details_covers_rows_and_default_workshop(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """飞书配置清单：返回全部已配置车间 + 默认车间（环境变量回退）。"""
    _patch_env_empty(monkeypatch)
    monkeypatch.setattr(config_service.settings, "EQUIPMENT_FEISHU_APP_ID", "cli_env")
    monkeypatch.setattr(
        config_service.settings, "EQUIPMENT_FEISHU_APP_SECRET", "env_secret"
    )
    monkeypatch.setattr(
        config_service.settings,
        "EQUIPMENT_FEISHU_BITABLE_APP_TOKEN",
        "bascn_env",
    )
    await config_service.update_config(
        db_session,
        "101-2",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_ws",
            app_secret="secret_value",
            app_token="bascn_1012",
            today_table_id="tbl_today",
            history_table_id="tbl_history",
            device_table_id="tbl_devices",
            is_enabled=True,
        ),
    )
    details = await config_service.list_config_details(db_session)
    by_workshop = {d.workshop_code: d for d in details}
    assert set(by_workshop) == {"101-2", "201-1"}
    assert by_workshop["101-2"].source == "database"
    assert by_workshop["101-2"].app_token == "bascn_1012"
    assert by_workshop["201-1"].source == "environment"
    assert by_workshop["201-1"].app_token == "bascn_env"
