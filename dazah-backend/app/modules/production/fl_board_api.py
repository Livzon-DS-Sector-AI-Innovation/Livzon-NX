"""氟苯尼考预混剂（FL）生产看板 API — 批次工序流转口径（入库确认为准）。

数据来源：production.fl_batches（飞书多维表按月分表同步，**计划**口径，
日期为预填计划值）+ 仓储「入库台账（明细）」（**实际**入库，批次级，
「入库确认」勾选才算入库）+ 产销计划（计划产量）。FL 为合成预混工艺、
无发酵工段。

核心规则：
- 归组与展示按所选月（批号 YYMM），月份筛选器是唯一视图主轴；
- 批次状态（以锚点时刻判定；当前月=现在，历史月=月末）：
  待投料（未到投料开始时刻）/ 在制（已投料未到计划入库日且无台账登记）/
  待入库确认（台账有登记未勾确认）/ 滞留（已过计划入库日且无登记）/
  已入库（台账已确认，以实际入库日期为准）；
- 工序流转实时状态为锚点前后各 2 天的滚动窗口：中间态（在制/待确认/
  滞留）常驻，已入库保留 2 天后移出，未来 2 天内待投料的预告进入；
- 入库 KPI 只计已确认行（扎帐月 27～26 口径）；产量数值挂提炼权限。
"""

from __future__ import annotations

import calendar
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.production.fermentation_board_api import (
    _stage_permissions,
)
from app.modules.production.fermentation_board_service import (
    WAREHOUSE_INBOUND_PRODUCT_NAMES,
    _extract_planned_yield_kg,
)
from app.modules.production.fl_models import FlBatch
from app.modules.production.models import ProductionPlan
from app.platform.identity.deps import CurrentUser
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)

router = create_module_router(MODULES_BY_CODE["production"])

BEIJING_TZ = timezone(timedelta(hours=8))

FL_PRODUCT_NAME = WAREHOUSE_INBOUND_PRODUCT_NAMES["FL"]

# 工序节点（顺序即流转顺序）；当前工序按计划时间推导
_STAGE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("order", "order_date", "指令"),
    ("pick", "pick_date", "领料"),
    ("charge", "charge_date", "投料"),
    ("mix", "mix_date", "混合"),
    ("pack", "pack_date", "包装"),
    ("inspection", "inspection_date", "请检"),
    ("inbound", "inbound_date", "入库"),
)

# 批次状态（入库确认为准）
STATE_UPCOMING = "upcoming"
STATE_RUNNING = "running"
STATE_CONFIRM_PENDING = "confirm_pending"
STATE_STALLED = "stalled"
STATE_INBOUND = "inbound"
STATE_LABELS: dict[str, str] = {
    STATE_UPCOMING: "待投料",
    STATE_RUNNING: "在制",
    STATE_CONFIRM_PENDING: "待入库确认",
    STATE_STALLED: "滞留",
    STATE_INBOUND: "已入库",
}
# 在制口径的三态（已投料开始且未确认入库）
ACTIVE_STATES = frozenset({STATE_RUNNING, STATE_CONFIRM_PENDING, STATE_STALLED})

# 工序流转滚动窗口：锚点前后各 2 天
FLOW_WINDOW_DAYS = 2

# 最近完成批次展示条数
RECENT_COMPLETED_SIZE = 10

_CHARGE_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _settlement_period(year: int, month: int) -> tuple[date, date, str]:
    """所选月对应的扎帐月：上月 27 日～本月 26 日（与全厂扎帐口径一致）。"""
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    start = date(prev_year, prev_month, 27)
    end = date(year, month, 26)
    label = f"{prev_month}月27日～{month}月26日"
    return start, end, label


def _time_start(text: str | None) -> time | None:
    """文本时间区间（如 8:00~10:00）的起点。"""
    if not text:
        return None
    matched = _CHARGE_TIME_RE.search(text)
    if not matched:
        return None
    return time(min(int(matched.group(1)), 23), min(int(matched.group(2)), 59))


def _charge_start(item: FlBatch) -> datetime | None:
    """投料开始时刻 = 投料日期 + 投料时间区间起点（无时间按当日零点）。"""
    if item.charge_date is None:
        return None
    start = _time_start(item.charge_time) or time.min
    return datetime.combine(item.charge_date, start)


def _node_datetime(item: FlBatch, stage_key: str) -> datetime | None:
    """工序节点的计划时刻：有时间区间用起点；纯日期节点按当日末刻
    （同日多工序时保持 时序：投料→混合→包装→请检→入库 不乱序）。"""
    date_attr = {
        "order": "order_date",
        "pick": "pick_date",
        "charge": "charge_date",
        "mix": "mix_date",
        "pack": "pack_date",
        "inspection": "inspection_date",
        "inbound": "inbound_date",
    }[stage_key]
    node_date = getattr(item, date_attr)
    if node_date is None:
        return None
    if stage_key == "charge":
        return _charge_start(item)
    if stage_key in ("mix", "pack"):
        start = _time_start(getattr(item, f"{stage_key}_time")) or time(23, 59)
        return datetime.combine(node_date, start)
    return datetime.combine(node_date, time(23, 59))


def _batch_seq(item: FlBatch) -> int | None:
    """月内流水序号（批号尾部）。"""
    digits = item.batch_no.upper().replace("－", "-").split("-")[-1]
    tail = digits[4:]
    return int(tail) if tail.isdigit() else None


def _current_stage(item: FlBatch, anchor: datetime) -> tuple[str, str]:
    """按计划时间推导当前工序：最后一个已到期的计划节点。"""
    key, label = _STAGE_FIELDS[0][0], _STAGE_FIELDS[0][2]
    for stage_key, _field, stage_label in _STAGE_FIELDS:
        node_at = _node_datetime(item, stage_key)
        if node_at is not None and node_at <= anchor:
            key, label = stage_key, stage_label
    return key, label


async def _warehouse_rows(db: AsyncSession) -> list[dict[str, Any]] | None:
    """仓储「入库台账（明细）」批次行（全量）；快照未建/异常降级 None。"""
    from app.modules.warehouse.public_api import get_finished_inbound_batches

    try:
        return await get_finished_inbound_batches(db, product_name=FL_PRODUCT_NAME)
    except Exception:  # noqa: BLE001 —— 看板降级，仓储故障不阻断看板
        logger.exception(
            "warehouse finished inbound batches failed",
            extra={"product": FL_PRODUCT_NAME},
        )
        return None


def _batch_state(
    item: FlBatch,
    batch_inbound: dict[str, Any] | None,
    anchor: datetime,
) -> tuple[str, date | None]:
    """(状态, 实际入库日期)：入库确认勾选才算已入库。"""
    if batch_inbound and batch_inbound["confirmed"]:
        return STATE_INBOUND, batch_inbound["inbound_date"]
    if batch_inbound:
        # 已登记未确认：无论计划日期如何，都是待仓库确认
        return STATE_CONFIRM_PENDING, None
    charge_start = _charge_start(item)
    if charge_start is None or anchor < charge_start:
        return STATE_UPCOMING, None
    # 已投料：计划入库日（次日零点）前为在制，过期无登记为滞留
    if item.inbound_date is not None:
        inbound_end = datetime.combine(
            item.inbound_date + timedelta(days=1), time.min
        )
        if anchor < inbound_end:
            return STATE_RUNNING, None
    return STATE_STALLED, None


def _build_batch_index(
    rows: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """行级数据归并为批次索引：确认位/最新已确认入库日/已确认数量合计。"""
    index: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        batch_no = row["batch_no"]
        entry = index.setdefault(
            batch_no,
            {
                "confirmed": False,
                "inbound_date": None,
                "kg": 0.0,
                "registered": False,
            },
        )
        entry["registered"] = True
        if row["confirmed"]:
            entry["confirmed"] = True
            inbound = row["inbound_date"]
            if inbound is not None and (
                entry["inbound_date"] is None or inbound > entry["inbound_date"]
            ):
                entry["inbound_date"] = inbound
            entry["kg"] += row["qty"] or 0.0
    return index


def _serialize_batch(
    item: FlBatch,
    *,
    anchor: datetime,
    state: str,
    actual_inbound: date | None,
    include_weight: bool,
) -> dict[str, Any]:
    stage_key, stage_label = _current_stage(item, anchor)
    data: dict[str, Any] = {
        "batch_no": item.batch_no,
        "seq": _batch_seq(item),
        "order_date": item.order_date.isoformat() if item.order_date else None,
        "pick_date": item.pick_date.isoformat() if item.pick_date else None,
        "charge_date": item.charge_date.isoformat() if item.charge_date else None,
        "charge_time": item.charge_time,
        "mix_date": item.mix_date.isoformat() if item.mix_date else None,
        "mix_time": item.mix_time,
        "spec": item.spec,
        "pack_date": item.pack_date.isoformat() if item.pack_date else None,
        "pack_time": item.pack_time,
        "inspection_date": (
            item.inspection_date.isoformat() if item.inspection_date else None
        ),
        "planned_inbound_date": (
            item.inbound_date.isoformat() if item.inbound_date else None
        ),
        "actual_inbound_date": (
            actual_inbound.isoformat() if actual_inbound else None
        ),
        "stage_key": stage_key,
        "stage_label": stage_label,
        "state": state,
        "state_label": STATE_LABELS[state],
        "source_table": item.source_table,
    }
    if include_weight:
        data["pack_weight_kg"] = item.pack_weight_kg
    if state in ACTIVE_STATES:
        charge_start = _charge_start(item)
        data["elapsed_days"] = (
            (anchor - charge_start).days if charge_start is not None else None
        )
    return data


@router.get("/fl-board", summary="氟苯尼考预混剂生产看板（批次工序流转）")
async def get_fl_board(
    month: str | None = Query(
        None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="查看月份 YYYY-MM；缺省为当月（北京时间）",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    now = datetime.now(BEIJING_TZ).replace(tzinfo=None)
    month_str = month or now.strftime("%Y-%m")
    year, month_no = (int(part) for part in month_str.split("-"))

    # 状态判定锚点：当前月=现在；历史月=该月最后一天（月末收尾视角）
    is_current_month = month_str == now.strftime("%Y-%m")
    if is_current_month:
        anchor = now
    else:
        anchor = datetime(
            year,
            month_no,
            calendar.monthrange(year, month_no)[1],
            23,
            59,
            59,
        )

    # FL 无发酵工段：产量类数值挂提炼（生产）权限
    _, has_extract = await _stage_permissions(db, current_user)

    batch_prefix = f"FL-{year % 100:02d}{month_no:02d}"
    month_rows = (
        (
            await db.execute(
                select(FlBatch).where(
                    FlBatch.is_deleted.is_(False),
                    FlBatch.batch_no.like(f"{batch_prefix}%"),
                )
            )
        )
        .scalars()
        .all()
    )

    # 仓储实际入库（批次级，全量取回后按月/状态使用）
    warehouse_index = _build_batch_index(await _warehouse_rows(db))

    # 各批次状态
    states: dict[str, tuple[str, date | None]] = {
        row.batch_no: _batch_state(row, warehouse_index.get(row.batch_no), anchor)
        for row in month_rows
    }
    inbound_rows = [r for r in month_rows if states[r.batch_no][0] == STATE_INBOUND]
    active_rows = [r for r in month_rows if states[r.batch_no][0] in ACTIVE_STATES]
    upcoming_rows = [r for r in month_rows if states[r.batch_no][0] == STATE_UPCOMING]

    # 计划产量：产销计划提炼车间行（自然月，与既有提炼计划卡同口径）
    month_start = date(year, month_no, 1)
    month_end = date(year, month_no, calendar.monthrange(year, month_no)[1])
    plan_rows = (
        (
            await db.execute(
                select(ProductionPlan).where(
                    ProductionPlan.plan_date >= month_start,
                    ProductionPlan.plan_date <= month_end,
                    ProductionPlan.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    planned_kg = (
        _extract_planned_yield_kg(plan_rows, FL_PRODUCT_NAME) if has_extract else None
    )

    # 实际入库 KPI：入库台账（明细）已确认行，扎帐月 27～26 口径
    period_start, period_end, period_label = _settlement_period(year, month_no)
    confirmed_batches: set[str] = set()
    inbound_kg_value = 0.0
    for batch_no, entry in warehouse_index.items():
        if (
            entry["confirmed"]
            and entry["inbound_date"] is not None
            and period_start <= entry["inbound_date"] <= period_end
        ):
            confirmed_batches.add(batch_no)
            inbound_kg_value += entry["kg"]
    inbound_batches = len(confirmed_batches)
    inbound_kg = round(inbound_kg_value, 2) if has_extract else None
    completion_rate = (
        round(inbound_kg / planned_kg * 100, 2)
        if has_extract and inbound_kg is not None and planned_kg
        else None
    )

    include_weight = has_extract

    # 工序流转滚动窗口：中间态常驻；已入库保留 2 天；未来 2 天内待投料预告
    window_start = anchor.date() - timedelta(days=FLOW_WINDOW_DAYS)
    window_end = anchor + timedelta(days=FLOW_WINDOW_DAYS)
    recent_inbound_rows = [
        r
        for r in inbound_rows
        if (states[r.batch_no][1] or date.min) >= window_start
    ]
    upcoming_window_rows = [
        r for r in upcoming_rows if (_charge_start(r) or anchor) <= window_end
    ]
    flow_rows = active_rows + recent_inbound_rows + upcoming_window_rows
    flow_rows.sort(
        key=lambda r: (
            _charge_start(r) or datetime.combine(r.order_date or date.min, time.min),
            r.batch_no,
        )
    )

    # 当月批次明细（A 口径）：仅已确认入库批次，按实际入库日期倒序
    month_batches = sorted(
        (
            _serialize_batch(
                r,
                anchor=anchor,
                state=states[r.batch_no][0],
                actual_inbound=states[r.batch_no][1],
                include_weight=include_weight,
            )
            for r in inbound_rows
        ),
        key=lambda b: (b["actual_inbound_date"] or "", b["batch_no"]),
        reverse=True,
    )

    # 最近完成批次：全产线已确认批次按实际入库日期倒序（含未排产月的历史批次）
    recent_names = sorted(
        (
            (entry["inbound_date"], batch_no)
            for batch_no, entry in warehouse_index.items()
            if entry["confirmed"] and entry["inbound_date"] is not None
        ),
        reverse=True,
    )[:RECENT_COMPLETED_SIZE]
    recent_schedule = (
        {
            row.batch_no: row
            for row in (
                (
                    await db.execute(
                        select(FlBatch).where(
                            FlBatch.is_deleted.is_(False),
                            FlBatch.batch_no.in_(
                                [name for _, name in recent_names]
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        if recent_names
        else {}
    )
    recent_completed = [
        _serialize_batch(
            recent_schedule.get(name) or FlBatch(batch_no=name),
            anchor=anchor,
            state=STATE_INBOUND,
            actual_inbound=inbound_date,
            include_weight=include_weight,
        )
        for inbound_date, name in recent_names
    ]

    flow = [
        _serialize_batch(
            r,
            anchor=anchor,
            state=states[r.batch_no][0],
            actual_inbound=states[r.batch_no][1],
            include_weight=include_weight,
        )
        for r in flow_rows
    ]

    return success_response(
        {
            "month": month_str,
            "batch_prefix": batch_prefix,
            "is_current_month": is_current_month,
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "label": period_label,
            },
            "planned_kg": planned_kg,
            "planned_batches": len(month_rows),
            "inbound_batches": inbound_batches,
            "inbound_kg": inbound_kg,
            "completion_rate": completion_rate,
            "in_progress_count": len(active_rows),
            "progress": {
                "by_batches": {
                    "inbound": len(inbound_rows),
                    "in_progress": len(active_rows),
                    "not_started": len(upcoming_rows),
                },
                "by_kg": {
                    "completed_kg": inbound_kg,
                    "planned_kg": planned_kg,
                },
            },
            "flow": flow,
            "month_batches": month_batches,
            "recent_completed": recent_completed,
            "generated_at": datetime.now(BEIJING_TZ).isoformat(),
        }
    )
