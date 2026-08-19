"""MC 霉酚酸 — 仪表盘聚合 API"""

import logging
from datetime import date, datetime
from fastapi import Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.response import success_response
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)

router = create_module_router(MODULES_BY_CODE["production"])

# 各工段表 → 实际生产日期字段映射（blending 走批号解析，不在此列）
STAGE_DATE_COLUMNS = {
    "crude":      ("refining_batches",       "produce_date"),
    "extraction": ("extraction_records",     "extract_date"),
    "refinement": ("mc_refinement_records",  "input_date"),
    "qc":         ("qc_inspections",         "input_date"),
    "ba":         ("butyl_acetate_records", "created_at"),
}


@router.get("/mc/dashboard/summary", summary="MC 仪表盘汇总数据")
async def get_mc_dashboard(
    month: str = Query(
        default=None,
        description="筛选月份 (YYYY-MM)，默认当前月",
        pattern=r"^\d{4}-\d{2}$",
    ),
    workshop: str = Query(
        default="201-2",
        description="车间编号",
    ),
    session: AsyncSession = Depends(get_db),
):

    if month is None:
        now = datetime.now()
        month = f"{now.year}-{now.month:02d}"

    # 计算月份范围
    try:
        parts = month.split("-")
        year, mon = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        now = datetime.now()
        year, mon = now.year, now.month
        month = f"{year}-{mon:02d}"
    start_date = date(year, mon, 1)
    if mon == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, mon + 1, 1)

    # 混粉批号解析：MC-260101 → year=26, month=01
    blend_yy = str(year)[2:]   # "26"
    blend_mm = f"{mon:02d}"    # "07"

    result: dict = {"_month": month}

    # ── 辅助：按日期字段过滤计数 ──
    async def _count_month(
        table: str, date_col: str, extra_where: str = "", params: dict | None = None
    ) -> int:
        where = (
            f"{date_col} >= :start AND {date_col} < :end AND is_deleted = false"
        )
        if extra_where:
            where += f" AND {extra_where}"
        p = {"start": start_date, "end": end_date, **(params or {})}
        try:
            r = await session.execute(
                text(f"SELECT COUNT(1) FROM production.{table} WHERE {where}"), p
            )
            return r.scalar() or 0
        except Exception:
            logger.exception(f"_count_month[{table}] failed")
            await session.rollback()
            return 0

    # ── 辅助：混合批号按月过滤（MC-260101 格式） ──
    async def _count_blending(extra_where: str = "", params: dict | None = None) -> int:
        """从 batch_no 第4-5位解析年份、第6-7位解析月份"""
        where = (
            "SUBSTRING(batch_no FROM 4 FOR 2) = :yy AND "
            "SUBSTRING(batch_no FROM 6 FOR 2) = :mm AND "
            "is_deleted = false"
        )
        if extra_where:
            where += f" AND {extra_where}"
        p = {"yy": blend_yy, "mm": blend_mm, **(params or {})}
        try:
            r = await session.execute(
                text(f"SELECT COUNT(1) FROM production.blending_records WHERE {where}"), p
            )
            return r.scalar() or 0
        except Exception:
            logger.exception("_count_blending failed")
            await session.rollback()
            return 0

    # ── 1. 各工段进行中批次数 ──
    result["stages"] = {}
    extra_conditions = {
        "crude":      "workshop = :ws",
        "extraction": "workshop = :ws AND status < 2",
        "refinement": "workshop = :ws AND status < 2",
        "qc":         "status < 2",    # 无 workshop 字段，仅 201-2 有效
        "ba":         "status = 1",     # 无 workshop 字段，仅 201-2 有效
    }
    for key, (table, date_col) in STAGE_DATE_COLUMNS.items():
        # QC 和丁酯表无 workshop 字段，非 201-2 车间直接返回 0
        if key in ("qc", "ba") and workshop != "201-2":
            result["stages"][key] = 0
            continue
        result["stages"][key] = await _count_month(
            table, date_col, extra_conditions.get(key, ""), {"ws": workshop}
        )
    # blending 走批号解析
    result["stages"]["blending"] = await _count_blending(
        "workshop = :ws AND status < 2", {"ws": workshop}
    )

    # ── 2. 本月产量：混粉表 total_weight 按月筛选 ──
    try:
        r = await session.execute(
            text("""SELECT COALESCE(SUM(total_weight), 0) FROM production.blending_records
                   WHERE workshop = :ws AND is_deleted = false
                   AND SUBSTRING(batch_no FROM 4 FOR 2) = :yy
                   AND SUBSTRING(batch_no FROM 6 FOR 2) = :mm"""),
            {"ws": workshop, "yy": blend_yy, "mm": blend_mm},
        )
        result["monthly_output_kg"] = round(float(r.scalar() or 0), 1)
    except Exception:
        logger.exception("monthly_output_kg failed")
        result["monthly_output_kg"] = 0

    # ── 3. 本月批次数：提炼表本月记录数 ──
    try:
        r = await session.execute(
            text("""SELECT COUNT(1) FROM production.refining_batches
                   WHERE workshop = :ws AND is_deleted = false
                   AND produce_date >= :start AND produce_date < :end"""),
            {"ws": workshop, "start": start_date, "end": end_date},
        )
        result["monthly_batches"] = r.scalar() or 0
    except Exception:
        logger.exception("monthly_batches failed")
        result["monthly_batches"] = 0

    # ── 4. 平均收率：提取工段本月 ──
    try:
        r = await session.execute(
            text("""SELECT COALESCE(AVG(yield_rate), 0) FROM production.extraction_records
                   WHERE workshop = :ws AND is_deleted = false AND yield_rate IS NOT NULL
                   AND extract_date >= :start AND extract_date < :end"""),
            {"ws": workshop, "start": start_date, "end": end_date},
        )
        result["avg_yield"] = round(float(r.scalar() or 0), 1)
    except Exception:
        logger.exception("avg_yield failed")
        result["avg_yield"] = 0

    # ── 5. 收率达标率：提取工段本月 yield_rate ≥ 80% 批数占比 ──
    try:
        r = await session.execute(
            text("""SELECT
                   COUNT(CASE WHEN yield_rate >= 80 THEN 1 END) AS passed,
                   COUNT(1) AS total
                   FROM production.extraction_records
                   WHERE workshop = :ws AND is_deleted = false
                   AND yield_rate IS NOT NULL
                   AND extract_date >= :start AND extract_date < :end"""),
            {"ws": workshop, "start": start_date, "end": end_date},
        )
        row = r.one()
        total = row.total or 0
        passed = row.passed or 0
        result["pass_rate"] = round(passed / total * 100, 1) if total > 0 else 0
    except Exception:
        logger.exception("yield_pass_rate failed")
        result["pass_rate"] = 0

    # ── 6. 流程监控 ──
    flow = []
    stage_defs_date = [
        ("crude", "粗提", "refining_batches", "produce_date",
         "workshop = :ws"),
        ("extraction", "提取", "extraction_records", "extract_date",
         "workshop = :ws AND status < 2"),
        ("refinement", "二次精制", "mc_refinement_records", "input_date",
         "workshop = :ws AND status < 2"),
        ("qc", "QC检验", "qc_inspections", "input_date",
         "status < 2"),
    ]
    for key, name, table, date_col, extra in stage_defs_date:
        try:
            r = await session.execute(
                text(
                    f"SELECT COUNT(1) FROM production.{table} "
                    f"WHERE {date_col} >= :start AND {date_col} < :end "
                    f"AND is_deleted = false AND {extra}"
                ),
                {"start": start_date, "end": end_date, "ws": workshop},
            )
            in_progress = r.scalar() or 0
        except Exception:
            logger.exception(f"flow[{key}] failed")
            in_progress = 0
        flow.append({"key": key, "label": name, "in_progress": in_progress})

    # blending 走批号解析
    try:
        r = await session.execute(
            text("""SELECT COUNT(1) FROM production.blending_records
                   WHERE SUBSTRING(batch_no FROM 4 FOR 2) = :yy
                   AND SUBSTRING(batch_no FROM 6 FOR 2) = :mm
                   AND is_deleted = false AND workshop = :ws AND status < 2"""),
            {"yy": blend_yy, "mm": blend_mm, "ws": workshop},
        )
        flow.append({"key": "blending", "label": "混粉计算", "in_progress": r.scalar() or 0})
    except Exception:
        logger.exception("flow[blending] failed")
        flow.append({"key": "blending", "label": "混粉计算", "in_progress": 0})
    result["flow"] = flow

    # ── 7. 近12个月产量趋势（按月混粉总重量） ──
    monthly_trend = [{"month": m, "output_kg": 0} for m in range(1, 13)]
    try:
        r = await session.execute(
            text("""SELECT SUBSTRING(batch_no FROM 6 FOR 2)::int AS m,
                   COALESCE(SUM(total_weight), 0) AS kg
                   FROM production.blending_records
                   WHERE workshop = :ws AND is_deleted = false
                   AND SUBSTRING(batch_no FROM 4 FOR 2) = :yy
                   GROUP BY m ORDER BY m"""),
            {"ws": workshop, "yy": blend_yy},
        )
        for row in r:
            m = row.m
            if 1 <= m <= 12:
                monthly_trend[m - 1] = {"month": m, "output_kg": round(float(row.kg or 0), 1)}
    except Exception:
        logger.exception("monthly_trend failed")
    result["monthly_trend"] = monthly_trend

    # ── 7.5. RRT 杂质合格率（本月混粉批次，按标准限值统计） ──
    rrt_limits = {
        "RRT 0.53":      ("rrt_053",       0.05),
        "RRT 0.755":     ("rrt_0755",      0.07),
        "RRT 0.94-0.96": ("rrt_094_096",   0.14),
        "RRT 1.03-1.06": ("rrt_103_106",   0.075),
        "RRT 2.01":      ("rrt_201",       0.08),
    }
    rrt_pass_rates = []
    try:
        for label, (col, limit) in rrt_limits.items():
            r = await session.execute(
                text(f"""SELECT COUNT(1) AS total,
                   COUNT(CASE WHEN {col} IS NOT NULL AND {col} <= :limit THEN 1 END) AS passed
                   FROM production.blending_records
                   WHERE workshop = :ws AND is_deleted = false
                   AND SUBSTRING(batch_no FROM 4 FOR 2) = :yy
                   AND SUBSTRING(batch_no FROM 6 FOR 2) = :mm"""),
                {"ws": workshop, "yy": blend_yy, "mm": blend_mm, "limit": limit},
            )
            row = r.one()
            total = row.total or 0
            passed = row.passed or 0
            rate = round(passed / total * 100, 1) if total > 0 else 0
            rrt_pass_rates.append({
                "label": label, "field": col, "limit": limit,
                "total": total, "passed": passed, "rate": rate,
            })
    except Exception:
        logger.exception("rrt_pass_rates failed")
    result["rrt_pass_rates"] = rrt_pass_rates

    # ── 8. 溶剂库存（丁酯）— 仅 201-2 车间有效 ──
    result["ba_stock_kg"] = 0
    result["ba_batches"] = 0
    result["ba_monthly_consume"] = 0
    if workshop == "201-2":
        try:
            # 最新盘点库存(吨→kg)
            r = await session.execute(
                text("""SELECT consumption FROM production.butyl_acetate_records
                       WHERE is_deleted = false AND is_check = true
                       ORDER BY check_date DESC LIMIT 1"""),
            )
            row = r.scalar()
            result["ba_stock_kg"] = round(float(row * 1000) if row else 0, 1)
            result["ba_batches"] = (await session.execute(
                text("SELECT COUNT(*) FROM production.butyl_acetate_records WHERE is_deleted = false AND is_check = true")
            )).scalar() or 0

            # 当月消耗合计
            r2 = await session.execute(
                text("""SELECT COALESCE(SUM(consumption), 0) FROM production.butyl_acetate_records
                       WHERE is_deleted = false AND is_check = false AND is_inbound = false
                       AND check_date >= :start AND check_date < :end"""),
                {"start": start_date, "end": end_date},
            )
            result["ba_monthly_consume"] = round(float(r2.scalar() or 0), 1)
        except Exception:
            logger.exception("ba_stock failed")
            result["ba_stock_kg"] = 0
            result["ba_batches"] = 0
            result["ba_monthly_consume"] = 0

    # ── 9. 批次状态分布（按实际数据完整性判定，非互斥） ──
    status_dist = [
        {"status": "待补数据", "count": 0, "color": "#faad14"},
        {"status": "计算完成", "count": 0, "color": "#1677ff"},
        {"status": "已完工",   "count": 0, "color": "#52c41a"},
    ]
    try:
        r = await session.execute(
            text("""SELECT
                   COUNT(1) FILTER (
                     WHERE NOT EXISTS (SELECT 1 FROM production.blending_inputs WHERE blend_batch = b.batch_no)
                   ) AS pending,
                   COUNT(1) FILTER (
                     WHERE EXISTS (SELECT 1 FROM production.blending_inputs WHERE blend_batch = b.batch_no)
                   ) AS calculated,
                   COUNT(1) FILTER (
                     WHERE EXISTS (
                       SELECT 1 FROM production.qc_inspections q
                       WHERE q.batch_no = b.batch_no
                       AND EXISTS (SELECT 1 FROM production.qc_inspection_inputs i WHERE i.qc_batch = q.batch_no)
                     )
                   ) AS completed
                   FROM production.blending_records b
                   WHERE b.workshop = :ws AND b.is_deleted = false
                   AND SUBSTRING(b.batch_no FROM 4 FOR 2) = :yy
                   AND SUBSTRING(b.batch_no FROM 6 FOR 2) = :mm"""),
            {"ws": workshop, "yy": blend_yy, "mm": blend_mm},
        )
        row = r.one()
        status_dist[0]["count"] = row.pending or 0
        status_dist[1]["count"] = row.calculated or 0
        status_dist[2]["count"] = row.completed or 0
    except Exception:
        logger.exception("status_distribution failed")
    result["status_distribution"] = status_dist

    return success_response(result)
