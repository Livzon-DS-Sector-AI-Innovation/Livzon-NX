"""Explicit Feishu push actions for platform-owned OOS/OOT data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service import oos_oot as oos_oot_service
from app.modules.quality.service.quality_feishu_sync import feishu_sync


def _as_text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


async def sync_oos_oot_record_to_feishu(
    db: AsyncSession, *, record_id: Any
) -> dict[str, str | datetime]:
    record = await oos_oot_service.get_oos_oot_record(db, record_id)
    entity_code = "oos_ledger" if record.record_type == "OOS" else "oot_ledger"
    runtime = await feishu_sync._resolve_runtime(db)
    if not runtime.get_entity_config(entity_code, direction="push"):
        raise ValueError("请先在质量飞书设置中启用并配置该 OOS/OOT 台账的推送表")

    # 目标台账表的实际列：序号/日期/物料名称/批号/调查编号/问题描述/产生原因/
    # 纠正预防措施/最终处理结果/登记人/备注。旧实现按本地记录字段名直写，
    # 未匹配的列会被 _upsert_record 静默丢弃，导致台账行几乎为空。
    description = _as_text(record.description) or _as_text(record.title)
    fields = {
        "调查编号": _as_text(record.record_code),
        "物料名称": _as_text(record.product_name),
        "批号": _as_text(record.batch_number),
        "日期": record.discovery_date.isoformat() if record.discovery_date else "",
        "问题描述": description,
        "纠正预防措施": _as_text(record.corrective_actions),
    }
    remote_record_id, table_id = await feishu_sync._upsert_record(
        db,
        entity_code,
        None,
        None,
        fields,
        search_conditions=[("调查编号", _as_text(record.record_code))],
    )
    return {
        "resource_code": "oos_oot_records",
        "entity_code": entity_code,
        "record_id": remote_record_id,
        "table_id": table_id,
        "synced_at": datetime.now(UTC),
    }


async def sync_oot_limit_product_to_feishu(
    db: AsyncSession, *, product_id: Any
) -> dict[str, str | datetime]:
    product = await oos_oot_service.get_oot_limit_product(db, product_id)
    entity_code = "oot_limit_product"
    runtime = await feishu_sync._resolve_runtime(db)
    if not runtime.get_entity_config(entity_code, direction="push"):
        raise ValueError("请先在质量飞书设置中启用并配置 OOT 限度产品表")
    fields = {
        "产品编码": product.product_code,
        "产品名称": product.product_name,
        "标准文件编号": product.document_no or "",
        "标准文件版本": product.document_version or "",
        "是否启用": "是" if product.is_active else "否",
        "备注": product.remark or "",
    }
    remote_record_id, table_id = await feishu_sync._upsert_record(
        db,
        entity_code,
        None,
        None,
        fields,
        search_conditions=[("产品编码", _as_text(product.product_code))],
    )
    return {
        "resource_code": "oot_limit_products",
        "entity_code": entity_code,
        "record_id": remote_record_id,
        "table_id": table_id,
        "synced_at": datetime.now(UTC),
    }


async def sync_oot_limit_item_to_feishu(
    db: AsyncSession, *, item_id: Any
) -> dict[str, str | datetime]:
    from app.modules.quality.repository import oos_oot as repository

    item = await repository.get_oot_limit_item(db, item_id)
    if item is None:
        from app.core.exceptions import NotFoundException

        raise NotFoundException("OOT限度项目", str(item_id))
    product = await oos_oot_service.get_oot_limit_product(db, item.product_id)
    entity_code = "oot_limit_item"
    runtime = await feishu_sync._resolve_runtime(db)
    if not runtime.get_entity_config(entity_code, direction="push"):
        raise ValueError("请先在质量飞书设置中启用并配置 OOT 限度项目表")
    fields = {
        "产品编码": product.product_code,
        "显示顺序": item.display_order,
        "项目分组": item.item_group or "",
        "项目名称": item.item_name,
        "标准规定": item.specification or "",
        "OOT限度": item.oot_limit,
        "备注": item.remark or "",
    }
    remote_record_id, table_id = await feishu_sync._upsert_record(
        db,
        entity_code,
        None,
        None,
        fields,
        search_conditions=[
            ("产品编码", _as_text(product.product_code)),
            ("显示顺序", _as_text(item.display_order)),
        ],
    )
    return {
        "resource_code": "oot_limit_items",
        "entity_code": entity_code,
        "record_id": remote_record_id,
        "table_id": table_id,
        "synced_at": datetime.now(UTC),
    }
