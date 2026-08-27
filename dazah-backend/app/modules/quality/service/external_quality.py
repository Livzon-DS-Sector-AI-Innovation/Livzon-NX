"""Business services for supplier and external quality management."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateException, NotFoundException
from app.modules.quality.models.external_quality import (
    ComplaintRecord,
    ProductQualityRecord,
    ProductQualityStandardItem,
    ReturnRecallRecord,
    Supplier,
    SupplierQualification,
)
from app.modules.quality.repository import external_quality as repository


@dataclass(frozen=True)
class ExternalQualityResource:
    code: str
    label: str
    model: type[Any]
    unique_field: str
    unique_label: str
    search_fields: tuple[str, ...]


_RESOURCES: dict[str, ExternalQualityResource] = {
    "suppliers": ExternalQualityResource(
        code="suppliers",
        label="供应商",
        model=Supplier,
        unique_field="supplier_code",
        unique_label="供应商编号",
        search_fields=("supplier_code", "name", "contact_person", "scope_of_supply"),
    ),
    "complaints": ExternalQualityResource(
        code="complaints",
        label="投诉记录",
        model=ComplaintRecord,
        unique_field="complaint_code",
        unique_label="投诉编号",
        search_fields=(
            "complaint_code",
            "title",
            "customer_name",
            "product_name",
            "batch_number",
            "description",
        ),
    ),
    "return_recalls": ExternalQualityResource(
        code="return_recalls",
        label="退货/召回记录",
        model=ReturnRecallRecord,
        unique_field="record_code",
        unique_label="退货/召回编号",
        search_fields=(
            "record_code",
            "title",
            "product_name",
            "batch_number",
            "reason",
        ),
    ),
    "product_quality_records": ExternalQualityResource(
        code="product_quality_records",
        label="产品质量记录",
        model=ProductQualityRecord,
        unique_field="record_code",
        unique_label="产品质量记录编号",
        search_fields=(
            "record_code",
            "title",
            "product_name",
            "customer_name",
            "quality_standard",
            "conclusion",
        ),
    ),
}


def get_resource(resource_code: str) -> ExternalQualityResource:
    return _RESOURCES[resource_code]


async def _get_resource_record(
    db: AsyncSession, resource_code: str, record_id: uuid.UUID
) -> Any:
    resource = get_resource(resource_code)
    record = await repository.get_record_by_id(db, resource.model, record_id)
    if record is None:
        raise NotFoundException(resource.label, str(record_id))
    return record


async def list_resource_records(
    db: AsyncSession,
    resource_code: str,
    *,
    filters: dict[str, Any],
    keyword: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Any], int]:
    resource = get_resource(resource_code)
    return await repository.list_records(
        db,
        resource.model,
        search_fields=resource.search_fields,
        filters=filters,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


async def get_resource_record(
    db: AsyncSession, resource_code: str, record_id: uuid.UUID
) -> Any:
    return await _get_resource_record(db, resource_code, record_id)


async def _ensure_unique_value(
    db: AsyncSession,
    resource: ExternalQualityResource,
    data: dict[str, Any],
    *,
    exclude_id: uuid.UUID | None = None,
) -> None:
    value = data.get(resource.unique_field)
    if value is None:
        return
    normalized = str(value).strip()
    if not normalized:
        return
    if await repository.get_record_by_value(
        db,
        resource.model,
        field_name=resource.unique_field,
        value=normalized,
        exclude_id=exclude_id,
    ):
        raise DuplicateException(resource.unique_label, normalized)


async def create_resource_record(
    db: AsyncSession, resource_code: str, data: dict[str, Any]
) -> Any:
    resource = get_resource(resource_code)
    await _ensure_unique_value(db, resource, data)
    defaults: dict[str, Any] = {}
    if resource_code == "complaints":
        defaults["status"] = "pending"
    elif resource_code == "return_recalls":
        defaults["status"] = "pending"
    elif resource_code == "product_quality_records":
        defaults["status"] = "draft"
    normalized = {
        **data,
        resource.unique_field: str(data[resource.unique_field]).strip(),
    }
    return await repository.create_record(
        db, resource.model, {**normalized, **defaults}
    )


async def update_resource_record(
    db: AsyncSession,
    resource_code: str,
    record_id: uuid.UUID,
    data: dict[str, Any],
) -> Any:
    resource = get_resource(resource_code)
    record = await _get_resource_record(db, resource_code, record_id)
    if getattr(record, "status", None) in {"closed", "completed", "approved"}:
        raise ValueError(f"{resource.label}处于最终状态，不能编辑")
    if resource.unique_field in data:
        data = {**data, resource.unique_field: str(data[resource.unique_field]).strip()}
        await _ensure_unique_value(db, resource, data, exclude_id=record_id)
    await repository.update_record(db, record, data)
    refreshed = await repository.get_record_by_id(db, resource.model, record_id)
    if refreshed is None:
        raise NotFoundException(resource.label, str(record_id))
    return refreshed


async def delete_resource_record(
    db: AsyncSession, resource_code: str, record_id: uuid.UUID
) -> None:
    record = await _get_resource_record(db, resource_code, record_id)
    if resource_code == "suppliers":
        for qualification in await repository.list_records_by_value(
            db,
            SupplierQualification,
            field_name="supplier_id",
            value=record.id,
        ):
            await repository.soft_delete_record(db, qualification)
    if resource_code == "product_quality_records":
        for item in await repository.list_records_by_value(
            db,
            ProductQualityStandardItem,
            field_name="product_quality_id",
            value=record.id,
            order_field="display_order",
        ):
            await repository.soft_delete_record(db, item)
    await repository.soft_delete_record(db, record)


async def _get_supplier(db: AsyncSession, supplier_id: uuid.UUID) -> Supplier:
    supplier = await repository.get_record_by_id(db, Supplier, supplier_id)
    if supplier is None:
        raise NotFoundException("供应商", str(supplier_id))
    return cast(Supplier, supplier)


async def get_supplier_qualification(
    db: AsyncSession, qualification_id: uuid.UUID
) -> SupplierQualification:
    qualification = await repository.get_record_by_id(
        db, SupplierQualification, qualification_id
    )
    if qualification is None:
        raise NotFoundException("供应商资质", str(qualification_id))
    return cast(SupplierQualification, qualification)


async def list_supplier_qualifications(
    db: AsyncSession, supplier_id: uuid.UUID
) -> list[SupplierQualification]:
    await _get_supplier(db, supplier_id)
    return await repository.list_records_by_value(
        db,
        SupplierQualification,
        field_name="supplier_id",
        value=supplier_id,
        order_field="expiry_date",
    )


async def create_supplier_qualification(
    db: AsyncSession, supplier_id: uuid.UUID, data: dict[str, Any]
) -> SupplierQualification:
    await _get_supplier(db, supplier_id)
    code = str(data["qualification_code"]).strip()
    if await repository.get_record_by_value(
        db,
        SupplierQualification,
        field_name="qualification_code",
        value=code,
    ):
        raise DuplicateException("资质编号", code)
    return cast(
        SupplierQualification,
        await repository.create_record(
            db,
            SupplierQualification,
            {**data, "supplier_id": supplier_id, "qualification_code": code},
        ),
    )


async def update_supplier_qualification(
    db: AsyncSession, qualification_id: uuid.UUID, data: dict[str, Any]
) -> SupplierQualification:
    qualification = await get_supplier_qualification(db, qualification_id)
    if "qualification_code" in data:
        code = str(data["qualification_code"]).strip()
        if await repository.get_record_by_value(
            db,
            SupplierQualification,
            field_name="qualification_code",
            value=code,
            exclude_id=qualification_id,
        ):
            raise DuplicateException("资质编号", code)
        data = {**data, "qualification_code": code}
    await repository.update_record(db, qualification, data)
    refreshed = await repository.get_record_by_id(
        db, SupplierQualification, qualification_id
    )
    if refreshed is None:
        raise NotFoundException("供应商资质", str(qualification_id))
    return cast(SupplierQualification, refreshed)


async def delete_supplier_qualification(
    db: AsyncSession, qualification_id: uuid.UUID
) -> None:
    await repository.soft_delete_record(
        db, await get_supplier_qualification(db, qualification_id)
    )


async def start_complaint_investigation(
    db: AsyncSession, complaint_id: uuid.UUID
) -> ComplaintRecord:
    complaint = await _get_resource_record(db, "complaints", complaint_id)
    if complaint.status != "pending":
        raise ValueError("仅待处理投诉可以启动调查")
    await repository.update_record(db, complaint, {"status": "investigating"})
    return cast(
        ComplaintRecord, await _get_resource_record(db, "complaints", complaint_id)
    )


async def respond_to_complaint(
    db: AsyncSession,
    complaint_id: uuid.UUID,
    *,
    investigation_result: str,
    response_content: str,
    response_date: date,
) -> ComplaintRecord:
    complaint = await _get_resource_record(db, "complaints", complaint_id)
    if complaint.status != "investigating":
        raise ValueError("仅调查中的投诉可以提交回复")
    await repository.update_record(
        db,
        complaint,
        {
            "status": "responded",
            "investigation_result": investigation_result.strip(),
            "response_content": response_content.strip(),
            "response_date": response_date,
        },
    )
    return cast(
        ComplaintRecord, await _get_resource_record(db, "complaints", complaint_id)
    )


async def close_complaint(db: AsyncSession, complaint_id: uuid.UUID) -> ComplaintRecord:
    complaint = await _get_resource_record(db, "complaints", complaint_id)
    if complaint.status != "responded":
        raise ValueError("仅已回复的投诉可以关闭")
    await repository.update_record(
        db,
        complaint,
        {"status": "closed", "closed_at": datetime.now(UTC)},
    )
    return cast(
        ComplaintRecord, await _get_resource_record(db, "complaints", complaint_id)
    )


async def start_return_recall_assessment(
    db: AsyncSession, record_id: uuid.UUID
) -> ReturnRecallRecord:
    record = await _get_resource_record(db, "return_recalls", record_id)
    if record.status != "pending":
        raise ValueError("仅待处理的退货/召回记录可以启动评估")
    await repository.update_record(db, record, {"status": "assessing"})
    return cast(
        ReturnRecallRecord, await _get_resource_record(db, "return_recalls", record_id)
    )


async def start_return_recall_processing(
    db: AsyncSession, record_id: uuid.UUID, assessment_date: date
) -> ReturnRecallRecord:
    record = await _get_resource_record(db, "return_recalls", record_id)
    if record.status != "assessing":
        raise ValueError("仅评估中的退货/召回记录可以进入处置")
    await repository.update_record(
        db,
        record,
        {"status": "processing", "assessment_date": assessment_date},
    )
    return cast(
        ReturnRecallRecord, await _get_resource_record(db, "return_recalls", record_id)
    )


async def complete_return_recall(
    db: AsyncSession,
    record_id: uuid.UUID,
    *,
    disposition: str,
    completion_date: date,
) -> ReturnRecallRecord:
    record = await _get_resource_record(db, "return_recalls", record_id)
    if record.status != "processing":
        raise ValueError("仅处置中的退货/召回记录可以完成")
    await repository.update_record(
        db,
        record,
        {
            "status": "completed",
            "disposition": disposition.strip(),
            "completion_date": completion_date,
        },
    )
    return cast(
        ReturnRecallRecord, await _get_resource_record(db, "return_recalls", record_id)
    )


async def complete_product_quality_record(
    db: AsyncSession,
    record_id: uuid.UUID,
    *,
    conclusion: str,
    reviewer: str,
    review_date: date,
) -> ProductQualityRecord:
    record = await _get_resource_record(db, "product_quality_records", record_id)
    if record.status != "draft":
        raise ValueError("仅草稿产品质量记录可以完成")
    await repository.update_record(
        db,
        record,
        {
            "status": "completed",
            "conclusion": conclusion.strip(),
            "reviewer": reviewer.strip(),
            "review_date": review_date,
        },
    )
    return cast(
        ProductQualityRecord,
        await _get_resource_record(db, "product_quality_records", record_id),
    )


async def approve_product_quality_record(
    db: AsyncSession, record_id: uuid.UUID
) -> ProductQualityRecord:
    record = await _get_resource_record(db, "product_quality_records", record_id)
    if record.status != "completed":
        raise ValueError("仅已完成的产品质量记录可以批准")
    await repository.update_record(
        db,
        record,
        {"status": "approved", "approved_at": datetime.now(UTC)},
    )
    return cast(
        ProductQualityRecord,
        await _get_resource_record(db, "product_quality_records", record_id),
    )


async def _get_product_quality_standard_record(
    db: AsyncSession, record_id: uuid.UUID
) -> ProductQualityRecord:
    record = await _get_resource_record(db, "product_quality_records", record_id)
    if record.record_type != "customer_standard":
        raise ValueError("仅客户质量标准记录可以维护标准明细")
    return cast(ProductQualityRecord, record)


async def get_product_quality_standard_item(
    db: AsyncSession, item_id: uuid.UUID
) -> ProductQualityStandardItem:
    item = await repository.get_record_by_id(db, ProductQualityStandardItem, item_id)
    if item is None:
        raise NotFoundException("产品质量标准明细", str(item_id))
    return cast(ProductQualityStandardItem, item)


async def list_product_quality_standard_items(
    db: AsyncSession, record_id: uuid.UUID
) -> list[ProductQualityStandardItem]:
    await _get_product_quality_standard_record(db, record_id)
    return await repository.list_records_by_value(
        db,
        ProductQualityStandardItem,
        field_name="product_quality_id",
        value=record_id,
        order_field="display_order",
    )


async def create_product_quality_standard_item(
    db: AsyncSession, record_id: uuid.UUID, data: dict[str, Any]
) -> ProductQualityStandardItem:
    await _get_product_quality_standard_record(db, record_id)
    display_order = int(data.get("display_order", 1))
    existing_items = await repository.list_records_by_value(
        db,
        ProductQualityStandardItem,
        field_name="product_quality_id",
        value=record_id,
        order_field="display_order",
    )
    if any(item.display_order == display_order for item in existing_items):
        raise DuplicateException("产品质量标准明细显示顺序", str(display_order))
    return cast(
        ProductQualityStandardItem,
        await repository.create_record(
            db,
            ProductQualityStandardItem,
            {**data, "product_quality_id": record_id, "display_order": display_order},
        ),
    )


async def update_product_quality_standard_item(
    db: AsyncSession, item_id: uuid.UUID, data: dict[str, Any]
) -> ProductQualityStandardItem:
    item = await get_product_quality_standard_item(db, item_id)
    await _get_product_quality_standard_record(db, item.product_quality_id)
    display_order = data.get("display_order")
    if display_order is not None:
        existing_items = await repository.list_records_by_value(
            db,
            ProductQualityStandardItem,
            field_name="product_quality_id",
            value=item.product_quality_id,
            order_field="display_order",
        )
        if any(
            other.id != item_id and other.display_order == int(display_order)
            for other in existing_items
        ):
            raise DuplicateException("产品质量标准明细显示顺序", str(display_order))
    await repository.update_record(db, item, data)
    refreshed = await repository.get_record_by_id(
        db, ProductQualityStandardItem, item_id
    )
    if refreshed is None:
        raise NotFoundException("产品质量标准明细", str(item_id))
    return cast(ProductQualityStandardItem, refreshed)


async def delete_product_quality_standard_item(
    db: AsyncSession, item_id: uuid.UUID
) -> None:
    await repository.soft_delete_record(
        db, await get_product_quality_standard_item(db, item_id)
    )
