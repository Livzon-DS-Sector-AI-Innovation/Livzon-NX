from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.modules.quality.api import complaint, product_quality, return_recall, supplier
from app.modules.quality.models.external_quality import (
    ComplaintRecord,
    ProductQualityRecord,
    ReturnRecallRecord,
    Supplier,
)


class _Result:
    def __init__(
        self, value: object | None = None, rows: list[object] | None = None
    ) -> None:
        self.value = value
        self.rows = rows or []

    def scalar(self) -> int:
        return int(self.value or 0)

    def scalar_one(self) -> object:
        return self.value

    def scalar_one_or_none(self) -> object | None:
        return self.value

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.rows


class _Db:
    def __init__(self, *results: _Result) -> None:
        self.execute = AsyncMock(side_effect=list(results))
        self.add = Mock()
        self.flush = AsyncMock(side_effect=self._flush)

    async def _flush(self) -> None:
        for call in self.add.call_args_list:
            record = call.args[0]
            if getattr(record, "id", None) is None:
                record.id = uuid4()
            now = datetime.now(UTC)
            record.created_at = getattr(record, "created_at", None) or now
            record.updated_at = getattr(record, "updated_at", None) or now
            record.is_deleted = False
            if getattr(record, "status", None) is None:
                record.status = {
                    ComplaintRecord: "pending",
                    ReturnRecallRecord: "pending",
                    Supplier: "active",
                    ProductQualityRecord: "draft",
                }[type(record)]


def _body(response: object) -> dict[str, object]:
    return json.loads(response.body)  # type: ignore[union-attr]


def _complaint() -> ComplaintRecord:
    item = ComplaintRecord(
        complaint_code="CMP-001",
        title="客户投诉",
        customer_name="客户A",
        product_name="产品A",
        status="pending",
    )
    item.id = uuid4()
    item.created_at = datetime(2026, 8, 20, tzinfo=UTC)
    item.updated_at = item.created_at
    item.is_deleted = False
    return item


def _return_recall() -> ReturnRecallRecord:
    item = ReturnRecallRecord(
        record_code="RET-001",
        record_type="return",
        title="退货申请",
        product_name="产品A",
        quantity=2,
        status="pending",
    )
    item.id = uuid4()
    item.created_at = datetime(2026, 8, 20, tzinfo=UTC)
    item.updated_at = item.created_at
    item.is_deleted = False
    return item


def _supplier() -> Supplier:
    item = Supplier(
        supplier_code="SUP-001",
        name="供应商A",
        category="原料",
        status="active",
    )
    item.id = uuid4()
    item.created_at = datetime(2026, 8, 20, tzinfo=UTC)
    item.updated_at = item.created_at
    item.is_deleted = False
    return item


def _product_quality() -> ProductQualityRecord:
    item = ProductQualityRecord(
        record_code="PQR-001",
        record_type="customer_standard",
        title="产品质量标准",
        product_name="产品A",
        review_type="年度回顾",
        quality_trend="稳定",
        status="draft",
    )
    item.id = uuid4()
    item.created_at = datetime(2026, 8, 20, tzinfo=UTC)
    item.updated_at = item.created_at
    item.is_deleted = False
    return item


@pytest.mark.anyio
async def test_quality_legacy_entity_apis_cover_crud_and_filter_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(complaint, "_require_user", Mock())
    monkeypatch.setattr(return_recall, "_require_user", Mock())
    monkeypatch.setattr(supplier, "_require_user", Mock())
    monkeypatch.setattr(product_quality, "_require_user", Mock())

    cases = (
        (
            complaint,
            _complaint,
            complaint.list_complaints,
            complaint.get_complaint,
            complaint.create_complaint,
            complaint.update_complaint,
            complaint.delete_complaint,
            {
                "complaint_code": "CMP-002",
                "title": "新增投诉",
                "customer_name": "客户B",
            },
            {"title": "已更新"},
            {"status": "responded", "complaint_category": "包装", "keyword": "CMP"},
        ),
        (
            return_recall,
            _return_recall,
            return_recall.list_return_recalls,
            return_recall.get_return_recall,
            return_recall.create_return_recall,
            return_recall.update_return_recall,
            return_recall.delete_return_recall,
            {
                "record_code": "RET-002",
                "record_type": "return",
                "title": "新增退货",
                "product_name": "产品B",
            },
            {"status": "assessing"},
            {"record_type": "return", "status": "pending", "keyword": "RET"},
        ),
        (
            supplier,
            _supplier,
            supplier.list_suppliers,
            supplier.get_supplier,
            supplier.create_supplier,
            supplier.update_supplier,
            supplier.delete_supplier,
            {"supplier_code": "SUP-002", "name": "新增供应商", "category": "包材"},
            {"name": "更新供应商"},
            {"status": "active", "category": "原料", "keyword": "SUP"},
        ),
        (
            product_quality,
            _product_quality,
            product_quality.list_product_quality,
            product_quality.get_product_quality,
            product_quality.create_product_quality,
            product_quality.update_product_quality,
            product_quality.delete_product_quality,
            {
                "record_code": "PQR-002",
                "record_type": "customer_standard",
                "title": "新增标准",
                "product_name": "产品B",
            },
            {"title": "更新标准"},
            {
                "review_type": "年度回顾",
                "status": "draft",
                "product_name": "产品A",
                "keyword": "PQR",
            },
        ),
    )

    for (
        module,
        factory,
        list_route,
        get_route,
        create_route,
        update_route,
        delete_route,
        create_data,
        update_data,
        filters,
    ) in cases:
        record = factory()
        listed = await list_route(
            page=2,
            page_size=5,
            db=_Db(_Result(1), _Result(rows=[record])),
            current_user=user,
            **filters,
        )
        assert listed.status_code == 200
        assert _body(listed)["meta"]["total"] == 1  # type: ignore[index]

        found = await get_route(record.id, db=_Db(_Result(record)), current_user=user)
        assert found.status_code == 200
        assert _body(found)["data"]["id"] == str(record.id)  # type: ignore[index]

        created_record = factory()
        created = await create_route(
            module.__dict__[
                {
                    complaint: "CreateComplaintRequest",
                    return_recall: "CreateReturnRecallRequest",
                    supplier: "CreateSupplierRequest",
                    product_quality: "CreateProductQualityRequest",
                }[module]
            ](**create_data),
            db=_Db(_Result(created_record)),
            current_user=user,
        )
        assert created.status_code == 200
        assert _body(created)["message"] == "创建成功"

        updated = await update_route(
            record.id,
            module.__dict__[
                {
                    complaint: "UpdateComplaintRequest",
                    return_recall: "UpdateReturnRecallRequest",
                    supplier: "UpdateSupplierRequest",
                    product_quality: "UpdateProductQualityRequest",
                }[module]
            ](**update_data),
            db=_Db(_Result(record), _Result(record)),
            current_user=user,
        )
        assert updated.status_code == 200
        assert _body(updated)["message"] == "更新成功"

        deleted = await delete_route(
            record.id, db=_Db(_Result(record)), current_user=user
        )
        assert deleted.status_code == 200
        assert _body(deleted)["message"] == "已删除"
