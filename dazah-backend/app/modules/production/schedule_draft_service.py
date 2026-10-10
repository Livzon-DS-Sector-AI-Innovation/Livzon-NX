"""FA 排产草稿生成器（二期）。

从最新 FA 排产存档推导期初状态（在制批次占用、轮转节奏、批号水位），
按领域规则确定性逐日模拟生成目标扎帐周期的排产草稿：每天 20:00 接种
（前瞻次日有可用罐才接种，避免废种）、次日 21:00 移种给「先空闲」的罐、
移种后第 3 天 10:00 同罐放罐。支持两条调整指令：按天跳过（空拍自动摊匀）
与罐占用窗口（检修/停用）。领域规则见 docs/production-fa-scheduling-rules.md。

草稿不落库、不生效：输出结构化预览 + 一期校验报告（应零 warn）+
与现行排产表逐行同构的单周期块 Excel（openpyxl，时间为文本格式，
保证现有上传解析器可原样读回），由排产员修改后走排产计划页上传。
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.production import fermentation_board_service as board
from app.modules.production import schedule_validation_service as validation
from app.modules.production.schedule_draft_models import ScheduleDraftRecord

SEED_TIME = time(20, 0)
TRANSFER_TIME = time(21, 0)
DUMP_TIME = time(10, 0)
# 移种 → 放罐的间隔天数（21:00 → 第 3 天 10:00，约 61h）
DUMP_GAP_DAYS = 3
# 批号模式：FA + 4~6 位数字（与一期校验器同口径），续号取最大序号 +1
FA_BATCH_RE = re.compile(r"^FA(\d{4,6})$")


# ═══════════════════ 请求参数与期初状态 ═══════════════════


@dataclass
class TankBlock:
    """罐占用窗口：该罐在 [from_date, to_date] 内不安排移种。"""

    tank_no: str
    from_date: date
    to_date: date

    def covers(self, day: date) -> bool:
        return self.from_date <= day <= self.to_date


@dataclass
class DraftParams:
    """草稿生成参数（周期由调用方解析，缺省为下一扎帐周期）。"""

    period_start: date
    period_end: date
    batch_start_no: int | None = None
    skip_dates: set[date] = field(default_factory=set)
    tank_blocks: list[TankBlock] = field(default_factory=list)


@dataclass
class InflightBatch:
    """上期在制批次：已移种、放罐落在草稿周期内。"""

    batch_no: str
    tank_no: str
    inoculated_at: datetime
    dump_at: datetime


def next_accounting_period(today: date) -> tuple[date, date]:
    """今天之后的下一个扎帐周期（27 日～次月 26 日）。"""
    start = board.unified_accounting_period(today)[1] + timedelta(days=1)
    end = board.unified_accounting_period(start)[1]
    return start, end


@dataclass
class _TankState:
    """模拟中的罐状态。"""

    tank_no: str
    # 可再次移种的最早时刻（上批放罐窗口结束 + 周转）
    free_at: datetime
    # 上次移种时刻（同刻多罐可用时，久未接罐者优先，空拍摊匀）
    last_inoculated_at: datetime | None = None


def _derive_initial_state(
    archive_rows: list[list[Any]],
    period_start: date,
    turnaround_hours: float | None,
) -> tuple[
    list[InflightBatch],
    list[_TankState],
    int | None,
    str | None,
    list[str],
    str | None,
]:
    """从最新存档推导在制批次、罐初始状态、批号水位与待进罐种子。

    - 在制批次：全表移种事件中，放罐落在草稿周期内的批次（放罐按存档
      排产放罐日 10:00；无放罐行的按移种 +3 天兜底）。
    - 罐初始空闲时刻：该罐最后一个在制批次的放罐窗口结束 + 周转；
      无在制占用的罐为自由态（最优先接罐）。
    - 批号水位：FA+数字 批号的最大数字（无匹配返回 None）。
    - 待进罐种子：周期首日的前一天已接种、尚无移种记录的批次
      （上期末为草稿首日备好的种子；无则首日无移种）。
    """
    ferm_events = board.collect_ferm_events(archive_rows)
    dump_dates = board.collect_dump_dates(archive_rows)
    inflight: list[InflightBatch] = []
    tank_latest: dict[str, tuple[datetime, datetime]] = {}
    max_seq: int | None = None
    turnaround = timedelta(hours=turnaround_hours or 0)
    ferm_batches = {event["batch_no"] for event in ferm_events}
    for event in ferm_events:
        match = FA_BATCH_RE.match(event["batch_no"])
        if match:
            seq = int(match.group(1))
            max_seq = seq if max_seq is None else max(max_seq, seq)
        dump_day = dump_dates.get(event["batch_no"])
        if dump_day is not None and dump_day < period_start:
            continue
        if dump_day is None:
            dump_day = event["start"].date() + timedelta(days=DUMP_GAP_DAYS)
        dump_at = datetime.combine(dump_day, DUMP_TIME)
        if dump_at.date() < period_start:
            continue
        inflight.append(
            InflightBatch(
                batch_no=event["batch_no"],
                tank_no=event["tank_no"],
                inoculated_at=event["start"],
                dump_at=dump_at,
            )
        )
        free_at = dump_at + board.DUMP_WINDOW + turnaround
        known = tank_latest.get(event["tank_no"])
        if known is None or free_at > known[0]:
            tank_latest[event["tank_no"]] = (free_at, event["start"])
    states = [
        _TankState(
            tank_no=tank,
            free_at=free_at,
            last_inoculated_at=last_inoc,
        )
        for tank, (free_at, last_inoc) in tank_latest.items()
    ]
    for tank in board.FERMENT_TANKS:
        if not any(s.tank_no == tank for s in states):
            states.append(
                _TankState(tank_no=tank, free_at=datetime.min, last_inoculated_at=None)
            )
    states.sort(key=lambda s: s.tank_no)
    # 种子行批号同样计入水位（上期末备好的种子号不能被重编）；
    # 周期首日前一日接种且无移种记录的种子 = 草稿首日待进罐批次；
    # 种子罐号沿用上期惯例（如 201A/202A 逐日轮转），从最后一粒续起
    prepared_seed: str | None = None
    seed_tanks: dict[str, None] = {}
    last_seed_tank: str | None = None
    last_seed_tank_date: date | None = None
    eve = period_start - timedelta(days=1)
    for row_index, row in enumerate(archive_rows):
        if not row:
            continue
        span = board.parse_period_title(str(row[0]))
        if not span:
            continue
        block = {"start_row": row_index, "start": span[0], "end": span[1], "label": ""}
        for event in board._seed_events(board.parse_block(archive_rows, block)["days"]):
            match = FA_BATCH_RE.match(event["batch_no"])
            if match:
                seq = int(match.group(1))
                max_seq = seq if max_seq is None else max(max_seq, seq)
            tank = str(event.get("tank_no") or "")
            if tank:
                seed_tanks.setdefault(tank, None)
                event_date = event["start"].date()
                if last_seed_tank_date is None or event_date >= last_seed_tank_date:
                    last_seed_tank = tank
                    last_seed_tank_date = event_date
            if (
                event["start"].date() == eve
                and event["batch_no"] not in ferm_batches
            ):
                prepared_seed = event["batch_no"]
    return (
        inflight,
        states,
        max_seq,
        prepared_seed,
        sorted(seed_tanks),
        last_seed_tank,
    )


# ═══════════════════ 逐日模拟 ═══════════════════


@dataclass
class DraftDay:
    """草稿中某日的排产事件（种子/移种/放罐，均可为空）。"""

    date: date
    seed_batch: str | None = None
    seed_tank: str | None = None  # 种子罐号（沿用上期轮转，如 201A/202A）
    seed_note: str = ""  # 未接种原因（次日跳过/无罐/周期末）
    transfer: tuple[str, str] | None = None  # (batch_no, tank_no)
    transfer_note: str = ""  # 未移种原因（跳过/种子废/无罐）
    dumps: list[tuple[str, str]] = field(default_factory=list)  # (batch, tank)
    dump_inflight: bool = False  # 放罐是否含上期在制批次
    # 当日 21:00 空闲却未接罐的罐（空拍罐·天统计口径）
    idle_tanks: list[str] = field(default_factory=list)


@dataclass
class DraftResult:
    days: list[DraftDay]
    rows: list[list[Any]]
    summary: dict[str, Any]


def _tank_blocked(blocks: list[TankBlock], tank_no: str, day: date) -> bool:
    return any(b.tank_no == tank_no and b.covers(day) for b in blocks)


def simulate_draft(
    params: DraftParams,
    inflight: list[InflightBatch],
    tank_states: list[_TankState],
    batch_start_no: int,
    turnaround_hours: float | None,
    prepared_seed: str | None = None,
    seed_tanks: list[str] | None = None,
    last_seed_tank: str | None = None,
) -> list[DraftDay]:
    """确定性逐日模拟目标周期，产出每日事件。

    种子前瞻：当天接种需确认次日 21:00 有罐可接（空闲 + 未被占用 +
    未跳过），否则计划性不接种，不产生废种。罐位选择：空闲且未被占用
    的罐中，上次移种最早者优先（延续上月轮转、空拍摊匀到各罐）。
    prepared_seed 为上期末备好、周期首日进罐的种子批号；
    种子罐号按 seed_tanks 池轮转（如 201A/202A 逐日交替），
    从 last_seed_tank 的下一台续起。
    """
    turnaround = timedelta(hours=turnaround_hours or 0)
    states = {s.tank_no: s for s in tank_states}
    seed_pool = seed_tanks or []
    seed_index = 0
    if seed_pool and last_seed_tank in seed_pool:
        seed_index = (seed_pool.index(last_seed_tank) + 1) % len(seed_pool)
    pending_seed: tuple[str, date] | None = (
        (prepared_seed, params.period_start - timedelta(days=1))
        if prepared_seed
        else None
    )
    dumps: list[tuple[str, str, datetime, bool]] = [
        (b.batch_no, b.tank_no, b.dump_at, True) for b in inflight
    ]
    next_seq = batch_start_no
    days: list[DraftDay] = []
    total = (params.period_end - params.period_start).days + 1

    def next_batch_no() -> str:
        nonlocal next_seq
        value = f"FA{next_seq}"
        next_seq += 1
        return value

    for offset in range(total):
        day = params.period_start + timedelta(days=offset)
        entry = DraftDay(date=day)

        # 放罐：放罐日落在本日的在制/草稿批次（同罐同批放罐=同罐）
        for batch, tank, dump_at, from_inflight in dumps:
            if dump_at.date() == day:
                entry.dumps.append((batch, tank))
                entry.dump_inflight = entry.dump_inflight or from_inflight

        # 当日 21:00 可接罐的候选（空闲 + 未被占用窗口）
        candidates = [
            s
            for s in states.values()
            if s.free_at <= datetime.combine(day, TRANSFER_TIME)
            and not _tank_blocked(params.tank_blocks, s.tank_no, day)
        ]

        # 移种（21:00）：昨日接种的种子进罐
        if pending_seed is not None and pending_seed[1] == day - timedelta(days=1):
            if day in params.skip_dates:
                entry.transfer_note = "跳过进罐日"
                entry.idle_tanks = [s.tank_no for s in candidates]
                pending_seed = None
            elif not candidates:
                entry.transfer_note = "无空闲罐（种子按废种留痕）"
                pending_seed = None
            else:
                chosen = min(
                    candidates,
                    key=lambda s: (s.last_inoculated_at or datetime.min, s.tank_no),
                )
                entry.transfer = (pending_seed[0], chosen.tank_no)
                dump_at = datetime.combine(
                    day + timedelta(days=DUMP_GAP_DAYS), DUMP_TIME
                )
                dumps.append((pending_seed[0], chosen.tank_no, dump_at, False))
                chosen.free_at = dump_at + board.DUMP_WINDOW + turnaround
                chosen.last_inoculated_at = datetime.combine(day, TRANSFER_TIME)
                entry.idle_tanks = [
                    s.tank_no for s in candidates if s.tank_no != chosen.tank_no
                ]
                pending_seed = None
        else:
            if day in params.skip_dates:
                entry.transfer_note = "跳过进罐日"
            elif pending_seed is None and not candidates:
                entry.transfer_note = "无空闲罐（罐占用）"
            elif pending_seed is None:
                entry.transfer_note = "无待进罐种子"
            entry.idle_tanks = [s.tank_no for s in candidates]

        # 接种（20:00）：前瞻次日有罐可接才接种。周期最后一天（26 日）
        # 的种子服务于下一周期首日进罐（车间惯例，见真实排产表），
        # 因此前瞻不做周期末截断，保证期与期之间的种子链不断
        tomorrow = day + timedelta(days=1)
        if pending_seed is not None:
            pass  # 今日种子已种，等明日进罐（上面分支已处理昨日种子）
        elif tomorrow in params.skip_dates:
            entry.seed_note = "次日跳过进罐，不接种"
        elif any(
            s.free_at <= datetime.combine(tomorrow, TRANSFER_TIME)
            and not _tank_blocked(params.tank_blocks, s.tank_no, tomorrow)
            for s in states.values()
        ):
            entry.seed_batch = next_batch_no()
            if seed_pool:
                entry.seed_tank = seed_pool[seed_index % len(seed_pool)]
                seed_index += 1
            pending_seed = (entry.seed_batch, day)
        else:
            entry.seed_note = "次日无空闲罐，不接种"

        days.append(entry)
    return days


# ═══════════════════ 排产表组装与摘要 ═══════════════════


def _split_accounting_periods(
    period_start: date, period_end: date
) -> list[tuple[date, date]]:
    """把草稿周期按扎帐周期（27 日～次月 26 日）切块。

    跨月草稿按块输出，与现行滚动多周期排产表格式一致；罐位轮转在
    块与块之间连续（调用方用整段日期模拟，这里只负责分块展示）。
    """
    periods: list[tuple[date, date]] = []
    cursor = period_start
    while cursor <= period_end:
        block_end = board.unified_accounting_period(cursor)[1]
        periods.append((cursor, min(block_end, period_end)))
        cursor = block_end + timedelta(days=1)
    return periods


def _build_block_rows(
    days: list[DraftDay], block_start: date, block_end: date
) -> list[list[Any]]:
    """组装单个周期块（一天一列，数据从第 3 列起）。

    行布局与 fermentation_board_service._ROW_* 偏移一致：标题/日期/
    表头/种子批号/种子罐号/接种时间/发酵批号/发酵罐号/移种时间/放罐批号/
    放罐罐号/放罐时间/备注。时间为文本（"21:00"），确保上传解析器
    `_parse_time` 可原样读回（真实时间对象会被序列化成 HH:MM:SS）。
    同日多批放罐时放罐行只落第一批（按批号序），其余在备注行提示。
    """
    dump_count = sum(len(d.dumps) for d in days)
    width = len(days) + 2
    seed_batches = [d.seed_batch or "" for d in days]
    seed_tank_cells = [d.seed_tank or "" for d in days]
    ferm_batches = [d.transfer[0] if d.transfer else "" for d in days]
    ferm_tanks = [d.transfer[1] if d.transfer else "" for d in days]
    ordered_dumps = [sorted(d.dumps) for d in days]
    dump_batches = [d[0][0] if d else "" for d in ordered_dumps]
    dump_tanks = [d[0][1] if d else "" for d in ordered_dumps]
    notes: list[str] = []
    for index, entry in enumerate(days):
        extra = ordered_dumps[index][1:]
        if extra:
            notes.append(
                "同日多批放罐，仅列首批：" + "、".join(b for b, _t in extra)
            )
        elif entry.transfer_note and entry.transfer_note != "无待进罐种子":
            notes.append(entry.transfer_note)
        elif "不接种" in entry.seed_note:
            notes.append(entry.seed_note)
        else:
            notes.append("")
    # 说明：备注行同时承载跳过/占用成因，一期校验器的无放罐日规则据此
    # 把这类计划性空档判为合法，不再提示确认
    return [
        [
            (
                f"{block_start.year}年{block_start.month}月{block_start.day}日～"
                f"{block_end.year}年{block_end.month}月{block_end.day}日"
                "103车间FA450T罐排产"
            )
        ]
        + [""] * (width - 1),
        ["", "日期"] + [d.date.day for d in days],
        ["时间", "罐号"] + [""] * len(days),
        ["种子罐", ""] + seed_batches,
        ["罐号", ""] + seed_tank_cells,
        ["接种时间", ""] + ["20:00" if b else "" for b in seed_batches],
        ["发酵罐", ""] + ferm_batches,
        ["罐号", ""] + ferm_tanks,
        ["移种时间", ""] + ["21:00" if b else "" for b in ferm_batches],
        ["放罐", ""] + dump_batches,
        ["罐号", ""] + dump_tanks,
        ["放罐时间", ""] + ["10:00" if b else "" for b in dump_batches],
        ["备注", f"{block_start.month}月共放罐{dump_count}批"] + notes,
        [""] * width,
    ]


def build_draft_rows(
    days: list[DraftDay], period_start: date, period_end: date
) -> list[list[Any]]:
    """按现行 FA 排产表格式组装草稿行：每个扎帐周期一块，逐块摞放。"""
    rows: list[list[Any]] = []
    for block_start, block_end in _split_accounting_periods(
        period_start, period_end
    ):
        block_days = [d for d in days if block_start <= d.date <= block_end]
        rows.extend(_build_block_rows(block_days, block_start, block_end))
    return rows


def build_summary(
    days: list[DraftDay],
    params: DraftParams,
    inflight: list[InflightBatch],
    turnaround_hours: float | None,
    dump_target: int | None,
) -> dict[str, Any]:
    """草稿摘要：批数/种子/跳过/空拍与目标对比，供预览与决策。"""
    return {
        "period": {
            "start": params.period_start.isoformat(),
            "end": params.period_end.isoformat(),
        },
        "transfer_count": sum(1 for d in days if d.transfer),
        "seed_count": sum(1 for d in days if d.seed_batch),
        "dump_count": sum(len(d.dumps) for d in days),
        "dump_target": dump_target,
        "skip_dates": sorted(d.isoformat() for d in params.skip_dates),
        "no_seed_days": [
            d.date.isoformat() for d in days if "不接种" in d.seed_note
        ],
        # 空拍罐·天：当日 21:00 空闲可接却未接罐的罐数合计（稳态为 0）
        "idle_tank_days": sum(len(d.idle_tanks) for d in days),
        "tank_blocks": [
            {
                "tank_no": b.tank_no,
                "from_date": b.from_date.isoformat(),
                "to_date": b.to_date.isoformat(),
            }
            for b in params.tank_blocks
        ],
        "inflight_batches": [
            {"batch_no": b.batch_no, "tank_no": b.tank_no} for b in inflight
        ],
        "turnaround_hours": turnaround_hours,
    }


# ═══════════════════ 编排与 Excel ═══════════════════


def generate_draft(
    archive_rows: list[list[Any]],
    params: DraftParams,
    *,
    constraints: dict[str, Any] | None = None,
) -> DraftResult:
    """编排：期初推导 → 逐日模拟 → 组装排产行与摘要。"""
    constraints = constraints or {}
    turnaround_hours = constraints.get("turnaround_hours")
    (
        inflight,
        tank_states,
        watermark,
        prepared_seed,
        seed_tanks,
        last_seed_tank,
    ) = _derive_initial_state(
        archive_rows, params.period_start, turnaround_hours
    )
    days = simulate_draft(
        params,
        inflight,
        tank_states,
        params.batch_start_no or (watermark + 1 if watermark else 1),
        turnaround_hours,
        prepared_seed=prepared_seed,
        seed_tanks=seed_tanks,
        last_seed_tank=last_seed_tank,
    )
    rows = build_draft_rows(days, params.period_start, params.period_end)
    summary = build_summary(
        days,
        params,
        inflight,
        turnaround_hours,
        constraints.get("monthly_dump_target"),
    )
    return DraftResult(days=days, rows=rows, summary=summary)


def validate_draft(
    result: DraftResult,
    archive_rows: list[list[Any]],
    *,
    constraints: dict[str, Any] | None = None,
    maintenance: list[dict[str, Any]] | None = None,
    now: datetime,
) -> dict[str, Any]:
    """对草稿跑一期校验器（上份存档 = 最新 FA 存档，覆盖跨周期衔接）。"""
    return validation.validate_schedule_rows(
        result.rows,
        previous_rows=archive_rows,
        constraints=constraints,
        maintenance=maintenance,
        now=now,
    )


def build_draft_workbook(result: DraftResult) -> BytesIO:
    """草稿行 → xlsx 工作簿字节流（文本时间保证解析器可读回）。"""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "排产草稿"
    for row in result.rows:
        sheet.append(list(row))
    sheet.column_dimensions["A"].width = 10
    sheet.column_dimensions["B"].width = 10
    for index in range(3, len(result.rows[0]) + 1):
        sheet.column_dimensions[get_column_letter(index)].width = 8
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════ 生成历史（工作台记录，不生效） ═══════════════════

_DRAFT_UPLOAD_SUB_DIR = "schedule_drafts"


def _canonical_params(params: DraftParams) -> dict[str, Any]:
    """归一化参数（对齐后周期 + 排序后的指令），用于落库与去重指纹。"""
    return {
        "period_start": params.period_start.isoformat(),
        "period_end": params.period_end.isoformat(),
        "batch_start_no": params.batch_start_no,
        "skip_dates": sorted(d.isoformat() for d in params.skip_dates),
        "tank_blocks": [
            {
                "tank_no": b.tank_no,
                "from_date": b.from_date.isoformat(),
                "to_date": b.to_date.isoformat(),
            }
            for b in sorted(
                params.tank_blocks, key=lambda b: (b.tank_no, b.from_date)
            )
        ],
    }


def _days_payload(result: DraftResult) -> list[dict[str, Any]]:
    return [
        {
            "date": entry.date.isoformat(),
            "seed_batch": entry.seed_batch,
            "seed_tank": entry.seed_tank,
            "seed_note": entry.seed_note,
            "transfer": (
                {"batch_no": entry.transfer[0], "tank_no": entry.transfer[1]}
                if entry.transfer
                else None
            ),
            "transfer_note": entry.transfer_note,
            "dumps": [
                {"batch_no": batch, "tank_no": tank} for batch, tank in entry.dumps
            ],
            "dump_inflight": entry.dump_inflight,
            "idle_tanks": entry.idle_tanks,
        }
        for entry in result.days
    ]


def _save_draft_file(workbook_bytes: bytes) -> str:
    """导出文件落盘 uploads/schedule_drafts/，返回相对路径。"""
    base = Path(get_settings().UPLOAD_DIR)
    directory = base / _DRAFT_UPLOAD_SUB_DIR
    directory.mkdir(parents=True, exist_ok=True)
    object_name = f"{uuid.uuid4().hex}.xlsx"
    (directory / object_name).write_bytes(workbook_bytes)
    return f"{_DRAFT_UPLOAD_SUB_DIR}/{object_name}"


async def upsert_draft_record(
    session: AsyncSession,
    *,
    product_code: str,
    params: DraftParams,
    result: DraftResult,
    validation_report: dict[str, Any],
    workbook_bytes: bytes | None = None,
    file_name: str | None = None,
    operator_id: Any = None,
) -> ScheduleDraftRecord:
    """落一条生成历史；同参数（指纹一致）去重更新，导出时附文件。

    预览（generate）与导出（export）共用：预览仅刷新快照，
    导出额外保存 Excel 文件并记录 downloaded_at。
    """
    canonical = _canonical_params(params)
    digest = hashlib.md5(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    found = await session.execute(
        select(ScheduleDraftRecord).where(
            ScheduleDraftRecord.product_code == product_code,
            ScheduleDraftRecord.params_hash == digest,
            ScheduleDraftRecord.is_deleted.is_(False),
        )
    )
    record = found.scalar_one_or_none()
    if record is None:
        record = ScheduleDraftRecord(
            product_code=product_code,
            params=canonical,
            params_hash=digest,
            days=_days_payload(result),
            summary=result.summary,
            validation=validation_report,
            created_by=operator_id,
        )
        session.add(record)
    else:
        record.params = canonical
        record.days = _days_payload(result)
        record.summary = result.summary
        record.validation = validation_report
        record.updated_by = operator_id
    if workbook_bytes is not None and file_name:
        record.file_name = file_name
        record.original_path = _save_draft_file(workbook_bytes)
        record.downloaded_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(record)
    return record


def serialize_draft_record_summary(
    item: ScheduleDraftRecord, created_by_name: str | None = None
) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "product_code": item.product_code,
        "params": item.params,
        "summary": item.summary,
        "downloaded_at": (
            item.downloaded_at.isoformat() if item.downloaded_at else None
        ),
        "file_name": item.file_name,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "created_by_name": created_by_name,
    }


def serialize_draft_record_detail(
    item: ScheduleDraftRecord, created_by_name: str | None = None
) -> dict[str, Any]:
    data = serialize_draft_record_summary(item, created_by_name)
    data["days"] = item.days
    data["validation"] = item.validation
    return data


async def list_draft_records(
    session: AsyncSession,
    *,
    product_code: str,
    page: int,
    page_size: int,
) -> tuple[list[tuple[ScheduleDraftRecord, str | None]], int]:
    from app.modules.production.schedule_excel_service import get_user_name

    count_result = await session.execute(
        select(func.count())
        .select_from(ScheduleDraftRecord)
        .where(
            ScheduleDraftRecord.product_code == product_code,
            ScheduleDraftRecord.is_deleted.is_(False),
        )
    )
    total = int(count_result.scalar() or 0)
    result = await session.execute(
        select(ScheduleDraftRecord)
        .where(
            ScheduleDraftRecord.product_code == product_code,
            ScheduleDraftRecord.is_deleted.is_(False),
        )
        .order_by(ScheduleDraftRecord.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    names: dict[Any, str | None] = {}
    for user_id in {item.created_by for item in items if item.created_by}:
        names[user_id] = await get_user_name(session, user_id)
    return [(item, names.get(item.created_by)) for item in items], total


async def get_draft_record(
    session: AsyncSession, record_id: Any
) -> ScheduleDraftRecord | None:
    result = await session.execute(
        select(ScheduleDraftRecord).where(
            ScheduleDraftRecord.id == record_id,
            ScheduleDraftRecord.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def soft_delete_draft_record(
    session: AsyncSession,
    item: ScheduleDraftRecord,
    *,
    deleted_by: Any = None,
) -> None:
    item.is_deleted = True
    item.updated_by = deleted_by
    await session.commit()
