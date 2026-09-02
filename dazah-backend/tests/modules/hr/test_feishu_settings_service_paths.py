from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.hr import feishu_settings_service as service
from app.modules.hr.schemas import (
    UpdateHrFeishuAppSettingsRequest,
    UpdateHrFeishuEntitySettingRequest,
)


class _Result:
    def __init__(
        self, row: object | None = None, rows: list[object] | None = None
    ) -> None:
        self.row = row
        self.rows = rows or ([] if row is None else [row])

    def scalar_one_or_none(self) -> object | None:
        return self.row

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.rows


class _Db:
    def __init__(self, results: list[_Result]) -> None:
        self.results = results
        self.added: list[object] = []
        self.deleted_queries: list[object] = []
        self.execute = AsyncMock(side_effect=self._execute)
        self.flush = AsyncMock(side_effect=self._flush)
        self.commit = AsyncMock()

    async def _execute(self, query: object) -> _Result:
        if "DELETE" in str(query).upper():
            self.deleted_queries.append(query)
        return self.results.pop(0) if self.results else _Result()

    def add(self, row: object) -> None:
        self.added.append(row)

    async def _flush(self) -> None:
        for row in self.added:
            if getattr(row, "id", None) is None:
                row.id = "new-id"


def _app_row(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "app_id": "app-id",
        "app_secret": "secret",
        "is_enabled": True,
        "last_test_status": None,
        "last_test_error": None,
        "last_tested_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _entity_row(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "entity_code": "employee",
        "entity_name": "员工花名册",
        "entity_group": "人事台账",
        "app_token": "token",
        "base_table_name": "员工档案",
        "base_table_id": "table-id",
        "is_enabled": True,
        "enable_push_to_feishu": True,
        "enable_pull_from_feishu": True,
        "field_mappings": [],
        "sort_order": 1,
        "last_sync_status": None,
        "last_sync_error": None,
        "last_synced_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_small_helpers_cover_masking_and_mapping_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "decrypt_api_key", lambda value: f"decrypted-{value}")
    monkeypatch.setattr(service, "mask_api_key", lambda value: f"masked-{value}")
    detail = service._build_app_settings_detail(_app_row())
    assert detail.app_secret_masked == "masked-decrypted-secret"
    assert service._build_system_fields("employee")
    assert service._build_system_fields("unknown") == []
    item = service._build_entity_setting_item(_entity_row(field_mappings=None))
    assert item.field_mappings == []

    monkeypatch.setattr(
        service, "decrypt_api_key", lambda _value: (_ for _ in ()).throw(ValueError())
    )
    assert service._build_app_settings_detail(_app_row()).app_secret_masked == "****"


@pytest.mark.asyncio
async def test_app_settings_seed_credentials_and_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _app_row()
    db = _Db([_Result(existing)])
    assert await service._ensure_app_settings_seeded(db) is existing

    # 严格独立：新建行不再从平台 env 播种凭证，留空待用户在设置页填写
    monkeypatch.setattr(service._settings, "FEISHU_APP_ID", "env-id")
    monkeypatch.setattr(service._settings, "FEISHU_APP_SECRET", "env-secret")
    db = _Db([_Result()])
    seeded = await service._ensure_app_settings_seeded(db)
    assert seeded.app_id == ""
    assert seeded.app_secret == ""

    # DB 中配置了凭证（启用行）→ 解密后返回，env 不参与
    monkeypatch.setattr(
        service, "decrypt_api_key", lambda value: value.removeprefix("enc-")
    )
    cred_row = _app_row(app_id="db-id", app_secret="enc-db-secret")
    assert await service.get_hr_feishu_app_credentials(_Db([_Result(cred_row)])) == (
        "db-id",
        "db-secret",
    )

    db = _Db([_Result(_app_row()), _Result(_app_row())])
    updated = await service.update_hr_feishu_app_settings(
        db,
        UpdateHrFeishuAppSettingsRequest(
            app_id=" new-id ", app_secret=" new-secret ", is_enabled=False
        ),
    )
    assert updated.app_id == "new-id"
    assert updated.is_enabled is False
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_credentials_fallback_and_app_connection_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 严格独立：行未配置凭证时直接抛错，即使平台 env 有配置也不回退
    monkeypatch.setattr(service._settings, "FEISHU_APP_ID", "fallback-id")
    monkeypatch.setattr(service._settings, "FEISHU_APP_SECRET", "fallback-secret")
    monkeypatch.setattr(
        service, "decrypt_api_key", lambda _value: (_ for _ in ()).throw(ValueError())
    )
    with pytest.raises(service.HrFeishuNotConfigured):
        await service.get_hr_feishu_app_credentials(
            _Db([_Result(_app_row(app_id=""))])
        )

    missing = _app_row(app_id="", app_secret="")
    result = await service.test_hr_feishu_app_settings(_Db([_Result(missing)]))
    assert not result.success and missing.last_test_status == "failed"

    good = _app_row(app_secret="encrypted")
    monkeypatch.setattr(service, "decrypt_api_key", lambda _value: "secret")
    auth = AsyncMock(return_value="access-token")
    monkeypatch.setattr(service.FeishuAuth, "get_tenant_access_token", auth)
    result = await service.test_hr_feishu_app_settings(_Db([_Result(good)]))
    assert result.success and good.last_test_status == "success"

    failed = _app_row(app_secret="encrypted")
    auth.side_effect = RuntimeError("unavailable")
    result = await service.test_hr_feishu_app_settings(_Db([_Result(failed)]))
    assert not result.success and "unavailable" in result.message


@pytest.mark.asyncio
async def test_entity_reconciliation_and_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "DEFAULT_HR_FEISHU_ENTITIES",
        [
            ("employee", "员工花名册", "人事台账", 1),
            ("candidate", "候选人表", "招聘入职", 2),
        ],
    )
    monkeypatch.setattr(
        service,
        "DEFAULT_HR_FEISHU_ENTITY_MAP",
        {
            "employee": ("employee", "员工花名册", "人事台账", 1),
            "candidate": ("candidate", "候选人表", "招聘入职", 2),
        },
    )
    monkeypatch.setattr(service, "HR_FEISHU_LEGACY_TABLE_IDS", {"legacy": "fixed"})
    monkeypatch.setattr(service._settings, "FEISHU_BITABLE_APP_TOKEN", "env-token")
    existing = _entity_row(app_token=None, base_table_id="legacy", base_table_name=None)
    obsolete = _entity_row(entity_code="obsolete")
    db = _Db([_Result(rows=[existing, obsolete])])
    await service.ensure_hr_feishu_entity_settings(db)
    assert existing.base_table_id == "fixed"
    assert existing.app_token == "env-token"
    assert len(db.added) == 1
    assert db.deleted_queries

    rows = [_entity_row()]
    db = _Db([_Result(rows=rows), _Result(rows=rows)])
    listed = await service.list_hr_feishu_entity_settings(db)
    assert listed[0].entity_code == "employee"


@pytest.mark.asyncio
async def test_tables_fields_and_entity_connection_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_row(app_secret="encrypted")
    row = _entity_row()
    monkeypatch.setattr(service, "decrypt_api_key", lambda _value: "secret")

    class _Bitable:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def list_tables(self) -> list[dict[str, str]]:
            return [{"table_id": "t1", "name": "表一"}]

        async def list_fields(self, _table_id: str) -> list[dict[str, object]]:
            return [{"field_id": "f1", "field_name": "姓名", "type": 1}]

        async def search_records(
            self, _table_id: str, page_size: int
        ) -> list[dict[str, object]]:
            assert page_size == 1
            return [{"id": "r1"}]

    monkeypatch.setattr(service, "BitableClient", _Bitable)
    db = _Db([_Result(app)])
    tables = await service.list_hr_feishu_tables(db, "employee", app_token="token")
    assert tables[0].table_name == "表一"

    db = _Db([_Result(row), _Result(app), _Result(row)])
    bundle = await service.get_hr_feishu_entity_field_mapping_bundle(db, "employee")
    assert bundle.feishu_fields[0].field_name == "姓名"
    with pytest.raises(ValueError, match="不存在"):
        await service.get_hr_feishu_entity_field_mapping_bundle(_Db([]), "missing")

    broken = _Bitable.list_fields

    async def _raise_fields(self: object, _table_id: str) -> list[dict[str, object]]:
        raise RuntimeError("fields unavailable")

    monkeypatch.setattr(_Bitable, "list_fields", _raise_fields)
    db = _Db([_Result(row), _Result(app)])
    bundle = await service.get_hr_feishu_entity_field_mapping_bundle(db, "employee")
    assert bundle.feishu_fields == []
    monkeypatch.setattr(_Bitable, "list_fields", broken)

    connection = await service.test_hr_feishu_entity_setting(
        _Db([_Result(row), _Result(app)]), "employee"
    )
    assert connection.success and connection.table_id == "table-id"

    no_token = _entity_row(app_token=None, base_table_id=None)
    monkeypatch.setattr(service._settings, "FEISHU_BITABLE_APP_TOKEN", None)
    result = await service.test_hr_feishu_entity_setting(
        _Db([_Result(no_token), _Result(app)]), "employee"
    )
    assert not result.success

    monkeypatch.setattr(
        _Bitable, "search_records", AsyncMock(side_effect=RuntimeError("search failed"))
    )
    result = await service.test_hr_feishu_entity_setting(
        _Db([_Result(row), _Result(app)]), "employee"
    )
    assert not result.success and "search failed" in result.message


@pytest.mark.asyncio
async def test_entity_setting_update_and_missing_table_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "DEFAULT_HR_FEISHU_ENTITIES", [])
    monkeypatch.setattr(service, "DEFAULT_HR_FEISHU_ENTITY_MAP", {})
    # 凭证严格独立：先解析人事凭证（首个 _Result 供凭证查询），再走缺失 App Token 分支
    monkeypatch.setattr(service, "decrypt_api_key", lambda _value: "secret")
    with pytest.raises(ValueError, match="App Token"):
        await service.list_hr_feishu_tables(
            _Db([_Result(_app_row()), _Result()]), "unknown", app_token=None
        )

    monkeypatch.setattr(
        service,
        "DEFAULT_HR_FEISHU_ENTITIES",
        [("employee", "员工花名册", "人事台账", 1)],
    )
    monkeypatch.setattr(
        service,
        "DEFAULT_HR_FEISHU_ENTITY_MAP",
        {"employee": ("employee", "员工花名册", "人事台账", 1)},
    )
    row = _entity_row()
    db = _Db([_Result(rows=[row]), _Result(row)])
    updated = await service.update_hr_feishu_entity_setting(
        db,
        "employee",
        UpdateHrFeishuEntitySettingRequest(
            app_token="new-token",
            base_table_name="新表",
            base_table_id="new-table",
            field_mappings=[{"system_field": "name", "feishu_field": "姓名"}],
        ),
    )
    assert updated.app_token == "new-token"
    assert row.field_mappings[0]["system_field"] == "name"

    monkeypatch.setattr(service, "DEFAULT_HR_FEISHU_ENTITY_MAP", {})
    with pytest.raises(ValueError, match="不存在"):
        await service.update_hr_feishu_entity_setting(
            _Db([_Result(rows=[])]), "missing", UpdateHrFeishuEntitySettingRequest()
        )
