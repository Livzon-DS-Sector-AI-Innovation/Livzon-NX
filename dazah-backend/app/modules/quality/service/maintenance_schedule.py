"""维护保养记录「下次维保时间」自动计算与回写。

飞书侧该列已由死公式改为可填写的日期列。以本地镜像的
QC检测仪器维护保养周期表为准：按「仪器编号」（一格多编号顿号分隔）找到
对应维护周期（月），以完成日期（未完成用生成日期）为基准加 N 个月得到
下次维保时间：
- 页面/档案展示：只填充空值，不覆盖飞书侧已填写的日期；
- 同步回写（backfill）：镜像同步时把算出的日期写回飞书空值行，
  手动填过的不动；回写失败仅记日志，不影响同步。
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service.instruments_dashboard import (
    _cell_text,
    _load_page,
    parse_feishu_date,
)

_TZ_SH = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)


def _to_int(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def add_months(base: date, months: int) -> date:
    """基准日期加 N 个月（日值超过目标月天数时取月末）。"""
    month_index = base.year * 12 + (base.month - 1) + months
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _today() -> date:
    return datetime.now(tz=_TZ_SH).date()


def _parse_row_date(row: dict[str, Any], *keys: str) -> date | None:
    for key in keys:
        parsed = parse_feishu_date(row.get(key))
        if parsed is not None and parsed.year >= 2000:
            return parsed
    return None


async def _load_cycle_index(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """周期表按编号分词建索引：编号 -> {months, category, cycle_text}。"""
    page = await _load_page(db, "qc_instr_plans")
    index: dict[str, dict[str, Any]] = {}
    for row in page.get("items") or []:
        months = _to_int(row.get("周期（月）"))
        if months is None or months <= 0:
            continue
        info = {
            "months": int(months),
            "category": _cell_text(row.get("仪器类别")),
            "cycle_text": _cell_text(row.get("维护周期")),
        }
        raw_codes = _cell_text(row.get("仪器编号"))
        tokens = {
            token.strip()
            for token in raw_codes.replace("、", ",").split(",")
            if token.strip()
        }
        for token in tokens:
            index.setdefault(token, info)
    return index


async def enrich_maintenance_schedule(
    db: AsyncSession, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """就地填充维护保养记录行的「下次维保时间」（已有值不覆盖）。"""
    cycle_index = await _load_cycle_index(db)
    if not cycle_index:
        return items
    today = _today()
    for item in items:
        if _cell_text(item.get("下次维保时间")):
            continue
        code = _cell_text(item.get("仪器编号")).strip()
        info = cycle_index.get(code)
        if info is None:
            # 一格多编号的维护保养记录：任一编号命中周期表即可
            info = next(
                (
                    entry
                    for token in code.replace("、", ",").split(",")
                    if (entry := cycle_index.get(token.strip()))
                ),
                None,
            )
        if info is None:
            continue
        base = _parse_row_date(item, "完成日期", "生成日期")
        if base is None:
            continue
        next_due = add_months(base, info["months"])
        item["下次维保时间"] = next_due.isoformat()
        # 剩余天数（提前1周通知）在飞书侧同为死公式，一并补齐
        if not _cell_text(item.get("剩余天数（提前1周通知）")):
            item["剩余天数（提前1周通知）"] = str((next_due - today).days)
    return items


def _next_due_ms(next_due: date) -> int:
    """日期 -> 飞书 DateTime 字段的毫秒时间戳（东八区当天零点）。"""
    stamp = datetime(next_due.year, next_due.month, next_due.day, tzinfo=_TZ_SH)
    return int(stamp.timestamp() * 1000)


async def backfill_next_maintenance_dates(
    db: AsyncSession,
    client: Any,
    table_id: str,
    records: list[dict[str, Any]],
) -> int:
    """把算出的「下次维保时间」回写飞书（仅空值），返回回写条数。

    在维护保养镜像同步时调用：records 为本次拉取的飞书记录（原始 dict，
    fields 为飞书原始值）。回写成功后同步更新本地 fields，使镜像与飞书一致；
    单条失败仅记日志，不中断其余回写。
    """
    cycle_index = await _load_cycle_index(db)
    if not cycle_index:
        return 0
    updated = 0
    for record in records:
        fields = record.get("fields") or {}
        if fields.get("下次维保时间") not in (None, ""):
            continue
        code = _cell_text(fields.get("仪器编号")).strip()
        info = cycle_index.get(code)
        if info is None:
            info = next(
                (
                    entry
                    for token in code.replace("、", ",").split(",")
                    if (entry := cycle_index.get(token.strip()))
                ),
                None,
            )
        if info is None:
            continue
        base = _parse_row_date(fields, "完成日期", "生成日期")
        if base is None:
            continue
        next_due = add_months(base, info["months"])
        record_id = str(record.get("record_id") or "")
        try:
            await client.update_record(
                table_id,
                record_id,
                {"下次维保时间": _next_due_ms(next_due)},
                user_id_type="open_id",
            )
        except Exception as exc:  # noqa: BLE001 - 单条回写失败不中断
            logger.warning(
                "下次维保时间回写失败 record=%s: %s", record_id, exc
            )
            continue
        fields["下次维保时间"] = _next_due_ms(next_due)
        updated += 1
    if updated:
        logger.info(
            "下次维保时间回写完成：共 %d 条（table=%s）", updated, table_id
        )
    return updated
