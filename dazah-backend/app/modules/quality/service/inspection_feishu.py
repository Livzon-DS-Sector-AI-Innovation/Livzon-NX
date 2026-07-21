"""Explicit single-record Feishu push for inspection resources."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service import inspection as inspection_service
from app.modules.quality.service.quality_feishu_sync import feishu_sync

_RESOURCE_ENTITY_CODES = {
    "inspection_records": "inspection_general",
    "lab_items": "inspection_lab_item",
    "lab_instruments": "inspection_lab_instrument",
    "finished_product_inspections": "inspection_finished_product",
    "solid_material_inspections": "inspection_solid_material",
    "liquid_material_inspections": "inspection_liquid_material",
}


def _as_text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _build_fields(
    resource_code: str,
    record: Any,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    if resource_code == "lab_items":
        return (
            {
                "物品名称": record.name,
                "规格": record.specification or "",
                "类别": record.category or "",
                "数量": record.quantity,
                "单位": record.unit or "",
                "存放位置": record.location or "",
                "供应商": record.supplier or "",
                "批号": record.batch_no or "",
                "有效期至": (
                    record.expiry_date.isoformat() if record.expiry_date else ""
                ),
                "状态": record.status,
                "备注": record.remark or "",
            },
            [("物品名称", record.name)],
        )
    if resource_code == "lab_instruments":
        lookup_value = record.serial_no or record.name
        return (
            {
                "仪器名称": record.name,
                "仪器序列号": record.serial_no or "",
                "型号": record.model or "",
                "生产厂家": record.manufacturer or "",
                "所属部门": record.department or "",
                "放置位置": record.location or "",
                "最近校准日期": (
                    record.calibration_date.isoformat()
                    if record.calibration_date
                    else ""
                ),
                "下次校准日期": (
                    record.next_calibration_date.isoformat()
                    if record.next_calibration_date
                    else ""
                ),
                "状态": record.status,
                "备注": record.remark or "",
            },
            [(("仪器序列号" if record.serial_no else "仪器名称"), lookup_value)],
        )

    subject = (
        record.product_name
        if hasattr(record, "product_name")
        else record.material_name
    )
    batch_no = (
        record.batch_no if hasattr(record, "batch_no") else record.material_batch
    )
    fields = {
        "检验编号": record.inspection_no,
        "产品/物料名称": subject or "",
        "批号": batch_no or "",
        "检验项目": record.inspection_item or "",
        "标准规定": record.specification or "",
        "检验结果": record.test_result or "",
        "检验结论": record.conclusion or "",
        "检验人": record.inspector or "",
        "检验日期": (
            record.inspection_date.isoformat() if record.inspection_date else ""
        ),
        "备注": record.remark or "",
    }
    if resource_code == "inspection_records":
        fields["检验类型"] = record.inspection_type or ""
        fields["检验部门"] = record.department or ""
    if resource_code in {"solid_material_inspections", "liquid_material_inspections"}:
        fields["供应商"] = record.supplier or ""
    return fields, [("检验编号", record.inspection_no)]


async def sync_inspection_record_to_feishu(
    db: AsyncSession,
    *,
    resource_code: str,
    record_id: Any,
) -> dict[str, str | datetime]:
    entity_code = _RESOURCE_ENTITY_CODES.get(resource_code)
    if entity_code is None:
        raise ValueError("不支持的检验飞书同步资源")

    record = await inspection_service.get_resource_record(db, resource_code, record_id)
    runtime = await feishu_sync._resolve_runtime(db)
    if not runtime.get_entity_config(entity_code, direction="push"):
        raise ValueError("请先在质量飞书设置中启用并配置该检验实体的推送表")

    fields, search_conditions = _build_fields(resource_code, record)
    remote_record_id, table_id = await feishu_sync._upsert_record(
        db,
        entity_code,
        None,
        None,
        fields,
        search_conditions=[
            (field_name, _as_text(value))
            for field_name, value in search_conditions
        ],
    )
    return {
        "resource_code": resource_code,
        "entity_code": entity_code,
        "record_id": remote_record_id,
        "table_id": table_id,
        "synced_at": datetime.now(UTC),
    }
