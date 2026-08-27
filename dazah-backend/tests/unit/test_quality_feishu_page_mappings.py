from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.quality.service import quality_feishu_pages as pages
from app.modules.quality.service import quality_feishu_sync

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


def test_deviation_ledger_mapping_and_field_building() -> None:
    now = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    record = {
        "record_id": "rec_dev_001",
        "created_time": int(now.timestamp() * 1000),
        "last_modified_time": int(now.timestamp() * 1000),
        "fields": {
            "偏差编号": "DEV-001",
            "偏差简要描述": "洁净区压差异常",
            "偏差是否曾发生": "是",
            "调查完成时间": int(now.timestamp() * 1000),
            "关闭时间": int(now.timestamp() * 1000),
            "关联capa": "CAPA-1，CAPA-2/CAPA-3",
            "是否关闭": "是",
            "偏差等级": "major",
            "产品名称/批号": "产品A/B001",
            "产品/物料处理结果": "放行",
            "纠正预防措施": "更换过滤器",
            "根本原因": "过滤器破损",
        },
    }
    item = pages._map_deviation_ledger_base_item(record, _entity())
    assert item["deviation_code"] == "DEV-001"
    assert item["status"] == "closed"
    assert item["has_occurred_before"] is True
    assert item["related_capa_codes"] == ["CAPA-1", "CAPA-2", "CAPA-3"]
    assert item["feishu_base_table_id"] == "tbl_quality"

    detail = pages._map_deviation_ledger_detail_item(record, _entity())
    assert detail["updated_at"] == item["feishu_source_updated_at"]
    assert detail["attachments"] is None

    fields = pages._build_deviation_ledger_fields(
        {
            "affected_items": "产品A",
            "batch_number": "B001",
            "description": "偏差描述",
            "has_occurred_before": False,
            "root_cause_analysis": "根因",
            "level": "minor",
            "investigation_completed_at": now.isoformat(),
            "corrective_actions": "纠正措施",
            "material_disposition": "隔离",
            "status": "closed",
            "close_time": now.isoformat(),
        },
        deviation_code="DEV-002",
    )
    assert fields["产品名称/批号"] == "产品A/B001"
    assert fields["偏差是否曾发生"] == "否"
    assert fields["是否关闭"] == "是"
    assert fields["关闭时间"] == int(now.timestamp() * 1000)


def test_page_helpers_cover_text_dates_aliases_and_validation_mapping() -> None:
    assert pages._build_page_result([{"id": 1}], 1, 2, 20)["page"] == 2
    assert pages._contains_text("CAPA Record", "record")
    assert pages._contains_text(None, None)
    assert not pages._contains_text(None, "record")
    assert pages._normalize_yes_no(True) == "是"
    assert pages._normalize_yes_no(False) == "否"
    assert pages._normalize_yes_no(None) == ""
    assert pages._split_related_capa_codes(" A, B，C/D ") == [
        "A",
        "B",
        "C",
        "D",
    ]
    assert pages._split_related_capa_codes("") is None
    assert pages._normalize_closed_status("否") == "draft"
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
    assert mapped["participants"] == "张三、李四、王五"
    assert mapped["owner_name"] == "赵六"
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


def test_resolve_bitable_users_prefers_bitable_id_then_open_id() -> None:
    contacts = [
        {
            "name": "张三",
            "bitable_user_id": "ou_bitable_1",
            "open_id": "ou_open_1",
        },
        {
            "name": "李四",
            "bitable_user_id": "",
            "open_id": "ou_open_2",
        },
    ]
    assert pages._resolve_bitable_user_ids_from_names(
        contacts,
        "张三、李四、未知",
    ) == ["ou_bitable_1", "ou_open_2"]
    assert pages._resolve_bitable_user_ids_from_names(contacts, None) is None
    assert pages._resolve_bitable_user_ids_from_names([], "张三") is None


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
