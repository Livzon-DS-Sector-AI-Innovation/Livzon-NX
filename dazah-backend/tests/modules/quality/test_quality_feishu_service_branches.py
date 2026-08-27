from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality.service import quality_feishu_pages as pages


@pytest.mark.asyncio
async def test_validation_statistics_groups_types_statuses_and_deadlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = date.today()
    monkeypatch.setattr(
        pages,
        "list_validation_records_from_feishu",
        AsyncMock(
            return_value={
                "items": [
                    {
                        "validation_type": "process_validation",
                        "status": "进行中",
                        "planned_end_date": today.isoformat(),
                    },
                    {
                        "validation_type": "process_validation",
                        "status": None,
                        "planned_end_date": (today + timedelta(days=31)).isoformat(),
                    },
                    {
                        "validation_type": None,
                        "status": "已完成",
                        "planned_end_date": "not-a-date",
                    },
                ]
            }
        ),
    )
    result = await pages.get_validation_statistics_from_feishu(SimpleNamespace())
    assert result["total"] == 3
    assert {
        item["validation_type"]: item["count"] for item in result["typeDistribution"]
    } == {
        "process_validation": 2,
        "unknown": 1,
    }
    assert {item["status"]: item["count"] for item in result["statusDistribution"]} == {
        "进行中": 1,
        "unknown": 1,
        "已完成": 1,
    }
    assert result["executionDistribution"] == result["typeDistribution"]
    assert result["revalidationUpcoming"] == 1

    monkeypatch.setattr(
        pages,
        "list_validation_records_from_feishu",
        AsyncMock(side_effect=RuntimeError("down")),
    )
    failed = await pages.get_validation_statistics_from_feishu(SimpleNamespace())
    assert failed["total"] == 0
    assert failed["revalidationUpcoming"] == 0


@pytest.mark.asyncio
async def test_deviation_report_create_update_delete_uses_shared_entity_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contact = SimpleNamespace(name="张三", department="质量部")
    management = SimpleNamespace(
        _resolve_selected_reporter_contact=AsyncMock(return_value=contact),
        _generate_monthly_deviation_code=AsyncMock(return_value="PC-260801"),
    )
    sync = SimpleNamespace(
        _resolve_contact_bitable_user_value=AsyncMock(return_value=[{"id": "ou-1"}]),
        _to_ms_timestamp=pages.feishu_sync_service._to_ms_timestamp,
    )
    monkeypatch.setattr(pages, "quality_management_service", management)
    monkeypatch.setattr(pages, "feishu_sync_service", sync)
    create_entity = AsyncMock(return_value={"record_id": "report-1"})
    get_report = AsyncMock(
        return_value={
            "record_id": "report-1",
            "deviation_code": "PC-260801",
            "description": "偏差内容",
            "product_batch": "产品A/批次1",
        }
    )
    monkeypatch.setattr(pages, "_create_entity_record", create_entity)
    monkeypatch.setattr(pages, "get_deviation_report_record", get_report)

    result = await pages.create_deviation_report_record(
        SimpleNamespace(),
        {
            "description": " 偏差内容 ",
            "product_batch": "产品A/批次1",
            "reporter_open_id": "ou-reporter",
        },
    )
    assert result["record_id"] == "report-1"
    fields = create_entity.await_args.args[2]
    assert fields["部门"] == "质量部"
    assert fields["报告人"] == [{"id": "ou-1"}]

    with pytest.raises(AppException):
        await pages.create_deviation_report_record(
            SimpleNamespace(),
            {"description": "", "product_batch": "批次", "reporter_open_id": "ou"},
        )
    with pytest.raises(AppException):
        await pages.create_deviation_report_record(
            SimpleNamespace(),
            {"description": "内容", "product_batch": "", "reporter_open_id": "ou"},
        )

    update_entity = AsyncMock()
    monkeypatch.setattr(pages, "_update_entity_record", update_entity)
    updated = await pages.update_deviation_report_record(
        SimpleNamespace(),
        "report-1",
        {
            "description": "新内容",
            "product_batch": "产品A/批次2",
            "reporter_name": "张三",
            "attachments": [{"name": "附件.pdf"}],
        },
    )
    assert updated["record_id"] == "report-1"
    assert update_entity.await_args.args[1:3] == (
        "deviation_report_record",
        "report-1",
    )
    assert update_entity.await_args.args[3]["附件"] == [{"name": "附件.pdf"}]

    monkeypatch.setattr(pages, "_delete_entity_record", AsyncMock())
    await pages.delete_deviation_report_record(SimpleNamespace(), "report-1")
    with pytest.raises(NotFoundException):
        get_report.side_effect = NotFoundException(resource="报告")
        await pages.delete_deviation_report_record(SimpleNamespace(), "missing")


@pytest.mark.asyncio
async def test_deviation_ledger_listing_filters_and_maps_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pages,
        "_resolve_runtime_entity",
        AsyncMock(
            return_value=(
                SimpleNamespace(),
                SimpleNamespace(id="tbl", table_id="tbl", field_mappings={}),
            )
        ),
    )
    monkeypatch.setattr(
        pages,
        "_search_entity_records",
        AsyncMock(
            return_value=[
                {
                    "record_id": "r-1",
                    "fields": {
                        "偏差编号": "D-1",
                        "偏差简要描述": "包装偏差",
                        "是否关闭": "是",
                        "产品名称/批号": "产品A",
                        "根本原因": "温度异常",
                        "纠正预防措施": "复核",
                    },
                },
                {
                    "record_id": "r-2",
                    "fields": {
                        "偏差编号": "D-2",
                        "偏差简要描述": "其他问题",
                        "是否关闭": "否",
                        "产品名称/批号": "产品B",
                    },
                },
            ]
        ),
    )
    result = await pages.list_deviation_ledger_records(
        SimpleNamespace(),
        keyword="包装",
        product_keyword="产品A",
        is_closed=True,
        root_cause_keyword="温度",
        corrective_actions_keyword="复核",
        page=1,
        page_size=20,
    )
    assert result["total"] == 1
    assert result["items"][0]["record_id"] == "r-1"


@pytest.mark.asyncio
async def test_validation_listing_handles_missing_base_and_filters_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pages,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(SimpleNamespace(), SimpleNamespace(id="tbl"))),
    )
    monkeypatch.setattr(
        pages,
        "_search_entity_records",
        AsyncMock(
            return_value=[
                {
                    "record_id": "v-1",
                    "created_time": "2026-01-01T00:00:00Z",
                    "last_modified_time": "2026-02-01T00:00:00Z",
                    "fields": {
                        "验证类别": "工艺验证",
                        "确认名称": "产品工艺确认",
                        "任务状态": "进行中",
                        "部门名称": "质量部",
                        "方案名称": "方案A",
                        "方案编码": "P-1",
                        "验证到期时间": "2026.02",
                        "起草时间": "2026-01-10T00:00:00Z",
                    },
                }
            ]
        ),
    )
    result = await pages.list_validation_records_from_feishu(
        SimpleNamespace(),
        validation_type="process_validation",
        status="进行中",
        department="质量部",
        keyword="方案A",
        planned_end_date_from="2026-01-01",
        planned_end_date_to="2026-03-01",
        drafted_at_from="2025-01-01",
        page=1,
        page_size=20,
    )
    assert result["total"] == 1
    assert result["items"][0]["validation_type"] == "process_validation"

    monkeypatch.setattr(
        pages,
        "_resolve_runtime_entity",
        AsyncMock(side_effect=AppException(message="disabled")),
    )
    empty = await pages.list_validation_records_from_feishu(
        SimpleNamespace(), page=2, page_size=10
    )
    assert empty == {"items": [], "total": 0, "page": 2, "page_size": 10}
