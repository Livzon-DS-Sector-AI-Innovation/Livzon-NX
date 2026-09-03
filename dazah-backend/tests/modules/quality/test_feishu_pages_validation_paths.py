from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.quality.service import quality_feishu_pages as pages


class _FeishuSync:
    @staticmethod
    def _to_ms_timestamp(value: datetime | None) -> int | None:
        return int(value.timestamp() * 1000) if value else None

    @staticmethod
    def _parse_feishu_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time(), tzinfo=UTC)
        if isinstance(value, str) and value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return None

    @staticmethod
    def _get_record_modified_at(record: dict[str, object]) -> datetime | None:
        return record.get("last_modified_at")  # type: ignore[return-value]

    @staticmethod
    def _normalize_text(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            return "、".join(str(item) for item in value)
        return str(value).strip() or None


@pytest.mark.asyncio
async def test_build_validation_fields_covers_people_dates_and_optional_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pages,
        "_get_department_contacts_cache",
        AsyncMock(
            return_value=[
                {"name": "张三", "bitable_user_id": "ou_1"},
                {"name": "李四", "open_id": "ou_2"},
            ]
        ),
    )
    monkeypatch.setattr(pages, "feishu_sync_service", _FeishuSync)
    payload = {
        "validation_type": "process_validation",
        "title": "  工艺验证  ",
        "status": "进行中",
        "department": " 质量部 ",
        "equipment_code": " EQ-01 ",
        "product_codes": ["P-1", "P-2"],
        "participants": ["张三", "李四"],
        "owner_name": ["张三", "未知"],
        "plan_name": "方案 A",
        "plan_code": "PLAN-1",
        "report_no": "REPORT-1",
        "planned_end_date": "2026.08",
        "drafted_at": "2026-08-01T08:00:00+00:00",
        "approved_at": date(2026, 8, 2),
        "drafted_at_1": datetime(2026, 8, 3, tzinfo=UTC),
        "approved_at_1": None,
        "revalidation_cycle_years": "3",
    }
    fields = await pages._build_validation_feishu_fields(SimpleNamespace(), payload)
    assert fields["验证类别"] == "工艺验证"
    assert fields["确认名称"] == "工艺验证"
    assert fields["人员"] == [{"id": "ou_1"}, {"id": "ou_2"}]
    assert fields["负责人"] == [{"id": "ou_1"}]
    assert fields["验证到期时间"] == "2026.08"
    assert fields["再验证周期（几年）"] == "3年"
    assert "群组" not in fields

    monkeypatch.setattr(
        pages, "_get_department_contacts_cache", AsyncMock(return_value=[])
    )
    fields = await pages._build_validation_feishu_fields(
        SimpleNamespace(),
        {
            "product_codes": "P-3",
            "participants": "",
            "owner_name": "unknown",
            "revalidation_cycle_years": "x",
        },
    )
    assert fields["产品代码"] == ["P-3"]
    assert "人员" not in fields and "负责人" not in fields
    assert "再验证周期（几年）" not in fields


def test_validation_mapping_and_parsing_supports_feishu_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pages, "feishu_sync_service", _FeishuSync)
    assert pages._entity_code_for_validation_type("equipment_qualification")
    assert pages._translate_validation_type_c2f("unknown") == "unknown"
    assert pages._translate_validation_type_f2c("未知类别") == "other_validation"
    assert pages._resolve_bitable_user_ids_from_names(
        [{"name": "张三", "open_id": "open-1"}], "张三"
    ) == ["open-1"]
    assert pages._resolve_bitable_user_ids_from_names([], "") is None
    assert pages._parse_feishu_text_field([{"text": " A "}, "B"]) == "A / B"
    assert pages._parse_feishu_text_field({"text": "名称"}) == "名称"
    assert pages._parse_feishu_text_field(12) == "12"
    assert pages._parse_validation_month_or_date("2026.08") == date(2026, 8, 1)
    assert pages._parse_validation_month_or_date("2026-08-11") == date(2026, 8, 11)
    assert pages._parse_validation_month_or_date("2026.99") is None

    record = {
        "record_id": "rec-1",
        "created_time": "2026-08-01T08:00:00+00:00",
        "last_modified_at": datetime(2026, 8, 4, tzinfo=UTC),
        "fields": {
            "验证类别": [{"text": "工艺验证"}],
            "确认名称": [{"text": "方案确认"}],
            "任务状态": "进行中",
            "部门名称": "质量部",
            "设备编码": [{"text": "EQ-1"}],
            "产品代码": ["P-1", " P-2 "],
            "验证到期时间": "2026.08",
            "人员": [{"name": "张三"}, {"text": "李四"}, "王五"],
            "负责人": [{"text": "张三"}],
            "方案名称": "方案 A",
            "方案编码": "PLAN-1",
            "起草时间": "2026-08-02T00:00:00+00:00",
            "批准时间": date(2026, 8, 3),
            "再验证周期（几年）": "3年",
        },
    }
    item = pages._map_validation_base_item(record)
    assert item["validation_type"] == "process_validation"
    assert item["product_codes"] == ["P-1", "P-2"]
    # 人员/负责人保留结构化信息（name/avatar_url/id），供前端渲染头像
    assert item["participants"] == [
        {"name": "张三", "avatar_url": "", "id": ""},
        {"name": "李四", "avatar_url": "", "id": ""},
        {"name": "王五", "avatar_url": "", "id": ""},
    ]
    assert item["owner_name"] == [{"name": "张三", "avatar_url": "", "id": ""}]
    assert item["revalidation_cycle_years"] == 3
    assert item["drafted_at"] == date(2026, 8, 2)


@pytest.mark.asyncio
async def test_list_validation_records_filters_and_paginates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pages,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(object(), object())),
    )
    records = [
        {
            "record_id": "r1",
            "created_time": "2026-08-01T00:00:00+00:00",
            "fields": {
                "验证类别": "工艺验证",
                "确认名称": "方案A",
                "任务状态": "进行中",
                "部门名称": "质量部",
                "验证到期时间": "2026.08",
                "起草时间": "2026-08-01T00:00:00+00:00",
            },
        },
        {
            "record_id": "r2",
            "created_time": "2026-07-01T00:00:00+00:00",
            "fields": {
                "验证类别": "设备确认",
                "确认名称": "设备B",
                "任务状态": "已完成",
                "部门名称": "工程部",
                "验证到期时间": "2027.01",
            },
        },
    ]
    monkeypatch.setattr(
        pages, "_search_entity_records", AsyncMock(return_value=records)
    )
    result = await pages.list_validation_records_from_feishu(
        SimpleNamespace(),
        validation_type="process_validation",
        status="进行中",
        keyword="方案",
        department="质量部",
        planned_end_date_from="2026-01-01",
        planned_end_date_to="2026-12-31",
        drafted_at_from="2026-01-01",
        drafted_at_to="2026-12-31",
        page=1,
        page_size=1,
    )
    assert result["total"] == 1
    assert result["items"][0]["record_id"] == "r1"

    monkeypatch.setattr(
        pages,
        "_resolve_runtime_entity",
        AsyncMock(side_effect=pages.AppException(message="disabled")),
    )
    result = await pages.list_validation_records_from_feishu(SimpleNamespace())
    assert result["total"] == 0
