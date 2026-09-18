"""质量检验-仪器管理 仪表盘聚合（读本地镜像，不实时打飞书）。

统计口径全部来自仪器镜像（service.inspection_instrument_mirror）：
- 设备概览：设备数据管理（设备状态/设备类型为飞书公式列，镜像内已是中文名）
- 校验到期：内校汇总 / 外部校准、检定 / 内部校验计划，30 天内到期与已过期。
  内部校验计划 2026-09 起表内新增「状态」公式列（未提醒/提醒中/已完成），
  提供了可靠完成标记，据此纳入到期提醒：已完成行不计（此前因无完成标记
  整表排除的口径作废）。
- 维保：设备维护保养记录未完成数 + 未完成且下次维保时间在 7 天内的
  临期数（已完成一律不计）+ QC检测仪器维护保养周期表条目数
- 合同：设备维保合同只统计总数。合同到期不提醒——历史合同必然过期、
  到期后换新合同，到期提醒无业务意义（2026-09 与用户确认口径）。

日期两种回读形态都兼容：普通 DateTime 列是毫秒时间戳（数字字符串），
公式日期列是 Excel 序列号（1899-12-30 起的天数，如 "46406"）。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service.inspection_instrument_mirror import (
    list_instrument_mirror,
)

logger = logging.getLogger(__name__)

# 到期提醒窗口（天）；负数=已过期
DUE_SOON_DAYS = 30
# 维保记录 7 天内临期窗口（仅未完成任务）
DUE_SOON_7D = 7
_PAGE_SIZE = 500

_EQUIPMENT = "qc_instr_equipment"
_MAINTENANCE = "qc_instr_maintenance"
_CYCLES = "qc_instr_plans"
_CONTRACTS = "qc_instr_contracts"
_CAL_INTERNAL_SUMMARY = "qc_instr_calibration"
_CAL_EXTERNAL = "qc_instr_cal_external"
_CAL_PLAN = "qc_instr_cal_plan"

# 内部校验计划「状态」公式列的完成标记（已完成行不进到期提醒）
_CAL_PLAN_DONE = "已完成"

_EXCEL_EPOCH = date(1899, 12, 30)
_TZ_SH = timezone(timedelta(hours=8))


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


def parse_feishu_date(value: Any) -> date | None:
    """镜像日期值 -> 本地日期；兼容毫秒时间戳与 Excel 序列号两种形态。"""
    numeric = _to_int(value)
    if numeric is None:
        return None
    if numeric > 1e11:  # 毫秒时间戳
        return datetime.fromtimestamp(numeric / 1000, tz=_TZ_SH).date()
    if 0 < numeric <= 400000:  # Excel 序列号
        return _EXCEL_EPOCH + timedelta(days=int(numeric))
    return None


def _days_until(target: date, today: date) -> int:
    return (target - today).days


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "")
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or item.get("text") or ""))
            elif item is not None:
                parts.append(str(item))
        return "、".join(part for part in parts if part)
    return str(value)


async def _load_page(db: AsyncSession, entity_code: str) -> dict[str, Any]:
    return await list_instrument_mirror(db, entity_code, page=1, page_size=_PAGE_SIZE)


def _calibration_item(
    source: str,
    row: dict[str, Any],
    *,
    name_key: str,
    code_key: str,
    date_key: str,
    days_key: str | None,
    today: date,
) -> dict[str, Any] | None:
    target = parse_feishu_date(row.get(date_key))
    if target is not None and target.year < 2000:
        # 脏数据：空校验时间时公式会算出 364/365 这类裸数字，被当作
        # 1900 年的序列号；无真实有效期的行直接跳过，不计入提醒
        return None
    days: int | None = None
    # 优先按有效期日期计算：飞书「剩余天数」公式常写成 MAX(0, 有效期-TODAY())，
    # 过期后钳在 0，会把长期过期项误归为临期
    if target is not None:
        days = _days_until(target, today)
    if days is None and days_key:
        raw_days = _to_int(row.get(days_key))
        if raw_days is not None:
            days = int(raw_days)
    if days is None:
        return None
    return {
        "source": source,
        "name": _cell_text(row.get(name_key)),
        "code": _cell_text(row.get(code_key)),
        "due_date": target.isoformat() if target else None,
        "days": days,
        "record_id": str(row.get("record_id") or ""),
    }


def _equipment_status_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """设备状态构成（按数量降序）；状态列为飞书公式列，镜像内已是中文名。"""
    counts: dict[str, int] = {}
    for row in rows:
        state = _cell_text(row.get("设备状态")) or "未填写"
        counts[state] = counts.get(state, 0) + 1
    return [
        {"name": name, "value": value}
        for name, value in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


def _calibration_upcoming_by_month(
    today: date,
    summary_rows: list[dict[str, Any]],
    external_rows: list[dict[str, Any]],
    months: int = 6,
) -> list[dict[str, Any]]:
    """未来 N 个月（含当月）校验数量分布：内校汇总 + 外部校准检定。

    只取真实有效期（1900 年序列号等公式脏数据跳过）。
    """
    counts = [0] * months
    for rows, date_key in (
        (summary_rows, "校验有效期"),
        (external_rows, "下次检定日期"),
    ):
        for row in rows:
            target = parse_feishu_date(row.get(date_key))
            if target is None or target.year < 2000:
                continue
            if target < today:
                # 已过期的不进未来分布（它们属于到期提醒的口径）
                continue
            offset = (target.year - today.year) * 12 + (target.month - today.month)
            if 0 <= offset < months:
                counts[offset] += 1
    result: list[dict[str, Any]] = []
    year, month = today.year, today.month
    for count in counts:
        result.append({"month": f"{year:04d}-{month:02d}", "count": count})
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result


def _maintenance_due_buckets(
    rows: list[dict[str, Any]], today: date
) -> list[dict[str, Any]]:
    """未完成维保任务的到期分布（已完成一律不计）。"""
    buckets = {"已过期": 0, "7 天内": 0, "8~30 天": 0, "31~90 天": 0, "90 天以上": 0}
    for row in rows:
        if _cell_text(row.get("是否完成")) != "否":
            continue
        due = parse_feishu_date(row.get("下次维保时间"))
        if due is None:
            continue
        days = _days_until(due, today)
        if days < 0:
            buckets["已过期"] += 1
        elif days <= 7:
            buckets["7 天内"] += 1
        elif days <= 30:
            buckets["8~30 天"] += 1
        elif days <= 90:
            buckets["31~90 天"] += 1
        else:
            buckets["90 天以上"] += 1
    return [{"name": name, "value": value} for name, value in buckets.items()]


async def get_instruments_dashboard(db: AsyncSession) -> dict[str, Any]:
    """聚合仪器管理仪表盘数据（读镜像；镜像未同步时 configured=False）。"""
    equipment_page = await _load_page(db, _EQUIPMENT)
    if not equipment_page.get("configured"):
        return {
            "configured": False,
            "equipment": {"total": 0, "ok": 0, "repairing": 0, "key_count": 0},
            "equipment_status": [],
            "calibration_due": [],
            "calibration_expired": [],
            "calibration_upcoming": [],
            "maintenance": {
                "total": 0,
                "unfinished": 0,
                "due_soon_7d": 0,
                "cycle_count": 0,
            },
            "maintenance_due_buckets": [],
            "contracts": {"total": 0},
            "last_sync_time": None,
        }

    today = datetime.now(tz=_TZ_SH).date()
    equipment_rows = equipment_page.get("items") or []

    total = len(equipment_rows)
    ok = sum(1 for row in equipment_rows if _cell_text(row.get("设备状态")) == "完好")
    repairing = sum(
        1 for row in equipment_rows if _cell_text(row.get("设备状态")) == "维修"
    )
    key_count = sum(
        1 for row in equipment_rows if _cell_text(row.get("设备类型")) == "重点设备"
    )

    calibration_due: list[dict[str, Any]] = []
    calibration_expired: list[dict[str, Any]] = []

    def _collect(items: list[dict[str, Any] | None]) -> None:
        for item in items:
            if item is None:
                continue
            if item["days"] < 0:
                calibration_expired.append(item)
            elif item["days"] <= DUE_SOON_DAYS:
                calibration_due.append(item)

    summary_page = await _load_page(db, _CAL_INTERNAL_SUMMARY)
    _collect(
        [
            _calibration_item(
                "内校汇总",
                row,
                name_key="仪器、设备名称",
                code_key="仪器、设备编号",
                date_key="校验有效期",
                days_key=None,
                today=today,
            )
            for row in summary_page.get("items") or []
        ]
    )

    external_page = await _load_page(db, _CAL_EXTERNAL)
    _collect(
        [
            _calibration_item(
                "外部校准、检定",
                row,
                name_key="器具名称",
                code_key="器具编号",
                date_key="下次检定日期",
                days_key=None,
                today=today,
            )
            for row in external_page.get("items") or []
        ]
    )

    # 内部校验计划：状态公式列（未提醒/提醒中/已完成）提供可靠完成标记，
    # 已完成行不计；计划校验时间为到期口径，剩余天数公式过期后钳 0 不可信
    cal_plan_page = await _load_page(db, _CAL_PLAN)
    _collect(
        [
            _calibration_item(
                "内校计划",
                row,
                name_key="仪器、设备名称",
                code_key="仪器、设备编号",
                date_key="计划校验时间",
                days_key="剩余天数",
                today=today,
            )
            for row in cal_plan_page.get("items") or []
            if _cell_text(row.get("状态")) != _CAL_PLAN_DONE
        ]
    )

    calibration_due.sort(key=lambda item: item["days"])
    calibration_expired.sort(key=lambda item: item["days"])

    maintenance_page = await _load_page(db, _MAINTENANCE)
    maintenance_rows = maintenance_page.get("items") or []
    unfinished = 0
    due_soon_7d = 0
    for row in maintenance_rows:
        # 已完成（是否完成=是）一律不统计
        if _cell_text(row.get("是否完成")) != "否":
            continue
        unfinished += 1
        due = parse_feishu_date(row.get("下次维保时间"))
        if due is None:
            continue
        if 0 <= _days_until(due, today) <= DUE_SOON_7D:
            due_soon_7d += 1
    cycles_page = await _load_page(db, _CYCLES)

    contracts_page = await _load_page(db, _CONTRACTS)

    # 合同：只统计总数（到期不提醒，历史合同必然过期、到期即换新）

    return {
        "configured": True,
        "equipment": {
            "total": total,
            "ok": ok,
            "repairing": repairing,
            "key_count": key_count,
        },
        "equipment_status": _equipment_status_distribution(equipment_rows),
        "calibration_due": calibration_due,
        "calibration_expired": calibration_expired,
        "calibration_upcoming": _calibration_upcoming_by_month(
            today,
            summary_page.get("items") or [],
            external_page.get("items") or [],
        ),
        "maintenance": {
            "total": len(maintenance_rows),
            "unfinished": unfinished,
            "due_soon_7d": due_soon_7d,
            "cycle_count": len(cycles_page.get("items") or []),
        },
        "maintenance_due_buckets": _maintenance_due_buckets(maintenance_rows, today),
        "contracts": {
            "total": len(contracts_page.get("items") or []),
        },
        "last_sync_time": equipment_page.get("last_sync_time"),
    }
