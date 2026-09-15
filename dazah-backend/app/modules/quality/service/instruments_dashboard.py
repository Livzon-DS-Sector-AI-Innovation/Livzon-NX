"""质量检验-仪器管理 仪表盘聚合（读本地镜像，不实时打飞书）。

统计口径全部来自仪器镜像（service.inspection_instrument_mirror）：
- 设备概览：设备数据管理（设备状态/设备类型为飞书公式列，镜像内已是中文名）
- 校验到期：内校汇总 / 内部校验计划 / 外部校准、检定，30 天内到期与已过期
- 维保：设备维护保养记录未完成数 + QC检测仪器维护保养周期表条目数
- 合同：设备维保合同总数与 30 天内到期/已过期

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
_PAGE_SIZE = 500

_EQUIPMENT = "qc_instr_equipment"
_MAINTENANCE = "qc_instr_maintenance"
_CYCLES = "qc_instr_plans"
_CONTRACTS = "qc_instr_contracts"
_CAL_INTERNAL_SUMMARY = "qc_instr_calibration"
_CAL_INTERNAL_PLAN = "qc_instr_cal_plan"
_CAL_EXTERNAL = "qc_instr_cal_external"

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


def _contract_item(row: dict[str, Any], today: date) -> dict[str, Any] | None:
    target = parse_feishu_date(row.get("有效期"))
    if target is None or target.year < 2000:
        return None  # 无有效期的合同无法提醒；裸数字/负序列视为脏数据
    days = _days_until(target, today)
    if abs(days) > 3650:
        # 超过 10 年的偏差视为异常数据
        return None
    return {
        "name": _cell_text(row.get("设备维保合同")),
        "due_date": target.isoformat() if target else None,
        "days": days,
        "record_id": str(row.get("record_id") or ""),
    }


async def get_instruments_dashboard(db: AsyncSession) -> dict[str, Any]:
    """聚合仪器管理仪表盘数据（读镜像；镜像未同步时 configured=False）。"""
    equipment_page = await _load_page(db, _EQUIPMENT)
    if not equipment_page.get("configured"):
        return {
            "configured": False,
            "equipment": {"total": 0, "ok": 0, "repairing": 0, "key_count": 0},
            "calibration_due": [],
            "calibration_expired": [],
            "maintenance": {"total": 0, "unfinished": 0, "cycle_count": 0},
            "contracts": {"total": 0, "expiring": []},
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

    plan_page = await _load_page(db, _CAL_INTERNAL_PLAN)
    _collect(
        [
            _calibration_item(
                "内部校验计划",
                row,
                name_key="仪器、设备名称",
                code_key="仪器、设备编号",
                date_key="校验有效期",
                days_key="剩余天数",
                today=today,
            )
            for row in plan_page.get("items") or []
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

    calibration_due.sort(key=lambda item: item["days"])
    calibration_expired.sort(key=lambda item: item["days"])

    maintenance_page = await _load_page(db, _MAINTENANCE)
    maintenance_rows = maintenance_page.get("items") or []
    unfinished = sum(
        1 for row in maintenance_rows if _cell_text(row.get("是否完成")) == "否"
    )
    cycles_page = await _load_page(db, _CYCLES)

    contracts_page = await _load_page(db, _CONTRACTS)
    contract_rows = contracts_page.get("items") or []
    expiring = []
    for row in contract_rows:
        item = _contract_item(row, today)
        if item is not None and item["days"] <= DUE_SOON_DAYS:
            expiring.append(item)
    expiring.sort(key=lambda item: item["days"])

    return {
        "configured": True,
        "equipment": {
            "total": total,
            "ok": ok,
            "repairing": repairing,
            "key_count": key_count,
        },
        "calibration_due": calibration_due,
        "calibration_expired": calibration_expired,
        "maintenance": {
            "total": len(maintenance_rows),
            "unfinished": unfinished,
            "cycle_count": len(cycles_page.get("items") or []),
        },
        "contracts": {"total": len(contract_rows), "expiring": expiring},
        "last_sync_time": equipment_page.get("last_sync_time"),
    }
