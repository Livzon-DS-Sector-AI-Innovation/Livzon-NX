"""发酵车间看板：从排产 Excel 存档推算计划驱动数据。

一期口径（与用户确认）：
- 看板三台发酵罐 = 排产表中 302A/303A/304A（移种 → 放罐约 3 天 / 72h）；
- "本月" = 27 日～次月 26 日扎帐月（排产周期块）；
- 状态由计划时间与当前时间推算；"检修维护"来自 tank_maintenance 人工标注；
- 计划放罐时间起 2 小时内为"放罐中"，窗口结束后批次才算"已放罐/完成"
  （最近完成列表与"本月已完成批次" KPI 同口径，计划放罐时间以排产表为准）；
- 运行批次的"距预估放罐"播报只提醒 24h 内将要放罐的批次。

批号与时间关系（由表结构验证）：
- 种子罐段：每天 20:00 接种一个新批号；
- 发酵罐段：同批号在次日（实际为下一列日）21:00 移种进 302A/303A/304A 之一；
- 放罐段：批号在移种日后第 3 天 10:00 放罐（放罐批号 = 移种批号）。
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.fermentation_batch_actual_models import (
    FermentationBatchActual,
)
from app.modules.production.fermentation_month_setting_models import (
    FermentationMonthSetting,
)
from app.modules.production.schedule_excel_models import ScheduleExcelArchive
from app.modules.production.tank_maintenance_models import TankMaintenance

FERMENT_TANKS = ("302A", "303A", "304A")

# 放罐窗口：计划放罐时间起 2 小时内为「放罐中」（批次仍在罐上，不算完成）；
# 窗口结束后批次才视为「已放罐/完成」（罐状态、recent 最近完成、完成 KPI 同口径）。
DUMP_WINDOW = timedelta(hours=2)

_TITLE_RE = re.compile(
    r"(\d{4})年(\d{1,2})月27日～(\d{4})年(\d{1,2})月26日"
)
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

# 块内固定行偏移（0 基，块首为标题行）
_ROW_DATE = 1        # 日期行
_ROW_SEED_BATCH = 3  # 种子罐批号
_ROW_SEED_TANK = 4
_ROW_SEED_TIME = 5   # 接种时间
_ROW_FERM_BATCH = 6  # 发酵罐批号
_ROW_FERM_TANK = 7
_ROW_FERM_TIME = 8   # 移种时间
_ROW_DUMP_BATCH = 9  # 放罐批号
_ROW_DUMP_TANK = 10
_ROW_DUMP_TIME = 11  # 放罐时间

_BLOCK_HEIGHT = 16


# ═══════════════════ 排产表解析（纯函数） ═══════════════════


def _parse_time(value: Any) -> time | None:
    text = str(value or "").strip()
    match = _TIME_RE.match(text)
    if not match:
        return None
    return time(int(match.group(1)), int(match.group(2)))


def _format_dump_remain(hours: float) -> str:
    """放罐剩余时长：满 1 小时显示 Xh Ymin，整点只显示 Xh，不满 1 小时只显示分钟。"""
    total_minutes = max(0, int(hours * 60))
    h, m = divmod(total_minutes, 60)
    if h == 0:
        return f"{m}min"
    if m == 0:
        return f"{h}h"
    return f"{h}h{m}min"


def _batch_seq(batch_no: str) -> int:
    """批次顺序号 = 批次号后三位；无法解析时排最前。"""
    match = re.search(r"(\d{3})$", batch_no or "")
    return int(match.group(1)) if match else -1


def parse_period_title(text: str) -> tuple[date, date] | None:
    """标题 'YYYY年MM月27日～YYYY年MM月26日' → (start, end)。"""
    match = _TITLE_RE.match(text.strip())
    if not match:
        return None
    y1, m1, y2, m2 = (int(g) for g in match.groups())
    return date(y1, m1, 27), date(y2, m2, 26)


def find_period_block(
    rows: list[list[Any]], now: datetime
) -> dict[str, Any] | None:
    """定位包含 now 的扎帐周期块；无匹配（如排产未覆盖当前日期）返回 None。"""
    for index, row in enumerate(rows):
        if not row:
            continue
        span = parse_period_title(str(row[0]))
        if not span:
            continue
        start, end = span
        if start <= now.date() <= end:
            return {
                "start_row": index,
                "start": start,
                "end": end,
                "label": f"{start.month}月{start.day}日～{end.month}月{end.day}日",
            }
    return None


def _row_values(rows: list[list[Any]], row_index: int) -> list[Any]:
    """行内 ci>=2 的值（与日期列对齐）。"""
    row = rows[row_index] if row_index < len(rows) else []
    return list(row[2:]) if len(row) > 2 else []


def _col_dates(days_row: list[Any], block_start: date) -> list[date]:
    """日期行（27..26）→ 每列的 date。"""
    result: list[date] = []
    for value in days_row[2:]:
        try:
            day = int(str(value).strip())
        except ValueError:
            result.append(block_start)  # 空列占位，不影响统计
            continue
        if day >= 27:
            result.append(block_start.replace(day=day))
        else:
            # 次月
            if block_start.month == 12:
                nxt = block_start.replace(year=block_start.year + 1, month=1)
            else:
                nxt = block_start.replace(month=block_start.month + 1)
            result.append(nxt.replace(day=day))
    return result


def parse_block(
    rows: list[list[Any]], block: dict[str, Any]
) -> dict[str, Any]:
    """把一个周期块解析成按日期的计划列表。"""
    start_row = block["start_row"]
    days_row = rows[start_row + _ROW_DATE]
    col_dates = _col_dates(days_row, block["start"])
    col_count = len(col_dates)

    def col_list(row_offset: int) -> list[Any]:
        values = _row_values(rows, start_row + row_offset)
        while len(values) < col_count:
            values.append("")
        return values

    seed_batches = col_list(_ROW_SEED_BATCH)
    seed_tanks = col_list(_ROW_SEED_TANK)
    seed_times = col_list(_ROW_SEED_TIME)
    ferm_batches = col_list(_ROW_FERM_BATCH)
    ferm_tanks = col_list(_ROW_FERM_TANK)
    ferm_times = col_list(_ROW_FERM_TIME)
    dump_batches = col_list(_ROW_DUMP_BATCH)
    dump_tanks = col_list(_ROW_DUMP_TANK)
    dump_times = col_list(_ROW_DUMP_TIME)

    parsed: list[dict[str, Any]] = []
    for ci in range(col_count):
        day = col_dates[ci]
        parsed.append(
            {
                "date": day,
                "seed_batch": str(seed_batches[ci]).strip(),
                "seed_tank": str(seed_tanks[ci]).strip(),
                "seed_time": _parse_time(seed_times[ci]),
                "ferm_batch": str(ferm_batches[ci]).strip(),
                "ferm_tank": str(ferm_tanks[ci]).strip(),
                "ferm_time": _parse_time(ferm_times[ci]),
                "dump_batch": str(dump_batches[ci]).strip(),
                "dump_tank": str(dump_tanks[ci]).strip(),
                "dump_time": _parse_time(dump_times[ci]),
            }
        )
    return {"block": block, "days": parsed}


def collect_dump_dates(
    rows: list[list[Any]],
) -> dict[str, date]:
    """全表所有放罐批号 → 放罐日期（跨块连续，批号唯一）。"""
    mapping: dict[str, date] = {}
    for index, row in enumerate(rows):
        if not row:
            continue
        span = parse_period_title(str(row[0]))
        if not span:
            continue
        days_row = rows[index + _ROW_DATE]
        col_dates = _col_dates(days_row, span[0])
        batches = _row_values(rows, index + _ROW_DUMP_BATCH)
        for ci, batch in enumerate(batches):
            batch_no = str(batch).strip()
            if batch_no and ci < len(col_dates):
                mapping[batch_no] = col_dates[ci]
    return mapping


def _ferm_events(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """发酵罐移种事件（罐号、批号、移种 datetime）。"""
    events: list[dict[str, Any]] = []
    for item in days:
        if item["ferm_batch"] and item["ferm_tank"] and item["ferm_time"]:
            events.append(
                {
                    "tank_no": item["ferm_tank"],
                    "batch_no": item["ferm_batch"],
                    "start": datetime.combine(item["date"], item["ferm_time"]),
                }
            )
    return events


def _seed_events(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """种子接种事件（每天 20:00）。"""
    events: list[dict[str, Any]] = []
    for item in days:
        if item["seed_batch"] and item["seed_time"]:
            events.append(
                {
                    "tank_no": item["seed_tank"] or "",
                    "batch_no": item["seed_batch"],
                    "start": datetime.combine(item["date"], item["seed_time"]),
                }
            )
    return events


# ═══════════════════ 看板组装 ═══════════════════


def build_board(
    rows: list[list[Any]],
    maintenance: list[dict[str, Any]],
    now: datetime,
    actuals: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """由存档行与检修标注组装看板数据；无当前周期返回 None。

    actuals 为已录入的批次实际产量（serialize_batch_actual 列表），
    用于回填最近完成批次的放罐产量，并生成单批产量图表序列。
    """
    block = find_period_block(rows, now)
    if block is None:
        return None
    parsed = parse_block(rows, block)
    days = parsed["days"]
    dump_map = collect_dump_dates(rows)

    maint_by_tank = {m["tank_no"]: m for m in maintenance}
    actual_by_batch = {
        a["batch_no"]: a for a in (actuals or []) if a.get("batch_no")
    }

    # ── 罐状态 ──
    ferm_events = _ferm_events(days)
    tanks: list[dict[str, Any]] = []
    for tank_no in FERMENT_TANKS:
        maint = maint_by_tank.get(tank_no)
        if maint:
            tanks.append(
                {
                    "tank_no": tank_no,
                    "status": "maintenance",
                    "batch_no": None,
                    "inoculate_at": None,
                    "cultured_hours": None,
                    "cycle_hours": None,
                    "dump_at": None,
                    "note": f"检修：{maint['reason']}",
                }
            )
            continue
        running: dict[str, Any] | None = None
        dumping: dict[str, Any] | None = None
        for event in ferm_events:
            if event["tank_no"] != tank_no:
                continue
            dump_date = dump_map.get(event["batch_no"])
            if dump_date is None:
                continue
            dump_at = datetime.combine(dump_date, time(10, 0))
            dump_end = dump_at + DUMP_WINDOW
            if event["start"] <= now < dump_at:
                running = {**event, "dump_at": dump_at}
            elif dump_at <= now < dump_end:
                dumping = {**event, "dump_at": dump_at, "dump_end": dump_end}
        if running:
            hours = (now - running["start"]).total_seconds() / 3600
            remain = (running["dump_at"] - now).total_seconds() / 3600
            cycle = (
                (running["dump_at"] - running["start"]).total_seconds() / 3600
            )
            tanks.append(
                {
                    "tank_no": tank_no,
                    "status": "running",
                    "batch_no": running["batch_no"],
                    "inoculate_at": running["start"],
                    "cultured_hours": round(hours, 1),
                    "cycle_hours": round(cycle, 1),
                    "dump_at": running["dump_at"],
                    "note": f"距放罐约 {max(0, int(remain))}h",
                }
            )
        elif dumping:
            hours = (now - dumping["start"]).total_seconds() / 3600
            remain = (dumping["dump_end"] - now).total_seconds() / 3600
            cycle = (
                (dumping["dump_at"] - dumping["start"]).total_seconds() / 3600
            )
            tanks.append(
                {
                    "tank_no": tank_no,
                    "status": "dumping",
                    "batch_no": dumping["batch_no"],
                    "inoculate_at": dumping["start"],
                    "cultured_hours": round(hours, 1),
                    "cycle_hours": round(cycle, 1),
                    "dump_at": dumping["dump_at"],
                    "note": f"放罐中（预计{_format_dump_remain(remain)}后结束）",
                }
            )
        else:
            # 找下一个计划移种事件
            next_event = None
            for event in ferm_events:
                if event["tank_no"] == tank_no and event["start"] > now:
                    next_event = event
                    break
            note = "等待排产"
            next_inoculate = None
            if next_event:
                next_inoculate = next_event["start"]
                next_time = next_event["start"].strftime("%m-%d %H:%M")
                note = f"预计{next_time}移种{next_event['batch_no']}"
            tanks.append(
                {
                    "tank_no": tank_no,
                    "status": "idle",
                    "batch_no": None,
                    "inoculate_at": next_inoculate,
                    "cultured_hours": None,
                    "cycle_hours": None,
                    "dump_at": None,
                    "note": note,
                }
            )

    # ── KPI（扎帐月 = 当前块）──
    month_dump_count = sum(1 for item in days if item["dump_batch"])
    # 已放罐（窗口结束）的批次按是否已录入产量拆分，供进度条分段；
    # 已录入产量合计为"已完成产能"
    month_done_with_yield = 0
    month_yield_pending = 0
    month_done_yield_kg: float | None = None
    for item in days:
        if not item["dump_batch"]:
            continue
        dump_at = datetime.combine(item["date"], item["dump_time"] or time(10, 0))
        if dump_at + DUMP_WINDOW > now:
            continue
        yield_kg = (actual_by_batch.get(item["dump_batch"]) or {}).get("yield_kg")
        if yield_kg is None:
            month_yield_pending += 1
        else:
            month_done_with_yield += 1
            month_done_yield_kg = (month_done_yield_kg or 0) + float(yield_kg)
    month_done = month_done_with_yield + month_yield_pending
    seed_events = _seed_events(days)
    pending_count = sum(1 for ev in seed_events if ev["start"] > now)
    running_count = sum(1 for t in tanks if t["status"] == "running")

    # ── 最近放罐（按计划，取放罐窗口已结束的批次，最多整个周期 31 批；
    #     前端表格内部滚动展示）──
    recent: list[dict[str, Any]] = []
    for item in reversed(days):
        if not item["dump_batch"]:
            continue
        dump_at = datetime.combine(item["date"], item["dump_time"] or time(10, 0))
        if dump_at + DUMP_WINDOW <= now:
            recent.append(
                {
                    "batch_no": item["dump_batch"],
                    "dump_date": item["date"].isoformat(),
                    "tank_no": item["dump_tank"] or "",
                    "yield_kg": (
                        actual_by_batch.get(item["dump_batch"]) or {}
                    ).get("yield_kg"),
                    "remark": (
                        actual_by_batch.get(item["dump_batch"]) or {}
                    ).get("remark"),
                    "yield_rate": None,
                    "result": "计划放罐",
                }
            )
        if len(recent) >= 31:
            break
    if not recent:
        recent = []

    # ── 单批产量（已录入实际产量的批次，按批次顺序升序，最多 31 批）──
    measured = sorted(
        (a for a in (actuals or []) if a.get("yield_kg") is not None),
        key=lambda a: _batch_seq(a["batch_no"]),
    )
    recent_measured = measured[-31:]
    trend = None
    if recent_measured:
        trend = {
            "batches": [a["batch_no"] for a in recent_measured],
            "outputs": [round(float(a["yield_kg"]), 2) for a in recent_measured],
        }

    # ── 已放罐批次清单（供产量录入下拉；完成口径与 recent 一致）──
    dumped_batches: list[dict[str, Any]] = []
    seen_batches: set[str] = set()
    for item in days:
        if not item["dump_batch"] or item["dump_batch"] in seen_batches:
            continue
        dump_at = datetime.combine(item["date"], item["dump_time"] or time(10, 0))
        if dump_at + DUMP_WINDOW <= now:
            seen_batches.add(item["dump_batch"])
            dumped_batches.append(
                {
                    "batch_no": item["dump_batch"],
                    "dump_date": item["date"].isoformat(),
                }
            )

    # ─ 告警 ──
    alerts: list[dict[str, Any]] = []
    for tank in tanks:
        if tank["status"] == "running" and tank["dump_at"]:
            remain_h = int((tank["dump_at"] - now).total_seconds() // 3600)
            # 播报只提醒 24h 内将要放罐的批次
            if 0 < remain_h <= 24:
                alerts.append(
                    {
                        "level": "warn",
                        "text": (
                            f"【播报】{tank['tank_no']}罐批次 {tank['batch_no']} "
                            f"距预估放罐剩余 {remain_h}h"
                        ),
                    }
                )
        elif tank["status"] == "dumping" and tank["dump_at"]:
            alerts.append(
                {
                    "level": "warn",
                    "text": (
                        f"【放罐中】{tank['tank_no']}罐批次 {tank['batch_no']} "
                        f"正在放罐"
                    ),
                }
            )
    # 检修与计划冲突：检修罐在块内有移种计划
    for tank_no, maint in maint_by_tank.items():
        conflict = [
            ev["batch_no"]
            for ev in ferm_events
            if ev["tank_no"] == tank_no
        ]
        if conflict:
            alerts.append(
                {
                    "level": "warn",
                    "text": (
                        f"【冲突】{tank_no}罐检修中，但本周期仍有移种计划"
                        f"（如 {conflict[0]}），请确认"
                    ),
                }
            )
    # 今日待接种提醒（20:00 前提示今天批次）
    today_seed = next(
        (
            ev
            for ev in seed_events
            if ev["start"].date() == now.date() and ev["start"] > now
        ),
        None,
    )
    if today_seed:
        alerts.append(
            {
                "level": "info",
                "text": (
                    f"待接种批次 {today_seed['batch_no']} 今日 "
                    f"{today_seed['start'].strftime('%H:%M')} 进种子罐"
                    f"（{today_seed['tank_no'] or '按排产'}）"
                ),
            }
        )

    if not alerts:
        alerts = [{"level": "info", "text": "车间运行正常，无待处理播报"}]

    return {
        "now": now.isoformat(),
        "period": {
            "start": block["start"].isoformat(),
            "end": block["end"].isoformat(),
            "label": block["label"],
        },
        "kpis": {
            "month_planned": month_dump_count,
            "month_done_planned": month_done,
            "done_with_yield": month_done_with_yield,
            "yield_pending": month_yield_pending,
            "month_done_yield_kg": month_done_yield_kg,
            "running": running_count,
            "pending": pending_count,
            # 以下指标依赖实际数据，一期返回 None（前端显示 --）
            "plan_capacity": None,
            "contam_count": None,
            "contam_rate": None,
            "avg_yield_rate": None,
            "utilization": None,
            "avg_batch_yield": None,
            "qualify_rate": None,
        },
        "tanks": tanks,
        "recent": recent,
        "trend": trend,
        "dumped_batches": dumped_batches,
        "alerts": alerts,
        "maintenance": maintenance,
    }


# ═══════════════════ 检修标注 CRUD ═══════════════════


async def list_active_maintenance(session: AsyncSession) -> list[TankMaintenance]:
    result = await session.execute(
        select(TankMaintenance)
        .where(TankMaintenance.is_deleted.is_(False))
        .order_by(TankMaintenance.started_at.asc())
    )
    return list(result.scalars().all())


def serialize_maintenance(item: TankMaintenance) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "tank_no": item.tank_no,
        "reason": item.reason,
        "started_at": item.started_at.isoformat() if item.started_at else None,
    }


async def upsert_maintenance(
    session: AsyncSession,
    *,
    tank_no: str,
    reason: str,
    created_by: Any = None,
) -> TankMaintenance:
    """同一罐存在进行中标注则更新（保持单条进行中）。"""
    result = await session.execute(
        select(TankMaintenance).where(
            TankMaintenance.tank_no == tank_no,
            TankMaintenance.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        item = TankMaintenance(tank_no=tank_no, reason=reason, created_by=created_by)
        session.add(item)
    else:
        item.reason = reason
        item.updated_by = created_by
    await session.commit()
    await session.refresh(item)
    return item


async def delete_maintenance(
    session: AsyncSession,
    item: TankMaintenance,
    *,
    deleted_by: Any = None,
) -> None:
    item.is_deleted = True
    item.updated_by = deleted_by
    await session.commit()


async def get_maintenance(
    session: AsyncSession, item_id: Any
) -> TankMaintenance | None:
    result = await session.execute(
        select(TankMaintenance).where(
            TankMaintenance.id == item_id,
            TankMaintenance.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def load_latest_archive(session: AsyncSession) -> ScheduleExcelArchive | None:
    result = await session.execute(
        select(ScheduleExcelArchive)
        .where(ScheduleExcelArchive.is_deleted.is_(False))
        .order_by(ScheduleExcelArchive.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ═══════════════════ 批次实际产量（历史数据） ═══════════════════


def serialize_batch_actual(item: FermentationBatchActual) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "batch_no": item.batch_no,
        "dump_date": item.dump_date.isoformat() if item.dump_date else None,
        "yield_kg": item.yield_kg,
        "remark": item.remark,
    }


async def list_batch_actuals(session: AsyncSession) -> list[FermentationBatchActual]:
    result = await session.execute(
        select(FermentationBatchActual)
        .where(FermentationBatchActual.is_deleted.is_(False))
        .order_by(
            FermentationBatchActual.dump_date.desc().nullslast(),
            FermentationBatchActual.batch_no.desc(),
        )
    )
    return list(result.scalars().all())


async def upsert_batch_actual(
    session: AsyncSession,
    *,
    batch_no: str,
    dump_date: date | None = None,
    yield_kg: float | None = None,
    remark: str | None = None,
    created_by: Any = None,
) -> FermentationBatchActual:
    """同一批次存在进行中记录则更新（批号唯一）。"""
    result = await session.execute(
        select(FermentationBatchActual).where(
            FermentationBatchActual.batch_no == batch_no,
            FermentationBatchActual.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        item = FermentationBatchActual(
            batch_no=batch_no,
            dump_date=dump_date,
            yield_kg=yield_kg,
            remark=remark,
            created_by=created_by,
        )
        session.add(item)
    else:
        item.dump_date = dump_date
        item.yield_kg = yield_kg
        item.remark = remark
        item.updated_by = created_by
    await session.commit()
    await session.refresh(item)
    return item


async def get_batch_actual(
    session: AsyncSession, item_id: Any
) -> FermentationBatchActual | None:
    result = await session.execute(
        select(FermentationBatchActual).where(
            FermentationBatchActual.id == item_id,
            FermentationBatchActual.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def delete_batch_actual(
    session: AsyncSession,
    item: FermentationBatchActual,
    *,
    deleted_by: Any = None,
) -> None:
    item.is_deleted = True
    item.updated_by = deleted_by
    await session.commit()


# ═══════════════════ 扎帐月设置（计划产能） ═══════════════════


def current_period(
    rows: list[list[Any]], now: datetime
) -> tuple[date, date] | None:
    """最新存档中包含 now 的扎帐周期 (start, end)。"""
    block = find_period_block(rows, now)
    if block is None:
        return None
    return block["start"], block["end"]


async def get_month_setting(
    session: AsyncSession, period_start: date
) -> FermentationMonthSetting | None:
    result = await session.execute(
        select(FermentationMonthSetting).where(
            FermentationMonthSetting.period_start == period_start,
            FermentationMonthSetting.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def upsert_month_setting(
    session: AsyncSession,
    *,
    period_start: date,
    period_end: date,
    planned_capacity_kg: float | None,
    updated_by: Any = None,
) -> FermentationMonthSetting:
    """同一周期存在进行中记录则更新。"""
    result = await session.execute(
        select(FermentationMonthSetting).where(
            FermentationMonthSetting.period_start == period_start,
            FermentationMonthSetting.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        item = FermentationMonthSetting(
            period_start=period_start,
            period_end=period_end,
            planned_capacity_kg=planned_capacity_kg,
            created_by=updated_by,
        )
        session.add(item)
    else:
        item.period_end = period_end
        item.planned_capacity_kg = planned_capacity_kg
        item.updated_by = updated_by
    await session.commit()
    await session.refresh(item)
    return item


def serialize_month_setting(item: FermentationMonthSetting) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "period_start": item.period_start.isoformat(),
        "period_end": item.period_end.isoformat(),
        "planned_capacity_kg": item.planned_capacity_kg,
    }
