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

import calendar
import logging
import re
from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
from functools import partial
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.fermentation_batch_actual_models import (
    FermentationBatchActual,
)
from app.modules.production.fermentation_month_setting_models import (
    FermentationMonthSetting,
)
from app.modules.production.models import ProductionLineStatus, ProductionPlan
from app.modules.production.schedule_excel_models import ScheduleExcelArchive
from app.modules.production.tank_maintenance_models import TankMaintenance

FERMENT_TANKS = ("302A", "303A", "304A")

logger = logging.getLogger(__name__)

# 「提炼已出成品（仓储成品入库）」卡片：看板产品代码 → 仓储成品入库总账产品名。
# 仅维护已接入产品；未在映射内的产品卡片维持"数据源待接入"。
WAREHOUSE_INBOUND_PRODUCT_NAMES: dict[str, str] = {
    "FA": "L-苯丙氨酸",
    "MC": "霉酚酸",
    "DR": "多拉菌素",
    "LV": "洛伐他汀",
    "MV": "美伐他汀",
    "TY": "L-色氨酸",
    "FL": "2%氟苯尼考预混剂",
}

# 支持停产状态的产品生产线（与提炼已出成品卡同一产品集合）
PRODUCTION_LINE_CODES = frozenset(WAREHOUSE_INBOUND_PRODUCT_NAMES)

# 放罐窗口：计划放罐时间起 2 小时内为「放罐中」（批次仍在罐上，不算完成）；
# 窗口结束后批次才视为「已放罐/完成」（罐状态、recent 最近完成、完成 KPI 同口径）。
DUMP_WINDOW = timedelta(hours=2)

# 漏录提醒：批次过放罐窗口超 24h 仍未录产量 → info；超 72h 升级 warn
YIELD_ENTRY_GRACE_HOURS = 24
YIELD_ENTRY_WARN_HOURS = 72
# 周期末进度预警：周期剩余 ≤7 天且已录产量进度落后时间进度 ≥10 个百分点
PROGRESS_WARN_DAYS = 7
PROGRESS_LAG_PCT = 10
# 下周期排产提醒：当前周期剩余 ≤3 天且无存档覆盖下一周期
SCHEDULE_UPLOAD_WARN_DAYS = 3

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
_ROW_NOTE = 12       # 排产备注

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
    notes = col_list(_ROW_NOTE)
    # 备注行第 2 格为周期级汇总备注（如"1.09月共放罐31批"），第 3 格起为按日期备注
    note_row = (
        rows[start_row + _ROW_NOTE]
        if start_row + _ROW_NOTE < len(rows)
        else []
    )
    block_note = (
        str(note_row[1]).strip() if len(note_row) > 1 and note_row[1] else ""
    )

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
                "note": str(notes[ci]).strip(),
            }
        )
    return {"block": block, "days": parsed, "block_note": block_note}


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


def collect_dump_tanks(
    rows: list[list[Any]],
    product_code: str = "FA",
) -> dict[str, str]:
    """全表所有放罐批号 → 放罐罐号（跨块连续，批号唯一）。

    FA/MP/DR 排产表布局不同，按产品分派解析；供批次产量列表回填罐号。
    """
    if product_code == "DR":
        batches, _, _ = _dr_parse_batches(rows)
        return {
            b["batch_no"]: str(b["dump_tank"] or b["ferm_tank"] or "")
            for b in batches
            if b["batch_no"] and (b["dump_tank"] or b["ferm_tank"])
        }
    # MP 与克隆其看板管线的他汀产品（LV 洛伐他汀 / MV 美伐他汀）同分支
    if product_code in ("MC", "LV", "MV"):
        timeline = (
            _statin_batch_timeline(rows)
            if product_code in _STATIN_KEYWORD
            else _mp_batch_timeline(rows)
        )
        return {
            batch_no: str(entry["dump_tank"] or entry["ferm_tank"] or "")
            for batch_no, entry in timeline.items()
            if entry["dump_tank"] or entry["ferm_tank"]
        }
    mapping: dict[str, str] = {}
    for index, row in enumerate(rows):
        if not row:
            continue
        span = parse_period_title(str(row[0]))
        if not span:
            continue
        days_row = rows[index + _ROW_DATE]
        col_dates = _col_dates(days_row, span[0])
        batches = _row_values(rows, index + _ROW_DUMP_BATCH)
        tanks = _row_values(rows, index + _ROW_DUMP_TANK)
        for ci, batch in enumerate(batches):
            batch_no = str(batch).strip()
            if batch_no and ci < len(col_dates):
                tank = str(tanks[ci]).strip() if ci < len(tanks) else ""
                mapping[batch_no] = tank
    return mapping


# ═══════════════════ 多拉菌素（DR）排产解析 ═══════════════════
# 102 车间排产格式：块标题「102车间2026年09月份多拉计划（09.05）」，
# 月份为扎帐归属（9月份 = 8月27日～9月26日）；块内日期行为自然月 1..N 日；
# 行布局（相对块首）：+1 日期 +2 菌种 +3 种子批号 +4 种子罐号
# +5 发酵（进罐）批号 +6 发酵罐号 +7 放罐批号 +8 放罐罐号
# +9 培养周期(h) +10 备注。无接种/放罐时刻，只有日期与培养周期。

_DR_TITLE_RE = re.compile(
    r"(\d{4})年(\d{1,2})月份多拉计划"
)
_DR_ROW_DATE = 1
_DR_ROW_FERM_BATCH = 5
_DR_ROW_FERM_TANK = 6
_DR_ROW_DUMP_BATCH = 7
_DR_ROW_DUMP_TANK = 8
_DR_ROW_CYCLE = 9
_DR_ROW_NOTE = 10


def _dr_is_batch_no(value: Any) -> bool:
    """DR 批号：含连字符且含数字（DR-26035 / 中试-2620 / ZS-006 / DR-26035/36）。

    排除「两个发酵」「进两个种子」等纯文字说明。
    """
    text = str(value).strip()
    return "-" in text and any(ch.isdigit() for ch in text)


def _dr_split_batch(value: Any) -> list[str]:
    """复合批号拆分：'DR-26035/36' → ['DR-26035', 'DR-26036']（短尾共享前缀）。"""
    text = str(value).strip()
    if "/" not in text:
        return [text]
    left, _, right = text.partition("/")
    right = right.strip()
    if right and right.isdigit():
        # 短尾共享左批号前缀：去掉左批号尾部等长数字后拼接
        # 'DR-26035/36' → 'DR-260' + '36' → 'DR-26036'
        tail = re.search(r"\d+$", left)
        if tail and len(tail.group(0)) >= len(right):
            prefix = left[: -len(right)]
        else:
            prefix = re.sub(r"\d+$", "", left)
        right = prefix + right
    return [left, right] if right else [left]


def _dr_split_tank(value: Any) -> list[str]:
    """复合罐号拆分：'B401/2' → ['B401', 'B402']；非罐号返回空。"""
    text = str(value).strip()
    match = re.match(r"^([A-Z]\d{3})(?:/(\d{1,3}))?$", text)
    if not match:
        return []
    head, tail = match.group(1), match.group(2)
    tanks = [head]
    if tail:
        if len(tail) == 3:
            tanks.append(head[0] + tail)
        else:
            tanks.append(head[0] + head[1:-len(tail)] + tail)
    return tanks


def _dr_norm_tank(value: Any) -> str | None:
    """罐号归一：'B401/2' → 'B401'；非罐号文本返回 None。"""
    tanks = _dr_split_tank(value)
    return tanks[0] if tanks else None


def find_dr_period_block(
    rows: list[list[Any]], now: datetime
) -> dict[str, Any] | None:
    """定位 now 所在扎帐周期的 DR 排产块。

    扎帐归属：27 日及以后属次月块，此前属当月块；块标题年月匹配即命中。
    """
    if now.day >= 27:
        year, month = (now.year + 1, 1) if now.month == 12 else (
            now.year,
            now.month + 1,
        )
    else:
        year, month = now.year, now.month
    if month == 1:
        start = date(year - 1, 12, 27)
    else:
        start = date(year, month - 1, 27)
    end = date(year, month, 26)
    for index, row in enumerate(rows):
        if not row:
            continue
        match = _DR_TITLE_RE.search(str(row[0]))
        if match and (int(match.group(1)), int(match.group(2))) == (
            year,
            month,
        ):
            return {
                "start_row": index,
                "start": start,
                "end": end,
                "label": f"{start.month}月{start.day}日～{end.month}月{end.day}日",
            }
    return None


def _dr_column_dates(
    rows: list[list[Any]], block: dict[str, Any]
) -> dict[int, date]:
    """块内列号 → 自然月日期（日期行 1..N = 标题月 1..N 日）。"""
    match = _DR_TITLE_RE.search(str(rows[block["start_row"]][0]))
    if match is None:
        return {}
    year, month = int(match.group(1)), int(match.group(2))
    date_row = rows[block["start_row"] + _DR_ROW_DATE] or []
    result: dict[int, date] = {}
    for col, value in enumerate(date_row):
        if col == 0:
            continue
        text = str(value).strip()
        if not text.isdigit():
            continue
        try:
            result[col] = date(year, month, int(text))
        except ValueError:
            continue
    return result


def _dr_global_ferm_events(
    rows: list[list[Any]],
) -> dict[str, tuple[date, str | None, float | None]]:
    """全表各块的发酵事件：批号 →（最早进罐日, 罐号, 培养周期h）。

    上月块遗留批次（本块只出现在放罐行）的移种时间/周期从这里回查补齐。
    """
    result: dict[str, tuple[date, str | None, float | None]] = {}
    for index, row in enumerate(rows):
        if not row or not _DR_TITLE_RE.search(str(row[0])):
            continue
        col_dates = _dr_column_dates(rows, {"start_row": index})
        ferm_b = rows[index + _DR_ROW_FERM_BATCH] or []
        ferm_t = rows[index + _DR_ROW_FERM_TANK] or []
        cycle_r = rows[index + _DR_ROW_CYCLE] or []
        for col, col_date in sorted(col_dates.items()):
            value = ferm_b[col] if col < len(ferm_b) else None
            if not _dr_is_batch_no(value):
                continue
            cycle_match = re.match(
                r"^(\d+)h$",
                str(cycle_r[col] if col < len(cycle_r) else "").strip(),
            )
            cycle_hours = (
                float(cycle_match.group(1)) if cycle_match else None
            )
            batch_no = str(value).strip()
            known = result.get(batch_no)
            if known is None or col_date < known[0]:
                result[batch_no] = (
                    col_date,
                    _dr_norm_tank(ferm_t[col] if col < len(ferm_t) else None),
                    cycle_hours,
                )
    return result


def _dr_parse_batches(
    rows: list[list[Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """全表解析所有 DR 月度块的批次与罐事件。

    扎帐周期跨自然月（上月 27 日～本月 26 日），周期头尾的批次分别落在
    相邻两个自然月块里，因此必须全表解析后再按周期过滤，
    否则周期头尾的批次会漏计。
    返回（批次列表, 进罐事件流, 放罐事件流）。
    """
    batches: dict[str, dict[str, Any]] = {}
    inoc_events: list[dict[str, Any]] = []
    dump_events: list[dict[str, Any]] = []

    def _ensure(batch_no: str) -> dict[str, Any]:
        return batches.setdefault(
            batch_no,
            {
                "batch_no": batch_no,
                "inoculate": None,
                "ferm_tank": None,
                "dump": None,
                "dump_tank": None,
                "cycle_hours": None,
            },
        )

    for index, row in enumerate(rows):
        if not row:
            continue
        if not _DR_TITLE_RE.search(str(row[0])):
            continue
        col_dates = _dr_column_dates(rows, {"start_row": index})
        ferm_b = rows[index + _DR_ROW_FERM_BATCH] or []
        ferm_t = rows[index + _DR_ROW_FERM_TANK] or []
        dump_b = rows[index + _DR_ROW_DUMP_BATCH] or []
        dump_t = rows[index + _DR_ROW_DUMP_TANK] or []
        cycle_r = rows[index + _DR_ROW_CYCLE] or []

        for col, col_date in sorted(col_dates.items()):
            cycle_match = re.match(
                r"^(\d+)h$",
                str(cycle_r[col] if col < len(cycle_r) else "").strip(),
            )
            col_cycle = float(cycle_match.group(1)) if cycle_match else None
            ferm_raw = ferm_b[col] if col < len(ferm_b) else None
            if _dr_is_batch_no(ferm_raw):
                # 复合批号/罐号按位置拆分配对：
                # 「DR-26035/36 + B401/2」→ DR-26035 进 B401、DR-26036 进 B402
                batch_list = _dr_split_batch(ferm_raw)
                tank_list = _dr_split_tank(
                    ferm_t[col] if col < len(ferm_t) else None
                )
                for i, batch_no in enumerate(batch_list):
                    tank = (
                        tank_list[i]
                        if i < len(tank_list)
                        else (tank_list[-1] if tank_list else None)
                    )
                    batch = _ensure(batch_no)
                    if (
                        batch["inoculate"] is None
                        or col_date < batch["inoculate"]
                    ):
                        batch["inoculate"] = col_date
                    if tank and batch["ferm_tank"] is None:
                        batch["ferm_tank"] = tank
                    if (
                        col_cycle is not None
                        and batch["cycle_hours"] is None
                    ):
                        batch["cycle_hours"] = col_cycle
                    # 罐事件流：每条（罐, 批, 移种日, 周期）独立记录
                    if tank:
                        inoc_events.append(
                            {
                                "tank": tank,
                                "batch_no": batch_no,
                                "date": col_date,
                                "cycle_hours": col_cycle,
                            }
                        )
            if _dr_is_batch_no(dump_b[col] if col < len(dump_b) else None):
                batch = _ensure(str(dump_b[col]).strip())
                # 同一批号多次出现时取最后一次放罐（表内一般唯一）
                batch["dump"] = col_date
                tank = _dr_norm_tank(dump_t[col] if col < len(dump_t) else None)
                if tank:
                    batch["dump_tank"] = tank
                    dump_events.append(
                        {
                            "tank": tank,
                            "batch_no": batch["batch_no"],
                            "date": col_date,
                            "cycle_hours": (
                                float(cycle_match.group(1))
                                if cycle_match
                                else None
                            ),
                        }
                    )
    return list(batches.values()), inoc_events, dump_events


def _note_row_text(row: list[Any] | None) -> str:
    """备注行 → 备注内容：跳过首列'备注'标签，合并其余非空格。"""
    if not row:
        return ""
    parts: list[str] = []
    for index, cell in enumerate(row):
        text = str(cell or "").strip()
        if not text:
            continue
        if index == 0:
            text = re.sub(r"^备注[:：]?", "", text).strip()
            if not text:
                continue
        parts.append(text)
    return "，".join(parts)


def _append_schedule_alerts(
    alerts: list[dict[str, Any]],
    *,
    tanks: list[dict[str, Any]],
    now: datetime,
    maint_tanks: set[str],
    planned_on_tanks: list[dict[str, Any]],
    upcoming_inocs: list[dict[str, Any]],
    note_text: str,
) -> None:
    """DR/MP/他汀播报引擎（对齐 FA 播报体验）：

    - 预放罐提醒：运行罐预估放罐剩 0~72h（仅日期的按当日 08:00 计）；
    - 检修冲突：检修罐本周期仍有计划批次；
    - 待进罐提醒：最近一个已排未进罐批次；
    - 排产备注；全部为空时兜底固定文案。
    """
    for tank in tanks:
        if tank.get("status") != "running" or not tank.get("dump_at"):
            continue
        raw = str(tank["dump_at"])
        try:
            dump_at = (
                datetime.combine(date.fromisoformat(raw), time(8, 0))
                if len(raw) == 10
                else datetime.fromisoformat(raw)
            )
        except ValueError:
            continue
        remain_h = int((dump_at - now).total_seconds() // 3600)
        if 0 <= remain_h <= 72:
            alerts.append(
                {
                    "level": "warn",
                    "text": (
                        f"【播报】{tank['tank_no']}罐批次 {tank['batch_no']} "
                        f"距预估放罐剩余 {remain_h}h"
                    ),
                }
            )
    for tank_no in sorted(maint_tanks):
        conflict = [
            item["batch_no"]
            for item in planned_on_tanks
            if item["tank_no"] == tank_no
        ]
        if conflict:
            alerts.append(
                {
                    "level": "warn",
                    "text": (
                        f"【冲突】{tank_no}罐检修中，但本周期仍有计划批次"
                        f"（如 {conflict[0]}），请确认"
                    ),
                }
            )
    next_inoc = min(
        (item for item in upcoming_inocs if item["start"] > now),
        key=lambda item: item["start"],
        default=None,
    )
    if next_inoc is not None:
        start: datetime = next_inoc["start"]
        when = (
            start.strftime("%m-%d")
            if next_inoc.get("all_day")
            else start.strftime("%m-%d %H:%M")
        )
        tank_label = (
            f"进 {next_inoc['tank_no']} 罐"
            if next_inoc.get("tank_no")
            else "进罐"
        )
        alerts.append(
            {
                "level": "info",
                "text": (
                    f"待进罐批次 {next_inoc['batch_no']} "
                    f"计划 {when} {tank_label}"
                ),
            }
        )
    if note_text:
        alerts.append({"level": "info", "text": f"【排产备注】{note_text}"})
    if not alerts:
        alerts.append(
            {"level": "info", "text": "车间运行正常，无待处理播报"}
        )


def _fmt_batches(value: float | int) -> str:
    """批次数文案：整数批显示整数；他汀折算小数批保留有效小数（9.65→9.65）。"""
    if isinstance(value, float) and value % 1:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(int(value))


def _append_kpi_alerts(
    alerts: list[dict[str, Any]],
    *,
    block: dict[str, Any],
    now: datetime,
    kpis: dict[str, Any],
    missing_dumps: list[tuple[str, datetime]],
    today: date | None = None,
) -> None:
    """漏录提醒与周期末进度预警（FA/DR/MP 看板共用，阈值见模块头部常量）。

    - 待录：批次过放罐窗口超宽限期仍未录产量；超 72h 升级 warn（此时不再
      重复播 info 档，录入抽屉的下拉本就列出全部未录批次）；
    - 进度：周期临期（剩余 ≤7 天）且已录产量进度落后时间进度 ≥10 个百分点。
    仅「真实今天落在周期内」时播报：历史周期只读回看不播旧账，
    未来周期无产可录；汇总路径须传真实 today（其 now 为所选月 15 日）。
    """
    ref_today = today or now.date()
    if not (block["start"] <= ref_today <= block["end"]):
        return
    grace = timedelta(hours=YIELD_ENTRY_GRACE_HOURS)
    warn_after = timedelta(hours=YIELD_ENTRY_WARN_HOURS)
    stale_info: list[str] = []
    stale_warn: list[str] = []
    for batch_no, dump_end in missing_dumps:
        overdue = now - dump_end
        if overdue > warn_after:
            stale_warn.append(batch_no)
        elif overdue > grace:
            stale_info.append(batch_no)
    if stale_warn:
        sample = "、".join(stale_warn[:2])
        prefix = "如 " if len(stale_warn) > 1 else ""
        alerts.append(
            {
                "level": "warn",
                "text": (
                    f"【待录】{len(stale_warn)} 批已放罐超 3 天未录产量"
                    f"（{prefix}{sample}），影响完成 KPI 与产量图表"
                ),
            }
        )
    elif stale_info:
        sample = "、".join(stale_info[:2])
        prefix = "如 " if len(stale_info) > 1 else ""
        alerts.append(
            {
                "level": "info",
                "text": (
                    f"【待录】{len(stale_info)} 批已放罐超 1 天未录产量"
                    f"（{prefix}{sample}），请录入"
                ),
            }
        )
    remaining_days = (block["end"] - ref_today).days
    if remaining_days <= PROGRESS_WARN_DAYS:
        planned = kpis.get("month_planned")
        done = kpis.get("done_with_yield")
        if planned and done is not None:
            span_days = (block["end"] - block["start"]).days + 1
            elapsed_pct = (
                (ref_today - block["start"]).days + 1
            ) / span_days * 100
            actual_pct = done / planned * 100
            lag = elapsed_pct - actual_pct
            if lag >= PROGRESS_LAG_PCT:
                alerts.append(
                    {
                        "level": "warn",
                        "text": (
                            f"【进度】本周期剩 {remaining_days} 天，已录产量 "
                            f"{_fmt_batches(done)}/{_fmt_batches(planned)} 批"
                            f"（{round(actual_pct)}%），"
                            f"落后时间进度 {round(lag)} 个百分点"
                        ),
                    }
                )


def build_dr_board(
    rows: list[list[Any]],
    maintenance: list[dict[str, Any]],
    now: datetime,
    actuals: list[dict[str, Any]] | None = None,
    block: dict[str, Any] | None = None,
    today: date | None = None,
    alert_now: datetime | None = None,
) -> dict[str, Any] | None:
    """DR（102车间）看板组装：罐状态按进罐/放罐日期推算，KPI 按批次计。

    today/alert_now 为漏录/进度告警的真实时间基准（汇总路径传入）。
    """
    if block is None:
        block = find_dr_period_block(rows, now)
    if block is None:
        return None
    as_of = now.date()
    # 全表解析（扎帐周期跨自然月，周期头尾批次在相邻月块里）
    batches, inoc_events, dump_events = _dr_parse_batches(rows)
    actual_by_batch = {
        a["batch_no"]: a for a in (actuals or []) if a.get("batch_no")
    }
    maint_by_tank = {m["tank_no"]: m for m in maintenance}

    # 罐事件流：每罐的进罐/放罐时间线（复合批拆分后逐罐独立）
    inoc_by_tank: dict[str, list[dict[str, Any]]] = {}
    for ev in inoc_events:
        inoc_by_tank.setdefault(ev["tank"], []).append(ev)
    dump_by_tank: dict[str, list[dict[str, Any]]] = {}
    for ev in dump_events:
        dump_by_tank.setdefault(ev["tank"], []).append(ev)

    # 周期窗口内（块内自然月仅覆盖 1..26 日，27 日后属下周期）
    def _in_period(day: date | None) -> bool:
        return day is not None and block["start"] <= day <= block["end"]

    # 统计基线 = 时间线中与本扎帐周期相关的批（放罐或移种落在周期内）；
    # 全表解析会带出历史月份老批，须按周期过滤后再算 KPI
    batches = [
        b
        for b in batches
        if _in_period(b["dump"]) or _in_period(b["inoculate"])
    ]

    done = sorted(
        (b for b in batches if _in_period(b["dump"]) and b["dump"] <= as_of),
        key=lambda b: (b["dump"], b["batch_no"]),
        reverse=True,
    )
    # 已放罐未录产量批次（供漏录提醒；DR 排产无放罐时刻，按当日零点折算）
    missing_dumps = [
        (b["batch_no"], datetime.combine(b["dump"], time(0, 0)))
        for b in done
        if not actual_by_batch.get(b["batch_no"], {}).get("yield_kg")
    ]
    # 运行中/未开始按「本周期计划放罐」口径（放罐日期在周期内）：
    # 跨周期放罐的在制罐不计入 KPI，保证四段进度之和 = 计划放罐数
    #（罐状态板仍完整展示在制罐）
    running = [
        b
        for b in batches
        if b["inoculate"] is not None
        and b["inoculate"] <= as_of
        and (b["dump"] is None or b["dump"] > as_of)
        and _in_period(b["dump"])
    ]
    pending = [
        b
        for b in batches
        if b["inoculate"] is not None
        and b["inoculate"] > as_of
        and _in_period(b["dump"])
    ]
    planned_dump = [b for b in batches if _in_period(b["dump"])]

    # ── 罐状态：事件流时间线推算（复合批拆分后逐罐独立）──
    tank_nos: list[str] = []
    for tank in [*inoc_by_tank, *dump_by_tank]:
        if tank not in tank_nos:
            tank_nos.append(tank)
    batch_map = {b["batch_no"]: b for b in batches}
    tanks: list[dict[str, Any]] = []
    for tank_no in sorted(tank_nos):
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
        # ── 罐时间线（事件流）：进罐/放罐按罐独立排序 ──
        inocs = sorted(
            inoc_by_tank.get(tank_no, []), key=lambda e: (e["date"], e["batch_no"])
        )
        dumps = sorted(
            dump_by_tank.get(tank_no, []), key=lambda e: (e["date"], e["batch_no"])
        )
        past_inocs = [e for e in inocs if e["date"] <= as_of]
        past_dumps = [e for e in dumps if e["date"] <= as_of]
        status = "idle"
        note = "等待排产"
        batch_no: str | None = None
        inoculate: date | None = None
        display_dump: date | None = None
        display_cycle: float | None = None
        cultured: float | None = None
        if past_inocs and (
            not past_dumps or past_inocs[-1]["date"] >= past_dumps[-1]["date"]
        ):
            # 最新一次进罐后尚未放罐 → 运行中
            event = past_inocs[-1]
            status = "running"
            note = "运行中"
            batch_no = event["batch_no"]
            inoculate = event["date"]
            display_cycle = event["cycle_hours"]
            cultured = (as_of - event["date"]).days * 24
        elif past_dumps:
            event = past_dumps[-1]
            status = "dumped"
            note = "已放罐"
            batch_no = event["batch_no"]
            display_dump = event["date"]
            display_cycle = event["cycle_hours"]
            batch_info = batch_map.get(event["batch_no"])
            if batch_info is not None:
                inoculate = batch_info["inoculate"]
        elif inocs:
            event = inocs[0]
            status = "idle"
            note = "待进罐"
            batch_no = event["batch_no"]
            inoculate = event["date"]
            display_cycle = event["cycle_hours"]
        # 运行中/待进罐：预估放罐 = 该罐晚于移种的下一次放罐计划
        # （含跨周期排罐，如本块排到月末后一两天的批次）
        if display_dump is None and inoculate is not None:
            upcoming = [e for e in dumps if e["date"] >= inoculate]
            if upcoming:
                nxt = min(upcoming, key=lambda e: e["date"])
                display_dump = nxt["date"]
                display_cycle = display_cycle or nxt["cycle_hours"]
        tanks.append(
            {
                "tank_no": tank_no,
                "status": status,
                "batch_no": batch_no,
                "inoculate_at": (
                    inoculate.isoformat() if inoculate else None
                ),
                "cultured_hours": cultured,
                "cycle_hours": display_cycle,
                "dump_at": (
                    display_dump.isoformat() if display_dump else None
                ),
                "note": note,
            }
        )

    # ── KPI / 最近完成 / 录入下拉 ──
    with_yield = [
        b
        for b in done
        if actual_by_batch.get(b["batch_no"], {}).get("yield_kg")
    ]
    kpis = {
        "month_planned": len(planned_dump),
        "month_done_planned": len(done),
        "done_with_yield": len(with_yield),
        "yield_pending": len(done) - len(with_yield),
        "month_done_yield_kg": (
            sum(
                actual_by_batch[b["batch_no"]]["yield_kg"]
                for b in with_yield
            )
            or None
        ),
        "running": len(running),
        "pending": len(pending),
    }
    recent = [
        {
            "batch_no": b["batch_no"],
            "dump_date": b["dump"].isoformat() if b["dump"] else None,
            "tank_no": b["dump_tank"] or b["ferm_tank"],
            "yield_kg": actual_by_batch.get(b["batch_no"], {}).get("yield_kg"),
            "extract_kg": actual_by_batch.get(b["batch_no"], {}).get("extract_kg"),
            "batch_yield_rate": None,
            "yield_rate": None,
            "result": "计划放罐",
            # 凑数已放罐行展示用：移种时间与计划总周期
            "inoculate_at": (
                b["inoculate"].isoformat() if b["inoculate"] else None
            ),
            "cycle_hours": b["cycle_hours"],
        }
        for b in done[:12]
    ]
    dumped_batches = [
        {"batch_no": b["batch_no"], "dump_date": b["dump"].isoformat()}
        for b in done
        if b["dump"]
    ]
    ledger_rows = [
        {
            "batch_no": b["batch_no"],
            "dump_date": b["dump"].isoformat() if b["dump"] else None,
            "yield_kg": actual_by_batch.get(b["batch_no"], {}).get("yield_kg"),
            "extract_kg": actual_by_batch.get(b["batch_no"], {}).get("extract_kg"),
        }
        for b in sorted(batches, key=lambda x: x["batch_no"])
    ]
    note_text = _note_row_text(rows[block["start_row"] + _DR_ROW_NOTE])
    # 播报：漏录/进度告警 + 预放罐/检修冲突/待进罐/排产备注（对齐 FA 播报体验）；
    # KPI 告警先入列，_append_schedule_alerts 的空列表兜底才不会误触发
    alerts: list[dict[str, Any]] = []
    _append_kpi_alerts(
        alerts,
        block=block,
        now=alert_now or now,
        kpis=kpis,
        missing_dumps=missing_dumps,
        today=today,
    )
    _append_schedule_alerts(
        alerts,
        tanks=tanks,
        now=now,
        maint_tanks=set(maint_by_tank),
        planned_on_tanks=[
            {"tank_no": b["ferm_tank"], "batch_no": b["batch_no"]}
            for b in batches
            if b.get("ferm_tank")
        ],
        upcoming_inocs=[
            {
                "batch_no": b["batch_no"],
                "start": datetime.combine(b["inoculate"], time(8, 0)),
                "tank_no": b.get("ferm_tank"),
                "all_day": True,
            }
            for b in batches
            if b["inoculate"] and b["inoculate"] > as_of
        ],
        note_text=note_text,
    )
    # 罐序按移种（进罐）时间先后：已进罐的在前，待进罐/无批次罐在后
    def _tank_order(entry: dict[str, Any]) -> tuple[bool, str, str]:
        inoculate = entry.get("inoculate_at")
        return (
            inoculate is None,
            inoculate or "",
            str(entry.get("tank_no")),
        )

    tanks.sort(key=_tank_order)
    # 单批产量趋势：周期内已放罐且有产量的批次，按放罐日期升序取最近 31 批
    done_dump = {b["batch_no"]: b["dump"] for b in done}
    measured = sorted(
        (
            a
            for a in (actuals or [])
            if a.get("yield_kg") is not None and a.get("batch_no") in done_dump
        ),
        key=lambda a: (done_dump[a["batch_no"]], str(a["batch_no"])),
    )
    recent_measured = measured[-31:]
    trend = (
        {
            "batches": [a["batch_no"] for a in recent_measured],
            "outputs": [round(float(a["yield_kg"]), 2) for a in recent_measured],
        }
        if recent_measured
        else None
    )
    return {
        "now": now.isoformat(),
        "period": {
            "start": block["start"].isoformat(),
            "end": block["end"].isoformat(),
            "label": block["label"],
        },
        "kpis": kpis,
        "tanks": tanks,
        "recent": recent,
        "trend": trend,
        "dumped_batches": dumped_batches,
        "extraction": summarize_extraction(ledger_rows),
        "extraction_ledger": ledger_rows,
        "alerts": alerts,
        "maintenance": [dict(m) for m in maintenance],
    }


# ═══════════════════ 霉酚酸（MP）排产解析 ═══════════════════
# 101 车间 MC 放罐计划格式：块标题「2026年08月MC放罐计划」；
# 块内序号行 1..N = 自然月第 1..N 天（列数随月天数变化）；
# 批号贯穿四级流转：一级种子(16:00) → 2天后二级种子(15:00)
# → 次日发酵(14:00) → 约7天后放罐(08:00)，同批号跨行跨块追踪时间线。

# ═══════════════════ 103 他汀转产排产（洛伐 LV / 美伐 MV） ═══════════════════
# 103车间一份文件竖排多月块、美伐/洛伐来回转产，块标题带产品关键字：
# 「2026年6月01日～2026年6月30日103发酵洛伐计划」。标题年月 = 扎帐归属月，
# 周期 = 上月 27 日～本月 26 日（与其他车间一致）；块内日期列仍为归属月
# 自然日。转产月块内混有另一产品批次（放罐/倒罐行按块整体解析），且时间
# 线全局扫描——扎帐头尾的批次写在相邻产品的月块里，不能按关键字裁剪。
# 批号 MV-/LV- 前缀，复合尾 '/NN' 拆分。罐号语义：301B~306B 为 200kl
# 发酵罐；倒罐 = 当日整批并入 301A（450kl），原 200kl 罐腾空，批号此后
# 跟随 301A 至放罐——倒罐/放罐罐格里 301A 与源罐混排且顺序不统一，故
# 倒罐批罐号直接取 301A；未倒罐直放批按罐格位置对应（第 i 批 ↔ 第 i 罐）。

_STATIN_TITLE_RE = re.compile(
    r"(\d{4})年(\d{1,2})月(\d{1,2})日～\s*(\d{4})年(\d{1,2})月(\d{1,2})日"
    r"\s*103发酵(洛伐/美伐|美伐|洛伐)计划"
)
_STATIN_KEYWORD = {"LV": "洛伐", "MV": "美伐"}
_STATIN_TURN_TANK = "301A"  # 倒罐目的罐（450kl），倒罐后批号跟随此罐
# 批次折算基数（标准接种量）：洛伐单批 100；美伐复合批每子批 200
#（复合接种量 400 ÷ 2）。接种量不足标准的批按比例折算小数批，
# 如洛伐接种量 65 → 0.65 批（对齐排产表备注"9月份洛伐放罐9.65批"口径）
_STATIN_SEED_BASE = {"LV": 100.0, "MV": 200.0}


def _statin_blocks(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """全表扫描他汀月度块：[{start_row, year, month, start, end, keyword, note_row}]。

    start/end 为标题年月的扎帐周期（上月 27 日～本月 26 日）。
    """
    blocks: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not row:
            continue
        match = _STATIN_TITLE_RE.search(str(row[0]).strip())
        if match is None:
            continue
        y1, m1, d1, y2, m2, d2 = (int(match.group(i)) for i in range(1, 7))
        start = date(y1 - 1, 12, 27) if m1 == 1 else date(y1, m1 - 1, 27)
        try:
            blocks.append(
                {
                    "start_row": index,
                    "year": y1,
                    "month": m1,
                    "start": start,
                    "end": date(y1, m1, 26),
                    "keyword": match.group(7),
                    "note_row": None,
                }
            )
        except ValueError:
            continue
    # 备注行（'备注：…'）归属其上方最近的块
    for r, row in enumerate(rows):
        if row and str(row[0]).strip().startswith("备注"):
            prior = [b for b in blocks if b["start_row"] < r]
            if prior:
                prior[-1]["note_row"] = r
    return blocks


def _statin_split_batch(value: Any) -> list[str]:
    """他汀批号拆分：'MV-26009/010' → MV-26009、MV-26010；非批号文本忽略。"""
    text = str(value or "").strip()
    if not re.fullmatch(r"(?:MV|LV)-\d{3,6}(?:/\d{1,6})?", text):
        return []
    return [
        part
        for part in _dr_split_batch(text)
        if re.fullmatch(r"(?:MV|LV)-\d{3,6}", part)
    ]


def _statin_split_tanks(value: Any) -> list[str]:
    """罐格拆分：'304B/306B'、多行 '301A\\n303B\\n305B' → 罐号列表。"""
    text = str(value or "").replace("\n", "/").strip()
    return [tank.strip() for tank in text.split("/") if tank.strip()]


def _statin_row_time(value: Any, default: str) -> time:
    """时刻解析：Excel 小数分数（0.666…=16:00）或 'HH:MM(:SS)' 文本；异常回退默认。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = round(float(value) * 24 * 3600)
        return time(seconds // 3600 % 24, (seconds // 60) % 60)
    match = re.match(r"^(\d{1,2}):(\d{2})", str(value or "").strip())
    if match is None:
        return time.fromisoformat(default)
    return time(int(match.group(1)), int(match.group(2)))


def _statin_column_dates(
    block: dict[str, Any], day_row: list[Any]
) -> dict[int, date]:
    """日期行 → {列号: 日期}（日 = 扎帐归属月内自然日）。"""
    result: dict[int, date] = {}
    for col in range(1, len(day_row)):
        try:
            day = int(float(str(day_row[col]).strip()))
        except (TypeError, ValueError):
            continue
        try:
            result[col] = date(block["year"], block["month"], day)
        except ValueError:
            continue
    return result


def _statin_batch_timeline(
    rows: list[list[Any]],
) -> dict[str, dict[str, Any]]:
    """全表扫描他汀批号时间线（全部月度块，跨产品转产批不裁剪）。

    返回结构与 _mp_batch_timeline 一致：{批号: {inoculate, ferm_tank,
    dump, dump_tank}}。扎帐头尾批次写在相邻产品块里，须全局扫描；
    倒罐批（跨块全局集合）罐号取 301A；直放批按罐格位置对应。
    """
    all_blocks = _statin_blocks(rows)
    timeline: dict[str, dict[str, Any]] = {}

    def _ensure(batch_no: str) -> dict[str, Any]:
        return timeline.setdefault(
            batch_no,
            {
                "batch_no": batch_no,
                "inoculate": None,
                "ferm_tank": None,
                "dump": None,
                "dump_tank": None,
                # 批次折算数（标准接种量 = 1.0）；无种子记录的批默认整批
                "units": 1.0,
            },
        )

    # 倒罐批全局集合：倒罐块与放罐块可能不同（如 5/31 倒罐、6/6 放罐）
    turned: set[str] = set()
    for row in rows:
        if row and str(row[0]).strip() == "倒罐":
            for cell in row[1:]:
                turned.update(_statin_split_batch(cell))

    for block in all_blocks:
        following = next(
            (
                b["start_row"]
                for b in all_blocks
                if b["start_row"] > block["start_row"]
            ),
            None,
        )
        block_end = following if following is not None else len(rows)
        labeled: dict[str, tuple[int, list[Any]]] = {}
        for r in range(block["start_row"] + 1, block_end):
            row = rows[r] or []
            # 标签一般在首列；日期行例外（首列空、'日期' 在第 1 列）
            label = str(row[0]).strip() if row else ""
            if not label and len(row) > 1:
                label = str(row[1]).strip()
            if label and label not in labeled:
                labeled[label] = (r, row)
        col_dates = _statin_column_dates(block, labeled.get("日期", (0, []))[1])
        ferm_idx, ferm_row = labeled.get("发酵罐", (None, []))
        shift_row = labeled.get("移种", (None, []))[1]
        dump_idx, dump_row = labeled.get("放罐", (None, []))
        dump_time_row = labeled.get("放罐时间", (None, []))[1]
        ferm_tank_row = rows[ferm_idx + 1] if ferm_idx is not None else []
        dump_tank_row = rows[dump_idx + 1] if dump_idx is not None else []
        # 种子接种量 → 批次折算数：复合批均摊到子批，再除以标准接种量
        seed_row = labeled.get("种子罐", (None, []))[1]
        inoc_row = labeled.get("接种量", (None, []))[1]
        for col, col_date in col_dates.items():
            seed_batches = _statin_split_batch(
                seed_row[col] if col < len(seed_row) else None
            )
            if not seed_batches:
                continue
            try:
                total_inoc = (
                    float(inoc_row[col]) if col < len(inoc_row) else 0.0
                )
            except (TypeError, ValueError):
                total_inoc = 0.0
            if not total_inoc:
                continue
            per_batch = total_inoc / len(seed_batches)
            for seed_no in seed_batches:
                base = _STATIN_SEED_BASE.get(seed_no.split("-")[0], 100.0)
                entry = _ensure(seed_no)
                entry["units"] = round(per_batch / base, 4)
        for col, col_date in col_dates.items():
            ferm_tanks = _statin_split_tanks(
                ferm_tank_row[col] if col < len(ferm_tank_row) else None
            )
            ferm_when = datetime.combine(
                col_date,
                _statin_row_time(
                    shift_row[col] if col < len(shift_row) else None,
                    "14:00",
                ),
            )
            for i, ferm_no in enumerate(
                _statin_split_batch(
                    ferm_row[col] if col < len(ferm_row) else None
                )
            ):
                batch = _ensure(ferm_no)
                if batch["inoculate"] is None or ferm_when < batch["inoculate"]:
                    batch["inoculate"] = ferm_when
                tank = (
                    ferm_tanks[i]
                    if i < len(ferm_tanks)
                    else (ferm_tanks[0] if ferm_tanks else None)
                )
                if tank and batch["ferm_tank"] is None:
                    batch["ferm_tank"] = tank
            dump_cell_tanks = _statin_split_tanks(
                dump_tank_row[col] if col < len(dump_tank_row) else None
            )
            dump_when = datetime.combine(
                col_date,
                _statin_row_time(
                    dump_time_row[col] if col < len(dump_time_row) else None,
                    "08:00",
                ),
            )
            for i, dump_no in enumerate(
                _statin_split_batch(
                    dump_row[col] if col < len(dump_row) else None
                )
            ):
                batch = _ensure(dump_no)
                batch["dump"] = dump_when
                if dump_no in turned:
                    batch["dump_tank"] = _STATIN_TURN_TANK
                elif batch["dump_tank"] is None:
                    tank = (
                        dump_cell_tanks[i]
                        if i < len(dump_cell_tanks)
                        else (dump_cell_tanks[0] if dump_cell_tanks else None)
                    )
                    if tank:
                        batch["dump_tank"] = tank
    return timeline


def _find_statin_period_block(
    rows: list[list[Any]], now: datetime, keyword: str
) -> dict[str, Any] | None:
    """定位 now 所在扎帐周期（上月27～本月26）的他汀月度块。"""
    if now.day >= 27:
        year, month = (
            (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
        )
    else:
        year, month = now.year, now.month
    for block in _statin_blocks(rows):
        if (
            keyword in block["keyword"]
            and (block["year"], block["month"]) == (year, month)
        ):
            return {
                "start_row": block["start_row"],
                "start": block["start"],
                "end": block["end"],
                "label": (
                    f"{block['start'].month}月{block['start'].day}日～"
                    f"{block['end'].month}月{block['end'].day}日"
                ),
                "note_row": block["note_row"],
            }
    return None


_MP_TITLE_RE = re.compile(r"(\d{4})年(\d{1,2})月MC放罐计划")
_MP_ROW_SEQ = 1
_MP_ROW_FERM_BATCH = 8
_MP_ROW_FERM_TANK = 9
_MP_ROW_FERM_TIME = 10
_MP_ROW_DUMP_BATCH = 11
_MP_ROW_DUMP_TANK = 12
_MP_ROW_DUMP_TIME = 13
_MP_ROW_NOTE = 18


def find_mp_period_block(
    rows: list[list[Any]], now: datetime, product: str = "MC"
) -> dict[str, Any] | None:
    """定位 now 所在扎帐周期的 MC 放罐计划块（27 日及以后属次月块）。

    product 为 LV/MV 时改走 103 他汀自然月块（标题含 洛伐/美伐 关键字）。
    """
    if product in _STATIN_KEYWORD:
        return _find_statin_period_block(rows, now, _STATIN_KEYWORD[product])
    if now.day >= 27:
        year, month = (now.year + 1, 1) if now.month == 12 else (
            now.year,
            now.month + 1,
        )
    else:
        year, month = now.year, now.month
    if month == 1:
        start = date(year - 1, 12, 27)
    else:
        start = date(year, month - 1, 27)
    end = date(year, month, 26)
    for index, row in enumerate(rows):
        if not row:
            continue
        match = _MP_TITLE_RE.search(str(row[0]))
        if match and (int(match.group(1)), int(match.group(2))) == (
            year,
            month,
        ):
            return {
                "start_row": index,
                "start": start,
                "end": end,
                "label": f"{start.month}月{start.day}日～{end.month}月{end.day}日",
            }
    return None


def _mp_column_dates(
    rows: list[list[Any]], start_row: int
) -> dict[int, date]:
    """块内列号 → 自然月日期（序号 n = 标题月第 n 日）。"""
    match = _MP_TITLE_RE.search(str(rows[start_row][0]))
    if match is None:
        return {}
    year, month = int(match.group(1)), int(match.group(2))
    seq_row = rows[start_row + _MP_ROW_SEQ] or []
    result: dict[int, date] = {}
    for col in range(1, len(seq_row)):
        text = str(seq_row[col]).strip()
        if not text.isdigit():
            continue
        try:
            result[col] = date(year, month, int(text))
        except ValueError:
            continue
    return result


def _mp_row_time(text: Any, default: str) -> time:
    """时刻行解析（"14:00:00"）；异常回退默认时刻。"""
    match = re.match(r"^(\d{1,2}):(\d{2})", str(text or "").strip())
    if match is None:
        return time.fromisoformat(default)
    return time(int(match.group(1)), int(match.group(2)))


def _mp_split_batch(value: Any) -> list[str]:
    """MC 放罐计划批号拆分：支持完整前缀 'MC-26246/47' 与缺前缀 '26246/47'。

    复合批短尾共享前缀（26246/47 → 26246、26247）；
    裸数字批号统一补 MC- 前缀，与同表其他批号口径一致。
    非批号文本返回空列表。
    """
    text = str(value).strip()
    if not text:
        return []
    if re.fullmatch(r"\d{3,6}/\d{1,6}", text):
        return [f"MC-{b}" for b in _dr_split_batch(text)]
    if _dr_is_batch_no(text):
        return [
            b if "-" in b else f"MC-{b}" for b in _dr_split_batch(text)
        ]
    return []


def _mp_batch_timeline(
    rows: list[list[Any]],
) -> dict[str, dict[str, Any]]:
    """全表扫描批号时间线：发酵(进罐)与放罐事件按批号聚合。

    返回 {批号: {"inoculate": datetime, "ferm_tank", "dump": datetime|None,
    "dump_tank"}}；跨块流转的批（上月发酵、本月放罐）自然补齐。
    复合批号（26246/47 等）拆分为独立批次后分别计数。
    """
    timeline: dict[str, dict[str, Any]] = {}

    def _ensure(batch_no: str) -> dict[str, Any]:
        return timeline.setdefault(
            batch_no,
            {
                "batch_no": batch_no,
                "inoculate": None,
                "ferm_tank": None,
                "dump": None,
                "dump_tank": None,
            },
        )

    for index, row in enumerate(rows):
        if not row or not _MP_TITLE_RE.search(str(row[0])):
            continue
        col_dates = _mp_column_dates(rows, index)
        ferm_b = rows[index + _MP_ROW_FERM_BATCH] or []
        ferm_t = rows[index + _MP_ROW_FERM_TANK] or []
        ferm_time = rows[index + _MP_ROW_FERM_TIME] or []
        dump_b = rows[index + _MP_ROW_DUMP_BATCH] or []
        dump_t = rows[index + _MP_ROW_DUMP_TANK] or []
        dump_time = rows[index + _MP_ROW_DUMP_TIME] or []
        for col, col_date in col_dates.items():
            ferm_when = datetime.combine(
                col_date,
                _mp_row_time(
                    ferm_time[col] if col < len(ferm_time) else None,
                    "14:00",
                ),
            )
            # 复合批号拆分（26246/47 → MC-26246、MC-26247）后逐批记录
            for ferm_no in _mp_split_batch(
                ferm_b[col] if col < len(ferm_b) else None
            ):
                batch = _ensure(ferm_no)
                if batch["inoculate"] is None or ferm_when < batch["inoculate"]:
                    batch["inoculate"] = ferm_when
                tank = _dr_norm_tank(ferm_t[col] if col < len(ferm_t) else None)
                if tank and batch["ferm_tank"] is None:
                    batch["ferm_tank"] = tank
            dump_when = datetime.combine(
                col_date,
                _mp_row_time(
                    dump_time[col] if col < len(dump_time) else None,
                    "08:00",
                ),
            )
            for dump_no in _mp_split_batch(
                dump_b[col] if col < len(dump_b) else None
            ):
                batch = _ensure(dump_no)
                batch["dump"] = dump_when
                tank = _dr_norm_tank(dump_t[col] if col < len(dump_t) else None)
                if tank:
                    batch["dump_tank"] = tank
    return timeline


def build_mp_board(
    rows: list[list[Any]],
    maintenance: list[dict[str, Any]],
    now: datetime,
    actuals: list[dict[str, Any]] | None = None,
    block: dict[str, Any] | None = None,
    product: str = "MC",
    today: date | None = None,
    alert_now: datetime | None = None,
) -> dict[str, Any] | None:
    """MP（101车间）看板组装：批号时间线推算罐状态，KPI 按批次计。

    product 为 LV/MV 时复用同一组装，改走 103 他汀自然月块解析
    （块内批次整体计入，罐号按倒罐/直放规则回填）。
    today/alert_now 为漏录/进度告警的真实时间基准（汇总路径传入）。
    """
    if block is None:
        block = find_mp_period_block(rows, now, product=product)
    if block is None:
        return None
    if product in _STATIN_KEYWORD:
        timeline = _statin_batch_timeline(rows)
    else:
        timeline = _mp_batch_timeline(rows)
    actual_by_batch = {
        a["batch_no"]: a for a in (actuals or []) if a.get("batch_no")
    }
    maint_by_tank = {m["tank_no"]: m for m in maintenance}

    def _in_period(when: datetime | None) -> bool:
        return (
            when is not None and block["start"] <= when.date() <= block["end"]
        )

    # 统计基线 = 时间线中与本扎帐周期相关的批：
    # 放罐落在本周期内，或移种落在本周期内（本周期移种、下周期放罐）。
    # 扎帐周期跨自然月（上月 27 日～本月 26 日），周期头尾的批次在
    # 相邻月块里，因此不能只按当前块行收集，须从全表时间线过滤。
    batches = sorted(
        (
            b
            for b in timeline.values()
            if _in_period(b["dump"]) or _in_period(b["inoculate"])
        ),
        key=lambda b: b["batch_no"],
    )
    done = sorted(
        (b for b in batches if _in_period(b["dump"]) and b["dump"] <= now),
        key=lambda b: (b["dump"], b["batch_no"]),
        reverse=True,
    )
    # 已放罐未录产量批次（供漏录提醒；与 KPI 的产量真值语义一致）
    missing_dumps = [
        (b["batch_no"], b["dump"] + DUMP_WINDOW)
        for b in done
        if not actual_by_batch.get(b["batch_no"], {}).get("yield_kg")
    ]
    # 运行中/未开始按「本周期计划放罐」口径（放罐日期在周期内）：
    # 跨周期放罐的在制罐不计入 KPI，保证四段进度之和 = 计划放罐数
    running = [
        b
        for b in batches
        if b["inoculate"] is not None
        and b["inoculate"] <= now
        and (b["dump"] is None or b["dump"] > now)
        and _in_period(b["dump"])
    ]
    pending = [
        b
        for b in batches
        if b["inoculate"]
        and b["inoculate"] > now
        and _in_period(b["dump"])
    ]
    planned = [b for b in batches if _in_period(b["dump"])]

    # ── 罐状态：发酵罐集合，每罐取当前在罐批 ──
    tank_nos: list[str] = []
    for b in batches:
        for tank in (b["ferm_tank"], b["dump_tank"]):
            if tank and tank not in tank_nos:
                tank_nos.append(tank)
    tanks: list[dict[str, Any]] = []
    for tank_no in sorted(tank_nos):
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
        own = [
            b
            for b in batches
            if b["ferm_tank"] == tank_no
            or (b["dump_tank"] == tank_no and b["ferm_tank"] is None)
        ]
        own.sort(
            key=lambda b: (
                b["inoculate"] or b["dump"] or datetime.max,
            )
        )
        active = [
            b
            for b in own
            if b["inoculate"] is not None
            and b["inoculate"] <= now
            and (b["dump"] is None or b["dump"] > now)
        ]
        finished = [b for b in own if b["dump"] is not None and b["dump"] <= now]
        batch = active[-1] if active else (finished[-1] if finished else None)
        if batch is None:
            tanks.append(
                {
                    "tank_no": tank_no,
                    "status": "idle",
                    "batch_no": None,
                    "inoculate_at": None,
                    "cultured_hours": None,
                    "cycle_hours": None,
                    "dump_at": None,
                    "note": "等待排产",
                }
            )
            continue
        if batch in active:
            status, note = "running", "运行中"
        else:
            status, note = "dumped", "已放罐"
        cultured = (
            round((now - batch["inoculate"]).total_seconds() / 3600, 1)
            if batch["inoculate"] and batch["inoculate"] <= now
            else None
        )
        cycle = (
            round(
                (batch["dump"] - batch["inoculate"]).total_seconds() / 3600, 1
            )
            if batch["dump"] and batch["inoculate"]
            else None
        )
        tanks.append(
            {
                "tank_no": tank_no,
                "status": status,
                "batch_no": batch["batch_no"],
                "inoculate_at": (
                    batch["inoculate"].isoformat()
                    if batch["inoculate"]
                    else None
                ),
                "cultured_hours": cultured,
                "cycle_hours": cycle,
                "dump_at": (
                    batch["dump"].isoformat() if batch["dump"] else None
                ),
                "note": note,
            }
        )
    # 罐序按移种时间
    def _tank_order(entry: dict[str, Any]) -> tuple[bool, str, str]:
        inoculate = entry.get("inoculate_at")
        return (inoculate is None, inoculate or "", str(entry.get("tank_no")))

    tanks.sort(key=_tank_order)

    with_yield = [
        b
        for b in done
        if actual_by_batch.get(b["batch_no"], {}).get("yield_kg")
    ]
    if product in _STATIN_KEYWORD:
        # 他汀：批次按种子接种量折算（标准 LV 100/批、MV 每子批 200/批），
        # 支持小数批（如接种量 65 → 0.65 批，对齐排产表备注口径）
        month_planned = round(sum(b["units"] for b in planned), 2)
        month_done_planned = round(sum(b["units"] for b in done), 2)
    else:
        month_planned = len(planned)
        month_done_planned = len(done)
    kpis = {
        "month_planned": month_planned,
        "month_done_planned": month_done_planned,
        "done_with_yield": len(with_yield),
        "yield_pending": len(done) - len(with_yield),
        "month_done_yield_kg": (
            sum(
                actual_by_batch[b["batch_no"]]["yield_kg"] for b in with_yield
            )
            or None
        ),
        "running": len(running),
        "pending": len(pending),
    }
    recent = [
        {
            "batch_no": b["batch_no"],
            "dump_date": b["dump"].date().isoformat() if b["dump"] else None,
            "tank_no": b["dump_tank"] or b["ferm_tank"],
            "yield_kg": actual_by_batch.get(b["batch_no"], {}).get("yield_kg"),
            "extract_kg": actual_by_batch.get(b["batch_no"], {}).get(
                "extract_kg"
            ),
            "batch_yield_rate": None,
            "yield_rate": None,
            "result": "计划放罐",
            "inoculate_at": (
                b["inoculate"].isoformat() if b["inoculate"] else None
            ),
            "cycle_hours": (
                round((b["dump"] - b["inoculate"]).total_seconds() / 3600, 1)
                if b["dump"] and b["inoculate"]
                else None
            ),
        }
        for b in done[:12]
    ]
    dumped_batches = [
        {"batch_no": b["batch_no"], "dump_date": b["dump"].date().isoformat()}
        for b in done
        if b["dump"]
    ]
    ledger_rows = [
        {
            "batch_no": b["batch_no"],
            "dump_date": b["dump"].date().isoformat() if b["dump"] else None,
            "yield_kg": actual_by_batch.get(b["batch_no"], {}).get("yield_kg"),
            "extract_kg": actual_by_batch.get(b["batch_no"], {}).get(
                "extract_kg"
            ),
        }
        for b in batches
    ]
    if product in _STATIN_KEYWORD:
        note_row = (
            rows[block["note_row"]] if block.get("note_row") is not None else []
        )
    else:
        for block_row in range(0, len(rows)):
            row = rows[block_row]
            if row and _MP_TITLE_RE.search(str(row[0])):
                note_row = rows[block_row + _MP_ROW_NOTE] or []
                break
        else:
            note_row = []
    note_text = _note_row_text(note_row)
    # 播报：漏录/进度告警 + 预放罐/检修冲突/待进罐/排产备注（对齐 FA 播报体验）；
    # KPI 告警先入列，_append_schedule_alerts 的空列表兜底才不会误触发
    alerts: list[dict[str, Any]] = []
    _append_kpi_alerts(
        alerts,
        block=block,
        now=alert_now or now,
        kpis=kpis,
        missing_dumps=missing_dumps,
        today=today,
    )
    _append_schedule_alerts(
        alerts,
        tanks=tanks,
        now=now,
        maint_tanks=set(maint_by_tank),
        planned_on_tanks=[
            {"tank_no": b["ferm_tank"], "batch_no": b["batch_no"]}
            for b in batches
            if b.get("ferm_tank")
        ],
        upcoming_inocs=[
            {
                "batch_no": b["batch_no"],
                "start": b["inoculate"],
                "tank_no": b.get("ferm_tank"),
            }
            for b in batches
            if b["inoculate"] and b["inoculate"] > now
        ],
        note_text=note_text,
    )
    # 单批产量趋势：周期内已放罐且有产量的批次，按放罐日期升序取最近 31 批
    done_dump = {b["batch_no"]: b["dump"] for b in done}
    measured = sorted(
        (
            a
            for a in (actuals or [])
            if a.get("yield_kg") is not None and a.get("batch_no") in done_dump
        ),
        key=lambda a: (done_dump[a["batch_no"]], str(a["batch_no"])),
    )
    recent_measured = measured[-31:]
    trend = (
        {
            "batches": [a["batch_no"] for a in recent_measured],
            "outputs": [round(float(a["yield_kg"]), 2) for a in recent_measured],
        }
        if recent_measured
        else None
    )
    return {
        "now": now.isoformat(),
        "period": {
            "start": block["start"].isoformat(),
            "end": block["end"].isoformat(),
            "label": block["label"],
        },
        "kpis": kpis,
        "tanks": tanks,
        "recent": recent,
        "trend": trend,
        "dumped_batches": dumped_batches,
        "extraction": summarize_extraction(ledger_rows),
        "extraction_ledger": ledger_rows,
        "alerts": alerts,
        "maintenance": [dict(m) for m in maintenance],
    }


# ═══════════════════ 重复存档合并（冻结历史日列） ═══════════════════


def _index_blocks(rows: list[list[Any]]) -> dict[date, dict[str, Any]]:
    """全表周期块索引：块起始日期 → 块定位（同起始周期取首个）。"""
    blocks: dict[date, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not row:
            continue
        span = parse_period_title(str(row[0]))
        if span and span[0] not in blocks:
            blocks[span[0]] = {"start_row": index, "start": span[0]}
    return blocks


def _block_day_columns(
    rows: list[list[Any]], block: dict[str, Any]
) -> list[tuple[int, date]]:
    """块内日列 → (相对日列的列序, 日期)；日期行无法解析的占位列跳过。"""
    days_row = (
        rows[block["start_row"] + _ROW_DATE]
        if block["start_row"] + _ROW_DATE < len(rows)
        else []
    )
    block_start = block["start"]
    result: list[tuple[int, date]] = []
    for offset, value in enumerate(days_row[2:]):
        try:
            day = int(str(value).strip())
        except ValueError:
            continue
        if day >= 27:
            result.append((offset, block_start.replace(day=day)))
            continue
        if block_start.month == 12:
            nxt = block_start.replace(year=block_start.year + 1, month=1)
        else:
            nxt = block_start.replace(month=block_start.month + 1)
        result.append((offset, nxt.replace(day=day)))
    return result


def _cell_at(rows: list[list[Any]], row_index: int, col_index: int) -> Any:
    row = rows[row_index] if row_index < len(rows) else []
    return row[col_index] if col_index < len(row) else ""


def _set_cell(
    grid: list[list[Any]], row_index: int, col_index: int, value: Any
) -> None:
    while row_index >= len(grid):
        grid.append([])
    row = grid[row_index]
    while col_index >= len(row):
        row.append("")
    row[col_index] = value


# ═══════════════════ 重存档历史冻结（按产品适配） ═══════════════════
# 重新上传排产 Excel 时冻结「今天之前」的日列，防止车间重发文件漏带或
# 改动历史放罐/移种记录，覆盖看板已依赖的历史口径（罐完成状态、最近
# 完成、完成 KPI、批次产量归属周期）。各产品表布局不同，周期块识别、
# 日列解析与冻结行跨度按产品适配；历史修正（以新文件为准）由调用方
# 通过 freeze_past=False 显式开启。


# 各产品排产表的标准块标题示例（识别失败时的存档拒绝提示）
SHEET_FORMAT_EXAMPLES: dict[str, str] = {
    "FA": "2026年08月27日～2026年09月26日",
    "DR": "102车间2026年09月份多拉计划（09.05）",
    "MC": "2026年08月MC放罐计划",
    "LV": "2026年08月27日～2026年09月26日 103发酵洛伐计划",
    "MV": "2026年08月27日～2026年09月26日 103发酵美伐计划",
}

# 历史改动清单上限：超出只记数不展开，避免整表重排撑爆响应与审计
MERGE_DIFF_LIMIT = 200


def _fa_sheet_blocks(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """FA 表周期块枚举：key=扎帐起始日，冻结行跨度=日期行～备注行。"""
    blocks: list[dict[str, Any]] = []
    for start, block in _index_blocks(rows).items():
        blocks.append(
            {
                "key": start,
                "start_row": block["start_row"],
                "label": f"{start.year}-{start.month:02d}",
                "row_span": (_ROW_DATE, _ROW_NOTE),
                "columns": {
                    offset + 2: day
                    for offset, day in _block_day_columns(rows, block)
                },
                "labels": {
                    _ROW_DATE: "日期",
                    _ROW_SEED_BATCH: "种子批号",
                    _ROW_SEED_TANK: "种子罐号",
                    _ROW_SEED_TIME: "接种时间",
                    _ROW_FERM_BATCH: "进罐批号",
                    _ROW_FERM_TANK: "发酵罐号",
                    _ROW_FERM_TIME: "移种时间",
                    _ROW_DUMP_BATCH: "放罐批号",
                    _ROW_DUMP_TANK: "放罐罐号",
                    _ROW_DUMP_TIME: "放罐时间",
                    _ROW_NOTE: "排产备注",
                },
            }
        )
    return blocks


def _dr_sheet_blocks(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """DR 表周期块枚举：key=标题月 1 日（扎帐归属月），列为自然月日。"""
    blocks: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not row:
            continue
        match = _DR_TITLE_RE.search(str(row[0]))
        if match is None:
            continue
        blocks.append(
            {
                "key": date(int(match.group(1)), int(match.group(2)), 1),
                "start_row": index,
                "label": f"{match.group(1)}-{int(match.group(2)):02d}",
                "row_span": (_DR_ROW_DATE, _DR_ROW_NOTE),
                "columns": _dr_column_dates(rows, {"start_row": index}),
                "labels": {
                    _DR_ROW_DATE: "日期",
                    _DR_ROW_FERM_BATCH: "进罐批号",
                    _DR_ROW_FERM_TANK: "发酵罐号",
                    _DR_ROW_DUMP_BATCH: "放罐批号",
                    _DR_ROW_DUMP_TANK: "放罐罐号",
                    _DR_ROW_CYCLE: "培养周期",
                    _DR_ROW_NOTE: "备注",
                },
            }
        )
    return blocks


def _mp_sheet_blocks(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """MC 表周期块枚举：key=标题月 1 日，序号行 n = 标题月第 n 日。"""
    blocks: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not row:
            continue
        match = _MP_TITLE_RE.search(str(row[0]))
        if match is None:
            continue
        blocks.append(
            {
                "key": date(int(match.group(1)), int(match.group(2)), 1),
                "start_row": index,
                "label": f"{match.group(1)}-{int(match.group(2)):02d}",
                "row_span": (_MP_ROW_SEQ, _MP_ROW_NOTE),
                "columns": _mp_column_dates(rows, index),
                "labels": {
                    _MP_ROW_SEQ: "日期",
                    _MP_ROW_FERM_BATCH: "进罐批号",
                    _MP_ROW_FERM_TANK: "发酵罐号",
                    _MP_ROW_FERM_TIME: "移种时间",
                    _MP_ROW_DUMP_BATCH: "放罐批号",
                    _MP_ROW_DUMP_TANK: "放罐罐号",
                    _MP_ROW_DUMP_TIME: "放罐时间",
                    _MP_ROW_NOTE: "备注",
                },
            }
        )
    return blocks


def _statin_sheet_blocks(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """他汀（LV/MV）周期块枚举：行布局 label 驱动无固定偏移，
    冻结行跨度取整块（标题行下一行～下块标题前一行），行标签取首列。"""
    all_blocks = _statin_blocks(rows)
    blocks: list[dict[str, Any]] = []
    for block in all_blocks:
        following = next(
            (
                b["start_row"]
                for b in all_blocks
                if b["start_row"] > block["start_row"]
            ),
            len(rows),
        )
        labels: dict[int, str] = {}
        labeled: dict[str, tuple[int, list[Any]]] = {}
        for r in range(block["start_row"] + 1, following):
            row = rows[r] or []
            label = str(row[0]).strip() if row else ""
            if not label and len(row) > 1:
                label = str(row[1]).strip()
            labels[r - block["start_row"]] = label or f"第{r + 1}行"
            if label and label not in labeled:
                labeled[label] = (r, row)
        blocks.append(
            {
                "key": block["start"],
                "start_row": block["start_row"],
                "label": f"{block['year']}-{block['month']:02d}",
                "row_span": (1, max(1, following - block["start_row"] - 1)),
                "columns": _statin_column_dates(
                    block, labeled.get("日期", (0, []))[1]
                ),
                "labels": labels,
            }
        )
    return blocks


def _sheet_blocks_for_product(
    rows: list[list[Any]], product_code: str
) -> list[dict[str, Any]]:
    """按产品分派周期块枚举（与看板管线的产品分派一致）。"""
    if product_code == "DR":
        return _dr_sheet_blocks(rows)
    if product_code in _STATIN_KEYWORD:
        return _statin_sheet_blocks(rows)
    if product_code == "MC":
        return _mp_sheet_blocks(rows)
    return _fa_sheet_blocks(rows)


def _merge_cell_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def merge_schedule_rows_for_product(
    new_rows: list[list[Any]],
    old_rows: list[list[Any]],
    today: date,
    product_code: str = "FA",
    *,
    freeze_past: bool = True,
) -> tuple[list[list[Any]], dict[str, Any]]:
    """重新存档排产表：冻结「今天之前」的日列，仅采用新文件当天及以后的计划。

    防止车间重发的排产漏带或改动历史放罐/移种记录，覆盖看板已依赖的
    历史口径：
    - 新旧文件按同 key 周期块对齐（各产品适配，见 _sheet_blocks_for_product）；
    - 块内日期 < today 的日列整体沿用旧存档（行跨度见各适配器）；
    - 旧存档无对应周期块/日列时保持新文件原样（无更可信的历史来源）；
    - freeze_past=False 时保留新文件值（显式历史修正），差异照常记录。
    返回 (merged_rows, report)：recognized=新文件是否识别出周期块；
    discarded_changes=被冻结放弃（修正时为被应用）的逐格改动，
    上限 MERGE_DIFF_LIMIT 条，超出置 truncated。
    返回深拷贝，不修改入参。
    """
    merged = [list(row) if isinstance(row, list) else row for row in new_rows]
    new_blocks = _sheet_blocks_for_product(new_rows, product_code)
    old_by_key = {
        block["key"]: block
        for block in _sheet_blocks_for_product(old_rows, product_code)
    }
    discarded: list[dict[str, Any]] = []
    truncated = False
    frozen_columns = 0
    matched_blocks = 0
    for new_block in new_blocks:
        old_block = old_by_key.get(new_block["key"])
        if old_block is None:
            continue
        matched_blocks += 1
        old_by_date = {
            day: col for col, day in old_block["columns"].items()
        }
        span_start, span_end = new_block["row_span"]
        for col, col_date in sorted(new_block["columns"].items()):
            if col_date >= today:
                continue
            old_col = old_by_date.get(col_date)
            if old_col is None:
                continue
            if freeze_past:
                frozen_columns += 1
            for rel in range(span_start, span_end + 1):
                old_value = _cell_at(
                    old_rows, old_block["start_row"] + rel, old_col
                )
                new_value = _cell_at(
                    new_rows, new_block["start_row"] + rel, col
                )
                if freeze_past:
                    _set_cell(
                        merged, new_block["start_row"] + rel, col, old_value
                    )
                if _merge_cell_text(old_value) == _merge_cell_text(new_value):
                    continue
                if len(discarded) >= MERGE_DIFF_LIMIT:
                    truncated = True
                    continue
                discarded.append(
                    {
                        "block": new_block["label"],
                        "row": new_block["labels"].get(
                            rel, f"第{new_block['start_row'] + rel + 1}行"
                        ),
                        "date": col_date.isoformat(),
                        "column": col,
                        "old": _merge_cell_text(old_value),
                        "new": _merge_cell_text(new_value),
                    }
                )
    report = {
        "recognized": bool(new_blocks),
        "matched_blocks": matched_blocks,
        "frozen_columns": frozen_columns,
        "discarded_changes": discarded,
        "truncated": truncated,
        # 修正已生效 = 显式修正模式且确有差异：无差异时为 False，
        # 调用方据此避免写入空审计记录与"修正 0 处"的误导文案
        "corrected": not freeze_past and bool(discarded),
    }
    return merged, report


def merge_schedule_rows_preserve_past(
    new_rows: list[list[Any]],
    old_rows: list[list[Any]],
    today: date,
) -> list[list[Any]]:
    """兼容包装：FA 表冻结历史列，仅返回合并后的行。

    原实现按 FA 布局内联，现统一走按产品适配的合并管线，FA 行为不变。
    """
    merged, _ = merge_schedule_rows_for_product(new_rows, old_rows, today, "FA")
    return merged


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
    block: dict[str, Any] | None = None,
    today: date | None = None,
    alert_now: datetime | None = None,
) -> dict[str, Any] | None:
    """由存档行与检修标注组装看板数据；无当前周期返回 None。

    actuals 为已录入的批次实际产量（serialize_batch_actual 列表），
    用于回填最近完成批次的放罐产量，并生成单批产量图表序列。
    block 为外部已定位的扎帐周期块（历史回看时传入，避免按 now 重新定位）；
    缺省时按 now 所在周期定位。
    today/alert_now 为漏录/进度告警的真实时间基准（汇总按所选月 15 日
    构建 now 时传入，单看板缺省即真实时间）。
    """
    if block is None:
        block = find_period_block(rows, now)
    if block is None:
        return None
    parsed = parse_block(rows, block)
    days = parsed["days"]
    block_note = parsed.get("block_note", "")
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
            if remain <= 0.5:
                note = "即将放罐"
            elif remain < 1:
                note = "不足 1h"
            else:
                note = f"距放罐约 {int(remain)}h"
            tanks.append(
                {
                    "tank_no": tank_no,
                    "status": "running",
                    "batch_no": running["batch_no"],
                    "inoculate_at": running["start"],
                    "cultured_hours": round(hours, 1),
                    "cycle_hours": round(cycle, 1),
                    "dump_at": running["dump_at"],
                    "note": note,
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
            if next_event:
                tanks.append(
                    {
                        "tank_no": tank_no,
                        "status": "idle",
                        "batch_no": None,
                        "inoculate_at": next_event["start"],
                        "cultured_hours": None,
                        "cycle_hours": None,
                        "dump_at": None,
                        "note": (
                            f"预计{next_event['start'].strftime('%m-%d %H:%M')}"
                            f"移种{next_event['batch_no']}"
                        ),
                    }
                )
                continue
            # 无后续移种：该罐最后一个放罐窗口已结束的批次 → 已放罐
            last_done = None
            for event in ferm_events:
                if event["tank_no"] != tank_no:
                    continue
                dump_day = dump_map.get(event["batch_no"])
                if dump_day is None:
                    continue
                dump_end = (
                    datetime.combine(dump_day, time(10, 0)) + DUMP_WINDOW
                )
                if dump_end <= now and (
                    last_done is None or event["start"] > last_done[0]
                ):
                    last_done = (event["start"], event["batch_no"], dump_day)
            if last_done:
                tanks.append(
                    {
                        "tank_no": tank_no,
                        "status": "dumped",
                        "batch_no": last_done[1],
                        "inoculate_at": None,
                        "cultured_hours": None,
                        "cycle_hours": None,
                        "dump_at": last_done[2].isoformat(),
                        "note": "该罐本批次放罐作业完成",
                    }
                )
            else:
                tanks.append(
                    {
                        "tank_no": tank_no,
                        "status": "idle",
                        "batch_no": None,
                        "inoculate_at": None,
                        "cultured_hours": None,
                        "cycle_hours": None,
                        "dump_at": None,
                        "note": "等待排产",
                    }
                )

    # ── KPI（扎帐月 = 当前块）──
    month_dump_count = sum(1 for item in days if item["dump_batch"])
    # 已放罐（窗口结束）的批次按是否已录入产量拆分，供进度条分段；
    # 已录入产量合计为"已完成产能"
    month_done_with_yield = 0
    month_yield_pending = 0
    month_done_yield_kg: float | None = None
    missing_dumps: list[tuple[str, datetime]] = []
    for item in days:
        if not item["dump_batch"]:
            continue
        dump_at = datetime.combine(item["date"], item["dump_time"] or time(10, 0))
        if dump_at + DUMP_WINDOW > now:
            continue
        yield_kg = (actual_by_batch.get(item["dump_batch"]) or {}).get("yield_kg")
        if yield_kg is None:
            month_yield_pending += 1
            missing_dumps.append((item["dump_batch"], dump_at + DUMP_WINDOW))
        else:
            month_done_with_yield += 1
            month_done_yield_kg = (month_done_yield_kg or 0) + float(yield_kg)
    month_done = month_done_with_yield + month_yield_pending
    # 运行中/未开始按「本周期计划放罐」口径统计（与 month_dump_count 分母
    # 一致）：放罐窗口未结束的计划批，已在罐（或移种时间已到）→ 运行中，
    # 否则未开始；跨周期放罐的在制罐不计入 KPI（罐状态板仍完整展示）
    tank_running_batches = {
        t["batch_no"] for t in tanks if t["status"] == "running"
    }
    ferm_starts = {ev["batch_no"]: ev["start"] for ev in _ferm_events(days)}
    running_count = 0
    pending_count = 0
    for item in days:
        if not item["dump_batch"]:
            continue
        dump_at = datetime.combine(item["date"], item["dump_time"] or time(10, 0))
        if dump_at + DUMP_WINDOW > now:
            start = ferm_starts.get(item["dump_batch"])
            if (
                item["dump_batch"] in tank_running_batches
                or (start is not None and start <= now)
            ):
                running_count += 1
            else:
                pending_count += 1
    seed_events = _seed_events(days)

    # ── 最近放罐（按计划，取放罐窗口已结束的批次，最多整个周期 31 批；
    #     前端表格内部滚动展示）──
    recent: list[dict[str, Any]] = []
    for item in reversed(days):
        if not item["dump_batch"]:
            continue
        dump_at = datetime.combine(item["date"], item["dump_time"] or time(10, 0))
        if dump_at + DUMP_WINDOW <= now:
            batch_actual = actual_by_batch.get(item["dump_batch"]) or {}
            batch_yield = batch_actual.get("yield_kg")
            batch_extract = batch_actual.get("extract_kg")
            inoculate = ferm_starts.get(item["dump_batch"])
            recent.append(
                {
                    "batch_no": item["dump_batch"],
                    "dump_date": item["date"].isoformat(),
                    "tank_no": item["dump_tank"] or "",
                    "yield_kg": batch_yield,
                    "extract_kg": batch_extract,
                    "batch_yield_rate": (
                        round(float(batch_extract) / float(batch_yield) * 100, 1)
                        if batch_yield and batch_extract is not None
                        else None
                    ),
                    "remark": batch_actual.get("remark"),
                    "yield_rate": None,
                    "result": "计划放罐",
                    # 凑数已放罐行展示用：移种时间与计划总周期
                    "inoculate_at": (
                        inoculate.isoformat() if inoculate else None
                    ),
                    "cycle_hours": (
                        round((dump_at - inoculate).total_seconds() / 3600, 1)
                        if inoculate
                        else None
                    ),
                }
            )
        if len(recent) >= 31:
            break
    if not recent:
        recent = []

    # ── 单批产量（本周期内已录入实际产量的批次，按批次顺序升序，最多 31 批）──
    # 批次归属周期：排产表有放罐日期的按排产判断，否则按录入的放罐日期判断
    block_start = cast(date, block["start"])
    block_end = cast(date, block["end"])

    def _batch_in_period(batch_no: str, record_date: Any) -> bool:
        raw_dump_day: Any = dump_map.get(batch_no)
        if raw_dump_day is None:
            raw_dump_day = record_date
        if isinstance(raw_dump_day, datetime):
            dump_day = raw_dump_day.date()
        elif isinstance(raw_dump_day, date):
            dump_day = raw_dump_day
        else:
            try:
                dump_day = date.fromisoformat(str(raw_dump_day))
            except (TypeError, ValueError):
                return False
        return block_start <= dump_day <= block_end

    measured = sorted(
        (
            a
            for a in (actuals or [])
            if a.get("yield_kg") is not None
            and _batch_in_period(a["batch_no"], a.get("dump_date"))
        ),
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
    # 排产备注：周期级汇总备注（备注行第 2 格）整月播报；
    # 按日期备注（第 3 格起）播今天及以后的，最多 6 条
    if block_note:
        alerts.append(
            {"level": "info", "text": f"【排产备注】{block_note}"}
        )
    schedule_notes = [
        item
        for item in days
        if item.get("note") and item["date"] >= now.date()
    ]
    for item in schedule_notes[:6]:
        alerts.append(
            {
                "level": "info",
                "text": (
                    f"【排产备注】{item['date'].strftime('%m-%d')}：{item['note']}"
                ),
            }
        )
    # 漏录/进度告警（放罐未录产量、周期末达成率落后；仅当前周期播）
    _append_kpi_alerts(
        alerts,
        block=block,
        now=alert_now or now,
        kpis={
            "month_planned": month_dump_count,
            "done_with_yield": month_done_with_yield,
        },
        missing_dumps=missing_dumps,
        today=today,
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
        "extraction_ledger": [
            {
                "batch_no": entry["batch_no"],
                "dump_date": entry["dump_date"],
                "yield_kg": (actual_by_batch.get(entry["batch_no"]) or {}).get(
                    "yield_kg"
                ),
                "extract_kg": (actual_by_batch.get(entry["batch_no"]) or {}).get(
                    "extract_kg"
                ),
            }
            for entry in dumped_batches
        ],
        "extraction": summarize_extraction(actuals or []),
        "alerts": alerts,
        "maintenance": maintenance,
    }


def summarize_extraction(actuals: list[dict[str, Any]]) -> dict[str, Any]:
    """提炼工段汇总：当期发酵放罐产量 vs 提炼成品产量与两种口径收率。

    - rate_realtime（实时口径）= Σ提炼成品 ÷ Σ发酵放罐（含尚未提炼的批次，
      反映实时进度，随放罐批数增大暂时走低）；
    - rate_paired（配对口径）= 已出成品批次内 Σ提炼成品 ÷ Σ对应放罐产量，
      反映真实工艺收率，不受在途批次影响。

    注意：提炼已出成品的权威数据源是成品日报（apply_daily_extract_source
    会在 API 层用日报合计覆盖本函数基于批次台账的成品合计）。
    """
    yields = [
        float(a["yield_kg"]) for a in actuals if a.get("yield_kg") is not None
    ]
    extracts = [
        float(a["extract_kg"]) for a in actuals if a.get("extract_kg") is not None
    ]
    paired = [
        (float(a["yield_kg"]), float(a["extract_kg"]))
        for a in actuals
        if a.get("yield_kg") is not None and a.get("extract_kg") is not None
    ]
    ferment_total = round(sum(yields), 2) if yields else None
    extract_total = round(sum(extracts), 2) if extracts else None

    def _rate(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or not denominator:
            return None
        return round(numerator / denominator * 100, 1)

    paired_extract = sum(e for _, e in paired) if paired else None
    paired_yield = sum(y for y, _ in paired) if paired else None
    return {
        "ferment_total_kg": ferment_total,
        "extract_total_kg": extract_total,
        "ferment_batches": len(yields),
        "extract_batches": len(extracts),
        "rate_realtime": _rate(extract_total, ferment_total),
        "rate_paired": _rate(paired_extract, paired_yield),
    }


async def sum_extraction_daily_reports(
    session: AsyncSession,
    period_start: date,
    period_end: date,
    product_code: str = "FA",
) -> list[float]:
    """当期成品日报的成品量列表（「提炼已出成品」KPI 的权威数据源）。"""
    from app.modules.production.extraction_report_models import (
        ExtractionDailyReport,
    )

    result = await session.execute(
        select(ExtractionDailyReport.quantity_kg).where(
            ExtractionDailyReport.is_deleted.is_(False),
            ExtractionDailyReport.product_code == product_code,
            ExtractionDailyReport.report_date >= period_start,
            ExtractionDailyReport.report_date <= period_end,
        )
    )
    return [float(value) for value in result.scalars().all()]


def apply_daily_extract_source(
    extraction: dict[str, Any] | None, daily_quantities: list[float]
) -> dict[str, Any] | None:
    """「提炼已出成品」以成品日报为唯一数据源。

    用日报合计覆盖提炼汇总中的成品合计、记录天数与实时收率；
    当期无日报记录时合计记为空（卡片显示 --），不回退批次台账口径。
    配对口径收率依赖批次级配对，仍取自批次台账。
    """
    if extraction is None:
        return None
    updated = {**extraction}
    if daily_quantities:
        daily_total = round(sum(daily_quantities), 2)
        updated["extract_total_kg"] = daily_total
        updated["extract_batches"] = len(daily_quantities)
        ferment_total = updated.get("ferment_total_kg")
        updated["rate_realtime"] = (
            round(daily_total / ferment_total * 100, 1) if ferment_total else None
        )
    else:
        updated["extract_total_kg"] = None
        updated["extract_batches"] = 0
        updated["rate_realtime"] = None
    return updated


def unified_accounting_period(today: date) -> tuple[date, date]:
    """统一扎帐周期：每月 27 日至次月 26 日（所有产品同规则）。

    新产品排产存档上传前无法从 Excel 定位周期，提炼入库合计
    以此统一规则取统计区间；排产上传后自动切换为存档块口径。
    """
    if today.day >= 27:
        start = today.replace(day=27)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=26)
        else:
            end = today.replace(month=today.month + 1, day=26)
    else:
        if today.month == 1:
            start = today.replace(year=today.year - 1, month=12, day=27)
        else:
            start = today.replace(month=today.month - 1, day=27)
        end = today.replace(day=26)
    return start, end


async def get_warehouse_finished_inbound_kg(
    session: AsyncSession,
    *,
    product_code: str,
    period_start: date,
    period_end: date,
) -> float | None:
    """「提炼已出成品（仓储成品入库）」卡片取数：当期仓储入库合计（KG）。

    跨模块只读仓储成品入库总账快照（走 warehouse.public_api）；
    未接入产品返回 None。仓储侧异常时降级为 None 并记录日志，
    看板其余模块不因仓储故障不可用。
    """
    product_name = WAREHOUSE_INBOUND_PRODUCT_NAMES.get(product_code)
    if product_name is None:
        return None
    from app.modules.warehouse.public_api import get_finished_inbound_kg_total

    try:
        return await get_finished_inbound_kg_total(
            session,
            product_name=product_name,
            start_date=period_start,
            end_date=period_end,
        )
    except Exception:  # noqa: BLE001 —— 看板卡片降级，仓储故障不阻断看板
        logger.exception(
            "warehouse finished inbound total failed",
            extra={"product_code": product_code},
        )
        return None


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


async def load_latest_archive(
    session: AsyncSession, product_code: str = "FA"
) -> ScheduleExcelArchive | None:
    result = await session.execute(
        select(ScheduleExcelArchive)
        .where(
            ScheduleExcelArchive.is_deleted.is_(False),
            ScheduleExcelArchive.product_code == product_code,
        )
        .order_by(ScheduleExcelArchive.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _board_functions(
    product_code: str,
) -> tuple[Callable[..., Any], Callable[..., Any]]:
    """按产品分派（块定位, 看板组装）函数对。

    FA/DR/MC 各自排产格式；他汀 LV/MV 复用 MC 管线。取档覆盖检查、
    扎帐周期解析、汇总聚合共用此分派，避免多处字典漂移。
    """
    if product_code == "DR":
        return find_dr_period_block, build_dr_board
    if product_code in ("MC", "LV", "MV"):
        return (
            partial(find_mp_period_block, product=product_code),
            partial(build_mp_board, product=product_code),
        )
    return find_period_block, build_board


async def load_archive_covering(
    session: AsyncSession,
    ref_date: date,
    product_code: str = "FA",
) -> ScheduleExcelArchive | None:
    """查找该产品 rows 覆盖指定日期所在扎帐周期的存档（含历史存档，从新到旧）。

    FA/DR/MC（含他汀 LV/MV）排产表格式不同：FA 按周期标题块、DR 按月度
    计划块（自然月列）、MC 按月度放罐计划块（批次序号列）识别。
    """
    ref_dt = datetime.combine(ref_date, time(12, 0))
    find_block, _ = _board_functions(product_code)
    result = await session.execute(
        select(ScheduleExcelArchive)
        .where(
            ScheduleExcelArchive.is_deleted.is_(False),
            ScheduleExcelArchive.product_code == product_code,
        )
        .order_by(ScheduleExcelArchive.created_at.desc())
        .limit(24)
    )
    for archive in result.scalars().all():
        if find_block(archive.rows, ref_dt) is not None:
            return archive
    return None


async def next_period_coverage_alert(
    session: AsyncSession,
    *,
    product_code: str,
    block: dict[str, Any],
    today: date,
) -> dict[str, Any] | None:
    """下周期排产未上传提醒：当前周期剩余 ≤3 天且无存档覆盖周期结束次日。

    仅临期窗口内查询存档（其余情形零额外查询）；块已结束（历史回看）
    或远期周期不提醒。复用 load_archive_covering 按产品格式找块，
    同一份竖排多月块的存档即可命中下一周期，不会误报。
    """
    remaining = (block["end"] - today).days
    if remaining < 0 or remaining > SCHEDULE_UPLOAD_WARN_DAYS:
        return None
    covered = await load_archive_covering(
        session, block["end"] + timedelta(days=1), product_code
    )
    if covered is not None:
        return None
    return {
        "level": "warn",
        "text": (
            f"【排产】本周期 {block['start'].isoformat()}～"
            f"{block['end'].isoformat()} 于 {block['end'].strftime('%m-%d')} 结束，"
            "尚无存档覆盖下一周期，请上传排产 Excel"
        ),
    }


# ═══════════════════ 批次实际产量（历史数据） ═══════════════════


def serialize_batch_actual(item: FermentationBatchActual) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "batch_no": item.batch_no,
        "dump_date": item.dump_date.isoformat() if item.dump_date else None,
        "yield_kg": item.yield_kg,
        "extract_kg": item.extract_kg,
        "remark": item.remark,
    }


async def list_batch_actuals(
    session: AsyncSession,
    period_start: date | None = None,
    period_end: date | None = None,
    product_code: str = "FA",
) -> list[FermentationBatchActual]:
    """按放罐日期列出批次产量；传入周期边界时仅返回该周期内的记录。"""
    stmt = select(FermentationBatchActual).where(
        FermentationBatchActual.is_deleted.is_(False),
        FermentationBatchActual.product_code == product_code,
    )
    if period_start is not None:
        stmt = stmt.where(FermentationBatchActual.dump_date >= period_start)
    if period_end is not None:
        stmt = stmt.where(FermentationBatchActual.dump_date <= period_end)
    stmt = stmt.order_by(
        FermentationBatchActual.dump_date.desc().nullslast(),
        FermentationBatchActual.batch_no.desc(),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def upsert_batch_actual(
    session: AsyncSession,
    *,
    batch_no: str,
    dump_date: date | None = None,
    yield_kg: float | None = None,
    extract_kg: float | None = None,
    remark: str | None = None,
    product_code: str = "FA",
    created_by: Any = None,
    provided_fields: set[str] | None = None,
) -> FermentationBatchActual:
    """同一产品下批次已存在进行中记录则更新（产品内批号唯一）。

    provided_fields 为请求体中显式给出的字段集合（缺省视为全量）；
    更新时仅覆盖显式给出的字段，防止某工段岗保存自身字段时
    清掉其他工段已录入的产量。
    """
    fields = provided_fields or {
        "dump_date",
        "yield_kg",
        "extract_kg",
        "remark",
    }
    result = await session.execute(
        select(FermentationBatchActual).where(
            FermentationBatchActual.batch_no == batch_no,
            FermentationBatchActual.product_code == product_code,
            FermentationBatchActual.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        item = FermentationBatchActual(
            batch_no=batch_no,
            dump_date=dump_date if "dump_date" in fields else None,
            yield_kg=yield_kg if "yield_kg" in fields else None,
            extract_kg=extract_kg if "extract_kg" in fields else None,
            remark=remark if "remark" in fields else None,
            product_code=product_code,
            created_by=created_by,
        )
        session.add(item)
    else:
        if "dump_date" in fields:
            item.dump_date = dump_date
        if "yield_kg" in fields:
            item.yield_kg = yield_kg
        if "extract_kg" in fields:
            item.extract_kg = extract_kg
        if "remark" in fields:
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
    rows: list[list[Any]], now: datetime, product_code: str = "FA"
) -> tuple[date, date] | None:
    """最新存档中包含 now 的扎帐周期 (start, end)。

    FA/DR/MC（含他汀 LV/MV）排产格式分派。
    """
    find_block, _ = _board_functions(product_code)
    block = find_block(rows, now)
    if block is None:
        return None
    return block["start"], block["end"]


_SUMMARY_PRODUCTS: tuple[tuple[str, str], ...] = (
    ("MC", "霉酚酸"),
    ("DR", "多拉菌素"),
    ("FA", "L-苯丙氨酸"),
    ("LV", "洛伐他汀"),
    ("MV", "美伐他汀"),
    ("TY", "L-色氨酸"),
    ("FL", "2%氟苯尼考预混剂"),
)


def _summary_rate(
    numerator: float | None, denominator: float | None
) -> float | None:
    """比率（百分数，1 位小数）；分母缺失或非正时返回 None。"""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def _extract_planned_yield_kg(
    plan_rows: Sequence[ProductionPlan], product_name: str
) -> float | None:
    """产销计划中该产品提炼车间行（车间名不含'发酵'）的 KG 计划合计。

    发酵车间行是发酵段口径（单位'批'），不计入提炼计划；无行返回 None。
    """
    total = 0.0
    found = False
    for row in plan_rows:
        if row.is_deleted or row.product_name != product_name:
            continue
        if not row.planned_yield:
            continue
        if "发酵" in (row.workshop or ""):
            continue
        found = True
        total += float(row.planned_yield)
    return round(total, 2) if found else None


async def build_production_summary(
    db: AsyncSession,
    *,
    ref_date: date,
    has_ferm: bool,
    has_extract: bool,
    today: date | None = None,
    alert_now: datetime | None = None,
) -> dict[str, Any]:
    """生产汇总：七条产线的发酵/提炼关键指标。

    逐产品复用既有看板口径（月计划批次、月计划产能、已完成产能），
    提炼段取产销计划提炼车间行与仓储成品入库，入库与计划同按
    扎帐周期口径：有存档用存档块周期，无存档（新产品排产未上传）
    用统一扎帐周期（27日～26日）；权限不足的段返回 None。
    KPI 的放罐窗口门控与告警统一按真实当前时间（alert_now，API 层传入），
    与单产品看板口径一致：已过放罐窗口的批次即为已放罐；此前按所选月
    15 日构建看板 now，16 日起放罐的批次在当月汇总中永久缺席。
    所选月 15 日锚点只用于存档覆盖与周期块定位（15 日必落在该月对应的
    扎帐周期内）；缺省时退回所选日期（直调兼容）。
    """
    kpi_today = today or ref_date
    kpi_now = alert_now or datetime.combine(ref_date, time(12, 0))
    month_start = ref_date.replace(day=1)
    month_end = month_start.replace(
        day=calendar.monthrange(ref_date.year, ref_date.month)[1]
    )
    plan_rows = (
        await db.execute(
            select(ProductionPlan).where(
                ProductionPlan.plan_date >= month_start,
                ProductionPlan.plan_date <= month_end,
                ProductionPlan.is_deleted.is_(False),
            )
        )
    ).scalars().all()

    # 周期块定位锚点：只决定"该月对应哪个扎帐周期"，不参与 KPI 门控
    anchor_dt = datetime.combine(ref_date, time(12, 0))
    rows: list[dict[str, Any]] = []
    period: dict[str, str] | None = None
    for code, name in _SUMMARY_PRODUCTS:
        ferment: dict[str, Any] = {
            "planned_batches": None,
            "planned_capacity_kg": None,
            "done_yield_kg": None,
            "capacity_rate": None,
        }
        extract: dict[str, Any] = {
            "planned_yield_kg": None,
            "finished_inbound_kg": None,
            "completion_rate": None,
        }
        covered = False
        extract_period: tuple[date, date] | None = None
        board_alerts: list[dict[str, Any]] = []
        archive = await load_archive_covering(db, ref_date, code)
        if archive is not None:
            find_block, build_board_fn = _board_functions(code)
            block = find_block(archive.rows, anchor_dt)
            if block is not None:
                covered = True
                extract_period = (block["start"], block["end"])
                if period is None:
                    period = {
                        "start": block["start"].isoformat(),
                        "end": block["end"].isoformat(),
                        "label": block["label"],
                    }
                if has_ferm:
                    actuals = await list_batch_actuals(
                        db,
                        period_start=block["start"],
                        period_end=block["end"],
                        product_code=code,
                    )
                    payload = build_board_fn(
                        archive.rows,
                        [],
                        kpi_now,
                        actuals=[
                            serialize_batch_actual(item) for item in actuals
                        ],
                        block=block,
                        today=kpi_today,
                        alert_now=kpi_now,
                    )
                    board_alerts = payload.get("alerts") or []
                    # 下周期排产未上传提醒：同样按真实今天判定临期
                    schedule_alert = await next_period_coverage_alert(
                        db, product_code=code, block=block, today=kpi_today
                    )
                    if schedule_alert:
                        board_alerts.append(schedule_alert)
                    kpis = payload.get("kpis") or {}
                    ferment["planned_batches"] = kpis.get("month_planned")
                    setting = await get_month_setting(
                        db, block["start"], code
                    )
                    ferment["planned_capacity_kg"] = (
                        setting.planned_capacity_kg if setting else None
                    )
                    ferment["done_yield_kg"] = kpis.get("month_done_yield_kg")
                    ferment["capacity_rate"] = _summary_rate(
                        ferment["done_yield_kg"],
                        ferment["planned_capacity_kg"],
                    )
        if has_extract:
            # 提炼口径与计划一致按扎帐周期：有存档用存档块周期，
            # 无存档（新产品排产未上传）用统一扎帐周期（27日～26日）
            if extract_period is None:
                extract_period = unified_accounting_period(ref_date)
            extract["planned_yield_kg"] = _extract_planned_yield_kg(
                plan_rows, name
            )
            extract["finished_inbound_kg"] = (
                await get_warehouse_finished_inbound_kg(
                    db,
                    product_code=code,
                    period_start=extract_period[0],
                    period_end=extract_period[1],
                )
            )
            extract["completion_rate"] = _summary_rate(
                extract["finished_inbound_kg"], extract["planned_yield_kg"]
            )
        rows.append(
            {
                "product_code": code,
                "product_name": name,
                "covered": covered,
                "ferment": ferment,
                "extract": extract,
                # 该产线的排产播报（发酵权限可见）；未覆盖产线为空
                "alerts": board_alerts if has_ferm else [],
            }
        )
    # 停产产线仅在查看当前月汇总时隐藏（历史月份照常显示全部产线）
    halted_map = await get_line_halted_map(db)
    halted_lines = {
        code
        for code, halted in halted_map.items()
        if halted
        and ref_date.year == kpi_today.year
        and ref_date.month == kpi_today.month
    }
    if halted_lines:
        rows = [row for row in rows if row["product_code"] not in halted_lines]
    return {"period": period, "rows": rows}


async def get_month_setting(
    session: AsyncSession,
    period_start: date,
    product_code: str = "FA",
) -> FermentationMonthSetting | None:
    result = await session.execute(
        select(FermentationMonthSetting).where(
            FermentationMonthSetting.period_start == period_start,
            FermentationMonthSetting.product_code == product_code,
            FermentationMonthSetting.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def get_line_halted_map(session: AsyncSession) -> dict[str, bool]:
    """全部产品生产线的停产状态映射（未记录的产品视为生产中）。"""
    result = await session.execute(
        select(ProductionLineStatus).where(
            ProductionLineStatus.is_deleted.is_(False)
        )
    )
    return {
        item.product_code: bool(item.halted)
        for item in result.scalars().all()
    }


async def set_line_halted(
    session: AsyncSession,
    *,
    product_code: str,
    halted: bool,
    updated_by: Any = None,
) -> ProductionLineStatus:
    """设置产品生产线停产状态（upsert；人工即时状态，不自动恢复）。"""
    result = await session.execute(
        select(ProductionLineStatus).where(
            ProductionLineStatus.product_code == product_code,
            ProductionLineStatus.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        item = ProductionLineStatus(product_code=product_code, halted=halted)
        session.add(item)
    else:
        item.halted = halted
    if updated_by is not None:
        item.updated_by = updated_by
    await session.flush()
    return item


async def upsert_month_setting(
    session: AsyncSession,
    *,
    period_start: date,
    period_end: date,
    planned_capacity_kg: float | None,
    product_code: str = "FA",
    updated_by: Any = None,
) -> FermentationMonthSetting:
    """同一产品下周期存在进行中记录则更新。"""
    result = await session.execute(
        select(FermentationMonthSetting).where(
            FermentationMonthSetting.period_start == period_start,
            FermentationMonthSetting.product_code == product_code,
            FermentationMonthSetting.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        item = FermentationMonthSetting(
            period_start=period_start,
            period_end=period_end,
            planned_capacity_kg=planned_capacity_kg,
            product_code=product_code,
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
