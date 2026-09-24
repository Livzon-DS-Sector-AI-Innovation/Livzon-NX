from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.quality.service import (
    change_action_plan,
    quality_feishu_sync,
)
from app.modules.quality.service import (
    quality_feishu_pages as pages,
)

SimpleNamespace: Any = _SimpleNamespace


def _entity() -> quality_feishu_sync.QualityFeishuEntityRuntimeConfig:
    return quality_feishu_sync.QualityFeishuEntityRuntimeConfig(
        app_token="bascn_quality",
        table_id="tbl_quality",
        is_enabled=True,
        enable_push_to_feishu=True,
        enable_pull_from_feishu=True,
        field_mappings={},
    )


def test_page_helpers_cover_text_dates_aliases_and_validation_mapping() -> None:
    assert pages._build_page_result([{"id": 1}], 1, 2, 20)["page"] == 2
    assert pages._contains_text("CAPA Record", "record")
    assert pages._contains_text(None, None)
    assert not pages._contains_text(None, "record")
    assert (
        pages._serialize_report_record_alias({"feishu_base_record_id": "rec-1"})[
            "record_id"
        ]
        == "rec-1"
    )
    assert (
        pages._serialize_investigation_record_alias({"id": "local-1"})["record_id"]
        == "local-1"
    )

    assert (
        pages._entity_code_for_validation_type("process_validation")
        == "validation_process"
    )
    assert pages._entity_code_for_validation_type("unknown") == "validation_master_plan"
    assert pages._translate_validation_type_f2c("工艺验证") == ("process_validation")
    assert pages._translate_validation_type_f2c("未知") == "other_validation"
    assert pages._translate_validation_type_c2f("cleaning_validation") == ("清洁验证")
    assert pages._translate_validation_type_c2f("custom") == "custom"

    assert pages._parse_feishu_text_field(" text ") == "text"
    assert (
        pages._parse_feishu_text_field([{"text": "A"}, " B ", {"text": ""}]) == "A / B"
    )
    assert pages._parse_feishu_text_field({"text": " C "}) == "C"
    assert pages._parse_feishu_text_field(None) is None
    assert pages._parse_validation_month_or_date("2026.07") == date(
        2026,
        7,
        1,
    )
    assert pages._parse_validation_month_or_date("2026年08月") == date(
        2026,
        8,
        1,
    )
    assert pages._parse_validation_month_or_date("202609") == date(
        2026,
        9,
        1,
    )
    assert pages._parse_validation_month_or_date("invalid") is None


def test_validation_record_mapping_handles_people_products_and_dates() -> None:
    now = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    mapped = pages._map_validation_base_item(
        {
            "record_id": "rec_validation_001",
            "created_time": int(now.timestamp() * 1000),
            "last_modified_time": int(now.timestamp() * 1000),
            "fields": {
                "验证类别": [{"text": "设备确认"}],
                "确认名称": "反应釜 IQ/OQ",
                "任务状态": "完成",
                "部门名称": "工程部",
                "设备编码": [{"text": "EQ-001"}],
                "产品代码": ["P001", "P002"],
                "验证到期时间": "2027.07",
                "群组": "验证组",
                "人员": [
                    {"name": "张三"},
                    {"text": "李四"},
                    "王五",
                ],
                "负责人": [{"name": "赵六"}],
                "方案名称": "确认方案",
                "方案编码": "VP-001",
                "起草时间": int(now.timestamp() * 1000),
                "批准时间": int(now.timestamp() * 1000),
                "报告编号": "VR-001",
                "报告起草时间": int(now.timestamp() * 1000),
                "报告批准时间": int(now.timestamp() * 1000),
                "再验证周期（几年）": "每 3 年",
            },
        }
    )
    assert mapped["validation_type"] == "equipment_qualification"
    assert mapped["product_codes"] == ["P001", "P002"]
    # 人员/负责人保留结构化信息（name/avatar_url/id），供前端渲染头像
    assert mapped["participants"] == [
        {"name": "张三", "avatar_url": "", "id": ""},
        {"name": "李四", "avatar_url": "", "id": ""},
        {"name": "王五", "avatar_url": "", "id": ""},
    ]
    assert mapped["owner_name"] == [{"name": "赵六", "avatar_url": "", "id": ""}]
    assert mapped["revalidation_cycle_years"] == 3
    assert mapped["drafted_at"] == date(2026, 7, 1)

    fallback = pages._map_validation_base_item(
        {
            "record_id": "rec_validation_002",
            "fields": {
                "验证类别": "其他",
                "确认名称": "其他验证",
                "产品代码": "P003",
                "人员": "单人",
                "负责人": "负责人",
            },
        }
    )
    assert fallback["validation_type"] == "other_validation"
    assert fallback["product_codes"] == ["P003"]
    assert fallback["participants"] == "单人"
    assert fallback["owner_name"] == "负责人"


@pytest.mark.anyio
async def test_resolve_bitable_users_resolves_names_via_person_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """姓名串 → 人员目录解析可写成员 id；未知姓名跳过，全空返回 None。"""
    import app.modules.quality.service.person_directory as pd

    people = {"张三": {"open_id": "ou_name_1"}, "李四": {"open_id": "ou_name_2"}}
    write_ids = {"ou_name_1": "on_union_1", "ou_name_2": "on_union_2"}

    async def fake_resolve_by_name(db: Any, name: str) -> Any:
        return people.get(name)

    async def fake_resolve_write_id(db: Any, open_id: str) -> Any:
        return write_ids.get(open_id)

    monkeypatch.setattr(pd, "resolve_person_by_name", fake_resolve_by_name)
    monkeypatch.setattr(pd, "resolve_person_write_id", fake_resolve_write_id)

    db = SimpleNamespace()
    assert await pages._resolve_bitable_user_ids_from_names(
        db,
        "张三、李四、未知",
    ) == ["on_union_1", "on_union_2"]
    assert await pages._resolve_bitable_user_ids_from_names(db, None) is None
    assert await pages._resolve_bitable_user_ids_from_names(db, "、未知、") is None


@pytest.mark.anyio
async def test_entity_record_helpers_and_change_sync_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db: Any = object()
    upsert: Any = AsyncMock(
        side_effect=[
            ("rec-created", "tbl-quality"),
            ("rec-updated", "tbl-quality"),
        ]
    )
    monkeypatch.setattr(
        quality_feishu_sync.feishu_sync,
        "_upsert_record",
        upsert,
    )
    created = await pages._create_entity_record(
        db,
        "change_ledger",
        {"变更控制号": "BG-001"},
        search_conditions=[("变更控制号", "BG-001")],
    )
    updated = await pages._update_entity_record(
        db,
        "change_ledger",
        "rec-origin",
        {"变更控制号": "BG-001"},
    )
    assert created == {
        "record_id": "rec-created",
        "table_id": "tbl-quality",
    }
    assert updated["record_id"] == "rec-updated"

    change: Any = SimpleNamespace(
        serial_number="1",
        change_code="BG-001",
        applicant_department="质量部",
        change_object="反应釜",
        change_content="密封件变更",
        change_level="一级",
        application_date=date(2026, 7, 1),
        planned_approval_date=date(2026, 7, 2),
        execution_date=date(2026, 7, 3),
        closure_date=date(2026, 7, 4),
    )
    fields = pages._build_change_feishu_fields(change)
    assert fields["变更控制号"] == "BG-001"
    assert fields["变更关闭日期"] is not None

    find: Any = AsyncMock(return_value=None)
    create_record: Any = AsyncMock(return_value={"record_id": "rec-new"})
    update_record: Any = AsyncMock(return_value={"record_id": "rec-existing"})
    delete_record: Any = AsyncMock()
    monkeypatch.setattr(pages, "_find_change_feishu_record_id", find)
    monkeypatch.setattr(pages, "_create_entity_record", create_record)
    monkeypatch.setattr(pages, "_update_entity_record", update_record)
    monkeypatch.setattr(pages, "_delete_entity_record", delete_record)

    assert await pages.sync_change_to_feishu(db, change) == {"record_id": "rec-new"}
    find.return_value = "rec-existing"
    assert await pages.sync_change_to_feishu(db, change) == {
        "record_id": "rec-existing"
    }
    assert await pages.delete_change_from_feishu(db, "BG-001") is True
    delete_record.assert_awaited_once_with(
        db,
        "change_ledger",
        "rec-existing",
    )

    find.return_value = None
    assert await pages.delete_change_from_feishu(db, "BG-404") is False


@pytest.mark.anyio
async def test_change_action_plan_upsert_uses_open_id_without_union_fields() -> None:
    client = SimpleNamespace(
        create_record=AsyncMock(return_value={"record_id": "rec-open"}),
        update_record=AsyncMock(),
    )
    sync = change_action_plan.ChangeActionPlanFeishuSync()
    sync._resolve_runtime = AsyncMock(return_value=(client, "tbl-change"))
    sync.build_fields = AsyncMock(return_value={"项目名称": "普通字段"})
    plan = SimpleNamespace(feishu_record_id=None)

    result = await sync.upsert_record(object(), plan)

    assert result == "rec-open"
    client.create_record.assert_awaited_once_with(
        "tbl-change", {"项目名称": "普通字段"}, user_id_type="open_id"
    )


@pytest.mark.anyio
async def test_pull_changes_handles_updates_creates_invalid_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing: Any = SimpleNamespace(change_code="BG-001")
    results = [
        SimpleNamespace(scalar_one_or_none=lambda: existing),
        SimpleNamespace(scalar_one_or_none=lambda: None),
    ]
    db: Any = SimpleNamespace(
        execute=AsyncMock(side_effect=results),
        add=Mock(),
        commit=AsyncMock(side_effect=[None, RuntimeError("commit failed")]),
        rollback=AsyncMock(),
    )
    monkeypatch.setattr(
        pages,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(object(), _entity())),
    )
    monkeypatch.setattr(
        pages,
        "_search_entity_records",
        AsyncMock(
            return_value=[
                {
                    "fields": {
                        "变更控制号": "BG-001",
                        "序号": "1",
                        "变更申请部门": "质量部",
                        "变更对象": "设备",
                        "变更内容": "更新",
                        "变更等级": "一级",
                    }
                },
                {"fields": {"变更控制号": ""}},
                {
                    "fields": {
                        "变更控制号": "BG-002",
                        "序号": "2",
                        "变更申请部门": "生产部",
                        "变更对象": "工艺",
                        "变更内容": "新增",
                        "变更等级": "二级",
                    }
                },
            ]
        ),
    )

    result = await pages.sync_changes_from_feishu(db)
    assert result == {"synced": 1, "failed": 2}
    assert existing.change_content == "更新"
    db.add.assert_called_once()
    db.rollback.assert_awaited_once()


@pytest.mark.anyio
async def test_pull_changes_marks_created_rows_with_requested_ledger_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db: Any = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[SimpleNamespace(scalar_one_or_none=lambda: None)]
        ),
        add=Mock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    monkeypatch.setattr(
        pages,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(object(), _entity())),
    )
    monkeypatch.setattr(
        pages,
        "_search_entity_records",
        AsyncMock(return_value=[{"fields": {"变更控制号": "BG-FILE-001"}}]),
    )

    result = await pages.sync_changes_from_feishu(db, change_type="file")
    assert result == {"synced": 1, "failed": 0}
    created = db.add.call_args.args[0]
    assert created.change_type == "file"


@pytest.mark.anyio
async def test_change_action_plan_search_records_follows_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages_seq: list[dict[str, Any]] = [
        {
            "items": [{"record_id": "r1"}, {"record_id": "r2"}],
            "has_more": True,
            "page_token": "tok2",
            "total": None,
        },
        {
            "items": [{"record_id": "r3"}],
            "has_more": False,
            "page_token": None,
            "total": None,
        },
    ]
    client = SimpleNamespace(search_records_page=AsyncMock(side_effect=pages_seq))

    async def fake_resolve(_db: Any) -> tuple[Any, str]:
        return client, "tbl_quality"

    monkeypatch.setattr(
        change_action_plan.feishu_sync, "_resolve_runtime", fake_resolve
    )
    items = await change_action_plan.feishu_sync.search_records(object())
    assert [item["record_id"] for item in items] == ["r1", "r2", "r3"]
    first_call, second_call = client.search_records_page.await_args_list
    assert first_call.kwargs["page_token"] is None
    assert second_call.kwargs["page_token"] == "tok2"
