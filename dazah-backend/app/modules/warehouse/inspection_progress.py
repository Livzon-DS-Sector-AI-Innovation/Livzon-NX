"""仓储检验进度统计.

数据源：
- ``warehouse.material_page_rows`` 镜像行（业务字段：入库日期/检测结果/质量状态等）
- ``warehouse.material_status_transitions`` 状态变更日志（同步镜像行时对比
  受监控字段捕获，见 repository.upsert_material_page_rows*）

统计口径（2026-09-09 拍板）：
- 从 ``INSPECTION_STATS_START_DATE`` 起统计，上线前的批次不回溯、不统计；
- 原辅料及包材（inbound-ledger）：检验周期 = 检测结果出结果时刻 − 入库日期；
- 成品：入库日期（product-inbound-detail 按批号关联）→ 待验开始（行初始
  状态记录时刻）→ 合格/不合格，分段统计。

本模块是 warehouse 模块的叶子依赖（仅依赖 models），service.py 与
repository.py 均从此导入共享常量，避免循环引用。
"""

from __future__ import annotations

import time as time_module
from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.models import (
    MaterialPageRow,
    MaterialPageSnapshot,
    MaterialStatusTransition,
)

CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")

# ── 页面与字段常量 ────────────────────────────────────────────────

INBOUND_LEDGER_PAGE_KEY = "inbound-ledger"
PRODUCT_INBOUND_DETAIL_PAGE_KEY = "product-inbound-detail"

# 成品库存按产品分表（每产品一张明细表）
FINISHED_PRODUCT_DETAIL_PAGE_KEYS = {
    "product-detail-l-phenylalanine",
    "product-detail-fumaric-acid",
    "product-detail-l-tryptophan",
    "product-detail-mevastatin",
    "product-detail-kitasamycin-hcl",
    "product-detail-doramectin",
    "product-detail-lovastatin",
    "product-detail-florfenicol-premix",
    "product-detail-demeclocycline-hcl",
    "product-detail-fenbendazole-powder",
}

RESULT_FIELD = "检测结果"
QUALITY_STATUS_FIELD = "质量状态"

# 每页监控的状态字段；不在表内的页面不捕获变更
INSPECTION_WATCHED_FIELDS: dict[str, str] = {
    INBOUND_LEDGER_PAGE_KEY: RESULT_FIELD,
    **{
        page_key: QUALITY_STATUS_FIELD
        for page_key in FINISHED_PRODUCT_DETAIL_PAGE_KEYS
    },
}

# 检验周期统计起点（上线日，Asia/Shanghai）；之前的批次不统计
INSPECTION_STATS_START_DATE = date(2026, 9, 9)

RESULT_QUALIFIED = "合格"
RESULT_UNQUALIFIED = "不合格"
PENDING_STATUS = "待验"

INBOUND_DATE_FIELD = "入库日期"
INSPECTION_REQUEST_FIELD = "是否请检"
MATERIAL_CATEGORY_FIELD = "物料类别"
MATERIAL_NAME_FIELD = "物料名称"
FACTORY_BATCH_FIELD = "厂内批号"
SPEC_FIELD = "规格"
PRODUCT_NAME_FIELD = "产品名称"
LABEL_BATCH_FIELD = "入库标签批号"
FRONT_BATCH_FIELD = "对应前台批号"

SCOPE_LABELS = {
    "raw": "原辅料及包材",
    "product": "成品",
}

_INSPECTION_OVERVIEW_CACHE: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}
_INSPECTION_OVERVIEW_CACHE_TTL_SECONDS = 300.0


def inspection_watched_field(page_key: str) -> str | None:
    """页面受监控的状态字段名；不受监控的页面返回 None。"""
    return INSPECTION_WATCHED_FIELDS.get(page_key)


# ── 同步捕获辅助（repository 使用） ──────────────────────────────


def inspection_status_text(value: object | None) -> str | None:
    """受监控字段取值归一化为可比较文本（空/None → None）。"""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return "、".join(parts) or None
    if isinstance(value, dict):
        return None
    return str(value)


def milliseconds_to_datetime(value: object | None) -> datetime | None:
    """飞书毫秒时间戳 → UTC datetime；非法值返回 None。"""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def cell_datetime(value: object | None) -> datetime | None:
    """镜像 cells 中的日期取值（飞书毫秒时间戳）→ 中国时区 datetime。"""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=CHINA_TIMEZONE)
    except (OverflowError, OSError, ValueError):
        return None


def build_change_transition(
    *,
    page_key: str,
    page_snapshot_id: Any,
    source_record_id: str,
    field_name: str,
    old_value: object | None,
    new_value: object | None,
    modified_ms: object | None,
    detected_at: datetime,
) -> MaterialStatusTransition | None:
    """构建已有行的状态变更日志；取值未变化时返回 None。"""
    old_text = inspection_status_text(old_value)
    new_text = inspection_status_text(new_value)
    if old_text == new_text:
        return None
    occurred_at = milliseconds_to_datetime(modified_ms) or detected_at
    return MaterialStatusTransition(
        page_key=page_key,
        page_snapshot_id=page_snapshot_id,
        source_record_id=source_record_id,
        field_name=field_name,
        old_value=old_text,
        new_value=new_text,
        occurred_at=occurred_at,
        detected_at=detected_at,
    )


def build_initial_transition(
    *,
    page_key: str,
    page_snapshot_id: Any,
    source_record_id: str,
    field_name: str,
    new_value: object | None,
    occurred_ms: object | None,
    modified_ms: object | None,
    detected_at: datetime,
) -> MaterialStatusTransition:
    """构建新进入镜像行的初始状态记录（old_value=None，作为起点锚）。"""
    new_text = inspection_status_text(new_value)
    occurred_at = (
        milliseconds_to_datetime(occurred_ms)
        or milliseconds_to_datetime(modified_ms)
        or detected_at
    )
    return MaterialStatusTransition(
        page_key=page_key,
        page_snapshot_id=page_snapshot_id,
        source_record_id=source_record_id,
        field_name=field_name,
        old_value=None,
        new_value=new_text,
        occurred_at=occurred_at,
        detected_at=detected_at,
    )


# ── 数据加载 ──────────────────────────────────────────────────────


async def load_page_rows(
    session: AsyncSession, page_key: str
) -> list[MaterialPageRow]:
    snapshot = await session.scalar(
        select(MaterialPageSnapshot).where(
            MaterialPageSnapshot.page_key == page_key,
            MaterialPageSnapshot.is_deleted.is_(False),
        )
    )
    if snapshot is None:
        return []
    result = await session.execute(
        select(MaterialPageRow)
        .where(
            MaterialPageRow.page_snapshot_id == snapshot.id,
            MaterialPageRow.is_deleted.is_(False),
        )
        .order_by(MaterialPageRow.row_order.asc())
    )
    return list(result.scalars().all())


async def load_page_row(
    session: AsyncSession, page_key: str, record_id: str
) -> MaterialPageRow | None:
    snapshot = await session.scalar(
        select(MaterialPageSnapshot).where(
            MaterialPageSnapshot.page_key == page_key,
            MaterialPageSnapshot.is_deleted.is_(False),
        )
    )
    if snapshot is None:
        return None
    return await session.scalar(
        select(MaterialPageRow).where(
            MaterialPageRow.page_snapshot_id == snapshot.id,
            MaterialPageRow.source_record_id == record_id,
            MaterialPageRow.is_deleted.is_(False),
        )
    )


async def load_transitions(
    session: AsyncSession,
    page_keys: Collection[str],
    *,
    record_ids: Collection[str] | None = None,
) -> list[MaterialStatusTransition]:
    if not page_keys:
        return []
    stmt = select(MaterialStatusTransition).where(
        MaterialStatusTransition.page_key.in_(page_keys),
        MaterialStatusTransition.is_deleted.is_(False),
    )
    if record_ids is not None:
        stmt = stmt.where(MaterialStatusTransition.source_record_id.in_(record_ids))
    stmt = stmt.order_by(
        MaterialStatusTransition.occurred_at.asc(),
        MaterialStatusTransition.detected_at.asc(),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _group_transitions(
    transitions: Sequence[MaterialStatusTransition],
) -> dict[tuple[str, str], list[MaterialStatusTransition]]:
    grouped: dict[tuple[str, str], list[MaterialStatusTransition]] = defaultdict(list)
    for transition in transitions:
        grouped[(transition.page_key, transition.source_record_id)].append(transition)
    return grouped


def _hours_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    seconds = (end - start).total_seconds()
    if seconds < 0:
        seconds = 0.0
    return round(seconds / 3600, 2)


def _percentile(values: Sequence[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(ratio * (len(ordered) - 1))))
    return round(ordered[index], 2)


def _avg(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _stats_start_datetime() -> datetime:
    return datetime.combine(
        INSPECTION_STATS_START_DATE, datetime.min.time(), tzinfo=CHINA_TIMEZONE
    )


def _latest_result_transition(
    transitions: Sequence[MaterialStatusTransition], result: str | None
) -> MaterialStatusTransition | None:
    """最近一次取值等于 result 的变更（含初始记录）。"""
    if not result:
        return None
    matched = [item for item in transitions if item.new_value == result]
    return matched[-1] if matched else None


# ── 行级检验周期（记录详情使用） ─────────────────────────────────


def clear_inspection_overview_cache() -> None:
    """清空概览进程缓存（测试/强制刷新用）。"""
    _INSPECTION_OVERVIEW_CACHE.clear()


async def build_record_inspection_cycle(
    session: AsyncSession,
    page_key: str,
    record_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """计算单条记录的检验进度周期；不受监控的页面返回 None。"""
    field_name = inspection_watched_field(page_key)
    if field_name is None:
        return None
    current = (now or datetime.now(CHINA_TIMEZONE)).astimezone(CHINA_TIMEZONE)
    row = await load_page_row(session, page_key, record_id)
    transitions = _group_transitions(
        await load_transitions(session, [page_key], record_ids=[record_id])
    ).get((page_key, record_id), [])

    if page_key == INBOUND_LEDGER_PAGE_KEY:
        return _build_raw_record_cycle(page_key, record_id, row, transitions, current)
    return await _build_product_record_cycle_async(
        session, page_key, record_id, row, transitions, current
    )


def _cycle_payload(
    *,
    page_key: str,
    record_id: str,
    status: str,
    status_label: str,
    result: str | None = None,
    inbound_date: str | None = None,
    pending_since: datetime | None = None,
    result_at: datetime | None = None,
    stages: list[dict[str, Any]] | None = None,
    total_hours: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "page_key": page_key,
        "record_id": record_id,
        "status": status,
        "status_label": status_label,
        "result": result,
        "inbound_date": inbound_date,
        "pending_since": pending_since,
        "result_at": result_at,
        "stages": stages or [],
        "total_hours": total_hours,
        "note": note,
    }


def _build_raw_record_cycle(
    page_key: str,
    record_id: str,
    row: MaterialPageRow | None,
    transitions: Sequence[MaterialStatusTransition],
    now: datetime,
) -> dict[str, Any]:
    start_dt = _stats_start_datetime()
    cells: dict[str, Any] = (row.cells if row else None) or {}
    inbound = cell_datetime(cells.get(INBOUND_DATE_FIELD))
    inbound_date = inbound.date().isoformat() if inbound else None
    result = inspection_status_text(cells.get(RESULT_FIELD))
    inspection_requested = inspection_status_text(
        cells.get(INSPECTION_REQUEST_FIELD)
    )

    if inbound is None:
        return _cycle_payload(
            page_key=page_key,
            record_id=record_id,
            status="no_data",
            status_label="无入库日期",
            result=result,
            note="记录缺少入库日期，无法统计检验周期",
        )
    if inbound < start_dt:
        return _cycle_payload(
            page_key=page_key,
            record_id=record_id,
            status="not_counted",
            status_label="上线前批次（不统计）",
            result=result,
            inbound_date=inbound_date,
            note="入库日期早于统计起点（2026-09-09），不纳入检验周期统计",
        )
    if result in (RESULT_QUALIFIED, RESULT_UNQUALIFIED):
        transition = _latest_result_transition(transitions, result)
        if transition is None:
            return _cycle_payload(
                page_key=page_key,
                record_id=record_id,
                status="not_counted",
                status_label="上线前已出结果（不统计）",
                result=result,
                inbound_date=inbound_date,
                note="检测结果在统计功能上线前已出，无变更时刻记录",
            )
        total_hours = _hours_between(inbound, transition.occurred_at)
        return _cycle_payload(
            page_key=page_key,
            record_id=record_id,
            status="completed",
            status_label="已完成",
            result=result,
            inbound_date=inbound_date,
            result_at=transition.occurred_at,
            stages=[
                {
                    "label": "入库 → 检测结果",
                    "hours": total_hours,
                    "from_at": inbound,
                    "to_at": transition.occurred_at,
                }
            ],
            total_hours=total_hours,
        )
    if inspection_requested == "否":
        return _cycle_payload(
            page_key=page_key,
            record_id=record_id,
            status="not_applicable",
            status_label="无需检验",
            result=None,
            inbound_date=inbound_date,
            note="是否请检为「否」，不参与检验周期统计",
        )
    waited_hours = _hours_between(inbound, now)
    return _cycle_payload(
        page_key=page_key,
        record_id=record_id,
        status="pending",
        status_label="待验中",
        result=None,
        inbound_date=inbound_date,
        pending_since=inbound,
        stages=[
            {
                "label": "入库 → 至今（待验中）",
                "hours": waited_hours,
                "from_at": inbound,
                "to_at": now,
            }
        ],
        total_hours=waited_hours,
    )


async def _build_product_inbound_map(
    session: AsyncSession,
) -> dict[str, datetime]:
    """成品入库明细：批号（标签/前台）→ 最近入库日期。"""
    inbound_rows = await load_page_rows(session, PRODUCT_INBOUND_DETAIL_PAGE_KEY)
    batch_map: dict[str, datetime] = {}
    for item in inbound_rows:
        cells: dict[str, Any] = item.cells or {}
        inbound = cell_datetime(cells.get(INBOUND_DATE_FIELD))
        if inbound is None:
            continue
        for field in (LABEL_BATCH_FIELD, FRONT_BATCH_FIELD):
            batch = inspection_status_text(cells.get(field))
            if not batch:
                continue
            existing = batch_map.get(batch)
            if existing is None or inbound > existing:
                batch_map[batch] = inbound
    return batch_map


async def _build_product_record_cycle_async(
    session: AsyncSession,
    page_key: str,
    record_id: str,
    row: MaterialPageRow | None,
    transitions: Sequence[MaterialStatusTransition],
    now: datetime,
) -> dict[str, Any]:
    start_dt = _stats_start_datetime()
    cells: dict[str, Any] = (row.cells if row else None) or {}
    status = inspection_status_text(cells.get(QUALITY_STATUS_FIELD))
    batch_map = await _build_product_inbound_map(session)
    inbound = None
    for field in (LABEL_BATCH_FIELD, FRONT_BATCH_FIELD):
        batch = inspection_status_text(cells.get(field))
        if batch and batch in batch_map:
            inbound = batch_map[batch]
            break
    inbound_date = inbound.date().isoformat() if inbound else None

    if inbound is None:
        return _cycle_payload(
            page_key=page_key,
            record_id=record_id,
            status="no_data",
            status_label="无入库记录",
            result=status,
            note="未在成品入库明细中按批号匹配到入库日期，无法统计检验周期",
        )
    if not transitions:
        return _cycle_payload(
            page_key=page_key,
            record_id=record_id,
            status="not_counted",
            status_label="上线前批次（不统计）",
            result=status,
            inbound_date=inbound_date,
            note="记录在统计功能上线前已存在，无待验开始时刻，不纳入统计",
        )
    if inbound < start_dt:
        return _cycle_payload(
            page_key=page_key,
            record_id=record_id,
            status="not_counted",
            status_label="上线前批次（不统计）",
            result=status,
            inbound_date=inbound_date,
            note="入库日期早于统计起点（2026-09-09），不纳入检验周期统计",
        )

    initial = transitions[0]
    pending_since = initial.occurred_at
    stage1_hours = _hours_between(inbound, pending_since)

    if status in (RESULT_QUALIFIED, RESULT_UNQUALIFIED):
        transition = _latest_result_transition(transitions, status)
        result_at = transition.occurred_at if transition else pending_since
        stage2_hours = _hours_between(pending_since, result_at)
        total_hours = _hours_between(inbound, result_at)
        return _cycle_payload(
            page_key=page_key,
            record_id=record_id,
            status="completed",
            status_label="已完成",
            result=status,
            inbound_date=inbound_date,
            pending_since=pending_since,
            result_at=result_at,
            stages=[
                {
                    "label": "入库 → 待验",
                    "hours": stage1_hours,
                    "from_at": inbound,
                    "to_at": pending_since,
                },
                {
                    "label": f"待验 → {status}",
                    "hours": stage2_hours,
                    "from_at": pending_since,
                    "to_at": result_at,
                },
            ],
            total_hours=total_hours,
        )

    waited_hours = _hours_between(inbound, now)
    return _cycle_payload(
        page_key=page_key,
        record_id=record_id,
        status="pending",
        status_label="待验中",
        result=None,
        inbound_date=inbound_date,
        pending_since=pending_since,
        stages=[
            {
                "label": "入库 → 待验",
                "hours": stage1_hours,
                "from_at": inbound,
                "to_at": pending_since,
            },
            {
                "label": "待验 → 至今（待验中）",
                "hours": _hours_between(pending_since, now),
                "from_at": pending_since,
                "to_at": now,
            },
        ],
        total_hours=waited_hours,
    )


# ── 概览统计（仪表盘使用） ───────────────────────────────────────


async def build_inspection_overview(
    session: AsyncSession,
    scope: str,
    *,
    days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """检验进度概览；scope ∈ {raw, product}。"""
    if scope not in SCOPE_LABELS:
        raise ValueError(f"未知检验进度统计范围：{scope}")
    current = (now or datetime.now(CHINA_TIMEZONE)).astimezone(CHINA_TIMEZONE)
    cache_key = (scope, days)
    cached = _INSPECTION_OVERVIEW_CACHE.get(cache_key)
    ttl_ok = (
        cached is not None
        and time_module.monotonic() - cached[0] < _INSPECTION_OVERVIEW_CACHE_TTL_SECONDS
    )
    if ttl_ok and cached is not None:
        return cached[1]
    if scope == "raw":
        payload = await _build_raw_overview(session, days, current)
    else:
        payload = await _build_product_overview(session, days, current)
    payload["scope"] = scope
    payload["scope_label"] = SCOPE_LABELS[scope]
    payload["start_date"] = INSPECTION_STATS_START_DATE.isoformat()
    payload["generated_at"] = current.isoformat()
    _INSPECTION_OVERVIEW_CACHE[cache_key] = (time_module.monotonic(), payload)
    return payload


def _daily_series(
    days: int,
    completed: Sequence[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    """按出结果日聚合每日完成数与平均周期（近 days 天，含今日，补零）。"""
    window_start_date = (now - timedelta(days=days - 1)).date()
    buckets: dict[date, dict[str, Any]] = {}
    for offset in range(days):
        day = window_start_date + timedelta(days=offset)
        buckets[day] = {
            "date": day.isoformat(),
            "qualified": 0,
            "unqualified": 0,
            "hours": [],
        }
    for entry in completed:
        # occurred_at 为 UTC，按中国时区归一后分桶
        result_day = entry["result_at"].astimezone(CHINA_TIMEZONE).date()
        bucket = buckets.get(result_day)
        if bucket is None:
            continue
        if entry["result"] == RESULT_UNQUALIFIED:
            bucket["unqualified"] += 1
        else:
            bucket["qualified"] += 1
        if entry["total_hours"] is not None:
            bucket["hours"].append(entry["total_hours"])
    series = []
    for day in sorted(buckets):
        bucket = buckets[day]
        series.append(
            {
                "date": bucket["date"],
                "qualified": bucket["qualified"],
                "unqualified": bucket["unqualified"],
                "avg_hours": _avg(bucket["hours"]),
            }
        )
    return series


def _window_summary(
    completed: Sequence[dict[str, Any]],
    days: int,
    now: datetime,
) -> dict[str, Any]:
    window_start = now - timedelta(days=days)
    window_entries = [
        item
        for item in completed
        if item["result_at"].astimezone(CHINA_TIMEZONE) >= window_start
    ]
    hours = [
        item["total_hours"]
        for item in window_entries
        if item["total_hours"] is not None
    ]
    return {
        "days": days,
        "start": window_start.date().isoformat(),
        "end": now.date().isoformat(),
        "completed_count": len(window_entries),
        "qualified_count": sum(
            1 for item in window_entries if item["result"] != RESULT_UNQUALIFIED
        ),
        "unqualified_count": sum(
            1 for item in window_entries if item["result"] == RESULT_UNQUALIFIED
        ),
        "avg_hours": _avg(hours),
        "median_hours": round(median(hours), 2) if hours else None,
        "p90_hours": _percentile(hours, 0.9),
        "max_hours": round(max(hours), 2) if hours else None,
    }


def _pending_summary(pending: Sequence[dict[str, Any]]) -> dict[str, Any]:
    hours = [
        item["waited_hours"] for item in pending if item["waited_hours"] is not None
    ]
    return {
        "pending_count": len(pending),
        "pending_avg_hours": _avg(hours),
        "pending_max_hours": round(max(hours), 2) if hours else None,
    }


async def _build_raw_overview(
    session: AsyncSession, days: int, now: datetime
) -> dict[str, Any]:
    start_dt = _stats_start_datetime()
    rows = await load_page_rows(session, INBOUND_LEDGER_PAGE_KEY)
    transitions = _group_transitions(
        await load_transitions(session, [INBOUND_LEDGER_PAGE_KEY])
    )

    pending: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    breakdown_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "label": "",
            "completed_count": 0,
            "qualified_count": 0,
            "unqualified_count": 0,
            "hours": [],
            "pending_count": 0,
        }
    )

    for item in rows:
        cells: dict[str, Any] = item.cells or {}
        inbound = cell_datetime(cells.get(INBOUND_DATE_FIELD))
        if inbound is None or inbound < start_dt:
            continue
        category = (
            inspection_status_text(cells.get(MATERIAL_CATEGORY_FIELD)) or "未分类"
        )
        result = inspection_status_text(cells.get(RESULT_FIELD))
        if result in (RESULT_QUALIFIED, RESULT_UNQUALIFIED):
            transition = _latest_result_transition(
                transitions.get((INBOUND_LEDGER_PAGE_KEY, item.source_record_id), []),
                result,
            )
            if transition is None:
                continue
            bucket = breakdown_map[category]
            bucket["label"] = category
            total_hours = _hours_between(inbound, transition.occurred_at)
            completed.append(
                {
                    "result": result,
                    "result_at": transition.occurred_at,
                    "total_hours": total_hours,
                    "label": category,
                }
            )
            bucket["completed_count"] += 1
            if result == RESULT_UNQUALIFIED:
                bucket["unqualified_count"] += 1
            else:
                bucket["qualified_count"] += 1
            if total_hours is not None:
                bucket["hours"].append(total_hours)
        else:
            if inspection_status_text(cells.get(INSPECTION_REQUEST_FIELD)) == "否":
                continue
            bucket = breakdown_map[category]
            bucket["label"] = category
            waited_hours = _hours_between(inbound, now)
            pending.append(
                {
                    "name": inspection_status_text(cells.get(MATERIAL_NAME_FIELD))
                    or "未命名物料",
                    "batch": inspection_status_text(cells.get(FACTORY_BATCH_FIELD)),
                    "category": category,
                    "inbound_date": inbound.date().isoformat(),
                    "waited_hours": waited_hours,
                }
            )
            bucket["pending_count"] += 1

    breakdown = []
    for category in sorted(breakdown_map):
        bucket = breakdown_map[category]
        breakdown.append(
            {
                "label": bucket["label"],
                "completed_count": bucket["completed_count"],
                "qualified_count": bucket["qualified_count"],
                "unqualified_count": bucket["unqualified_count"],
                "avg_hours": _avg(bucket["hours"]),
                "pending_count": bucket["pending_count"],
            }
        )

    pending.sort(key=lambda item: item["waited_hours"] or 0, reverse=True)
    return {
        "current": _pending_summary(pending),
        "window": _window_summary(completed, days, now),
        "breakdown": breakdown,
        "daily": _daily_series(days, completed, now),
        "oldest_pending": pending[:5],
        "stages": None,
    }


async def _build_product_overview(
    session: AsyncSession, days: int, now: datetime
) -> dict[str, Any]:
    start_dt = _stats_start_datetime()
    batch_map = await _build_product_inbound_map(session)
    page_keys = sorted(FINISHED_PRODUCT_DETAIL_PAGE_KEYS)
    transitions = _group_transitions(await load_transitions(session, page_keys))

    pending: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    stage1_hours_list: list[float] = []
    stage2_hours_list: list[float] = []
    breakdown_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "label": "",
            "completed_count": 0,
            "qualified_count": 0,
            "unqualified_count": 0,
            "hours": [],
            "pending_count": 0,
        }
    )

    for page_key in page_keys:
        rows = await load_page_rows(session, page_key)
        for item in rows:
            cells: dict[str, Any] = item.cells or {}
            inbound = None
            for field in (LABEL_BATCH_FIELD, FRONT_BATCH_FIELD):
                batch = inspection_status_text(cells.get(field))
                if batch and batch in batch_map:
                    inbound = batch_map[batch]
                    break
            if inbound is None or inbound < start_dt:
                continue
            record_transitions = transitions.get((page_key, item.source_record_id), [])
            if not record_transitions:
                continue
            initial = record_transitions[0]
            pending_since = initial.occurred_at
            product_label = (
                inspection_status_text(cells.get(PRODUCT_NAME_FIELD)) or page_key
            )
            bucket = breakdown_map[product_label]
            bucket["label"] = product_label
            stage1_hours = _hours_between(inbound, pending_since)
            status = inspection_status_text(cells.get(QUALITY_STATUS_FIELD))
            if status in (RESULT_QUALIFIED, RESULT_UNQUALIFIED):
                transition = _latest_result_transition(record_transitions, status)
                result_at = transition.occurred_at if transition else pending_since
                stage2_hours = _hours_between(pending_since, result_at)
                total_hours = _hours_between(inbound, result_at)
                completed.append(
                    {
                        "result": status,
                        "result_at": result_at,
                        "total_hours": total_hours,
                        "label": product_label,
                    }
                )
                bucket["completed_count"] += 1
                if status == RESULT_UNQUALIFIED:
                    bucket["unqualified_count"] += 1
                else:
                    bucket["qualified_count"] += 1
                if total_hours is not None:
                    bucket["hours"].append(total_hours)
                if stage1_hours is not None:
                    stage1_hours_list.append(stage1_hours)
                if stage2_hours is not None:
                    stage2_hours_list.append(stage2_hours)
            else:
                waited_hours = _hours_between(inbound, now)
                pending.append(
                    {
                        "name": product_label,
                        "batch": inspection_status_text(cells.get(LABEL_BATCH_FIELD)),
                        "product": product_label,
                        "inbound_date": inbound.date().isoformat(),
                        "waited_hours": waited_hours,
                    }
                )
                bucket["pending_count"] += 1
                if stage1_hours is not None:
                    stage1_hours_list.append(stage1_hours)

    breakdown = []
    for label in sorted(breakdown_map):
        bucket = breakdown_map[label]
        breakdown.append(
            {
                "label": bucket["label"],
                "completed_count": bucket["completed_count"],
                "qualified_count": bucket["qualified_count"],
                "unqualified_count": bucket["unqualified_count"],
                "avg_hours": _avg(bucket["hours"]),
                "pending_count": bucket["pending_count"],
            }
        )

    pending.sort(key=lambda item: item["waited_hours"] or 0, reverse=True)
    return {
        "current": _pending_summary(pending),
        "window": _window_summary(completed, days, now),
        "breakdown": breakdown,
        "daily": _daily_series(days, completed, now),
        "oldest_pending": pending[:5],
        "stages": {
            "inbound_to_pending_avg_hours": _avg(stage1_hours_list),
            "pending_to_result_avg_hours": _avg(stage2_hours_list),
        },
    }
