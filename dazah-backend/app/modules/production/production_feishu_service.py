"""Sync Feishu Bitable data to fermentation records."""

import logging
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.modules.production.fermentation_models import FermentationRecord
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

# 飞书字段名 → fermentation_records 字段名 映射
FIELD_MAP = {
    "批号": "batch_no",
    "产品名称": "product_name",
    "发酵罐": "fermenter",
    "进罐日期": "entry_date",
    "放罐日期": "discharge_date",
    "周期1": "cycle_1",
    "周期2": "cycle_2",
    "周期3": "cycle_3",
    "周期4": "cycle_4",
    "周期5": "cycle_5",
    "周期6": "cycle_6",
    "罐产": "tank_yield",
    "状态": "status",
    "备注": "remarks",
}


def _extract_text(field_value: list | dict | str | None) -> str | None:
    """Extract plain text from a Feishu field value."""
    if field_value is None:
        return None
    if isinstance(field_value, str):
        return field_value.strip() or None
    if isinstance(field_value, dict):
        return str(field_value.get("name") or field_value.get("text", "")).strip() or None
    if isinstance(field_value, list) and field_value:
        first = field_value[0]
        if isinstance(first, str):
            return first.strip() or None
        if isinstance(first, dict):
            return str(first.get("name") or first.get("text", "")).strip() or None
    return None


def _extract_number(field_value: list | dict | str | None) -> float | None:
    """Extract a number from a Feishu field value."""
    text = _extract_text(field_value)
    if text is None:
        return None
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


STATUS_MAP = {
    "发酵中": "in_progress",
    "已完成": "completed",
    "异常": "abnormal",
}


async def sync_config(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    """从飞书同步一个配置对应产品的发酵记录"""
    app_secret = decrypt_secret(config.encrypted_app_secret)
    client = ProductionFeishuClient(
        app_id=config.app_id,
        app_secret=app_secret,
        app_token=config.bitable_app_token,
    )

    created = 0
    updated = 0
    page_token: str | None = None

    while True:
        result = await client.list_records(config.table_id, page_token=page_token)
        items = result["items"]
        for item in items:
            fields = item.get("fields") or {}
            record_id = item.get("record_id", "")

            # 映射字段
            mapped = {}
            for feishu_name, db_name in FIELD_MAP.items():
                val = fields.get(feishu_name)
                if db_name in ("entry_date", "discharge_date"):
                    text = _extract_text(val)
                    mapped[db_name] = date.fromisoformat(text) if text else None
                elif db_name in ("cycle_1", "cycle_2", "cycle_3", "cycle_4", "cycle_5", "cycle_6", "tank_yield"):
                    mapped[db_name] = _extract_number(val)
                elif db_name == "status":
                    text = _extract_text(val)
                    mapped[db_name] = STATUS_MAP.get(text or "", "in_progress")
                else:
                    mapped[db_name] = _extract_text(val)

            # 必须字段检查
            if not mapped.get("batch_no") or not mapped.get("fermenter"):
                continue

            # 查重：按 批号+产品名称 判断
            batch_no = mapped["batch_no"]
            product_name = mapped.get("product_name") or config.product_name

            from sqlalchemy import select
            existing = await session.execute(
                select(FermentationRecord).where(
                    FermentationRecord.batch_no == batch_no,
                    FermentationRecord.product_name == product_name,
                    FermentationRecord.is_deleted == False,
                )
            )
            record = existing.scalar_one_or_none()

            mapped["product_name"] = product_name
            if not mapped.get("entry_date"):
                mapped["entry_date"] = date.today()

            if record:
                # 更新
                for key, value in mapped.items():
                    if value is not None:
                        setattr(record, key, value)
                updated += 1
            else:
                record = FermentationRecord(**mapped)
                session.add(record)
                created += 1

        await session.flush()

        if not result["has_more"]:
            break
        page_token = result.get("page_token")

    return {"created": created, "updated": updated, "product": config.product_name}


async def sync_all_active(session: AsyncSession) -> list[dict]:
    """同步所有启用的飞书配置"""
    from sqlalchemy import select

    result = await session.execute(
        select(ProductionFeishuConfig).where(ProductionFeishuConfig.is_active == True)
    )
    configs = list(result.scalars().all())
    summaries = []
    for config in configs:
        try:
            summary = await sync_config(config, session)
            summaries.append(summary)
        except Exception as e:
            logger.error("同步失败 [%s]: %s", config.product_name, e)
            summaries.append({"product": config.product_name, "error": str(e)})
    await session.commit()
    return summaries
