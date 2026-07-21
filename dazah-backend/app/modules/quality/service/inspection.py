"""Business services for quality inspection foundation resources."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateException, NotFoundException
from app.modules.quality.models.inspection import (
    FinishedProductInspection,
    InspectionRecord,
    LabInstrument,
    LabItem,
    LiquidMaterialInspection,
    SolidMaterialInspection,
)
from app.modules.quality.repository import inspection as repository


@dataclass(frozen=True)
class InspectionResource:
    code: str
    label: str
    model: type[Any]
    search_fields: tuple[str, ...]
    unique_field: str | None = None
    unique_label: str | None = None


_RESOURCES: dict[str, InspectionResource] = {
    "inspection_records": InspectionResource(
        code="inspection_records",
        label="检验记录",
        model=InspectionRecord,
        search_fields=("inspection_no", "product_name", "batch_no", "inspection_item"),
        unique_field="inspection_no",
        unique_label="检验编号",
    ),
    "lab_items": InspectionResource(
        code="lab_items",
        label="实验室物品",
        model=LabItem,
        search_fields=("name", "specification", "category", "batch_no", "supplier"),
    ),
    "lab_instruments": InspectionResource(
        code="lab_instruments",
        label="实验室仪器",
        model=LabInstrument,
        search_fields=("name", "model", "serial_no", "manufacturer", "department"),
        unique_field="serial_no",
        unique_label="仪器序列号",
    ),
    "finished_product_inspections": InspectionResource(
        code="finished_product_inspections",
        label="成品检验记录",
        model=FinishedProductInspection,
        search_fields=("inspection_no", "product_name", "batch_no", "inspection_item"),
        unique_field="inspection_no",
        unique_label="检验编号",
    ),
    "solid_material_inspections": InspectionResource(
        code="solid_material_inspections",
        label="固体物料检验记录",
        model=SolidMaterialInspection,
        search_fields=(
            "inspection_no",
            "material_name",
            "material_batch",
            "supplier",
            "inspection_item",
        ),
        unique_field="inspection_no",
        unique_label="检验编号",
    ),
    "liquid_material_inspections": InspectionResource(
        code="liquid_material_inspections",
        label="液体物料检验记录",
        model=LiquidMaterialInspection,
        search_fields=(
            "inspection_no",
            "material_name",
            "material_batch",
            "supplier",
            "inspection_item",
        ),
        unique_field="inspection_no",
        unique_label="检验编号",
    ),
}


def get_resource(resource_code: str) -> InspectionResource:
    return _RESOURCES[resource_code]


async def list_resource_records(
    db: AsyncSession,
    resource_code: str,
    *,
    keyword: str | None,
    page: int,
    page_size: int,
    filters: dict[str, Any] | None = None,
) -> tuple[list[Any], int]:
    resource = get_resource(resource_code)
    return await repository.list_records(
        db,
        resource.model,
        search_fields=resource.search_fields,
        filters=filters or {},
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


async def get_resource_record(
    db: AsyncSession,
    resource_code: str,
    record_id: uuid.UUID,
) -> Any:
    resource = get_resource(resource_code)
    record = await repository.get_record_by_id(db, resource.model, record_id)
    if record is None:
        raise NotFoundException(resource.label, str(record_id))
    return record


async def _ensure_unique_value(
    db: AsyncSession,
    resource: InspectionResource,
    data: dict[str, Any],
    *,
    exclude_id: uuid.UUID | None = None,
) -> None:
    if resource.unique_field is None:
        return
    value = data.get(resource.unique_field)
    if value is None or not str(value).strip():
        return
    if await repository.exists_value(
        db,
        resource.model,
        field_name=resource.unique_field,
        value=str(value).strip(),
        exclude_id=exclude_id,
    ):
        raise DuplicateException(
            resource.unique_label or resource.unique_field, str(value)
        )


async def create_resource_record(
    db: AsyncSession,
    resource_code: str,
    data: dict[str, Any],
) -> Any:
    resource = get_resource(resource_code)
    await _ensure_unique_value(db, resource, data)
    return await repository.create_record(db, resource.model, data)


async def update_resource_record(
    db: AsyncSession,
    resource_code: str,
    record_id: uuid.UUID,
    data: dict[str, Any],
) -> Any:
    resource = get_resource(resource_code)
    record = await get_resource_record(db, resource_code, record_id)
    await _ensure_unique_value(db, resource, data, exclude_id=record_id)
    await repository.update_record(db, record, data)
    refreshed = await repository.get_record_by_id(db, resource.model, record_id)
    if refreshed is None:
        raise NotFoundException(resource.label, str(record_id))
    return refreshed


async def delete_resource_record(
    db: AsyncSession,
    resource_code: str,
    record_id: uuid.UUID,
) -> None:
    resource = get_resource(resource_code)
    record = await get_resource_record(db, resource_code, record_id)
    await repository.soft_delete_record(db, record)
    await repository.get_record_by_id(
        db,
        resource.model,
        record_id,
        include_deleted=True,
    )
