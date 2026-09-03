"""验证与确认年度表（验证主计划/QC验证）解析与通用 CRUD 扩展测试。

覆盖：year → 实体后缀解析、年度列表/详情/增删改的实体路由、
QC验证实体白名单、人员字段写入转换、通用列表与配置检测。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException
from app.modules.quality.service import inspection_feishu_crud as crud_service
from app.modules.quality.service import quality_feishu_pages as pages

# ─── 验证主计划年度实体解析 ───────────────────────────────────────


def test_entity_code_for_validation_type_appends_year_suffix() -> None:
    assert pages._entity_code_for_validation_type(None) == "validation_master_plan"
    assert (
        pages._entity_code_for_validation_type(None, 2026)
        == "validation_master_plan_2026"
    )
    assert (
        pages._entity_code_for_validation_type("process_validation", 2025)
        == "validation_process_2025"
    )
    assert (
        pages._entity_code_for_validation_type("cleaning_validation")
        == "validation_cleaning"
    )


@pytest.mark.asyncio
async def test_list_validation_records_uses_year_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_entity_codes: list[str] = []

    async def _fake_search(db, entity_code: str, **kwargs):
        seen_entity_codes.append(entity_code)
        return []

    monkeypatch.setattr(
        pages, "_resolve_runtime_entity", AsyncMock(return_value=(object(), object()))
    )
    monkeypatch.setattr(pages, "_search_entity_records", _fake_search)

    await pages.list_validation_records_from_feishu(
        SimpleNamespace(), year=2026, page=1, page_size=10
    )
    assert seen_entity_codes == ["validation_master_plan_2026"]

    # 未配置年度实体 → 空列表不抛错
    monkeypatch.setattr(
        pages,
        "_resolve_runtime_entity",
        AsyncMock(side_effect=AppException(message="disabled")),
    )
    result = await pages.list_validation_records_from_feishu(
        SimpleNamespace(), year=2027
    )
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_get_validation_record_year_unconfigured_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pages,
        "_resolve_runtime_entity",
        AsyncMock(side_effect=AppException(message="disabled")),
    )
    with pytest.raises(AppException) as exc_info:
        await pages.get_validation_record_from_feishu(
            SimpleNamespace(), "rec-1", year=2026
        )
    assert "2026 年度验证飞书表未配置" in str(exc_info.value.message)

    # 无 year 时保持原提示
    with pytest.raises(AppException) as exc_info:
        await pages.get_validation_record_from_feishu(SimpleNamespace(), "rec-1")
    assert "验证与确认飞书 Base 未启用" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_validation_write_operations_route_to_year_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    async def _fake_create(db, entity_code, fields, *, search_conditions=None):
        seen["create"] = entity_code
        return {"record_id": "rec-new"}

    async def _fake_update(db, entity_code, record_id, fields, *,
                           search_conditions=None):
        seen["update"] = entity_code
        return {"record_id": record_id}

    async def _fake_delete(db, entity_code, record_id, actor_user_id=None):
        seen["delete"] = entity_code

    monkeypatch.setattr(pages, "_create_entity_record", _fake_create)
    monkeypatch.setattr(pages, "_update_entity_record", _fake_update)
    monkeypatch.setattr(pages, "_delete_entity_record", _fake_delete)
    monkeypatch.setattr(
        pages,
        "_get_department_contacts_cache",
        AsyncMock(return_value=[]),
    )
    detail = {
        "record_id": "rec-1",
        "validation_type": "",
        "title": "方案A",
        "record_code": "",
        "created_at": None,
        "updated_at": None,
    }

    async def _fake_get(db, record_id, validation_type=None, year=None):
        seen["get"] = pages._entity_code_for_validation_type(validation_type, year)
        return dict(detail)

    monkeypatch.setattr(pages, "get_validation_record_from_feishu", _fake_get)

    await pages.create_validation_record_in_feishu(
        SimpleNamespace(), {"title": "方案A", "validation_type": ""}, 2026
    )
    assert seen["create"] == "validation_master_plan_2026"

    await pages.update_validation_record_in_feishu(
        SimpleNamespace(), "rec-1", {"title": "方案A2"}, year=2025
    )
    assert seen["update"] == "validation_master_plan_2025"
    assert seen["get"] == "validation_master_plan_2025"

    await pages.delete_validation_record_in_feishu(
        SimpleNamespace(), "rec-1", None, year=2024
    )
    assert seen["delete"] == "validation_master_plan_2024"


# ─── 通用 CRUD 白名单与人员字段写入 ───────────────────────────────


def test_bitable_crud_entity_whitelist_includes_validation_qc() -> None:
    crud_service.validate_bitable_crud_entity("validation_qc_2026")
    crud_service.validate_bitable_crud_entity("qc_items_inventory")
    crud_service.validate_inspection_entity("qc_finished_fcc14")
    with pytest.raises(AppException):
        crud_service.validate_bitable_crud_entity("capa_ledger")
    with pytest.raises(AppException):
        crud_service.validate_bitable_crud_entity("validation_master_plan")


def test_coerce_write_value_supports_user_id_list() -> None:
    field_meta = {"ui_type": "User"}
    assert crud_service._coerce_write_value(
        field_meta, [{"id": "ou_1"}, {"id": " ou_2 "}]
    ) == [{"id": "ou_1"}, {"id": "ou_2"}]
    # 无有效 id 的人员值跳过写入
    assert (
        crud_service._coerce_write_value(field_meta, [{"name": "张三"}])
        is crud_service.feishu_sync_service.SKIP_REMOTE_FIELD
    )
    assert (
        crud_service._coerce_write_value(field_meta, "张三")
        is crud_service.feishu_sync_service.SKIP_REMOTE_FIELD
    )


class _FakeRuntime:
    app_id = "cli_1"
    app_secret = "secret_1"


class _FakeEntity:
    app_token = "app_token_qc"
    table_id = "tbl_qc"
    enable_push_to_feishu = True
    enable_pull_from_feishu = True
    field_mappings = {}


class _FakeBitable:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def list_fields(self, table_id: str) -> list[dict]:
        return [
            {"field_name": "方案名称", "ui_type": "Text"},
            {"field_name": "人员", "ui_type": "User"},
        ]


@pytest.mark.asyncio
async def test_list_bitable_feishu_records_maps_and_paginates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        {
            "record_id": f"rec-{i}",
            "created_time": "2026-08-01T00:00:00+00:00",
            "fields": {"方案名称": f"方案{i}"},
        }
        for i in range(3)
    ]
    monkeypatch.setattr(
        crud_service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(_FakeRuntime(), _FakeEntity())),
    )
    monkeypatch.setattr(crud_service, "BitableClient", _FakeBitable)
    monkeypatch.setattr(
        crud_service, "_search_entity_records", AsyncMock(return_value=records)
    )
    result = await crud_service.list_bitable_feishu_records(
        SimpleNamespace(), "validation_qc_2026", page=2, page_size=2
    )
    assert result["table_configured"] is True
    assert result["total"] == 3
    assert [item["record_id"] for item in result["items"]] == ["rec-2"]
    assert result["items"][0]["方案名称"] == "方案2"


@pytest.mark.asyncio
async def test_list_bitable_feishu_records_unconfigured_returns_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        crud_service,
        "_resolve_runtime_entity",
        AsyncMock(side_effect=AppException(message="disabled")),
    )
    result = await crud_service.list_bitable_feishu_records(
        SimpleNamespace(), "validation_qc_2027"
    )
    assert result["table_configured"] is False
    assert result["items"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_list_and_configured_degrade_on_credential_decrypt_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """应用凭证解密失败（密钥轮换）时按"表不可用"降级而非 500。"""
    from app.core.llm.exceptions import LLMConfigError

    monkeypatch.setattr(
        crud_service,
        "_resolve_runtime_entity",
        AsyncMock(side_effect=LLMConfigError("Failed to decrypt API key")),
    )
    result = await crud_service.list_bitable_feishu_records(
        SimpleNamespace(), "validation_qc_2026"
    )
    assert result["table_configured"] is False
    assert result["items"] == []
    assert (
        await crud_service.get_bitable_entity_configured(
            SimpleNamespace(), "validation_qc_2026"
        )
        is False
    )


@pytest.mark.asyncio
async def test_get_bitable_entity_configured_reflects_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        crud_service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(_FakeRuntime(), _FakeEntity())),
    )
    assert (
        await crud_service.get_bitable_entity_configured(
            SimpleNamespace(), "validation_qc_2026"
        )
        is True
    )
    monkeypatch.setattr(
        crud_service,
        "_resolve_runtime_entity",
        AsyncMock(side_effect=AppException(message="disabled")),
    )
    assert (
        await crud_service.get_bitable_entity_configured(
            SimpleNamespace(), "validation_qc_2027"
        )
        is False
    )


# ─── 真实年度台账字段适配 ─────────────────────────────────────────


def test_validation_mapping_supports_real_year_ledger_shape() -> None:
    """真实年度台账：无"验证类别"列、报告日期列名为 起草时间1/批准时间1。"""
    record = {
        "record_id": "rec-y1",
        "created_time": "2026-08-01T00:00:00+00:00",
        "fields": {
            "确认名称": "生化培养箱再确认",
            "任务状态": "已完成",
            "部门名称": "QC",
            "设备编码": "QC-2-2-066",
            "产品代码": ["公用"],
            "方案名称": "再确认方案",
            "方案编码": "VP-QC-2601-01",
            "起草时间": "2026-01-30T00:00:00+00:00",
            "批准时间": "2026-02-05T00:00:00+00:00",
            "起草时间1": "2026-03-01T00:00:00+00:00",
            "批准时间1": "2026-03-26T00:00:00+00:00",
            "再验证周期（几年）": "3",
        },
    }
    item = pages._map_validation_base_item(record)
    # 无"验证类别"列 → 标记为待 AI 分类（默认归入其他验证）
    assert item["validation_type"] == "other_validation"
    assert item["validation_type_source"] == "inferred"
    assert item["drafted_at"] == date(2026, 1, 30)
    assert item["approved_at"] == date(2026, 2, 5)
    assert item["drafted_at_1"] == date(2026, 3, 1)
    assert item["approved_at_1"] == date(2026, 3, 26)
    assert item["revalidation_cycle_years"] == 3


@pytest.mark.asyncio
async def test_adapt_validation_fields_for_real_year_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写入适配：别名改名、丢弃远端不存在字段、单选取首值。"""

    class _FakeRuntime:
        app_id = "cli_1"
        app_secret = "s"

    class _FakeEntity:
        app_token = "t"
        table_id = "tbl"

    class _FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def list_fields(self, table_id: str) -> list[dict]:
            return [
                {"field_name": "确认名称", "type": 1, "ui_type": "Text"},
                {"field_name": "起草时间1", "type": 5, "ui_type": "DateTime"},
                {"field_name": "批准时间1", "type": 5, "ui_type": "DateTime"},
                {"field_name": "产品代码", "type": 3, "ui_type": "SingleSelect"},
                {"field_name": "人员", "type": 11, "ui_type": "User"},
            ]

    async def _resolve_entity(db, code, *, direction):
        return _FakeRuntime(), _FakeEntity()

    async def _resolve_runtime(db):
        return _FakeRuntime()

    monkeypatch.setattr(pages, "_resolve_runtime_entity", _resolve_entity)
    monkeypatch.setattr(
        pages.feishu_sync_service.feishu_sync, "_resolve_runtime", _resolve_runtime
    )
    import app.platform.integrations.feishu.bitable as bitable_mod

    monkeypatch.setattr(bitable_mod, "BitableClient", _FakeClient)

    fields = {
        "确认名称": "方案A",
        "验证类别": "工艺验证",  # 真实台账无此列 → 丢弃
        "报告起草时间": 1700000000000,  # → 改名 起草时间1
        "报告批准时间": 1700000001000,  # → 改名 批准时间1
        "产品代码": ["MV", "LV"],  # 单选 → 取首值
        "人员": [{"id": "ou_1"}],
    }
    adapted = await pages._adapt_validation_fields_to_remote(
        SimpleNamespace(), "validation_master_plan_2026", fields
    )
    assert adapted == {
        "确认名称": "方案A",
        "起草时间1": 1700000000000,
        "批准时间1": 1700000001000,
        "产品代码": "MV",
        "人员": [{"id": "ou_1"}],
    }

    # 远端含标准列（验证总表）时保持原名、多选不取首值
    class _MultiClient(_FakeClient):
        async def list_fields(self, table_id: str) -> list[dict]:
            return [
                {"field_name": "确认名称", "type": 1, "ui_type": "Text"},
                {"field_name": "报告起草时间", "type": 5, "ui_type": "DateTime"},
                {"field_name": "报告批准时间", "type": 5, "ui_type": "DateTime"},
                {"field_name": "产品代码", "type": 4, "ui_type": "MultiSelect"},
                {"field_name": "验证类别", "type": 3, "ui_type": "SingleSelect"},
                {"field_name": "人员", "type": 11, "ui_type": "User"},
            ]

    monkeypatch.setattr(bitable_mod, "BitableClient", _MultiClient)
    fields2 = {
        "确认名称": "方案A",
        "验证类别": "工艺验证",
        "报告起草时间": 1700000000000,
        "产品代码": ["MV", "LV"],
    }
    adapted2 = await pages._adapt_validation_fields_to_remote(
        SimpleNamespace(), "validation_master_plan", fields2
    )
    assert adapted2["报告起草时间"] == 1700000000000
    assert adapted2["验证类别"] == "工艺验证"
    assert adapted2["产品代码"] == ["MV", "LV"]


@pytest.mark.asyncio
async def test_search_safe_retries_without_restricted_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全字段搜索被受限字段拒绝时，排除后重试成功。"""
    calls: list = []

    async def _fake_search(db, entity_code, *, field_names=None):
        calls.append(field_names)
        if field_names is None:
            raise RuntimeError("Feishu API error: code=1254302 RolePermNotAllow")
        return [{"record_id": "rec-ok", "fields": {"确认名称": "X"}}]

    class _FakeRuntime:
        app_id = "cli"
        app_secret = "s"

    class _FakeEntity:
        app_token = "t"
        table_id = "tbl"

    class _FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def list_fields(self, table_id: str) -> list[dict]:
            return [
                {"field_name": "确认名称", "type": 1},
                {"field_name": "无权限访问字段", "type": 99},
            ]

    async def _resolve_entity(db, code, *, direction):
        return _FakeRuntime(), _FakeEntity()

    async def _resolve_runtime(db):
        return _FakeRuntime()

    monkeypatch.setattr(pages, "_search_entity_records", _fake_search)
    monkeypatch.setattr(pages, "_resolve_runtime_entity", _resolve_entity)
    monkeypatch.setattr(
        pages.feishu_sync_service.feishu_sync, "_resolve_runtime", _resolve_runtime
    )
    import app.platform.integrations.feishu.bitable as bitable_mod

    monkeypatch.setattr(bitable_mod, "BitableClient", _FakeClient)

    records = await pages._search_validation_records_safe(
        SimpleNamespace(), "validation_master_plan_2026"
    )
    assert [r["record_id"] for r in records] == ["rec-ok"]
    assert calls[0] is None
    assert calls[1] == ["确认名称"]


@pytest.mark.asyncio
async def test_list_applies_ai_categories_for_real_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实台账记录（无验证类别列）由 AI 分类服务回填验证类别。"""
    records = [
        {
            "record_id": "rec-a",
            "created_time": "2026-08-01T00:00:00+00:00",
            "fields": {"确认名称": "303冷库温度分布确认", "任务状态": "已完成"},
        },
        {
            "record_id": "rec-b",
            "created_time": "2026-08-01T00:00:00+00:00",
            "fields": {
                "确认名称": "灭菌柜确认",
                "验证类别": "设备确认",
                "任务状态": "已完成",
            },
        },
    ]
    monkeypatch.setattr(
        pages, "_resolve_runtime_entity", AsyncMock(return_value=(object(), object()))
    )

    async def _fake_search(db, entity_code, **kwargs):
        return records

    monkeypatch.setattr(pages, "_search_validation_records_safe", _fake_search)

    async def _fake_resolve(db, titles):
        return {t: "other_validation" for t in titles}

    monkeypatch.setattr(
        pages.validation_classification_service,
        "resolve_validation_categories",
        _fake_resolve,
    )
    result = await pages.list_validation_records_from_feishu(
        SimpleNamespace(), page=1, page_size=10
    )
    by_id = {item["record_id"]: item for item in result["items"]}
    # AI 分类：温湿度分布确认 → 其他验证（而非设备确认）
    assert by_id["rec-a"]["validation_type"] == "other_validation"
    # 飞书自带验证类别的记录不受 AI 影响
    assert by_id["rec-b"]["validation_type"] == "equipment_qualification"
    assert "validation_type_source" not in by_id["rec-a"]


def test_button_field_is_read_only_and_stripped_from_writes() -> None:
    """QC 表"同步"按钮列会触发飞书工作流：元数据只读、写请求一律剥除。"""
    meta = {"field_name": "同步", "ui_type": "Button"}
    fields_result = {
        "field_name": meta["field_name"],
        "ui_type": meta["ui_type"],
        "editable": meta["ui_type"] not in crud_service._READ_ONLY_UI_TYPES,
        "options": None,
    }
    assert fields_result["editable"] is False
    assert (
        crud_service._coerce_write_value(meta, "点击")
        is crud_service.feishu_sync_service.SKIP_REMOTE_FIELD
    )

    # 写请求里混入按钮字段时被整体剥除
    remote_field_map = {
        "方案名称": {"ui_type": "Text"},
        "同步": {"ui_type": "Button"},
    }
    coerced = crud_service._coerce_write_fields(
        remote_field_map, {"方案名称": "新方案", "同步": "点击"}
    )
    assert coerced == {"方案名称": "新方案"}


def test_validation_mapping_group_chat_and_empty_row() -> None:
    """群组保留 {id,name,avatar_url} 结构；仅部门/无业务的占位行标记 is_empty_row。"""
    record = {
        "record_id": "rec-g",
        "created_time": "2026-08-01T00:00:00+00:00",
        "fields": {
            "确认名称": "生化培养箱再确认",
            "部门名称": "QC",
            "群组": [
                {"id": "oc_abc", "name": "验证群", "avatar_url": "https://x/a.png"}
            ],
            "人员": [{"name": "赵双"}],
        },
    }
    item = pages._map_validation_base_item(record)
    assert item["group_chat"] == [
        {"id": "oc_abc", "name": "验证群", "avatar_url": "https://x/a.png"}
    ]
    assert item["is_empty_row"] is False

    # 仅部门（无其他业务信息）的占位行
    empty_record = {
        "record_id": "rec-empty",
        "created_time": "2026-08-01T00:00:00+00:00",
        "fields": {
            "部门名称": "动力部",
            "父记录": {},
            "文本 9": {},
        },
    }
    empty_item = pages._map_validation_base_item(empty_record)
    assert empty_item["is_empty_row"] is True
