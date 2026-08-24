from __future__ import annotations

from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.quality.models.feishu_settings import (
    QualityFeishuAppSettings,
    QualityFeishuEntitySetting,
)
from app.modules.quality.schemas.feishu_settings import (
    UpdateQualityFeishuAppSettingsRequest,
    UpdateQualityFeishuEntitySettingRequest,
)
from app.modules.quality.service import quality_feishu_settings as service
from app.modules.quality.service import quality_feishu_sync

SimpleNamespace: Any = _SimpleNamespace


class _Result:
    def __init__(self: Any, value: Any = None, values: Any = None) -> None:
        self.value = value
        self.values = values or []

    def scalar_one_or_none(self: Any) -> Any:
        return self.value

    def scalars(self: Any) -> Any:
        return SimpleNamespace(all=lambda: self.values)


def _db() -> SimpleNamespace:
    return SimpleNamespace(
        add=Mock(),
        execute=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        flush=AsyncMock(),
    )


def _app_model() -> QualityFeishuAppSettings:
    return QualityFeishuAppSettings(
        app_id="cli_test_app",
        app_secret="encrypted-secret",
        is_enabled=True,
    )


def _entity_model(
    entity_code: str = "deviation_ledger",
) -> QualityFeishuEntitySetting:
    name, group, order = service.DEFAULT_QUALITY_FEISHU_ENTITY_MAP[entity_code]
    return QualityFeishuEntitySetting(
        entity_code=entity_code,
        entity_name=name,
        entity_group=group,
        sort_order=order,
        app_token="bascn123456789",
        base_table_name="偏差台账",
        base_table_id="tbl123456789",
        is_enabled=True,
        enable_push_to_feishu=True,
        enable_pull_from_feishu=True,
        field_mappings=[
            {
                "system_field": "偏差编号",
                "feishu_field": "偏差编号",
            }
        ],
    )


def test_quality_feishu_setting_helpers_cover_defaults_and_redaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = service._build_default_entity_items()
    assert len(defaults) == len(service.DEFAULT_QUALITY_FEISHU_ENTITIES)
    assert any(item.entity_code == "deviation_ledger" for item in defaults)

    assert service._get_default_sync_directions("inspection_records") == (
        True,
        False,
    )
    assert service._get_default_sync_directions("supplier_ledger") == (
        True,
        False,
    )
    assert service._get_default_sync_directions("deviation_ledger") == (
        True,
        True,
    )
    assert service._is_settings_table_missing(
        RuntimeError("quality_feishu_app_settings does not exist")
    )
    assert not service._is_settings_table_missing(RuntimeError("timeout"))

    assert service._looks_like_test_app_settings(
        " CLI_APP_SEEDED ",
        "normal",
    )
    assert service._looks_like_test_app_settings(
        "normal",
        " TEST_SECRET_SEEDED ",
    )
    assert not service._looks_like_test_app_settings("prod", "secret")
    assert service._mask_feishu_identifier("short") == "****"
    sanitized = service._sanitize_feishu_error_message(
        "failed bascn123456789 and tbl987654321"
    )
    assert "bascn123456789" not in sanitized
    assert "tbl987654321" not in sanitized

    with pytest.raises(ValueError, match="读取失败") as exc_info:
        service._raise_feishu_metadata_error(
            "读取",
            RuntimeError("bad bascn123456789"),
        )
    assert exc_info.value.__cause__ is not None

    fields = service._build_system_fields("deviation_ledger")
    assert fields
    assert all(field.field_key for field in fields)
    assert service._build_system_fields("missing") == []

    monkeypatch.setattr(
        service.settings,
        "FEISHU_APP_ID",
        "  cli_app  ",
    )
    assert service._get_setting_value("FEISHU_APP_ID") == "cli_app"
    assert service._get_setting_value("MISSING_SETTING") == ""


@pytest.mark.anyio
async def test_app_settings_create_update_and_connection_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db()
    monkeypatch.setattr(service, "encrypt_api_key", lambda value: f"enc:{value}")
    monkeypatch.setattr(
        service,
        "decrypt_api_key",
        lambda value: value.removeprefix("enc:"),
    )
    monkeypatch.setattr(service, "mask_api_key", lambda value: f"mask:{value}")
    get_model: Any = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "_get_app_settings_model", get_model)

    data = UpdateQualityFeishuAppSettingsRequest(
        app_id=" cli_app ",
        app_secret=" cli_secret ",
        is_enabled=True,
    )
    detail = await service.update_quality_feishu_app_settings(db, data)
    created = db.add.call_args.args[0]
    assert created.app_id == "cli_app"
    assert created.app_secret == "enc:cli_secret"
    assert detail.app_secret_masked == "mask:cli_secret"
    db.commit.assert_awaited_once()

    get_model.return_value = created
    masked = UpdateQualityFeishuAppSettingsRequest(
        app_id="updated_app",
        app_secret="mask:cli_secret",
        is_enabled=False,
    )
    await service.update_quality_feishu_app_settings(db, masked)
    assert created.app_id == "updated_app"
    assert created.app_secret == "enc:cli_secret"
    assert created.is_enabled is False

    monkeypatch.setattr(
        service,
        "_ensure_quality_feishu_app_settings_seeded",
        AsyncMock(return_value=created),
    )
    auth: Any = AsyncMock(return_value="tenant-token")
    monkeypatch.setattr(
        service.FeishuAuth,  # type: ignore[attr-defined]
        "get_tenant_access_token",
        auth,
    )
    success = await service.test_quality_feishu_app_settings(db)
    assert success.success is True
    assert created.last_test_status == "success"

    auth.side_effect = RuntimeError("network unavailable")
    failed = await service.test_quality_feishu_app_settings(db)
    assert failed.success is False
    assert "network unavailable" in failed.message
    assert created.last_test_status == "failed"


@pytest.mark.anyio
async def test_entity_refresh_records_success_and_sanitized_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db()
    model = _entity_model()
    monkeypatch.setattr(
        service,
        "_get_entity_settings_model",
        AsyncMock(return_value=model),
    )
    pull: Any = AsyncMock()
    monkeypatch.setattr(
        quality_feishu_sync,
        "pull_quality_records_from_feishu",
        pull,
    )

    refreshed = await service._refresh_entity_data_after_save(
        db,
        model.entity_code,
    )
    assert refreshed is model
    assert model.last_sync_status == "success"
    pull.assert_awaited_once_with(db, entity_code=model.entity_code)

    pull.side_effect = RuntimeError("failed tbl123456789")
    failed = await service._refresh_entity_data_after_save(
        db,
        model.entity_code,
    )
    assert failed is model
    assert model.last_sync_status == "failed"
    assert "tbl123456789" not in (model.last_sync_error or "")
    db.rollback.assert_awaited_once()

    model.is_enabled = False
    pull.reset_mock()
    assert await service._refresh_entity_data_after_save(db, model.entity_code) is model
    pull.assert_not_awaited()


@pytest.mark.anyio
async def test_list_tables_and_field_mapping_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db()
    app_model = _app_model()
    entity = _entity_model()
    client: Any = SimpleNamespace(
        list_tables=AsyncMock(
            return_value=[
                {"table_id": "tbl123456789", "name": "偏差台账"},
                {"table_id": "", "name": "invalid"},
            ]
        ),
        list_fields=AsyncMock(
            return_value=[
                {
                    "field_id": "fld001",
                    "field_name": "偏差编号",
                    "type": 1,
                },
                {"field_id": "", "field_name": "invalid", "type": 1},
            ]
        ),
    )
    monkeypatch.setattr(
        service,
        "_ensure_quality_feishu_app_settings_seeded",
        AsyncMock(return_value=app_model),
    )
    monkeypatch.setattr(
        service,
        "ensure_quality_feishu_entity_settings",
        AsyncMock(return_value=[entity]),
    )
    monkeypatch.setattr(service, "build_bitable_client", lambda **_: client)
    monkeypatch.setattr(service, "decrypt_api_key", lambda _: "secret")

    tables = await service.list_quality_feishu_tables(
        db,
        entity.entity_code,
    )
    assert [item.table_id for item in tables] == ["tbl123456789"]

    bundle = await service.get_quality_feishu_entity_field_mapping_bundle(
        db,
        entity.entity_code,
    )
    assert bundle.entity_code == entity.entity_code
    assert bundle.feishu_fields[0].field_name == "偏差编号"
    mapping = next(
        item for item in bundle.field_mappings if item.system_field == "偏差编号"
    )
    assert mapping.feishu_field == "偏差编号"

    with pytest.raises(ValueError, match="实体配置不存在"):
        await service.list_quality_feishu_tables(db, "unknown")


@pytest.mark.anyio
async def test_update_and_test_entity_setting_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db()
    entity = _entity_model()
    app_model = _app_model()
    monkeypatch.setattr(
        service,
        "ensure_quality_feishu_entity_settings",
        AsyncMock(return_value=[entity]),
    )
    monkeypatch.setattr(
        service,
        "_get_entity_settings_model",
        AsyncMock(return_value=entity),
    )
    monkeypatch.setattr(
        service,
        "_refresh_entity_data_after_save",
        AsyncMock(return_value=entity),
    )

    update = UpdateQualityFeishuEntitySettingRequest(
        app_token="bascnUPDATED123",
        base_table_name=" 更新台账 ",
        base_table_id="tblUPDATED123",
        is_enabled=True,
        enable_push_to_feishu=True,
        enable_pull_from_feishu=False,
        field_mappings=None,
    )
    item = await service.update_quality_feishu_entity_setting(
        db,
        entity.entity_code,
        update,
    )
    assert item.base_table_name == "更新台账"
    assert item.enable_pull_from_feishu is False

    client: Any = SimpleNamespace(search_records=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        service,
        "_ensure_quality_feishu_app_settings_seeded",
        AsyncMock(return_value=app_model),
    )
    db.execute.return_value = _Result(value=entity)
    monkeypatch.setattr(service, "build_bitable_client", lambda **_: client)
    monkeypatch.setattr(service, "decrypt_api_key", lambda _: "secret")

    success = await service.test_quality_feishu_entity_setting(
        db,
        entity.entity_code,
    )
    assert success.success is True
    assert entity.last_sync_status == "success"

    client.search_records.side_effect = RuntimeError("permission denied")
    failed = await service.test_quality_feishu_entity_setting(
        db,
        entity.entity_code,
    )
    assert failed.success is False
    assert entity.last_sync_status == "failed"
