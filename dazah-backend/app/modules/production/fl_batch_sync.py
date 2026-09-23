"""氟苯尼考预混剂（FL）批次工序流转 — 飞书多维表按月分表同步。

数据源是一个多维表格 base（如「氟苯尼考预混剂2026年排产」），内含按月
分表（「2月排产」「9月排产」…）。同步时按表名规则自动发现全部月表并
逐表分页拉取；跨年新 base 通过多条配置并存同步。记录以生产批号
（FL-YYMM+月内流水）全局唯一 upsert，归组月份取批号 YYMM，表名月份
仅做串表校验；批号月份与表名不一致的记录跳过并在结果中上报，不静默
入库。列名存在月表间差异（如「请检日期/成品清检日期」），映射按候选
列表兼容。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.modules.production.fl_models import FlBatch
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))

# 月表名规则：如「9月排产」「10月排产」；解析不出月份的表跳过并提示
MONTH_TABLE_RE = re.compile(r"^(\d{1,2})月排产$")
# 生产批号：FL-2609001 = 2026年09月第1批（FL + YY + MM + 月内流水）
BATCH_NO_RE = re.compile(r"^FL[-－]?(\d{2})(\d{2})(\d{3,4})$")

# 飞书字段名 → 模型字段；候选列表兼容各月表列名差异
_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "batch_no": ("生产批号",),
    "order_date": ("指令日期",),
    "pick_date": ("领料日期",),
    "charge_date": ("投料日期",),
    "charge_time": ("投料时间",),
    "mix_date": ("混合日期｜生产日期", "混合日期", "生产日期"),
    "mix_time": ("混合时间",),
    "spec": ("规格",),
    "pack_weight_kg": ("包装重量", "包装重量(kg)", "包装重量（kg）"),
    "pack_date": ("包装日期",),
    "pack_time": ("包装时间",),
    "inspection_date": ("请检日期", "成品清检日期"),
    "inbound_date": ("入库日期", "成品入库"),
}
_DATE_FIELDS = frozenset(
    {
        "order_date",
        "pick_date",
        "charge_date",
        "mix_date",
        "pack_date",
        "inspection_date",
        "inbound_date",
    }
)


def _first_value(fields: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    for name in candidates:
        if name in fields and fields[name] is not None:
            return fields[name]
    return None


def _extract_text(value: Any) -> str | None:
    """飞书字段值 → 文本：单选/文本为 str 或 dict(text|name)，多选为列表。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, dict):
        text = value.get("text") or value.get("name") or value.get("en_name")
        return str(text).strip() if text else None
    if isinstance(value, list):
        parts = [
            p
            for p in (_extract_text(item) for item in value)
            if p
        ]
        return "、".join(parts) or None
    return None


def _extract_date(value: Any) -> date | None:
    """飞书日期字段值 → date：兼容毫秒时间戳与常见文本格式。

    毫秒时间戳按北京时间落日期（车间按北京时间记录）；文本支持
    2026-09-19 / 2026.09.19 / 2026/09/19 及带时间的完整格式。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000, tz=BEIJING_TZ).date()
        except (OverflowError, OSError, ValueError):
            return None
    text = _extract_text(value)
    if text is None:
        return None
    matched = re.match(r"^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if not matched:
        return None
    try:
        return date(
            int(matched[1]),
            int(matched[2]),
            int(matched[3]),
        )
    except ValueError:
        return None


def _extract_weight_kg(value: Any) -> float | None:
    """包装重量 → kg 数值；文本形如「1980±10」取名目前值，逗号千分位容忍。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _extract_text(value)
    if text is None:
        return None
    matched = re.match(r"^-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not matched:
        return None
    try:
        return float(matched.group())
    except ValueError:
        return None


def parse_batch_no(batch_no: str) -> tuple[int, int, int] | None:
    """解析生产批号 → (年份四位, 月份, 月内流水)；不合规返回 None。"""
    matched = BATCH_NO_RE.match(batch_no.strip().upper())
    if not matched:
        return None
    yy, mm, seq = (int(g) for g in matched.groups())
    if not 1 <= mm <= 12:
        return None
    return 2000 + yy, mm, seq


def map_record(fields: dict[str, Any]) -> dict[str, Any]:
    """一条飞书记录 → FlBatch 字段字典（不含批号，由调用方校验后写入）。"""
    mapped: dict[str, Any] = {}
    for db_name, candidates in _FIELD_CANDIDATES.items():
        if db_name == "batch_no":
            continue
        raw = _first_value(fields, candidates)
        if db_name in _DATE_FIELDS:
            mapped[db_name] = _extract_date(raw)
        elif db_name == "pack_weight_kg":
            mapped[db_name] = _extract_weight_kg(raw)
        else:
            mapped[db_name] = _extract_text(raw)
    return mapped


async def sync_fl_batches(
    config: ProductionFeishuConfig, session: AsyncSession
) -> dict[str, Any]:
    """同步一个 FL 多维表 base：自动发现月表并逐表 upsert 批次记录。"""
    client = ProductionFeishuClient(
        app_id=config.app_id,
        app_secret=decrypt_secret(config.encrypted_app_secret),
        app_token=config.bitable_app_token,
    )

    tables = await client.list_tables()
    month_tables: list[tuple[str, str, int]] = []
    skipped_tables: list[str] = []
    for table in tables:
        name = str(table.get("name") or "")
        matched = MONTH_TABLE_RE.match(name)
        if matched:
            month_tables.append(
                (str(table.get("table_id")), name, int(matched.group(1)))
            )
        else:
            skipped_tables.append(name)

    created = 0
    updated = 0
    skipped_empty = 0
    anomalies: list[dict[str, str]] = []

    for table_id, table_name, table_month in month_tables:
        page_token: str | None = None
        while True:
            result = await client.list_records(table_id, page_token=page_token)
            for item in result.get("items") or []:
                fields = item.get("fields") or {}
                raw_batch_no = _extract_text(
                    _first_value(fields, _FIELD_CANDIDATES["batch_no"])
                )
                batch_no = (raw_batch_no or "").upper().replace("－", "-")
                if not batch_no:
                    skipped_empty += 1
                    continue
                parsed = parse_batch_no(batch_no)
                if parsed is None:
                    anomalies.append(
                        {"batch_no": batch_no, "reason": "批号不符合 FL-YYMM流水 规则"}
                    )
                    continue
                year, month, _seq = parsed
                if month != table_month:
                    # 串表防护：批号月份与来源表月份不一致，不入库仅上报
                    anomalies.append(
                        {
                            "batch_no": batch_no,
                            "reason": (
                                f"批号月份 {year:04d}-{month:02d}"
                                f" 与来源表「{table_name}」不一致"
                            ),
                        }
                    )
                    continue

                mapped = map_record(fields)
                existing = (
                    await session.execute(
                        select(FlBatch).where(
                            FlBatch.batch_no == batch_no,
                            FlBatch.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        FlBatch(
                            batch_no=batch_no,
                            source_table=table_name,
                            data_month=f"{year:04d}-{month:02d}",
                            sync_note=None,
                            **mapped,
                        )
                    )
                    created += 1
                else:
                    # 飞书为事实源：非空字段覆盖，空字段保留历史值
                    for key, value in mapped.items():
                        if value is not None:
                            setattr(existing, key, value)
                    existing.source_table = table_name
                    existing.data_month = f"{year:04d}-{month:02d}"
                    existing.sync_note = None
                    updated += 1

            await session.flush()
            if not result.get("has_more"):
                break
            page_token = result.get("page_token")

    logger.info(
        "FL 批次同步完成: tables=%s created=%s updated=%s "
        "skipped_empty=%s anomalies=%s",
        [name for _, name, _ in month_tables],
        created,
        updated,
        skipped_empty,
        len(anomalies),
    )
    return {
        "created": created,
        "updated": updated,
        "skipped_empty": skipped_empty,
        "tables": [name for _, name, _ in month_tables],
        "skipped_tables": skipped_tables,
        "anomalies": anomalies[:20],
        "anomaly_count": len(anomalies),
        "product": config.product_name,
    }
