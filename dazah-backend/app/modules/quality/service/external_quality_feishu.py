"""Explicit Feishu push actions for platform-owned external quality records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service import external_quality as external_quality_service
from app.modules.quality.service.quality_feishu_sync import feishu_sync

_RESOURCE_ENTITY_CODES = {
    "suppliers": "supplier_ledger",
    "supplier_qualifications": "supplier_qualification",
    "complaints": "complaint_ledger",
    "return_recalls": "return_recall_ledger",
    "product_quality_records": "product_quality_ledger",
    "product_quality_standard_items": "product_quality_standard_item",
}


def _as_text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


async def _get_record(db: AsyncSession, resource_code: str, record_id: Any) -> Any:
    if resource_code in {
        "suppliers",
        "complaints",
        "return_recalls",
        "product_quality_records",
    }:
        return await external_quality_service.get_resource_record(
            db, resource_code, record_id
        )
    if resource_code == "supplier_qualifications":
        return await external_quality_service.get_supplier_qualification(db, record_id)
    if resource_code == "product_quality_standard_items":
        return await external_quality_service.get_product_quality_standard_item(
            db, record_id
        )
    raise ValueError("不支持的外部质量飞书同步资源")


async def _build_fields(
    db: AsyncSession, resource_code: str, record: Any
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    if resource_code == "suppliers":
        return (
            {
                "供应商编号": record.supplier_code,
                "供应商名称": record.name,
                "供应商类别": record.category or "",
                "联系人": record.contact_person or "",
                "联系电话": record.contact_phone or "",
                "地址": record.address or "",
                "资质状态": record.qualification_status,
                "最近审计日期": record.audit_date.isoformat()
                if record.audit_date
                else "",
                "审计结论": record.audit_result or "",
                "下次审计日期": record.next_audit_date.isoformat()
                if record.next_audit_date
                else "",
                "供应范围": record.scope_of_supply or "",
                "状态": record.status,
                "备注": record.remark or "",
            },
            [("供应商编号", record.supplier_code)],
        )
    if resource_code == "supplier_qualifications":
        supplier = await external_quality_service.get_resource_record(
            db, "suppliers", record.supplier_id
        )
        return (
            {
                "供应商编号": supplier.supplier_code,
                "供应商名称": supplier.name,
                "资质编号": record.qualification_code,
                "资质名称": record.qualification_name,
                "文件编号": record.document_no or "",
                "取得日期": record.obtained_date.isoformat()
                if record.obtained_date
                else "",
                "到期日期": record.expiry_date.isoformat()
                if record.expiry_date
                else "",
                "资质状态": record.status,
                "责任人": record.responsible_person or "",
                "备注": record.remark or "",
            },
            [("资质编号", record.qualification_code)],
        )
    if resource_code == "complaints":
        return (
            {
                "投诉编号": record.complaint_code,
                "投诉标题": record.title,
                "投诉来源": record.complaint_source or "",
                "客户名称": record.customer_name or "",
                "产品名称": record.product_name or "",
                "批号": record.batch_number or "",
                "投诉日期": record.complaint_date.isoformat()
                if record.complaint_date
                else "",
                "投诉类别": record.complaint_category or "",
                "投诉描述": record.description or "",
                "处理人": record.handler or "",
                "调查结论": record.investigation_result or "",
                "回复内容": record.response_content or "",
                "回复日期": record.response_date.isoformat()
                if record.response_date
                else "",
                "关联CAPA编号": record.capa_code or "",
                "状态": record.status,
                "关闭时间": record.closed_at.isoformat() if record.closed_at else "",
            },
            [("投诉编号", record.complaint_code)],
        )
    if resource_code == "return_recalls":
        return (
            {
                "记录编号": record.record_code,
                "记录类型": record.record_type,
                "标题": record.title,
                "产品名称": record.product_name or "",
                "批号": record.batch_number or "",
                "数量": _as_text(record.quantity),
                "单位": record.unit or "",
                "客户/退货方": record.customer_name or "",
                "退货/召回原因": record.reason or "",
                "发生日期": record.occurrence_date.isoformat()
                if record.occurrence_date
                else "",
                "处理人": record.handler or "",
                "评估日期": record.assessment_date.isoformat()
                if record.assessment_date
                else "",
                "处置方式": record.disposition or "",
                "完成日期": record.completion_date.isoformat()
                if record.completion_date
                else "",
                "状态": record.status,
            },
            [("记录编号", record.record_code)],
        )
    if resource_code == "product_quality_records":
        return (
            {
                "质量记录编号": record.record_code,
                "记录类型": record.record_type,
                "标题": record.title,
                "产品名称": record.product_name,
                "客户名称": record.customer_name or "",
                "标准文件编号": record.document_no or "",
                "标准文件版本": record.document_version or "",
                "质量趋势": record.quality_trend or "",
                "质量标准": record.quality_standard or "",
                "特殊要求": record.special_requirements or "",
                "包装要求": record.packaging_requirements or "",
                "标签要求": record.label_requirements or "",
                "打托要求": record.pallet_requirements or "",
                "目标市场": record.target_market or "",
                "注册情况": record.registration_status or "",
                "评审结论": record.conclusion or "",
                "改进建议": record.suggestions or "",
                "评审人": record.reviewer or "",
                "评审日期": record.review_date.isoformat()
                if record.review_date
                else "",
                "状态": record.status,
                "批准时间": record.approved_at.isoformat()
                if record.approved_at
                else "",
            },
            [("质量记录编号", record.record_code)],
        )
    standard = await external_quality_service.get_resource_record(
        db, "product_quality_records", record.product_quality_id
    )
    return (
        {
            "质量记录编号": standard.record_code,
            "显示顺序": record.display_order,
            "要求分类": record.category or "",
            "要求项目": record.item_name,
            "要求内容": record.requirement,
            "是否关键要求": "是" if record.is_critical else "否",
            "备注": record.remark or "",
        },
        [
            ("质量记录编号", standard.record_code),
            ("显示顺序", _as_text(record.display_order)),
        ],
    )


async def sync_external_quality_record_to_feishu(
    db: AsyncSession, *, resource_code: str, record_id: Any
) -> dict[str, str | datetime]:
    entity_code = _RESOURCE_ENTITY_CODES.get(resource_code)
    if entity_code is None:
        raise ValueError("不支持的外部质量飞书同步资源")
    record = await _get_record(db, resource_code, record_id)
    runtime = await feishu_sync._resolve_runtime(db)
    if not runtime.get_entity_config(entity_code, direction="push"):
        raise ValueError("请先在质量飞书设置中启用并配置该外部质量实体的推送表")
    fields, search_conditions = await _build_fields(db, resource_code, record)
    remote_record_id, table_id = await feishu_sync._upsert_record(
        db,
        entity_code,
        None,
        None,
        fields,
        search_conditions=[
            (field_name, _as_text(value)) for field_name, value in search_conditions
        ],
    )
    return {
        "resource_code": resource_code,
        "entity_code": entity_code,
        "record_id": remote_record_id,
        "table_id": table_id,
        "synced_at": datetime.now(UTC),
    }
