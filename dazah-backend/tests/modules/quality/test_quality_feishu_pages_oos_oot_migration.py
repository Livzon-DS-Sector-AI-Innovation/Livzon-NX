from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality.service import quality_feishu_pages_oos_oot as service
from app.modules.quality.service.quality_feishu_sync import (
    QualityFeishuEntityRuntimeConfig,
)


def _entity() -> QualityFeishuEntityRuntimeConfig:
    return QualityFeishuEntityRuntimeConfig(
        app_token="app-token",
        table_id="table-id",
        is_enabled=True,
        enable_push_to_feishu=True,
        enable_pull_from_feishu=True,
        field_mappings={},
    )


def _record(fields: dict[str, object], record_id: str = "rec-1") -> dict[str, object]:
    return {
        "record_id": record_id,
        "created_time": "2026-08-20T08:00:00Z",
        "last_modified_time": "2026-08-21T08:00:00Z",
        "fields": fields,
    }


def test_checkbox_and_report_field_builders_cover_user_date_and_flags() -> None:
    assert service._map_checkbox(True) is True
    assert service._map_checkbox("是") is True
    assert service._map_checkbox("已确认") is True
    assert service._map_checkbox("0") is False
    assert service._map_nested_user({"name": "张三"}) == "张三"

    payload = {
        "report_time": "2026-08-20T08:00:00Z",
        "content": " 内容 ",
        "product_name": "产品A",
        "batch_number": "B001",
        "report_department": "质量部",
        "reporter": "ou-reporter",
        "qa": {"id": "ou-qa"},
        "qa_head": " ",
        "department_head_confirmed": 1,
        "fermentation_head_confirmed": False,
        "qa_confirmed": True,
    }
    fields = service._build_oos_oot_report_fields(payload)
    assert fields["内容"] == "内容"
    assert fields["报告人"] == [{"id": "ou-reporter"}]
    assert fields["QA"] == [{"id": "ou-qa"}]
    assert fields["部门负责人确认"] is True
    assert fields["报告时间"]

    api_fields = service._build_oos_oot_report_feishu_fields_async(
        SimpleNamespace(),
        {
            **payload,
            "reporter": "姓名",
            "qa": "ou_qa",
            "qa_head": {"id": "ou_head"},
        },
    )
    assert "报告人" not in api_fields
    assert api_fields["QA"] == [{"id": "ou_qa"}]
    assert api_fields["QA负责人"] == [{"id": "ou_head"}]
    assert api_fields["部门负责人确认"] is True


def test_report_and_investigation_mappers_normalize_nested_feishu_values() -> None:
    report = service._map_oos_oot_report_record(
        _record(
            {
                "报告时间": "2026-08-20T08:00:00Z",
                "内容": "偏差内容",
                "涉及产品名称": "产品A",
                "涉及批号": "B001",
                "报告部门": "质量部",
                "报告人": [{"id": "ou-r", "name": "报告人"}],
                "部门负责人": [{"id": "ou-d", "name": "部门负责人"}],
                "部门负责人确认": "是",
                "涉及发酵负责人": "发酵负责人",
                "涉及发酵负责人确认": True,
                "涉及提炼负责人": "提炼负责人",
                "QA": [{"id": "ou-qa", "name": "QA"}],
                "QA确认": 1,
                "QA负责人": [{"id": "ou-qh", "name": "QA负责人"}],
                "QA负责人确认": False,
                "附件": [{"name": "a.pdf", "url": "https://files/a"}],
            }
        ),
        _entity(),
    )
    assert report["record_id"] == "rec-1"
    assert report["content"] == "偏差内容"
    assert report["reporters"][0]["id"] == "ou-r"
    assert report["department_head_confirmed"] is True
    assert report["qa_confirmed"] is True
    assert report["attachments"][0]["name"] == "a.pdf"

    investigation = service._map_oos_oot_investigation_push(
        _record(
            {
                "OOS/OOT编号": "OOS-001",
                "第N次推送": 2,
                "调查报告": {"link": "https://report"},
                "提交日期": "2026-08-20T08:00:00Z",
                "部门": "生产部",
                "提交人": [{"id": "ou_s", "name": "提交人"}],
                "部门负责人": [{"id": "ou_d", "name": "负责人"}],
                "部门负责人审核结果": "通过",
                "QA": [{"id": "ou_q", "name": "QA"}],
                "QA审核结果": "通过",
                "QA负责人": [{"id": "ou_h", "name": "QA负责人"}],
                "QA负责人审核结果": "待审",
                "流程状态": "处理中",
                "已退回待重新提交": "已确认",
                "部门负责人(直接)": "直接负责人",
            },
            record_id="push-1",
        ),
        _entity(),
    )
    assert investigation["record_id"] == "push-1"
    assert investigation["investigation_report_url"] == "https://report"
    assert investigation["push_round"] == "2"
    assert investigation["department_head_result"] == "通过"
    assert investigation["need_resubmit"] is True

    push_fields = service._build_oos_oot_investigation_push_feishu_fields(
        {
            "oos_oot_code": "OOS-001",
            "push_round": "2",
            "department": "生产部",
            "department_head_result": "通过",
            "qa_result": "通过",
            "qa_head_result": "待审",
            "process_status": "处理中",
            "investigation_report_url": "https://report",
            "submitted_at": "2026-08-20T08:00:00Z",
            "submitter": "ou_s",
            "qa": {"id": "ou_q"},
            "need_resubmit": True,
        }
    )
    assert push_fields["调查报告"]["link"] == "https://report"
    assert push_fields["提交人"] == [{"id": "ou_s"}]
    assert push_fields["QA"] == [{"id": "ou_q"}]
    assert push_fields["已退回待重新提交"] is True


def test_ledger_and_product_department_field_builders_cover_numeric_fallbacks() -> None:
    numeric = service._build_ledger_feishu_fields(
        {
            "serial_number": "12",
            "material_name": "物料A",
            "batch_number": "B1",
            "investigation_code": "INV-1",
            "problem_description": "问题",
            "root_cause": "原因",
            "corrective_actions": "措施",
            "final_disposition": "结论",
            "remark": "备注",
            "registrant": "ou_user",
            "date": "2026-08-20",
        }
    )
    assert numeric["序号"] == 12
    assert numeric["登记人"] == [{"id": "ou_user"}]
    assert numeric["日期"]
    non_numeric = service._build_ledger_feishu_fields({"serial_number": "序号A"})
    assert non_numeric["序号"] == "序号A"

    ledger = service._map_oos_ledger(
        _record({"序号": 12, "物料名称": "物料A", "批号": "B1", "登记人": "张三"}),
        _entity(),
    )
    oot = service._map_oot_ledger(
        _record({"序号": 13, "物料名称": "物料B", "问题描述": "问题"}, "oot-1"),
        _entity(),
    )
    assert ledger["serial_number"] == "12"
    assert ledger["material_name"] == "物料A"
    assert oot["record_id"] == "oot-1"
    assert oot["problem_description"] == "问题"

    product = service._map_product_department(
        _record(
            {
                "序号": "1",
                "产品代码": "P-1",
                "涉及发酵部门": "发酵一部",
                "涉及发酵部门负责人": [{"id": "ou-f", "name": "发酵负责人"}],
                "涉及提炼部门": "提炼一部",
                "涉及提炼部门负责人": "提炼负责人",
            },
            "product-1",
        ),
        _entity(),
    )
    assert product["product_code"] == "P-1"
    assert product["fermentation_head"] == "发酵负责人"
    product_fields = service._build_product_department_feishu_fields(
        {
            "serial_number": "1",
            "product_code": "P-1",
            "fermentation_department": "发酵一部",
            "fermentation_head": {"id": "ou-f"},
            "extraction_department": "提炼一部",
            "extraction_head": "ou-e",
        }
    )
    assert product_fields["涉及发酵部门负责人"] == [{"id": "ou-f"}]
    assert product_fields["涉及提炼部门负责人"] == [{"id": "ou-e"}]


@pytest.mark.anyio
async def test_list_filters_and_pagination_for_all_legacy_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity = _entity()
    report_records = [
        _record({"内容": "命中内容", "涉及产品名称": "产品A"}, "r1"),
        _record({"内容": "其他", "涉及产品名称": "产品B"}, "r2"),
    ]
    push_records = [
        _record(
            {
                "OOS/OOT编号": "OOS-1",
                "第N次推送": "1",
                "部门负责人审核结果": "通过",
                "QA审核结果": "通过",
                "QA负责人审核结果": "待审",
                "流程状态": "处理中",
            },
            "p1",
        )
    ]
    ledger_records = [_record({"物料名称": "物料A", "批号": "B1"}, "l1")]
    product_records = [_record({"产品代码": "P-1", "涉及发酵部门": "发酵部"}, "pd1")]
    monkeypatch.setattr(
        service, "_resolve_runtime_entity", AsyncMock(return_value=(None, entity))
    )
    search = AsyncMock(
        side_effect=[
            report_records,
            push_records,
            ledger_records,
            ledger_records,
            product_records,
        ]
    )
    monkeypatch.setattr(service, "_search_entity_records", search)

    report_page = await service.list_oos_oot_report_records(
        SimpleNamespace(), keyword="命中", page=1, page_size=1
    )
    assert report_page["total"] == 1
    assert report_page["items"][0]["record_id"] == "r1"
    push_page = await service.list_oos_oot_investigation_push_records(
        SimpleNamespace(), oos_oot_code="OOS-1", qa_result="通过"
    )
    assert push_page["total"] == 1
    oos_page = await service.list_oos_ledger_records(SimpleNamespace(), keyword="物料A")
    oot_page = await service.list_oot_ledger_records(SimpleNamespace(), keyword="物料A")
    product_page = await service.list_product_department_records(
        SimpleNamespace(), keyword="P-1"
    )
    assert oos_page["total"] == oot_page["total"] == product_page["total"] == 1


@pytest.mark.anyio
async def test_lookup_create_delete_and_pull_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = SimpleNamespace()
    entity = _entity()
    monkeypatch.setattr(
        service, "_resolve_runtime_entity", AsyncMock(return_value=(None, entity))
    )
    monkeypatch.setattr(service, "_search_entity_records", AsyncMock(return_value=[]))
    with pytest.raises(NotFoundException):
        await service.get_oos_oot_report_record(db, "missing")
    with pytest.raises(NotFoundException):
        await service.get_oos_oot_investigation_push_record(db, "missing")
    with pytest.raises(NotFoundException):
        await service.get_oos_ledger_record(db, "missing")
    with pytest.raises(NotFoundException):
        await service.get_oot_ledger_record(db, "missing")
    with pytest.raises(NotFoundException):
        await service.get_product_department_record(db, "missing")
    with pytest.raises(AppException, match="内容不能为空"):
        await service.create_oos_oot_report_record(db, {})
    with pytest.raises(AppException, match="OOS/OOT编号不能为空"):
        await service.create_oos_oot_investigation_push_record(db, {})

    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(side_effect=AppException(message="disabled")),
    )
    assert await service.pull_oos_oot_report_records(db) == {
        "synced": 0,
        "failed": 0,
    }
    assert await service.pull_oos_oot_investigation_push_records(db) == {
        "synced": 0,
        "failed": 0,
    }
    assert await service.pull_oos_ledger_records(db) == {
        "synced": 0,
        "failed": 0,
    }
    assert await service.pull_oot_ledger_records(db) == {
        "synced": 0,
        "failed": 0,
    }
    assert await service.pull_product_department_records(db) == {
        "synced": 0,
        "failed": 0,
    }


@pytest.mark.anyio
async def test_contact_resolution_prefers_direct_id_then_contact_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = SimpleNamespace()
    assert await service._resolve_user_from_contacts(db, "ou-direct") == {
        "id": "ou-direct"
    }
    monkeypatch.setattr(
        service.feishu_sync_service.feishu_sync,
        "_get_department_contacts",
        AsyncMock(return_value=[{"name": "张三", "bitable_user_id": "ou-zhang"}]),
    )
    assert await service._resolve_user_from_contacts(db, "张三") == {"id": "ou-zhang"}
    assert await service._resolve_user_from_contacts(db, "未知") == {"id": "未知"}
    monkeypatch.setattr(
        service.feishu_sync_service.feishu_sync,
        "_get_department_contacts",
        AsyncMock(side_effect=RuntimeError("unavailable")),
    )
    assert await service._resolve_user_from_contacts(db, "回退") == {"id": "回退"}
    assert await service._resolve_user_from_contacts(db, None) is None


@pytest.mark.anyio
async def test_legacy_entity_create_update_delete_and_pull_success_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = SimpleNamespace()
    entity = _entity()
    runtime = SimpleNamespace(app_id="app-id", app_secret="secret")
    client = SimpleNamespace(update_record=AsyncMock())
    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(runtime, entity)),
    )
    monkeypatch.setattr(
        service,
        "_create_entity_record",
        AsyncMock(side_effect=lambda _db, _code, _fields: {"record_id": "created"}),
    )
    monkeypatch.setattr(service, "BitableClient", lambda **_kwargs: client)
    monkeypatch.setattr(service, "_delete_entity_record", AsyncMock())
    update_entity = AsyncMock()
    monkeypatch.setattr(service, "_update_entity_record", update_entity)

    async def _create_and_update(
        create_name: str,
        create_payload: dict[str, object],
        get_name: str,
        update_payload: dict[str, object],
    ) -> None:
        monkeypatch.setattr(
            service,
            get_name,
            AsyncMock(return_value={"record_id": "created", **create_payload}),
        )
        created = await getattr(service, create_name)(db, create_payload)
        assert created["record_id"] == "created"
        current = {"record_id": "created", **create_payload}
        monkeypatch.setattr(service, get_name, AsyncMock(return_value=current))
        updated = await getattr(
            service, "update_" + create_name.removeprefix("create_")
        )(db, "created", update_payload)
        assert updated["record_id"] == "created"
        await getattr(service, "delete_" + create_name.removeprefix("create_"))(
            db, "created"
        )

    await _create_and_update(
        "create_oos_oot_report_record",
        {"content": "内容", "report_department": "质量部"},
        "get_oos_oot_report_record",
        {"content": "更新"},
    )
    await _create_and_update(
        "create_oos_oot_investigation_push_record",
        {"oos_oot_code": "OOS-1", "push_round": "1"},
        "get_oos_oot_investigation_push_record",
        {"process_status": "完成"},
    )
    await _create_and_update(
        "create_oos_ledger_record",
        {"serial_number": "2", "material_name": "物料"},
        "get_oos_ledger_record",
        {"remark": "更新"},
    )
    await _create_and_update(
        "create_oot_ledger_record",
        {"serial_number": "3", "material_name": "物料"},
        "get_oot_ledger_record",
        {"remark": "更新"},
    )
    await _create_and_update(
        "create_product_department_record",
        {"serial_number": "4", "product_code": "P-1"},
        "get_product_department_record",
        {"extraction_department": "提炼部"},
    )
    assert client.update_record.await_count == 2
    assert update_entity.await_count == 3
    assert service._delete_entity_record.await_count == 5

    monkeypatch.setattr(
        service,
        "_search_entity_records",
        AsyncMock(return_value=[{"fields": {"序号": "9"}}]),
    )
    monkeypatch.setattr(
        service,
        "get_oos_ledger_record",
        AsyncMock(return_value={"record_id": "created"}),
    )
    await service.create_oos_ledger_record(db, {"material_name": "自动编号物料"})
    assert await service.pull_oos_oot_report_records(db) == {"synced": 1, "failed": 0}
