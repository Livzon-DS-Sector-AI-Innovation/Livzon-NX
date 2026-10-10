"""FA 排产校验器（一期）。

对排产存档行做结构化检查，输出问题清单（只报告、不阻断上传）。
排产存在多条合法路径——移种位可给任意空罐、放罐时刻可在小范围内
挪、空拍可摊给不同罐——因此校验只查硬约束与明显错漏，不校验
「标准排法」；检修窗口（含预计恢复日期）内的空位、废弃种子留痕、
扰动导致的无放罐日都是合法形态，不误报。领域规则见
docs/production-fa-scheduling-rules.md。

约束参数（标准周期/容差/上限/周转/月批数）按产品配置于
production.schedule_constraint_settings；未配置的检查自动跳过并在
报告中说明。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production import fermentation_board_service as board
from app.modules.production.schedule_constraint_models import (
    ScheduleConstraintSetting,
)
from app.modules.production.schedule_excel_models import ScheduleExcelArchive

# 校验当前仅支持 FA（解析复用 FA 管线；其他产线二期按同模式扩展）
VALIDATION_PRODUCTS = ("FA",)

FA_TANKS = frozenset(board.FERMENT_TANKS)
STANDARD_FERM_TIME = time(21, 0)
STANDARD_DUMP_TIME = time(10, 0)
# 无标准周期配置时的预计放罐间隔（FA 惯例：移种后第 3 天 10:00 放罐）
DEFAULT_DUMP_GAP_DAYS = 3
# 种子接种次日移种（隔两天即超龄废弃，不允许出现）
SEED_TRANSFER_GAP_DAYS = 1
# 宽容的 FA 批号模式（FA + 4~6 位数字）；仅做格式提示，不做硬约束
FA_BATCH_RE = re.compile(r"^FA\d{4,6}$")


# ═══════════════════ 事实提取 ═══════════════════


@dataclass
class _FermEvent:
    """发酵罐移种事件（不去重，重复移种由规则识别）。"""

    tank_no: str
    batch_no: str
    start: datetime
    block_label: str
    time_ok: bool


@dataclass
class _DumpEvent:
    """放罐事件。at 在时间格损坏时按默认 10:00 兜底（规则已另行报坏格）。"""

    batch_no: str
    tank_no: str
    at: datetime
    block_label: str
    time_ok: bool


@dataclass
class _SeedEvent:
    """种子接种事件。at 在时间格损坏时按默认 20:00 兜底。"""

    batch_no: str
    at: datetime
    block_label: str
    time_ok: bool


@dataclass
class _DayCell:
    """一个周期块内某日期列的原始单元格（供坏格与空列检查）。"""

    date: date
    block_label: str
    seed_batch: str
    ferm_batch: str
    ferm_tank: str
    dump_batch: str
    dump_tank: str
    seed_time: time | None
    ferm_time: time | None
    dump_time: time | None
    seed_time_raw: str
    ferm_time_raw: str
    dump_time_raw: str
    note: str


@dataclass
class _Facts:
    blocks: list[dict[str, Any]]
    ferm_events: list[_FermEvent]
    dump_events: list[_DumpEvent]
    seed_events: list[_SeedEvent]
    day_cells: list[_DayCell]
    coverage_start: date | None
    coverage_end: date | None


def _find_blocks(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """全表所有 FA 扎帐周期块（与 find_period_block 同口径）。"""
    blocks: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not row:
            continue
        span = board.parse_period_title(str(row[0]))
        if not span:
            continue
        blocks.append(
            {
                "start_row": index,
                "start": span[0],
                "end": span[1],
                "label": (
                    f"{span[0].month}月{span[0].day}日～"
                    f"{span[1].month}月{span[1].day}日"
                ),
            }
        )
    return blocks


def _padded(values: list[Any], size: int) -> list[str]:
    result = [str(v).strip() for v in values]
    while len(result) < size:
        result.append("")
    return result


def _collect_facts(rows: list[list[Any]]) -> _Facts:
    """从存档行提取事件流与逐列单元格事实（跨块，保留重复）。"""
    blocks = _find_blocks(rows)
    ferm_events: list[_FermEvent] = []
    dump_events: list[_DumpEvent] = []
    seed_events: list[_SeedEvent] = []
    day_cells: list[_DayCell] = []
    for block in blocks:
        start_row = block["start_row"]
        days = board.parse_block(rows, block)["days"]
        col_count = len(days)

        def raw(offset: int) -> list[str]:
            return _padded(board._row_values(rows, start_row + offset), col_count)

        seed_times_raw = raw(board._ROW_SEED_TIME)
        ferm_times_raw = raw(board._ROW_FERM_TIME)
        dump_times_raw = raw(board._ROW_DUMP_TIME)
        for ci, day in enumerate(days):
            day_cells.append(
                _DayCell(
                    date=day["date"],
                    block_label=block["label"],
                    seed_batch=day["seed_batch"],
                    ferm_batch=day["ferm_batch"],
                    ferm_tank=day["ferm_tank"],
                    dump_batch=day["dump_batch"],
                    dump_tank=day["dump_tank"],
                    seed_time=day["seed_time"],
                    ferm_time=day["ferm_time"],
                    dump_time=day["dump_time"],
                    seed_time_raw=seed_times_raw[ci],
                    ferm_time_raw=ferm_times_raw[ci],
                    dump_time_raw=dump_times_raw[ci],
                    note=day["note"],
                )
            )
            if day["seed_batch"]:
                seed_events.append(
                    _SeedEvent(
                        batch_no=day["seed_batch"],
                        at=datetime.combine(
                            day["date"],
                            day["seed_time"] or time(20, 0),
                        ),
                        block_label=block["label"],
                        time_ok=day["seed_time"] is not None,
                    )
                )
            if day["ferm_batch"] and day["ferm_tank"]:
                ferm_events.append(
                    _FermEvent(
                        tank_no=day["ferm_tank"],
                        batch_no=day["ferm_batch"],
                        start=datetime.combine(
                            day["date"],
                            day["ferm_time"] or STANDARD_FERM_TIME,
                        ),
                        block_label=block["label"],
                        time_ok=day["ferm_time"] is not None,
                    )
                )
            if day["dump_batch"]:
                dump_events.append(
                    _DumpEvent(
                        batch_no=day["dump_batch"],
                        tank_no=day["dump_tank"],
                        at=datetime.combine(
                            day["date"],
                            day["dump_time"] or STANDARD_DUMP_TIME,
                        ),
                        block_label=block["label"],
                        time_ok=day["dump_time"] is not None,
                    )
                )
    spans = [(b["start"], b["end"]) for b in blocks]
    return _Facts(
        blocks=blocks,
        ferm_events=ferm_events,
        dump_events=dump_events,
        seed_events=seed_events,
        day_cells=day_cells,
        coverage_start=min((s for s, _ in spans), default=None),
        coverage_end=max((e for _, e in spans), default=None),
    )


@dataclass
class _MaintenanceWindow:
    tank_no: str
    started_on: date
    recovery_on: date | None

    def covers(self, day: date) -> bool:
        return self.started_on <= day and (
            self.recovery_on is None or day <= self.recovery_on
        )


def _maintenance_windows(
    maintenance: list[dict[str, Any]] | None,
) -> list[_MaintenanceWindow]:
    windows: list[_MaintenanceWindow] = []
    for item in maintenance or []:
        started = board._parse_board_time(item.get("started_at"))
        if started is None:
            continue
        recovery = board._parse_board_date(item.get("expected_recovery_date"))
        windows.append(
            _MaintenanceWindow(
                tank_no=str(item.get("tank_no") or ""),
                started_on=started.date(),
                recovery_on=recovery,
            )
        )
    return windows


def _any_maintenance_covers(
    windows: list[_MaintenanceWindow], day: date
) -> bool:
    return any(
        w.tank_no in FA_TANKS and w.covers(day) for w in windows
    )


@dataclass
class _Issue:
    level: str  # "warn" | "info"
    rule: str
    text: str
    block: str | None = None
    date: date | None = None
    tank_no: str | None = None
    batch_no: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "rule": self.rule,
            "text": self.text,
            "block": self.block,
            "date": self.date.isoformat() if self.date else None,
            "tank_no": self.tank_no,
            "batch_no": self.batch_no,
        }


# ═══════════════════ 校验主流程 ═══════════════════


def validate_schedule_rows(
    rows: list[list[Any]],
    *,
    previous_rows: list[list[Any]] | None = None,
    constraints: dict[str, Any] | None = None,
    maintenance: list[dict[str, Any]] | None = None,
    now: datetime,
) -> dict[str, Any]:
    """校验 FA 排产行，返回问题清单报告（纯函数，不访问数据库）。

    只校验「今天及以后」的排产：更早的列已被上传合并冻结为历史，
    其问题属于既往存档而非本次排产决策。跨表链路（种子来源、放罐
    去向、在制批次衔接）用整表 + 上一份存档回查。
    """
    constraints = constraints or {}
    standard = constraints.get("standard_cycle_hours")
    tolerance = constraints.get("cycle_tolerance_hours")
    max_cycle = constraints.get("max_cycle_hours")
    turnaround = constraints.get("turnaround_hours")
    dump_target = constraints.get("monthly_dump_target")

    scope_from = now.date()
    facts = _collect_facts(rows)
    windows = _maintenance_windows(maintenance)
    issues: list[_Issue] = []

    if facts.coverage_start is None or facts.coverage_end is None:
        return {
            "scope": {"from": scope_from.isoformat(), "blocks": []},
            "coverage": None,
            "issues": [],
            "summary": {"warn": 0, "info": 0},
            "constraints": constraints or None,
            "message": "排产表中未识别到周期块，无法校验",
        }

    scope_blocks = [b for b in facts.blocks if b["end"] >= scope_from]
    validated_labels = [b["label"] for b in scope_blocks]
    # 日级检查只看受校验块内的列（防止跨块重复日误报）
    scope_block_labels = set(validated_labels)

    prev_facts = _collect_facts(previous_rows) if previous_rows else None
    ferm_by_batch: dict[str, list[_FermEvent]] = {}
    for ev in facts.ferm_events:
        ferm_by_batch.setdefault(ev.batch_no, []).append(ev)
    dump_by_batch = {ev.batch_no: ev for ev in facts.dump_events}
    seed_by_batch = {ev.batch_no: ev for ev in facts.seed_events}
    # 含罐号缺失等坏行的批号全集（供孤儿放罐判断，避免同一坏行连环误报）
    ferm_batch_numbers = {
        c.ferm_batch for c in facts.day_cells if c.ferm_batch
    }
    prev_ferm_batches: set[str] = set()
    if prev_facts:
        prev_ferm_batches = {
            ev.batch_no for ev in prev_facts.ferm_events
        } | {c.ferm_batch for c in prev_facts.day_cells if c.ferm_batch}
    prev_seed_batches = (
        {ev.batch_no for ev in prev_facts.seed_events} if prev_facts else set()
    )

    def _expected_dump_date(start: datetime) -> date:
        if standard:
            return (start + timedelta(hours=standard)).date()
        return start.date() + timedelta(days=DEFAULT_DUMP_GAP_DAYS)

    # ── A1 时间格子：有批号但时间缺失或无法识别（看板会静默忽略/兜底）──
    for cell in facts.day_cells:
        if cell.date < scope_from or cell.block_label not in scope_block_labels:
            continue
        for role, batch, parsed, raw_text in (
            ("移种", cell.ferm_batch, cell.ferm_time, cell.ferm_time_raw),
            ("放罐", cell.dump_batch, cell.dump_time, cell.dump_time_raw),
            ("接种", cell.seed_batch, cell.seed_time, cell.seed_time_raw),
        ):
            if not batch or parsed is not None:
                continue
            detail = (
                f"（单元格值“{raw_text}”无法识别）"
                if raw_text
                else "（时间为空，将按默认时刻处理）"
            )
            issues.append(
                _Issue(
                    level="warn",
                    rule="time_cell",
                    text=f"批次 {batch} 的{role}时间缺失或格式错误{detail}",
                    block=cell.block_label,
                    date=cell.date,
                    batch_no=batch,
                )
            )

    # ── A2 罐号非法/缺失 ──
    for cell in facts.day_cells:
        if cell.date < scope_from or cell.block_label not in scope_block_labels:
            continue
        if cell.ferm_batch and cell.ferm_tank not in FA_TANKS:
            text = (
                f"发酵罐号“{cell.ferm_tank}”不在 FA 三罐（302A/303A/304A）之列"
                if cell.ferm_tank
                else f"批次 {cell.ferm_batch} 的发酵罐号为空"
            )
            issues.append(
                _Issue(
                    level="warn",
                    rule="tank_invalid",
                    text=text + "，该批次不会进看板",
                    block=cell.block_label,
                    date=cell.date,
                    tank_no=cell.ferm_tank or None,
                    batch_no=cell.ferm_batch,
                )
            )
        if (
            cell.dump_batch
            and cell.dump_tank
            and cell.dump_tank not in FA_TANKS
        ):
            issues.append(
                _Issue(
                    level="warn",
                    rule="tank_invalid",
                    text=f"放罐罐号“{cell.dump_tank}”不在 FA 三罐之列",
                    block=cell.block_label,
                    date=cell.date,
                    tank_no=cell.dump_tank,
                    batch_no=cell.dump_batch,
                )
            )

    # ── A3/A13 同罐重叠与周转不足 ──
    by_tank: dict[str, list[_FermEvent]] = {}
    for ev in facts.ferm_events:
        by_tank.setdefault(ev.tank_no, []).append(ev)
    for tank_no, events in by_tank.items():
        events.sort(key=lambda e: (e.start, e.batch_no))
        for prev_ev, next_ev in zip(events, events[1:]):
            if next_ev.start.date() < scope_from:
                continue
            prev_dump = dump_by_batch.get(prev_ev.batch_no)
            if prev_dump is None:
                continue  # 无放罐安排由 A6 单独报
            dump_end = prev_dump.at + board.DUMP_WINDOW
            if next_ev.start < dump_end:
                issues.append(
                    _Issue(
                        level="warn",
                        rule="tank_overlap",
                        text=(
                            f"{tank_no} 批次 {next_ev.batch_no} 的移种时刻早于"
                            f"批次 {prev_ev.batch_no} 的放罐作业结束"
                            f"（{prev_dump.at:%m-%d %H:%M} + 2h），两批重叠"
                        ),
                        block=next_ev.block_label,
                        date=next_ev.start.date(),
                        tank_no=tank_no,
                        batch_no=next_ev.batch_no,
                    )
                )
            elif turnaround and (
                next_ev.start - dump_end
            ) < timedelta(hours=turnaround):
                gap = (next_ev.start - dump_end).total_seconds() / 3600
                issues.append(
                    _Issue(
                        level="warn",
                        rule="turnaround_short",
                        text=(
                            f"{tank_no} 批次 {prev_ev.batch_no} 放罐结束到批次"
                            f" {next_ev.batch_no} 移种仅间隔 {gap:.1f}h，"
                            f"低于配置的最小周转 {turnaround}h"
                        ),
                        block=next_ev.block_label,
                        date=next_ev.start.date(),
                        tank_no=tank_no,
                        batch_no=next_ev.batch_no,
                    )
                )

    # ── A4/A5/A14 放罐倒挂、罐号不一致、培养周期分级 ──
    for batch_no, events in ferm_by_batch.items():
        earliest = min(events, key=lambda e: e.start)
        if earliest.start.date() < scope_from:
            continue
        dump = dump_by_batch.get(batch_no)
        if dump is None:
            continue  # A6/C7 处理
        if dump.at.date() < earliest.start.date():
            issues.append(
                _Issue(
                    level="warn",
                    rule="dump_before_inoculate",
                    text=(
                        f"批次 {batch_no} 的放罐日（{dump.at:%m-%d}）早于"
                        f"移种日（{earliest.start:%m-%d}），日期倒挂"
                    ),
                    block=dump.block_label,
                    date=dump.at.date(),
                    tank_no=earliest.tank_no,
                    batch_no=batch_no,
                )
            )
        if dump.tank_no and dump.tank_no != earliest.tank_no:
            issues.append(
                _Issue(
                    level="warn",
                    rule="dump_tank_mismatch",
                    text=(
                        f"批次 {batch_no} 移种罐为 {earliest.tank_no}，"
                        f"放罐罐却写 {dump.tank_no}（FA 应同罐放罐）"
                    ),
                    block=dump.block_label,
                    date=dump.at.date(),
                    tank_no=dump.tank_no,
                    batch_no=batch_no,
                )
            )
        if not (earliest.time_ok and dump.time_ok):
            continue  # 时间格损坏，周期不可信（A1 已报）
        cycle = (dump.at - earliest.start).total_seconds() / 3600
        if max_cycle is not None and cycle > max_cycle:
            issues.append(
                _Issue(
                    level="warn",
                    rule="cycle_over_limit",
                    text=(
                        f"批次 {batch_no} 培养周期 {cycle:.1f}h，超过工艺上限"
                        f" {max_cycle}h"
                    ),
                    block=dump.block_label,
                    date=dump.at.date(),
                    tank_no=earliest.tank_no,
                    batch_no=batch_no,
                )
            )
        elif (
            standard is not None
            and tolerance is not None
            and abs(cycle - standard) > tolerance
        ):
            issues.append(
                _Issue(
                    level="info",
                    rule="cycle_deviation",
                    text=(
                        f"批次 {batch_no} 培养周期 {cycle:.1f}h，偏离标准"
                        f" {standard}h 超出容差 {tolerance}h"
                        "（若为有意延长/缩短培养请确认）"
                    ),
                    block=dump.block_label,
                    date=dump.at.date(),
                    tank_no=earliest.tank_no,
                    batch_no=batch_no,
                )
            )

    # ── A6 移种无放罐安排（周期末正常跨表的不报）──
    for batch_no, events in ferm_by_batch.items():
        earliest = min(events, key=lambda e: e.start)
        if earliest.start.date() < scope_from:
            continue
        if dump_by_batch.get(batch_no):
            continue
        expected = _expected_dump_date(earliest.start)
        if facts.coverage_end is not None and expected > facts.coverage_end:
            continue
        issues.append(
            _Issue(
                level="warn",
                rule="ferm_without_dump",
                text=(
                    f"批次 {batch_no} 于 {earliest.start:%m-%d} 移种"
                    f"{earliest.tank_no}，但排产覆盖范围内未见其放罐安排"
                ),
                block=earliest.block_label,
                date=earliest.start.date(),
                tank_no=earliest.tank_no,
                batch_no=batch_no,
            )
        )

    # ── A7 孤儿放罐：放罐批号对不上任何移种（含上一份表）──
    for dump in facts.dump_events:
        if dump.at.date() < scope_from:
            continue
        if dump.batch_no in ferm_batch_numbers or dump.batch_no in prev_ferm_batches:
            continue
        issues.append(
            _Issue(
                level="warn",
                rule="orphan_dump",
                text=(
                    f"放罐批号 {dump.batch_no} 对不上任何移种记录，"
                    "请核对是否抄错"
                ),
                block=dump.block_label,
                date=dump.at.date(),
                tank_no=dump.tank_no or None,
                batch_no=dump.batch_no,
            )
        )

    # ── A8 移种无种子来源 ──
    for batch_no, events in ferm_by_batch.items():
        earliest = min(events, key=lambda e: e.start)
        if earliest.start.date() < scope_from:
            continue
        if batch_no in seed_by_batch or batch_no in prev_seed_batches:
            continue
        expected_seed = earliest.start.date() - timedelta(
            days=SEED_TRANSFER_GAP_DAYS
        )
        if expected_seed >= (facts.coverage_start or expected_seed):
            issues.append(
                _Issue(
                    level="warn",
                    rule="ferm_without_seed",
                    text=(
                        f"批次 {batch_no} 排了 {earliest.start:%m-%d} 移种，"
                        f"但前一日（{expected_seed:%m-%d}）在本表中未见其种子接种"
                    ),
                    block=earliest.block_label,
                    date=earliest.start.date(),
                    tank_no=earliest.tank_no,
                    batch_no=batch_no,
                )
            )
        elif prev_facts is not None:
            issues.append(
                _Issue(
                    level="warn",
                    rule="ferm_without_seed",
                    text=(
                        f"批次 {batch_no} 的种子应在前一日"
                        f"（{expected_seed:%m-%d}，上一份排产表内），但未见其接种"
                    ),
                    block=earliest.block_label,
                    date=earliest.start.date(),
                    tank_no=earliest.tank_no,
                    batch_no=batch_no,
                )
            )

    # ── C16b 种子菌龄：接种到移种必须恰好隔一天 ──
    for batch_no, seed in seed_by_batch.items():
        ferm = ferm_by_batch.get(batch_no)
        if not ferm:
            continue
        earliest = min(ferm, key=lambda e: e.start)
        if earliest.start.date() < scope_from:
            continue
        gap = (earliest.start.date() - seed.at.date()).days
        if gap == SEED_TRANSFER_GAP_DAYS:
            continue
        if gap >= 2:
            text = (
                f"批次 {batch_no} 种子 {seed.at:%m-%d} 接种、"
                f"{earliest.start:%m-%d} 才移种，菌龄 {gap} 天超龄"
                "（对移种菌浓/OD 有要求，隔两天即太老）"
            )
        else:
            text = (
                f"批次 {batch_no} 的移种日（{earliest.start:%m-%d}）不晚于"
                f"种子接种日（{seed.at:%m-%d}），顺序错误"
            )
        issues.append(
            _Issue(
                level="warn",
                rule="seed_transfer_gap",
                text=text,
                block=earliest.block_label,
                date=earliest.start.date(),
                batch_no=batch_no,
            )
        )

    # ── A9 同批号重复移种 ──
    for batch_no, events in ferm_by_batch.items():
        if len(events) < 2:
            continue
        starts = sorted(e.start for e in events)
        if starts[-1].date() < scope_from:
            continue
        when = "、".join(f"{s:%m-%d}" for s in starts)
        issues.append(
            _Issue(
                level="warn",
                rule="duplicate_inoculation",
                text=(
                    f"批次 {batch_no} 出现 {len(events)} 次移种安排"
                    f"（{when}），看板只会取最早一次"
                ),
                block=events[0].block_label,
                date=starts[0].date(),
                tank_no=events[0].tank_no,
                batch_no=batch_no,
            )
        )

    # ── A10 日期行重复/跳日/坏值 ──
    for block in scope_blocks:
        days_row = rows[block["start_row"] + board._ROW_DATE]
        if len(days_row) <= 2:
            continue
        day_values = [str(v).strip() for v in days_row[2:]]
        seen: dict[date, int] = {}
        bad_values: list[str] = []
        col_dates: list[date] = []
        for value, col_date in zip(
            day_values, board._col_dates(days_row, block["start"])
        ):
            if not value:
                continue
            try:
                int(value)
            except ValueError:
                bad_values.append(value)
                continue
            col_dates.append(col_date)
            seen[col_date] = seen.get(col_date, 0) + 1
        for dup_date, count in seen.items():
            if count > 1:
                issues.append(
                    _Issue(
                        level="warn",
                        rule="date_column_anomaly",
                        text=f"日期行中 {dup_date:%m-%d} 出现 {count} 列，日期重复",
                        block=block["label"],
                        date=dup_date,
                    )
                )
        for bad in bad_values:
            issues.append(
                _Issue(
                    level="warn",
                    rule="date_column_anomaly",
                    text=f"日期行存在无法识别的值“{bad}”",
                    block=block["label"],
                )
            )
        missing = [
            d
            for d in (
                block["start"] + timedelta(days=i)
                for i in range((block["end"] - block["start"]).days + 1)
            )
            if d not in seen
        ]
        for miss in missing:
            issues.append(
                _Issue(
                    level="warn",
                    rule="date_column_anomaly",
                    text=f"周期 {block['label']} 缺少 {miss:%m-%d} 的日期列",
                    block=block["label"],
                    date=miss,
                )
            )

    # ── A11 检修冲突：检修窗口内仍有移种计划 ──
    for window in windows:
        if window.tank_no not in FA_TANKS:
            continue
        for ev in facts.ferm_events:
            if ev.tank_no != window.tank_no:
                continue
            if ev.start.date() < max(window.started_on, scope_from):
                continue
            if window.recovery_on is None:
                issues.append(
                    _Issue(
                        level="warn",
                        rule="maintenance_conflict",
                        text=(
                            f"{window.tank_no} 检修中（自 {window.started_on:%m-%d}），"
                            f"但 {ev.start:%m-%d} 仍排有 {ev.batch_no} 移种；"
                            "请补填预计恢复日期并确认检修可如期完成"
                        ),
                        block=ev.block_label,
                        date=ev.start.date(),
                        tank_no=ev.tank_no,
                        batch_no=ev.batch_no,
                    )
                )
            elif ev.start.date() <= window.recovery_on:
                issues.append(
                    _Issue(
                        level="warn",
                        rule="maintenance_conflict",
                        text=(
                            f"{window.tank_no} 预计 {window.recovery_on:%m-%d} 恢复，"
                            f"但 {ev.start:%m-%d} 已排 {ev.batch_no} 移种，"
                            "落在检修窗口内"
                        ),
                        block=ev.block_label,
                        date=ev.start.date(),
                        tank_no=ev.tank_no,
                        batch_no=ev.batch_no,
                    )
                )

    # ── A12 跨周期在制断链：上份表在制批次在新表缺放罐 ──
    if prev_facts is not None:
        prev_dump_map = {ev.batch_no: ev for ev in prev_facts.dump_events}
        prev_events: dict[str, _FermEvent] = {}
        for ev in prev_facts.ferm_events:
            known = prev_events.get(ev.batch_no)
            if known is None or ev.start < known.start:
                prev_events[ev.batch_no] = ev
        for batch_no, ev in prev_events.items():
            if batch_no in prev_dump_map or batch_no in dump_by_batch:
                continue
            expected = _expected_dump_date(ev.start)
            if (
                facts.coverage_start is None
                or expected < facts.coverage_start
                or expected > facts.coverage_end
            ):
                continue
            issues.append(
                _Issue(
                    level="warn",
                    rule="inflight_continuity",
                    text=(
                        f"上一份排产中批次 {batch_no}（{ev.start:%m-%d} 移种"
                        f"{ev.tank_no}）已移种未放罐，预计 {expected:%m-%d} 放罐，"
                        "但本表覆盖该日却未见其放罐安排"
                    ),
                    block=None,
                    date=expected,
                    tank_no=ev.tank_no,
                    batch_no=batch_no,
                )
            )

    # ── C16a 废弃种子留痕（检修窗口内静默）──
    discard_days: set[date] = set()
    for seed in facts.seed_events:
        if seed.at.date() < scope_from:
            continue
        if (
            seed.batch_no in ferm_by_batch
            or seed.batch_no in prev_ferm_batches
        ):
            continue
        expected_transfer = seed.at.date() + timedelta(
            days=SEED_TRANSFER_GAP_DAYS
        )
        if (
            facts.coverage_end is not None
            and expected_transfer > facts.coverage_end
        ):
            continue
        discard_days.add(expected_transfer)
        if _any_maintenance_covers(windows, expected_transfer):
            continue  # 配合检修的合法废种，不提示
        issues.append(
            _Issue(
                level="info",
                rule="seed_discarded",
                text=(
                    f"种子 {seed.batch_no}（{seed.at:%m-%d} 接种）次日无移种位，"
                    "按 OD 要求将废弃；若为有意留痕请确认"
                ),
                block=seed.block_label,
                date=seed.at.date(),
                batch_no=seed.batch_no,
            )
        )

    # ── C17 无放罐日（检修/废种造成的洞不重复提示）──
    gap_days = (
        max(1, round(standard / 24)) if standard else DEFAULT_DUMP_GAP_DAYS
    )
    dump_dates = {ev.at.date() for ev in facts.dump_events}
    ferm_dates = {ev.start.date() for ev in facts.ferm_events}
    day_notes = {
        cell.date: cell.note for cell in facts.day_cells if cell.note
    }
    if facts.coverage_end is not None:
        for block in scope_blocks:
            day = block["start"]
            while day <= block["end"]:
                check_day = day
                day = day + timedelta(days=1)
                if check_day < scope_from or check_day > (
                    facts.coverage_end or check_day
                ):
                    continue
                if check_day in dump_dates:
                    continue
                cause_day = check_day - timedelta(days=gap_days)
                if cause_day in ferm_dates or cause_day in discard_days:
                    continue  # 洞的成因已被前序规则覆盖或属合法废种
                if cause_day < (facts.coverage_start or cause_day):
                    continue  # 成因在上一份表，无法核实
                if _any_maintenance_covers(windows, cause_day):
                    continue  # 检修窗口内少移种一日，属合法扰动
                cause_note = day_notes.get(cause_day, "")
                if "跳过" in cause_note or "无空闲罐" in cause_note:
                    continue  # 备注标注的计划性跳过/罐占用（如自动排产草稿指令）
                issues.append(
                    _Issue(
                        level="info",
                        rule="no_dump_day",
                        text=(
                            f"{check_day:%m-%d} 当日无任何放罐安排，"
                            "且未见检修或废种等成因，请确认是否漏排"
                        ),
                        block=block["label"],
                        date=check_day,
                    )
                )

    # ── B15 计划批数偏差 ──
    if dump_target is not None:
        for block in scope_blocks:
            batches = {
                ev.batch_no
                for ev in facts.dump_events
                if ev.block_label == block["label"]
            }
            if len(batches) != dump_target:
                issues.append(
                    _Issue(
                        level="info",
                        rule="dump_target_deviation",
                        text=(
                            f"周期 {block['label']} 计划放罐 {len(batches)} 批，"
                            f"与月计划目标 {dump_target} 批不一致，请核对"
                        ),
                        block=block["label"],
                    )
                )

    # ── C18 非标准时刻（牵动提炼节奏与蒸汽安排）──
    for ev in facts.ferm_events:
        if ev.start.date() < scope_from or not ev.time_ok:
            continue
        if ev.start.time() != STANDARD_FERM_TIME:
            issues.append(
                _Issue(
                    level="info",
                    rule="nonstandard_time",
                    text=f"批次 {ev.batch_no} 移种时刻 {ev.start:%H:%M} 非惯用 21:00",
                    block=ev.block_label,
                    date=ev.start.date(),
                    tank_no=ev.tank_no,
                    batch_no=ev.batch_no,
                )
            )
    for dump_ev in facts.dump_events:
        if dump_ev.at.date() < scope_from or not dump_ev.time_ok:
            continue
        if dump_ev.at.time() != STANDARD_DUMP_TIME:
            issues.append(
                _Issue(
                    level="info",
                    rule="nonstandard_time",
                    text=(
                        f"批次 {dump_ev.batch_no} 放罐时刻 {dump_ev.at:%H:%M}"
                        " 非惯用 10:00"
                    ),
                    block=dump_ev.block_label,
                    date=dump_ev.at.date(),
                    tank_no=dump_ev.tank_no or None,
                    batch_no=dump_ev.batch_no,
                )
            )

    # ── C19 批号格式与整列空提示 ──
    seen_batches: set[str] = set()
    for cell in facts.day_cells:
        if cell.date < scope_from or cell.block_label not in scope_block_labels:
            continue
        for batch in (cell.seed_batch, cell.ferm_batch, cell.dump_batch):
            if batch and batch not in seen_batches:
                seen_batches.add(batch)
                if not FA_BATCH_RE.match(batch):
                    issues.append(
                        _Issue(
                            level="info",
                            rule="batch_format",
                            text=f"批号“{batch}”与常见格式（FA+数字）不符，请核对",
                            block=cell.block_label,
                            date=cell.date,
                            batch_no=batch,
                        )
                    )
        if not (
            cell.seed_batch or cell.ferm_batch or cell.dump_batch or cell.note
        ):
            issues.append(
                _Issue(
                    level="info",
                    rule="empty_column",
                    text=f"{cell.date:%m-%d} 整列未排产（无种子/移种/放罐/备注）",
                    block=cell.block_label,
                    date=cell.date,
                )
            )

    # ── C20 约束未配置说明 ──
    skipped: list[str] = []
    if standard is None or tolerance is None:
        skipped.append("培养周期偏离提示")
    if max_cycle is None:
        skipped.append("培养周期超上限检查")
    if turnaround is None:
        skipped.append("罐周转不足检查")
    if dump_target is None:
        skipped.append("月计划批数核对")
    if skipped:
        issues.append(
            _Issue(
                level="info",
                rule="constraint_missing",
                text=(
                    "以下检查因排产约束未配置被跳过："
                    + "、".join(skipped)
                    + "（在排产计划页「排产约束」卡片维护）"
                ),
            )
        )

    issues.sort(
        key=lambda i: (
            0 if i.level == "warn" else 1,
            i.date or date.max,
            i.rule,
        )
    )
    return {
        "scope": {
            "from": scope_from.isoformat(),
            "blocks": validated_labels,
        },
        "coverage": {
            "start": facts.coverage_start.isoformat(),
            "end": facts.coverage_end.isoformat(),
        },
        "issues": [i.as_dict() for i in issues],
        "summary": {
            "warn": sum(1 for i in issues if i.level == "warn"),
            "info": sum(1 for i in issues if i.level == "info"),
        },
        "constraints": constraints or None,
    }


# ═══════════════════ 约束配置存取 ═══════════════════


async def get_constraint_setting(
    session: AsyncSession, product_code: str
) -> ScheduleConstraintSetting | None:
    result = await session.execute(
        select(ScheduleConstraintSetting).where(
            ScheduleConstraintSetting.product_code == product_code,
            ScheduleConstraintSetting.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


def serialize_constraint_setting(item: ScheduleConstraintSetting) -> dict[str, Any]:
    return {
        "product_code": item.product_code,
        "standard_cycle_hours": item.standard_cycle_hours,
        "cycle_tolerance_hours": item.cycle_tolerance_hours,
        "max_cycle_hours": item.max_cycle_hours,
        "turnaround_hours": item.turnaround_hours,
        "monthly_dump_target": item.monthly_dump_target,
    }


def empty_constraint_setting(product_code: str) -> dict[str, Any]:
    return {
        "product_code": product_code,
        "standard_cycle_hours": None,
        "cycle_tolerance_hours": None,
        "max_cycle_hours": None,
        "turnaround_hours": None,
        "monthly_dump_target": None,
    }


async def upsert_constraint_setting(
    session: AsyncSession,
    *,
    product_code: str,
    standard_cycle_hours: float | None,
    cycle_tolerance_hours: float | None,
    max_cycle_hours: float | None,
    turnaround_hours: float | None,
    monthly_dump_target: int | None,
    updated_by: Any = None,
) -> ScheduleConstraintSetting:
    """按产品 upsert 约束配置（同一产品仅一条未删除记录）。"""
    if (
        standard_cycle_hours is not None
        and max_cycle_hours is not None
        and max_cycle_hours < standard_cycle_hours
    ):
        raise ValueError("最大培养周期不能小于标准培养周期")
    item = await get_constraint_setting(session, product_code)
    if item is None:
        item = ScheduleConstraintSetting(
            product_code=product_code,
            standard_cycle_hours=standard_cycle_hours,
            cycle_tolerance_hours=cycle_tolerance_hours,
            max_cycle_hours=max_cycle_hours,
            turnaround_hours=turnaround_hours,
            monthly_dump_target=monthly_dump_target,
            created_by=updated_by,
        )
        session.add(item)
    else:
        item.standard_cycle_hours = standard_cycle_hours
        item.cycle_tolerance_hours = cycle_tolerance_hours
        item.max_cycle_hours = max_cycle_hours
        item.turnaround_hours = turnaround_hours
        item.monthly_dump_target = monthly_dump_target
        item.updated_by = updated_by
    await session.commit()
    await session.refresh(item)
    return item


# ═══════════════════ 报告编排 ═══════════════════


async def build_validation_report(
    session: AsyncSession,
    archive: ScheduleExcelArchive,
    *,
    now: datetime,
) -> dict[str, Any]:
    """组装某存档的校验报告：约束 + 检修 + 上一份存档 + 存档行。"""
    constraints = await get_constraint_setting(session, archive.product_code)
    maintenance = [
        board.serialize_maintenance(item)
        for item in await board.list_active_maintenance(session)
    ]
    previous = await _load_previous_archive(session, archive)
    return validate_schedule_rows(
        archive.rows,
        previous_rows=previous.rows if previous else None,
        constraints=(
            serialize_constraint_setting(constraints)
            if constraints
            else empty_constraint_setting(archive.product_code)
        ),
        maintenance=maintenance,
        now=now,
    )


async def _load_previous_archive(
    session: AsyncSession, archive: ScheduleExcelArchive
) -> ScheduleExcelArchive | None:
    """同产品中创建时间早于本档的最近一份未删除存档。"""
    result = await session.execute(
        select(ScheduleExcelArchive)
        .where(
            ScheduleExcelArchive.product_code == archive.product_code,
            ScheduleExcelArchive.is_deleted.is_(False),
            ScheduleExcelArchive.id != archive.id,
            ScheduleExcelArchive.created_at < archive.created_at,
        )
        .order_by(ScheduleExcelArchive.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
