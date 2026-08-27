from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality.service import (
    quality_feishu_pages_complaint_return as complaint,
)
from app.modules.quality.service import quality_feishu_pages_supplier as supplier
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


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(app_id="app-id", app_secret="app-secret")


def _record(fields: dict[str, object], record_id: str = "rec-1") -> dict[str, object]:
    return {
        "record_id": record_id,
        "created_time": "2026-08-20T08:00:00Z",
        "last_modified_time": "2026-08-21T08:00:00Z",
        "fields": fields,
    }


class _BitableClient:
    record: dict[str, object] | None = None
    updated: list[tuple[str, str, dict[str, object]]] = []

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def get_record(
        self, _table_id: str, _record_id: str
    ) -> dict[str, object] | None:
        return self.record

    async def update_record(
        self, table_id: str, record_id: str, fields: dict[str, object]
    ) -> dict[str, object]:
        self.updated.append((table_id, record_id, fields))
        return {"record_id": record_id}


def test_external_feishu_mappers_and_field_builders_cover_business_fields() -> None:
    entity = _entity()
    complaint_row = complaint._map_complaint_ledger(
        _record(
            {
                "序号": 1,
                "投诉编号": "CMP-001",
                "投诉内容": "包装破损",
                "原因分析": "运输",
                "回复日期": "2026-08-22",
                "关闭时限": "30天",
                "投诉级别": "一般",
                "投诉单位（个人）": "客户A",
                "品名": "产品A",
                "数量": 2,
                "处理结果": "更换",
                "CAPA实施情况及结果": "完成",
                "批号": "B001",
            }
        ),
        entity,
    )
    assert complaint_row["complaint_number"] == "CMP-001"
    assert complaint_row["reply_date"] is not None
    complaint_fields = complaint._build_complaint_ledger_fields(
        {**complaint_row, "reply_date": "2026-08-23"}
    )
    assert complaint_fields["投诉编号"] == "CMP-001"
    assert complaint_fields["回复日期"]

    return_row = complaint._map_return_application(
        _record(
            {
                "序号": 1,
                "品名": "产品A",
                "退货总量": "10",
                "规格": "25kg",
                "批号": "B001",
                "数量": "2",
                "生产日期": "2026-01-01",
                "有效期/复验期": "2027-01-01",
                "批号1": "B002",
                "数量1": "3",
                "申请人": [{"name": "张三"}],
                "申请日期": "2026-08-20",
                "QA负责人意见": "同意",
                "QA负责人": [{"name": "李四"}],
                "QA负责人日期": "2026-08-21",
                "质量管理负责人建议": "批准",
                "质量管理负责人": [{"name": "王五"}],
                "质量管理负责人日期": "2026-08-22",
            },
            "return-1",
        ),
        entity,
    )
    assert return_row["product_name"] == "产品A"
    assert return_row["applicant"] == "张三"
    return_fields = complaint._build_return_application_fields(
        {
            "product_name": "产品A",
            "return_total": "10",
            "application_date": "2026-08-20",
            "applicant": {"id": "ou-applicant"},
            "qa_head": "ou_qa",
            "quality_manager": "invalid-name",
        }
    )
    assert return_fields["品名"] == "产品A"
    assert return_fields["申请人"] == [{"id": "ou-applicant"}]
    assert return_fields["QA负责人"] == [{"id": "ou_qa"}]

    ledger_row = complaint._map_return_ledger(
        _record(
            {
                "序号": 2,
                "品名": "产品B",
                "规格": "1kg",
                "产品批号": "PB-1",
                "数量": 4,
                "退货单位及地址": "客户B",
                "退回日期": "2026-08-24",
                "经办人": [{"name": "赵六"}],
                "退回产品处理结果": "销毁",
            },
            "ledger-1",
        ),
        entity,
    )
    assert ledger_row["product_batch_number"] == "PB-1"
    assert ledger_row["operator"] == "赵六"
    ledger_fields = complaint._build_return_ledger_fields(
        {
            "product_name": "产品B",
            "quantity": "4.5",
            "return_date": "2026-08-24",
            "operator": {"id": "ou-operator"},
        }
    )
    assert ledger_fields["数量"] == 4.5
    assert ledger_fields["经办人"] == [{"id": "ou-operator"}]
    with pytest.raises(AppException, match="数量必须为数字"):
        complaint._build_return_ledger_fields({"quantity": "not-a-number"})

    supplier_row = supplier._map_supplier_qualification(
        _record(
            {
                "供应商名称": "供应商A",
                "物料名称": "原料A",
                "物料类型": "原料",
                "资质名称": "营业执照",
                "资质文件": "license.pdf",
                "是否完成": "是",
                "截止日期": "2026-09-01",
                "负责人": [{"name": "张三"}, {"name": "李四"}],
                "备注": "重点供应商",
                "到期状态": "正常",
            },
            "supplier-1",
        ),
        entity,
    )
    assert supplier_row["supplier_name"] == "供应商A"
    assert supplier_row["responsible_person"] == "张三、李四"
    supplier_fields = supplier._build_supplier_qualification_fields(
        {
            "supplier_name": "供应商A",
            "qualification_name": "营业执照",
            "is_completed": True,
            "deadline": "2026-09-01",
            "responsible_person": "ou_owner",
        }
    )
    assert supplier_fields["是否完成"] is True
    assert supplier_fields["负责人"] == [{"id": "ou_owner"}]


@pytest.mark.anyio
async def test_external_feishu_services_cover_list_crud_pull_and_statistics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    entity = _entity()
    db = SimpleNamespace()
    monkeypatch.setattr(
        complaint,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(runtime, entity)),
    )
    monkeypatch.setattr(
        supplier,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(runtime, entity)),
    )
    complaint_rows = [
        _record(
            {"投诉编号": "CMP-001", "投诉内容": "包装破损", "品名": "产品A"},
            "complaint-1",
        ),
        _record({"投诉编号": "CMP-002", "投诉内容": "标签错误"}, "complaint-2"),
    ]
    return_rows = [
        _record({"品名": "产品A", "批号": "B001", "退货原因": "破损"}, "return-1")
    ]
    ledger_rows = [
        _record({"品名": "产品A", "产品批号": "B001", "经办人": "张三"}, "ledger-1")
    ]
    supplier_rows = [
        _record(
            {
                "供应商名称": "供应商A",
                "物料名称": "原料A",
                "物料类型": "原料",
                "资质名称": "营业执照",
                "是否完成": True,
                "截止日期": "2026-07-01",
            },
            "supplier-1",
        ),
        _record(
            {
                "供应商名称": "供应商B",
                "物料名称": "包材B",
                "物料类型": "包材",
                "资质名称": "审计报告",
                "是否完成": False,
                "截止日期": "2030-01-01",
            },
            "supplier-2",
        ),
    ]

    async def search(_db: object, entity_code: str) -> list[dict[str, object]]:
        return {
            complaint.ENTITY_COMPLAINT_LEDGER: complaint_rows,
            complaint.ENTITY_RETURN_APPLICATION: return_rows,
            complaint.ENTITY_RETURN_LEDGER: ledger_rows,
            supplier.ENTITY_SUPPLIER_QUALIFICATION: supplier_rows,
        }[entity_code]

    monkeypatch.setattr(complaint, "_search_entity_records", search)
    monkeypatch.setattr(supplier, "_search_entity_records", search)

    complaints = await complaint.list_complaint_ledger_records(
        db, keyword="包装", page=1, page_size=1
    )
    returns = await complaint.list_return_application_records(db, keyword="破损")
    ledgers = await complaint.list_return_ledger_records(db, keyword="产品A")
    suppliers = await supplier.list_supplier_qualification_records(
        db,
        keyword="供应商",
        supplier_name="供应商A",
        material_type="原料",
        qualification_name="营业执照",
        is_completed=True,
    )
    assert complaints["total"] == returns["total"] == ledgers["total"] == 1
    assert suppliers["items"][0]["supplier_name"] == "供应商A"

    for service, entity_code, payload, rows, record_id in (
        (
            complaint,
            complaint.ENTITY_COMPLAINT_LEDGER,
            {"complaint_content": "投诉内容", "complaint_number": "CMP-003"},
            complaint_rows,
            "complaint-1",
        ),
        (
            complaint,
            complaint.ENTITY_RETURN_APPLICATION,
            {"product_name": "产品A", "return_reason": "破损"},
            return_rows,
            "return-1",
        ),
        (
            complaint,
            complaint.ENTITY_RETURN_LEDGER,
            {"product_name": "产品A", "quantity": "2"},
            ledger_rows,
            "ledger-1",
        ),
        (
            supplier,
            supplier.ENTITY_SUPPLIER_QUALIFICATION,
            {"supplier_name": "供应商A", "qualification_name": "营业执照"},
            supplier_rows,
            "supplier-1",
        ),
    ):
        monkeypatch.setattr(
            service,
            "_create_entity_record",
            AsyncMock(return_value={"record_id": record_id}),
        )
        if service is supplier:
            _BitableClient.record = rows[0]
            monkeypatch.setattr(service, "BitableClient", _BitableClient)
            created = await service.create_supplier_qualification_record(db, payload)
            assert created["record_id"] == "supplier-1"
        elif entity_code == complaint.ENTITY_COMPLAINT_LEDGER:
            created = await complaint.create_complaint_ledger_record(db, payload)
            assert created["record_id"] == "complaint-1"
        elif entity_code == complaint.ENTITY_RETURN_APPLICATION:
            created = await complaint.create_return_application_record(db, payload)
            assert created["record_id"] == "return-1"
        else:
            created = await complaint.create_return_ledger_record(db, payload)
            assert created["record_id"] == "ledger-1"

    monkeypatch.setattr(complaint, "BitableClient", _BitableClient)
    _BitableClient.record = complaint_rows[0]
    updated_complaint = await complaint.update_complaint_ledger_record(
        db, "complaint-1", {"complaint_content": "已处理"}
    )
    assert updated_complaint["record_id"] == "complaint-1"
    _BitableClient.record = return_rows[0]
    updated_return = await complaint.update_return_application_record(
        db, "return-1", {"return_reason": "破损"}
    )
    assert updated_return["record_id"] == "return-1"
    _BitableClient.record = ledger_rows[0]
    updated_ledger = await complaint.update_return_ledger_record(
        db, "ledger-1", {"quantity": "3"}
    )
    assert updated_ledger["record_id"] == "ledger-1"

    monkeypatch.setattr(supplier, "BitableClient", _BitableClient)
    _BitableClient.record = supplier_rows[0]
    updated_supplier = await supplier.update_supplier_qualification_record(
        db, "supplier-1", {"remark": "更新"}
    )
    assert updated_supplier["record_id"] == "supplier-1"
    for service, entity_code, record_id in (
        (complaint, complaint.ENTITY_COMPLAINT_LEDGER, "complaint-1"),
        (complaint, complaint.ENTITY_RETURN_APPLICATION, "return-1"),
        (complaint, complaint.ENTITY_RETURN_LEDGER, "ledger-1"),
        (supplier, supplier.ENTITY_SUPPLIER_QUALIFICATION, "supplier-1"),
    ):
        deleted = AsyncMock()
        monkeypatch.setattr(service, "_delete_entity_record", deleted)
        if entity_code == complaint.ENTITY_COMPLAINT_LEDGER:
            await complaint.delete_complaint_ledger_record(db, record_id)
        elif entity_code == complaint.ENTITY_RETURN_APPLICATION:
            await complaint.delete_return_application_record(db, record_id)
        elif entity_code == complaint.ENTITY_RETURN_LEDGER:
            await complaint.delete_return_ledger_record(db, record_id)
        else:
            await supplier.delete_supplier_qualification_record(db, record_id)
        deleted.assert_awaited_once_with(db, entity_code, record_id)

    monkeypatch.setattr(
        complaint,
        "list_complaint_ledger_records",
        AsyncMock(return_value={"items": complaint_rows}),
    )
    monkeypatch.setattr(
        complaint,
        "list_return_application_records",
        AsyncMock(return_value={"items": return_rows}),
    )
    monkeypatch.setattr(
        complaint,
        "list_return_ledger_records",
        AsyncMock(return_value={"items": ledger_rows}),
    )
    monkeypatch.setattr(
        supplier,
        "list_supplier_qualification_records",
        AsyncMock(return_value={"items": supplier_rows}),
    )
    assert await complaint.pull_complaint_ledger_records(db) == {
        "synced": 2,
        "failed": 0,
    }
    assert await complaint.pull_return_application_records(db) == {
        "synced": 1,
        "failed": 0,
    }
    assert await complaint.pull_return_ledger_records(db) == {"synced": 1, "failed": 0}
    assert await supplier.pull_supplier_qualification_records(db) == {
        "synced": 2,
        "failed": 0,
    }

    stats_rows = [
        {
            "supplier_name": "供应商A",
            "material_type": "原料",
            "qualification_name": "营业执照",
            "is_completed": True,
            "deadline": "2026-07-01",
        },
        {
            "supplier_name": "供应商B",
            "material_type": "包材",
            "qualification_name": "审计报告",
            "is_completed": False,
            "deadline": "2030-01-01",
        },
    ]
    monkeypatch.setattr(
        supplier,
        "list_supplier_qualification_records",
        AsyncMock(return_value={"items": stats_rows}),
    )
    statistics = await supplier.get_supplier_statistics(db)
    assert statistics["total"] == 2
    assert statistics["expired_count"] == 1
    assert statistics["supplier_count"] == 2
    monkeypatch.setattr(
        supplier,
        "list_supplier_qualification_records",
        AsyncMock(side_effect=AppException(message="disabled")),
    )
    assert (await supplier.get_supplier_statistics(db))["total"] == 0

    monkeypatch.setattr(
        complaint,
        "_search_entity_records",
        AsyncMock(return_value=[]),
    )
    with pytest.raises(NotFoundException):
        await complaint.get_complaint_ledger_record(db, "missing")
    with pytest.raises(NotFoundException):
        await complaint.get_return_application_record(db, "missing")
    with pytest.raises(NotFoundException):
        await complaint.get_return_ledger_record(db, "missing")
    with pytest.raises(AppException, match="投诉内容不能为空"):
        await complaint.create_complaint_ledger_record(db, {})
    with pytest.raises(AppException, match="供应商名称不能为空"):
        await supplier.create_supplier_qualification_record(db, {})
