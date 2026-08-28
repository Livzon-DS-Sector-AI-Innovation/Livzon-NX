"""批次进度总览 API — 查询13个工艺步骤的数据完成情况"""
from datetime import date
from typing import Any

from fastapi import Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])

STEP_TABLES = [
    ("receive", "broth_receives", "received_batch"),
    ("pretreat", "pretreatments", "received_batch"),
    ("ceramic", "ceramic_feeds", "batch_no"),
    ("decolor1", "decolor1", "batch_no"),
    ("filter1", "filter1", "batch_no"),
    ("conc1", "conc1", "batch_no"),
    ("centrifuge1", "centrifuge1", "batch_no"),
    ("recrystallize", "recrystallize", "batch_no"),
    ("filter2", "filter2", "batch_no"),
    ("conc2", "conc2", "batch_no"),
    ("centrifuge2", "centrifuge2", "batch_no"),
    ("dry", "dry", "batch_no"),
    ("pack", "pack", "batch_no"),
]

STEP_LABELS = [
    ("receive", "发酵液接收", "接收"),
    ("pretreat", "预处理", "预处理"),
    ("ceramic", "陶瓷膜过滤", "膜过滤"),
    ("decolor1", "一次脱色", "脱色"),
    ("filter1", "一次板框过滤", "板框1"),
    ("conc1", "一次浓缩", "浓缩1"),
    ("centrifuge1", "一次离心", "离心1"),
    ("recrystallize", "二次重结晶脱色", "重结晶"),
    ("filter2", "二次板框过滤", "板框2"),
    ("conc2", "二次浓缩", "浓缩2"),
    ("centrifuge2", "二次离心", "离心2"),
    ("dry", "烘干", "烘干"),
    ("pack", "包装", "包装"),
]


@router.get("/batch-progress", summary="批次进度总览")
async def batch_progress(
    s: str | None = Query(None, alias="batch_no"),
    workshop: str = Query("203"),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """一次查询13张表，返回批次进度矩阵 + 概览统计 + 卡点分析"""
    # ── 1. 批次进度矩阵 ──
    unions = " UNION ALL ".join(
        f"SELECT \"{col}\" AS batch_no, '{key}' AS step FROM production.{table} WHERE is_deleted = false AND workshop = :ws"  # noqa: E501
        for key, table, col in STEP_TABLES
    )
    sql = f"SELECT batch_no, step FROM ({unions}) AS t"
    if s:
        sql += f" WHERE batch_no ILIKE '%{s}%'"
    sql += " ORDER BY batch_no DESC, step"

    result = await session.execute(text(sql), {"ws": workshop})
    rows = result.fetchall()

    batch_map: dict[str, set[str]] = {}
    for batch_no, step_key in rows:
        batch_map.setdefault(batch_no, set()).add(step_key)

    step_keys = [key for key, _, _ in STEP_LABELS]

    batches: list[dict[str, Any]] = [
        {
            "batch_no": bn,
            "steps": {sk: (sk in steps) for sk in step_keys},
            "completed": len(steps),
            "total": len(step_keys),
        }
        for bn, steps in batch_map.items()
    ]

    # ── 2. 概览统计 ──
    total_batches = len(batches)
    completed_count = sum(1 for b in batches if b["steps"].get("pack"))
    in_progress = total_batches - completed_count

    # ── 3. 本月包装产量 ──
    today = date.today()
    month_start = today.replace(day=1)
    pack_result = await session.execute(
        text(
            "SELECT COUNT(*) FILTER (WHERE created_at::date = :today) AS today_count,"
            " COALESCE(SUM(NULLIF(total_net_weight, '')::numeric), 0) AS monthly_output"
            " FROM production.pack"
            " WHERE is_deleted = false AND workshop = :ws AND created_at::date >= :month_start"  # noqa: E501
        ),
        {"today": today, "month_start": month_start, "ws": workshop},
    )
    pack_row = pack_result.fetchone()
    today_pack_count = int(pack_row[0]) if pack_row else 0
    monthly_output = round(float(pack_row[1]), 1) if pack_row and pack_row[1] else 0

    # ── 4. 卡点分析：上游有数据、当前步骤无数据 ──
    bottlenecks: list[dict[str, Any]] = []
    for i in range(1, len(step_keys)):
        prev_key = step_keys[i - 1]
        curr_key = step_keys[i]
        stuck_batches = [
            b["batch_no"]
            for b in batches
            if b["steps"].get(prev_key) and not b["steps"].get(curr_key)
        ]
        if stuck_batches:
            _, prev_label, _ = STEP_LABELS[i - 1]
            _, curr_label_long, curr_short = STEP_LABELS[i]
            bottlenecks.append(
                {
                    "prev_step": prev_key,
                    "prev_label": prev_label,
                    "step_key": curr_key,
                    "step_label": curr_label_long,
                    "step_short": curr_short,
                    "stuck_count": len(stuck_batches),
                    "stuck_batches": stuck_batches[:10],  # 最多展示10条
                    "has_more": len(stuck_batches) > 10,
                }
            )

    # ── 5. 最近完工 ──
    recent_completed: list[dict[str, Any]] = [
        {"batch_no": b["batch_no"], "completed": b["completed"], "total": b["total"]}
        for b in batches
        if b["steps"].get("pack")
    ]
    recent_completed.sort(key=lambda x: str(x["batch_no"]), reverse=True)
    recent_completed = recent_completed[:10]

    return success_response(
        {
            "batches": batches,
            "step_keys": step_keys,
            "step_labels": [
                {"key": k, "label": lb, "short": s} for k, lb, s in STEP_LABELS
            ],
            "summary": {
                "total_batches": total_batches,
                "in_progress": in_progress,
                "completed": completed_count,
                "today_pack_count": today_pack_count,
                "monthly_output_kg": monthly_output,
                "bottlenecks": bottlenecks,
                "recent_completed": recent_completed,
            },
        }
    )
