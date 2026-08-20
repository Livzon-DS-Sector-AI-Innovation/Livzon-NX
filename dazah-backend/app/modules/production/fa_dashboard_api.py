"""FA 苯丙氨酸 - 收率全链路看板 API"""

import logging
from datetime import date, datetime

from fastapi import Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import error_response, success_response
from app.modules.production.ai_analysis_models import AiAnalysis
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])


# ═══════════════════════════════════════════════════════════
# FA 仪表盘汇总
# ═══════════════════════════════════════════════════════════


@router.get("/fa/dashboard/summary", summary="FA 仪表盘汇总数据")
async def get_fa_dashboard(
    month: str = Query(
        default=None,
        description="筛选月份 (YYYY-MM)，默认当前月",
        pattern=r"^\d{4}-\d{2}$",
    ),
    session: AsyncSession = Depends(get_db),
):
    if month is None:
        now = datetime.now()
        month = f"{now.year}-{now.month:02d}"

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

    result: dict = {"_month": month}

    # ── 辅助：按月计数 ──
    async def _count_month(
        table: str, date_col: str, extra_where: str = "", params: dict | None = None
    ) -> int:
        where = f""""{date_col}" >= :start AND "{date_col}" < :end"""
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

    async def _count_ferm(extra_where: str = "", params: dict | None = None) -> int:
        where = """"放罐日期" >= :start AND "放罐日期" < :end"""
        if extra_where:
            where += f" AND {extra_where}"
        p = {"start": start_date, "end": end_date, **(params or {})}
        try:
            r = await session.execute(
                text(
                    f"SELECT COUNT(1) FROM production.fa_fermentation_batches WHERE {where}"  # noqa: E501
                ),
                p,
            )
            return r.scalar() or 0
        except Exception:
            logger.exception("_count_ferm failed")
            await session.rollback()
            return 0

    # ── 1. 各工段批次数 ──
    result["stages"] = {
        "fermentation": await _count_ferm(),
        "acidification": await _count_month("fa_acidification_records", "日期"),
        "decolor1": await _count_month("fa_decolor1_records", "日期"),
        "mvr": await _count_month("fa_mvr_records", "日期"),
        "mother_liquor": await _count_month("fa_mother_liquor_records", "日期"),
        "plate_recovery": await _count_month("fa_plate_recovery_records", "日期"),
        "decolor_centrifuge": await _count_month(
            "fa_decolor_centrifuge_records", "日期"
        ),
        "intermediate": 0,
    }

    # ── 2. 本月产量 ──
    try:
        r = await session.execute(
            text("""SELECT COALESCE(SUM("汇总总量_kg"), 0) FROM
        production.fa_fermentation_batches
                   WHERE "放罐日期" >= :start AND "放罐日期" < :end"""),
            {"start": start_date, "end": end_date},
        )
        result["monthly_output_kg"] = round(float(r.scalar() or 0), 1)
    except Exception:
        logger.exception("monthly_output_kg failed")
        result["monthly_output_kg"] = 0

    # ── 3. 本月批次数 ──
    result["monthly_batches"] = result["stages"]["fermentation"]

    # ── 4. 平均收率 ──
    try:
        r = await session.execute(
            text("""SELECT COALESCE(AVG(
                   CASE WHEN "批收率" ~ '^[0-9.]+$' THEN "批收率"::float
                        ELSE NULL END), 0) FROM production.fa_acidification_records
                   WHERE "日期" >= :start AND "日期" < :end"""),
            {"start": start_date, "end": end_date},
        )
        result["avg_yield"] = round(float(r.scalar() or 0), 1)
    except Exception:
        logger.exception("avg_yield failed")
        result["avg_yield"] = 0

    # ── 5. 收率达标率 ──
    try:
        r = await session.execute(
            text("""SELECT
                   COUNT(CASE WHEN "批收率" ~ '^[0-9.]+$' AND "批收率"::float >= 80
        THEN 1
        END) AS passed,
                   COUNT(CASE WHEN "批收率" ~ '^[0-9.]+$' THEN 1 END) AS total
                   FROM production.fa_acidification_records
                   WHERE "日期" >= :start AND "日期" < :end"""),
            {"start": start_date, "end": end_date},
        )
        row = r.one()
        total = row.total or 0
        passed = row.passed or 0
        result["pass_rate"] = round(passed / total * 100, 1) if total > 0 else 0
    except Exception:
        logger.exception("pass_rate failed")
        result["pass_rate"] = 0

    # ── 6. 流程监控 ──
    flow_stages = [
        ("fermentation", "发酵放罐", "fa_fermentation_batches", "放罐日期"),
        ("acidification", "酸化过滤", "fa_acidification_records", "日期"),
        ("decolor1", "一次脱色", "fa_decolor1_records", "日期"),
        ("mvr", "MVR浓缩", "fa_mvr_records", "日期"),
        ("decolor_centrifuge", "脱色离心", "fa_decolor_centrifuge_records", "日期"),
    ]
    flow = []
    for key, label, table, date_col in flow_stages:
        try:
            r = await session.execute(
                text(
                    f'SELECT COUNT(1) FROM production.{table} WHERE "{date_col}" >= :start AND "{date_col}" < :end'  # noqa: E501
                ),
                {"start": start_date, "end": end_date},
            )
            flow.append({"key": key, "label": label, "in_progress": r.scalar() or 0})
        except Exception:
            logger.exception(f"flow[{key}] failed")
            flow.append({"key": key, "label": label, "in_progress": 0})
    result["flow"] = flow

    # ── 7. 近12个月产量趋势 ──
    monthly_trend = [{"month": m, "output_kg": 0} for m in range(1, 13)]
    try:
        r = await session.execute(
            text("""SELECT EXTRACT(MONTH FROM "放罐日期")::int AS m,
                   COALESCE(SUM("汇总总量_kg"), 0) AS kg
                   FROM production.fa_fermentation_batches
                   WHERE EXTRACT(YEAR FROM "放罐日期") = :yr
                   GROUP BY m ORDER BY m"""),
            {"yr": year},
        )
        for row in r:
            m = row.m
            if 1 <= m <= 12:
                monthly_trend[m - 1] = {
                    "month": m,
                    "output_kg": round(float(row.kg or 0), 1),
                }
    except Exception:
        logger.exception("monthly_trend failed")
    result["monthly_trend"] = monthly_trend

    # ── 8. RRT 杂质合格率（FA 无 RRT 数据）──
    result["rrt_pass_rates"] = []

    # ── 9. 批次状态分布 ──
    result["status_distribution"] = [
        {
            "status": "发酵完成",
            "count": result["stages"]["fermentation"],
            "color": "#1677ff",
        },
        {
            "status": "酸化完成",
            "count": result["stages"]["acidification"],
            "color": "#52c41a",
        },
        {
            "status": "脱色完成",
            "count": result["stages"]["decolor1"],
            "color": "#fa8c16",
        },
    ]

    # ── 10. 溶剂库存（FA 不使用丁酯）──
    result["ba_stock_kg"] = 0
    result["ba_batches"] = 0
    result["ba_monthly_consume"] = 0

    return success_response(result)


def _to_yield(val) -> float:
    """安全转收率百分比值（兼容字符串带%、小数0-2等格式）"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        v = float(val)
        return v * 100 if v < 2 else v
    s = str(val).replace("%", "").replace(",", "").strip()
    try:
        v = float(s)
        return v * 100 if v < 2 else v
    except ValueError:
        return 0.0


def _to_float(val) -> float:
    """安全转浮点数，兼容字符串带%等格式"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


FA_STAGE_LABELS = {
    "fermentation": "发酵放罐",
    "acidification": "酸化过滤",
    "decolor1": "一次脱色",
    "decolor_centrifuge": "脱色离心",
}


@router.get("/fa/dashboard/yield-chain", summary="FA 收率全链路看板")
async def fa_yield_chain(
    month: str = Query(None, description="月份，格式 YYYY-MM"),
    session: AsyncSession = Depends(get_db),
):
    """返回 FA 收率全链路数据：各阶段收率 + 批次明细 + 汇总"""
    month_filter = ""
    params: dict = {}
    if month:
        month_filter = """
            AND fb."放罐日期"::text >= :month_start
            AND fb."放罐日期"::text < :month_end
        """
        params["month_start"] = f"{month}-01"
        # 计算下月第一天
        y, m = month.split("-")
        ym = int(y) * 12 + int(m)
        next_ym = ym + 1
        params["month_end"] = f"{next_ym // 12}-{next_ym % 12:02d}-01"

    # ── 1. 发酵批次的汇总数据 ──
    ferment_sql = text(f"""
        SELECT fb."发酵罐号" as batch_no, fb."放罐日期"::text as date,
               fb."汇总总量_kg" as total_kg, fb."电导_uscm" as conductivity,
               fb."收率" as yield_rate
        FROM production.fa_fermentation_batches fb
        WHERE fb."汇总总量_kg" IS NOT NULL
        {month_filter}
        ORDER BY fb."放罐日期" DESC
    """)
    ferment_rows = (await session.execute(ferment_sql, params)).fetchall()

    if not ferment_rows:
        return success_response(data={"batches": [], "stages": [], "summary": {}})

    # ── 2. 逐个批次查下游 ──
    batches = []
    stage_yields_all = {
        "fermentation": [],
        "acidification": [],
        "decolor1": [],
        "decolor_centrifuge": [],
    }

    for fr in ferment_rows:
        fb = fr.batch_no
        item = {
            "fermentation_batch": fb,
            "fermentation_date": fr.date,
            "fermentation_output": round(_to_float(fr.total_kg), 0)
            if fr.total_kg
            else 0,
            "fermentation_yield": round(_to_yield(fr.yield_rate), 1)
            if fr.yield_rate
            else None,
            "acid_batch": None,
            "acid_output": None,
            "acid_yield": None,
            "decolor1_batch": None,
            "centrifuge_batches": [],
            "centrifuge_avg_yield": None,
            "cumulative_yield": None,
        }
        fy = item["fermentation_yield"]
        if fy and fy > 0:
            stage_yields_all["fermentation"].append(fy)

        # 酸化
        acid_rows = (
            await session.execute(
                text(
                    """SELECT "批号", "膜滤液产品量（kg）" as mf_qty, "批收率" as
        yield_rate
               FROM production.fa_acidification_records
               WHERE "批号" = :bn AND "膜滤液产品量（kg）" IS NOT NULL LIMIT 1"""
                ),
                {"bn": fb},
            )
        ).fetchone()
        if acid_rows:
            item["acid_batch"] = acid_rows[0]
            item["acid_output"] = (
                round(_to_float(acid_rows[1]), 0) if acid_rows[1] else 0
            )
            yr = _to_yield(acid_rows[2])
            item["acid_yield"] = round(yr, 1)
            if yr > 0:
                stage_yields_all["acidification"].append(yr)

        # 脱色离心
        core = fb.replace("FA-EX", "")
        cent_rows = (
            await session.execute(
                text(
                    """SELECT "批号", "进料体积（kl）" as vol, "收率" as yield_rate
               FROM production.fa_decolor_centrifuge_records
               WHERE "批号" LIKE '%' || :core || '%' ORDER BY "批号" LIMIT 20"""
                ),
                {"core": core},
            )
        ).fetchall()
        total_yr = 0
        yr_count = 0
        for cr in cent_rows:
            yr = round(_to_yield(cr[2]), 1)
            if yr > 0:
                total_yr += yr
                yr_count += 1
                stage_yields_all["decolor_centrifuge"].append(yr)
            item["centrifuge_batches"].append(
                {
                    "batch": cr[0],
                    "vol": round(_to_float(cr[1]), 0) if cr[1] else None,
                    "yield": yr,
                }
            )
        if yr_count > 0:
            item["centrifuge_avg_yield"] = round(total_yr / yr_count, 1)

        # 脱色一次
        if cent_rows:
            cent_rows[0][0]  # FA-25316-1
            decolor_rows = (
                await session.execute(
                    text(
                        """SELECT "批号", "体积(kl)" as vol, "碳后含量(g/L)" as after_c
                   FROM production.fa_decolor1_records
                   WHERE "批号" LIKE '%' || :core || '%' LIMIT 1"""
                    ),
                    {"core": core},
                )
            ).fetchone()
            if decolor_rows:
                item["decolor1_batch"] = decolor_rows[0]

        # 累计收率 = 离心平均收率（因为离心是末段最直接的收率指标）
        if item["acid_yield"] and item["centrifuge_avg_yield"]:
            item["cumulative_yield"] = round(
                item["acid_yield"] * item["centrifuge_avg_yield"] / 100, 1
            )

        batches.append(item)

    # ── 3. 汇总统计 ──
    def _avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else 0

    stage_summary = []
    for sk, label in [
        ("fermentation", "发酵放罐"),
        ("acidification", "酸化过滤"),
        ("decolor1", "一次脱色"),
        ("decolor_centrifuge", "脱色离心"),
    ]:
        vals = stage_yields_all.get(sk, [])
        if vals:
            sorted_vals = sorted(vals)
            n = len(sorted_vals)
            stage_summary.append(
                {
                    "stage": sk,
                    "label": label,
                    "count": n,
                    "avg_yield": _avg(vals),
                    "min_yield": round(min(vals), 1),
                    "max_yield": round(max(vals), 1),
                    "q1": round(sorted_vals[n // 4], 1) if n >= 4 else sorted_vals[0],
                    "median": round(sorted_vals[n // 2], 1)
                    if n >= 2
                    else sorted_vals[0],
                    "q3": round(sorted_vals[n * 3 // 4], 1)
                    if n >= 4
                    else sorted_vals[-1],
                }
            )

    cumulatives = [b["cumulative_yield"] for b in batches if b["cumulative_yield"]]
    overall_cum = _avg(cumulatives)

    # 找出最大损失阶段
    losses = [
        ("酸化过滤", 100 - _avg(stage_yields_all.get("acidification", [100]))),
        ("脱色离心", 100 - _avg(stage_yields_all.get("decolor_centrifuge", [100]))),
    ]
    max_loss = max(losses, key=lambda x: x[1]) if losses else ("", 0)

    summary = {
        "total_batches": len(batches),
        "avg_cumulative_yield": overall_cum,
        "max_loss_stage": max_loss[0],
        "max_loss_percent": round(max_loss[1], 1),
    }

    return success_response(
        data={
            "batches": batches,
            "stages": stage_summary,
            "summary": summary,
        }
    )


@router.get("/fa/dashboard/golden-batches", summary="FA 黄金批次推荐")
async def fa_golden_batches(
    limit: int = Query(5, ge=1, le=20),
    score: str = Query("stability", description="评分模式: stability/quality/filtered"),
    session: AsyncSession = Depends(get_db),
):
    """按评分标准找出最近3个月最优批次，提取关键工艺参数范围
    - stability: 离心离散度越低越优（操作稳定性）
    - quality: 累计收率 × 碳后含量（产量+质量双维度）
    - filtered: 排除酸化收率>110%后按累计收率排
    """
    from datetime import date, timedelta

    three_months_ago = (date.today() - timedelta(days=92)).isoformat()
    # 复用 yield-chain 取近3个月数据
    ferment_sql = text("""
        SELECT fb."发酵罐号" as batch_no, fb."汇总总量_kg" as total_kg,
               fb."电导_uscm" as conductivity, fb."调酸量_L" as acid_adj,
               fb."酸化液滤速_ml10min" as filter_speed
        FROM production.fa_fermentation_batches fb
        WHERE fb."汇总总量_kg" IS NOT NULL
          AND fb."放罐日期"::text >= :min_date
        ORDER BY fb."放罐日期" DESC
    """)
    ferment_rows = (
        await session.execute(ferment_sql, {"min_date": three_months_ago})
    ).fetchall()

    golden = []
    for fr in ferment_rows:
        fb = fr.batch_no
        entry = {"batch_no": fb, "total_output": round(_to_float(fr.total_kg), 0)}

        # 酸化
        ar = (
            await session.execute(
                text(
                    """SELECT "用酸量（95-98%浓硫酸）" as acid, "PH（酸化后）" as ph,
               "渣损失率（渣苯丙量/罐产）" as slag, "膜滤液产品量（kg）" as mf_qty,
               "批收率" as yield_rate
               FROM production.fa_acidification_records WHERE "批号" = :bn LIMIT 1"""
                ),
                {"bn": fb},
            )
        ).fetchone()
        if not ar:
            continue
        acid_yr = _to_yield(ar[4])
        if acid_yr <= 0:
            continue
        entry["acid_yield"] = round(acid_yr, 1)
        entry["acid_used"] = round(_to_float(ar[0]), 0) if ar[0] else None
        entry["ph"] = round(_to_float(ar[1]), 2) if ar[1] else None
        entry["slag_loss"] = round(_to_float(ar[2]), 2) if ar[2] else None
        entry["mf_output"] = round(_to_float(ar[3]), 0) if ar[3] else None

        # 脱色一次
        core = fb.replace("FA-EX", "")
        dr = (
            await session.execute(
                text(
                    """SELECT "活性炭添加量(kg)" as carbon, "碳后含量(g/L)" as after_c
               FROM production.fa_decolor1_records
               WHERE "批号" LIKE '%' || :core || '%' LIMIT 1"""
                ),
                {"core": core},
            )
        ).fetchone()
        if dr:
            entry["carbon"] = round(_to_float(dr[0]), 0) if dr[0] else None
            entry["carbon_after"] = round(_to_float(dr[1]), 2) if dr[1] else None

        # 离心
        crs = (
            await session.execute(
                text(
                    """SELECT "收率" FROM production.fa_decolor_centrifuge_records
               WHERE "批号" LIKE '%' || :core || '%'"""
                ),
                {"core": core},
            )
        ).fetchall()
        cent_yields = [round(_to_yield(r[0]), 1) for r in crs if _to_yield(r[0]) > 0]
        if len(cent_yields) < 3:
            continue  # 至少 3 份离心数据
        entry["centrifuge_avg"] = round(sum(cent_yields) / len(cent_yields), 1)
        entry["centrifuge_std"] = round(
            (
                sum((y - entry["centrifuge_avg"]) ** 2 for y in cent_yields)
                / len(cent_yields)
            )
            ** 0.5,
            2,
        )
        entry["total_yield"] = round(acid_yr * entry["centrifuge_avg"] / 100, 1)

        # 发酵参数
        entry["conductivity"] = (
            round(_to_float(fr.conductivity), 0) if fr.conductivity else None
        )
        entry["acid_adj"] = round(_to_float(fr.acid_adj), 1) if fr.acid_adj else None
        entry["filter_speed"] = (
            round(_to_float(fr.filter_speed), 0) if fr.filter_speed else None
        )

        golden.append(entry)

    # 按总收率排序取 top N
    # 按评分标准排序
    if score == "stability":
        golden.sort(key=lambda x: x.get("centrifuge_std", 999))
    elif score == "quality":
        for b in golden:
            b["_quality_score"] = b["total_yield"] * (b.get("carbon_after") or 40) / 100
        golden.sort(key=lambda x: x["_quality_score"], reverse=True)
    else:  # filtered
        golden = [b for b in golden if b.get("acid_yield", 0) <= 110]
        golden.sort(key=lambda x: x["total_yield"], reverse=True)
    top = golden[:limit]

    # 计算黄金参数范围
    def _param_range(key, top_list):
        vals = [b[key] for b in top_list if b.get(key) is not None]
        if not vals:
            return None
        return {
            "avg": round(sum(vals) / len(vals), 2),
            "min": min(vals),
            "max": max(vals),
        }

    fields = [
        "conductivity",
        "acid_adj",
        "filter_speed",
        "acid_used",
        "ph",
        "slag_loss",
        "carbon",
        "carbon_after",
        "centrifuge_avg",
        "centrifuge_std",
    ]
    reference = {}
    for f in fields:
        label = {
            "conductivity": "电导(us/cm)",
            "acid_adj": "调酸量(L)",
            "filter_speed": "滤速(ml/10min)",
            "acid_used": "用酸量(kg)",
            "ph": "pH(酸化后)",
            "slag_loss": "渣损失率(%)",
            "carbon": "活性炭(kg)",
            "carbon_after": "碳后含量(g/L)",
            "centrifuge_avg": "离心均值(%)",
            "centrifuge_std": "离心离散度",
        }[f]
        r = _param_range(f, top)
        if r:
            reference[f] = {**r, "label": label}

    return success_response(data={"batches": top, "reference": reference})


# ═══════════════════════════════════════════════════════════
# 批次对比诊断 — 逐阶段参数对比 + 纠正建议
# ═══════════════════════════════════════════════════════════

_SUGGESTION_RULES = {
    "conductivity": {
        "high": {
            "happened": "发酵电导偏高，盐/杂质多，会加剧后续膜污染和MVR结垢风险。",
            "remedy": "酸化时可适当增加调酸量和冲洗水用量，加大膜滤通量，减轻膜表面污染。",  # noqa: E501
            "impact": "调控得当可减少膜滤时间约5~10%，降低后续蒸发结垢概率。",
            "prevent": "关注菌种培养阶段的盐分控制，优化放罐时机，避免发酵后期电导急剧升高。",  # noqa: E501
        },
        "low": {
            "happened": "电导偏低，盐分少、提炼负担轻，但需确认是菌种代谢充分还是营养不足导致发酵不完整。",  # noqa: E501
            "remedy": "正常操作即可，可适当减少调酸量和冲洗水用量，降低辅料成本。",
            "impact": "提炼难度小，膜滤通量高，预期收率优于常规批次。",
            "prevent": "记录低电导批次的放罐参数（体积、含量、菌体浓度），建立优质批次档案作为参照。",  # noqa: E501
        },
    },
    "acid_adj": {
        "low": {
            "happened": "调酸量偏低，可能导致酸化不充分，影响后续膜滤效果。",
            "remedy": "补充酸量至标准范围，确认酸化后pH达标。膜滤时加大顶洗量弥补。",
            "impact": "充分酸化可提升膜滤收率1~2个百分点。",
            "prevent": "建立调酸量-膜滤效率对照表，按电导水平动态调整用酸量。",
        },
        "high": {
            "happened": "调酸量偏高，pH可能过低，过度酸化会增加硫酸消耗成本，并可能导致蛋白变性和产品降解。",  # noqa: E501
            "remedy": "检查酸化后pH值，若低于目标范围应减少下一批用酸量。当前批次加大膜滤顶洗量减少酸残留。",  # noqa: E501
            "impact": "调酸量回归标准后每批可节省硫酸约5~10%。",
            "prevent": "按发酵液体积和电导水平计算理论用酸量，建立分档对照表，避免凭经验过量加酸。",  # noqa: E501
        },
    },
    "slag_loss": {
        "high": {
            "happened": "渣损失率偏高，部分苯丙氨酸随渣饼流失，降低了酸化工段收率。",
            "remedy": "后端离心工段提高操作精度，减少甩料损失。每份离心独立计量，发现收率低立即调整。",  # noqa: E501
            "impact": "离心精度提升可追回约1~3%的渣损失。",
            "prevent": "完善膜滤CIP清洗程序，确保每次卸渣前充分顶洗；定期检查滤布完好性。",  # noqa: E501
        }
    },
    "filter_speed": {
        "low": {
            "happened": "酸化液滤速偏慢，发酵液粘度或菌体量偏高，膜污染风险增大。",
            "remedy": "加大膜滤顶洗频率和冲洗水量；必要时适当提高操作温度降低料液粘度。",  # noqa: E501
            "impact": "滤速恢复至正常水平，单批处理时间可缩短10~15%。",
            "prevent": "优化发酵放罐条件：控制放罐时菌体浓度和自溶程度，避免过发酵。",
        }
    },
    "carbon_after": {
        "low": {
            "happened": "碳后含量低于黄金水平，脱色过程中可能吸附了部分有效成分。",
            "remedy": "后续离心注意收率监控，对低浓度料液可适当降低甩料转速减少损失。",
            "impact": "精细操作可减少含量损失约0.5~1g/L。",
            "prevent": "检查活性炭品牌和批次质量，优化炭量配比；确保脱色温度和时间参数一致。",  # noqa: E501
        },
        "high": {
            "happened": "碳后含量异常偏高，可能是活性炭用量不足、脱色时间不够，或碳前含量测量有误（碳后不应高于碳前）。",  # noqa: E501
            "remedy": "确认碳前和碳后取样是否有误。若数据属实，本批增加活性炭用量或延长脱色时间，下批按此调整。",  # noqa: E501
            "impact": "碳后含量回归正常后离心收率更稳定，成品质量一致性提升。",
            "prevent": "每批记录活性炭用量、脱色温度和时长，定期校验碳前/碳后含量检测方法的一致性。",  # noqa: E501
        },
    },
    "centrifuge_std": {
        "high": {
            "happened": "8份离心收率差异过大（离散度高），分批和母液回用操作不一致，已造成不可逆损失。",  # noqa: E501
            "remedy": "混粉时将收率<95%的份与>100%的份搭配混合，利用高收率份拉高均值。",
            "impact": "高/低搭配混粉可提升最终收率约2~3个百分点。",
            "prevent": "规范离心分批作业：统一进料体积（目标95~100kl）、统一甩料时长、母液回用限定本批内。",  # noqa: E501
        }
    },
    "centrifuge_avg": {
        "low": {
            "happened": "离心平均收率低于黄金水平，整体提炼效率有优化空间。",
            "remedy": "检查各份离心的进料体积和甩料时长是否一致，优化炭后料液分配均匀性。",  # noqa: E501
            "impact": "操作标准化后离心均值可提升3~5个百分点。",
            "prevent": "建立离心操作SOP，每批记录各份进料体积/甩料时长/收率，定期分析趋势。",  # noqa: E501
        },
        "high": {
            "happened": "离心平均收率超过100%，说明母液回用混入了上层残液或上一批的残留，数值虚高不代表真实收率。",  # noqa: E501
            "remedy": "排查母液回用管道是否有串料，确认离心机清洗是否彻底。混粉时注意搭配低收率份拉回正常范围。",  # noqa: E501
            "impact": "规范母液回用流程后收率数据更真实，便于准确评估工艺水平。",
            "prevent": "母液回用严格限定本批内，建立回用比例上限（建议不超过进料体积的5%），每批记录回用量。",  # noqa: E501
        },
    },
    "ph": {
        "high": {
            "happened": "酸化后pH偏高，酸化不充分，会影响膜滤效率和蛋白去除效果。",
            "remedy": "本批补充酸量至pH达标后再进行膜滤。若已进入膜滤阶段，加大顶洗水量减少残留。",  # noqa: E501
            "impact": "pH调至标准范围后膜滤通量可提升10~15%，渣损失率降低。",
            "prevent": "建立pH-用酸量对照曲线，每批根据发酵液体积和电导预估用酸量，酸化后取样确认pH再放行。",  # noqa: E501
        },
        "low": {
            "happened": "酸化后pH偏低，用酸过量，可能造成蛋白过度变性、产品降解，且浪费硫酸。",  # noqa: E501
            "remedy": "当前批次减少下一轮用酸量。已酸化的料液在膜滤时加大顶洗量，减少酸残留对下游的影响。",  # noqa: E501
            "impact": "用酸量优化后每批节省硫酸成本，且产品色泽和纯度更稳定。",
            "prevent": "严格控制酸化终点pH，每批取样确认，建立不同电导水平对应的用酸量分档表。",  # noqa: E501
        },
    },
    "acid_amount": {
        "high": {
            "happened": "硫酸用量偏高，和调酸量偏高通常是同一原因，酸化过度会增加成本和下游处理难度。",  # noqa: E501
            "remedy": "核对当前批次pH值，若pH已达标则下批降低酸量；若pH仍高则检查酸浓度是否有误。",  # noqa: E501
            "impact": "酸量优化后每批节省硫酸约5~10%，同时减少膜滤冲洗水用量。",
            "prevent": "硫酸用量与发酵液体积、电导水平挂钩，建立标准化配比表，避免按经验过量投加。",  # noqa: E501
        },
        "low": {
            "happened": "硫酸用量偏低，酸化可能不充分，蛋白去除不完全，膜滤时容易堵膜。",  # noqa: E501
            "remedy": "确认酸化后pH是否达标，若不达标补充酸量。膜滤时加大顶洗频率弥补酸化不足。",  # noqa: E501
            "impact": "酸化充分后膜滤收率可提升1~2%，膜清洗周期延长。",
            "prevent": "建立最小用酸量标准，按发酵液体积和电导设定安全下限，酸化后必须取样确认pH。",  # noqa: E501
        },
    },
    "carbon": {
        "high": {
            "happened": "活性炭用量偏高，过度脱色可能吸附有效成分，造成含量损失，且增加固废处理成本。",  # noqa: E501
            "remedy": "当前批次已无法挽回，下批降低炭量至黄金参考范围。关注离心收率是否偏低。",  # noqa: E501
            "impact": "炭量回归标准后碳后含量提升，离心收率可提高1~2个百分点，废炭处理量减少。",  # noqa: E501
            "prevent": "活性炭用量与料液体积、色素水平挂钩，建立分档配比表。定期评估不同品牌活性炭的吸附选择性。",  # noqa: E501
        },
        "low": {
            "happened": "活性炭用量偏低，脱色不充分，可能导致成品色泽和透光率不达标。",
            "remedy": "本批若尚未完成脱色可补充活性炭延长脱色时间。若已完成，关注成品色泽检测结果。",  # noqa: E501
            "impact": "炭量达标后成品透光率和色泽稳定性提升，减少因外观不合格导致的返工。",  # noqa: E501
            "prevent": "设定活性炭用量下限，每批根据料液色泽目测判断，异常深色料液自动上浮炭量。",  # noqa: E501
        },
    },
}

_DEVIATION_THRESHOLD = 10  # 偏离超过该百分比才生成建议


def _get_suggestion(key: str, direction: str) -> dict | None:
    """根据参数key和偏离方向返回四段式建议"""
    rules = _SUGGESTION_RULES.get(key, {})
    rule = rules.get(direction)
    if not rule:
        return None
    return {
        "happened": rule["happened"],
        "remedy": rule["remedy"],
        "impact": rule["impact"],
        "prevent": rule["prevent"],
    }


@router.get("/fa/dashboard/batch-params", summary="FA 批次参数对比诊断")
async def fa_batch_params(
    batch_no: str = Query(...),
    score: str = Query("stability"),
    session: AsyncSession = Depends(get_db),
):
    """查询指定批次的10个关键参数，与黄金均值对比，给出逐阶段纠正建议"""
    from datetime import date, timedelta

    three_months_ago = (date.today() - timedelta(days=92)).isoformat()

    # ── 1. 查批次数据 ──
    fb = (
        await session.execute(
            text(
                """SELECT "发酵罐号" as batch_no, "汇总总量_kg" as total_kg,
           "电导_uscm" as conductivity, "调酸量_L" as acid_adj,
           "酸化液滤速_ml10min" as filter_speed, "收率" as yield_rate
           FROM production.fa_fermentation_batches
           WHERE "发酵罐号" = :bn AND "汇总总量_kg" IS NOT NULL LIMIT 1"""
            ),
            {"bn": batch_no},
        )
    ).fetchone()
    if not fb:
        return error_response(f"未找到批次数据: {batch_no}")

    params = {}
    params["fermentation_batch"] = fb.batch_no

    ar = (
        await session.execute(
            text(
                """SELECT "用酸量（95-98%浓硫酸）" as acid, "PH（酸化后）" as ph,
           "渣损失率（渣苯丙量/罐产）" as slag, "膜滤液产品量（kg）" as mf_qty,
           "批收率" as yield_rate
           FROM production.fa_acidification_records WHERE "批号" = :bn LIMIT 1"""
            ),
            {"bn": batch_no},
        )
    ).fetchone()

    core = batch_no.replace("FA-EX", "")
    dr = (
        await session.execute(
            text(
                """SELECT "活性炭添加量(kg)" as carbon, "碳后含量(g/L)" as after_c
           FROM production.fa_decolor1_records
           WHERE "批号" LIKE '%' || :core || '%' LIMIT 1"""
            ),
            {"core": core},
        )
    ).fetchone()

    crs = (
        await session.execute(
            text(
                """SELECT "收率" FROM production.fa_decolor_centrifuge_records
           WHERE "批号" LIKE '%' || :core || '%'"""
            ),
            {"core": core},
        )
    ).fetchall()

    # ── 2. 构建参数 ──
    def _get(key, default=None):
        return params.get(key, {}).get("value", default)

    params = {
        "conductivity": {
            "value": round(_to_float(fb.conductivity), 0) if fb.conductivity else None,
            "label": "电导(us/cm)",
            "stage": "发酵放罐",
        },
        "acid_adj": {
            "value": round(_to_float(fb.acid_adj), 1) if fb.acid_adj else None,
            "label": "调酸量(L)",
            "stage": "发酵放罐",
        },
        "filter_speed": {
            "value": round(_to_float(fb.filter_speed), 1) if fb.filter_speed else None,
            "label": "滤速(ml/10min)",
            "stage": "发酵放罐",
        },
        "acid_used": {
            "value": round(_to_float(ar[0]), 0) if ar and ar[0] else None,
            "label": "用酸量(kg)",
            "stage": "酸化过滤",
        },
        "ph": {
            "value": round(_to_float(ar[1]), 2) if ar and ar[1] else None,
            "label": "pH(酸化后)",
            "stage": "酸化过滤",
        },
        "slag_loss": {
            "value": round(_to_float(ar[2]), 2) if ar and ar[2] else None,
            "label": "渣损失率(%)",
            "stage": "酸化过滤",
        },
        "carbon": {
            "value": round(_to_float(dr[0]), 0) if dr and dr[0] else None,
            "label": "活性炭(kg)",
            "stage": "一次脱色",
        },
        "carbon_after": {
            "value": round(_to_float(dr[1]), 2) if dr and dr[1] else None,
            "label": "碳后含量(g/L)",
            "stage": "一次脱色",
        },
    }

    cent_yields = [round(_to_yield(r[0]), 1) for r in crs if _to_yield(r[0]) > 0]
    if cent_yields:
        avg_cy = sum(cent_yields) / len(cent_yields)
        std_cy = (sum((y - avg_cy) ** 2 for y in cent_yields) / len(cent_yields)) ** 0.5
        params["centrifuge_avg"] = {
            "value": round(avg_cy, 1),
            "label": "离心均值(%)",
            "stage": "脱色离心",
        }
        params["centrifuge_std"] = {
            "value": round(std_cy, 2),
            "label": "离心离散度",
            "stage": "脱色离心",
        }

    # ── 3. 获取黄金参考（内联计算，复用 golden-batches 逻辑）──
    ferment_all = (
        await session.execute(
            text(
                """SELECT fb."发酵罐号" as batch_no, fb."汇总总量_kg" as total_kg,
           fb."电导_uscm" as conductivity, fb."调酸量_L" as acid_adj,
           fb."酸化液滤速_ml10min" as filter_speed
           FROM production.fa_fermentation_batches fb
           WHERE fb."汇总总量_kg" IS NOT NULL AND fb."放罐日期"::text >= :min_date
           ORDER BY fb."放罐日期" DESC"""
            ),
            {"min_date": three_months_ago},
        )
    ).fetchall()

    golden_entries = []
    for fr in ferment_all:
        entry = {"batch_no": fr.batch_no}
        ar2 = (
            await session.execute(
                text(
                    """SELECT "用酸量（95-98%浓硫酸）" as acid, "PH（酸化后）" as ph,
               "渣损失率（渣苯丙量/罐产）" as slag, "批收率" as yield_rate
               FROM production.fa_acidification_records WHERE "批号" = :bn LIMIT 1"""
                ),
                {"bn": fr.batch_no},
            )
        ).fetchone()
        if not ar2:
            continue
        acid_yr = _to_yield(ar2[3])
        if acid_yr <= 0:
            continue
        entry["acid_yield"] = round(acid_yr, 1)
        entry["acid_used"] = round(_to_float(ar2[0]), 0) if ar2[0] else 0
        entry["ph"] = round(_to_float(ar2[1]), 2) if ar2[1] else 0
        entry["slag_loss"] = round(_to_float(ar2[2]), 2) if ar2[2] else 0
        entry["conductivity"] = (
            round(_to_float(fr.conductivity), 0) if fr.conductivity else 0
        )
        entry["acid_adj"] = round(_to_float(fr.acid_adj), 1) if fr.acid_adj else 0
        entry["filter_speed"] = (
            round(_to_float(fr.filter_speed), 1) if fr.filter_speed else 0
        )
        entry["total_output"] = round(_to_float(fr.total_kg), 0)
        core2 = fr.batch_no.replace("FA-EX", "")
        dr2 = (
            await session.execute(
                text(
                    """SELECT "活性炭添加量(kg)" as carbon, "碳后含量(g/L)" as after_c
               FROM production.fa_decolor1_records WHERE "批号" LIKE '%' || :core || '%'
        LIMIT 1"""
                ),
                {"core": core2},
            )
        ).fetchone()
        if dr2:
            entry["carbon"] = round(_to_float(dr2[0]), 0) if dr2[0] else 0
            entry["carbon_after"] = round(_to_float(dr2[1]), 2) if dr2[1] else 0
        crs2 = (
            await session.execute(
                text(
                    """SELECT "收率" FROM production.fa_decolor_centrifuge_records WHERE
        "批号" LIKE '%' || :core || '%'"""
                ),
                {"core": core2},
            )
        ).fetchall()
        cent_ys = [round(_to_yield(r[0]), 1) for r in crs2 if _to_yield(r[0]) > 0]
        if len(cent_ys) >= 3:
            c_avg = sum(cent_ys) / len(cent_ys)
            entry["centrifuge_avg"] = round(c_avg, 1)
            entry["centrifuge_std"] = round(
                (sum((y - c_avg) ** 2 for y in cent_ys) / len(cent_ys)) ** 0.5, 2
            )
            entry["total_yield"] = round(acid_yr * c_avg / 100, 1)
            golden_entries.append(entry)

    # 排序 + Top 5
    if score == "stability":
        golden_entries.sort(key=lambda x: x.get("centrifuge_std", 999))
    elif score == "quality":
        for b in golden_entries:
            b["_qs"] = b["total_yield"] * (b.get("carbon_after") or 40) / 100
        golden_entries.sort(key=lambda x: x["_qs"], reverse=True)
    else:
        golden_entries = [b for b in golden_entries if b.get("acid_yield", 0) <= 110]
        golden_entries.sort(key=lambda x: x["total_yield"], reverse=True)

    top5 = golden_entries[:5]
    golden_ref = {}
    fields = [
        "conductivity",
        "acid_adj",
        "filter_speed",
        "acid_used",
        "ph",
        "slag_loss",
        "carbon",
        "carbon_after",
        "centrifuge_avg",
        "centrifuge_std",
    ]
    for f in fields:
        vals = [b[f] for b in top5 if b.get(f) is not None and b.get(f) != 0]
        if vals:
            golden_ref[f] = {
                "avg": round(sum(vals) / len(vals), 2),
                "min": min(vals),
                "max": max(vals),
            }

    # ── 4. 计算偏离 + 生成建议 ──
    stages: dict[str, list[dict]] = {
        "发酵放罐": [],
        "酸化过滤": [],
        "一次脱色": [],
        "脱色离心": [],
    }
    deviations = {}

    key_order = [
        "conductivity",
        "acid_adj",
        "filter_speed",
        "acid_used",
        "ph",
        "slag_loss",
        "carbon",
        "carbon_after",
        "centrifuge_avg",
        "centrifuge_std",
    ]
    for key in key_order:
        p = params.get(key)
        if not p or p["value"] is None:
            continue
        gr = golden_ref.get(key, {})
        golden_avg = gr.get("avg")
        p["golden_avg"] = golden_avg
        p["golden_min"] = gr.get("min")
        p["golden_max"] = gr.get("max")

        # 偏离百分比
        if golden_avg and golden_avg > 0:
            dev = round((p["value"] - golden_avg) / golden_avg * 100, 1)
        else:
            dev = 0
        p["deviation"] = dev
        deviations[key] = dev

        # 偏离方向
        direction = (
            "high"
            if dev > _DEVIATION_THRESHOLD
            else "low"
            if dev < -_DEVIATION_THRESHOLD
            else "normal"
        )
        p["direction"] = direction
        p["severity"] = (
            "normal" if abs(dev) < 10 else "warn" if abs(dev) < 20 else "danger"
        )

        # 生成建议（仅偏离超过阈值）
        if abs(dev) >= _DEVIATION_THRESHOLD:
            p["suggestion"] = _get_suggestion(key, direction)

        stages[p["stage"]].append(p)

    # ── 5. 保存到 ai_analysis ──
    try:
        save_data = AiAnalysis(
            batch_no=batch_no,
            stage="batch_compare",
            include_siblings=False,
            trace_snapshot={
                "params": {
                    k: v["value"]
                    for k, v in params.items()
                    if v.get("value") is not None
                }
            },
            dist_snapshot={
                "golden_ref": {
                    k: v["golden_avg"]
                    for k, v in params.items()
                    if v.get("golden_avg") is not None
                }
            },
            anomalies=[
                {
                    "key": k,
                    "deviation": deviations[k],
                    "direction": params[k].get("direction"),
                }
                for k in deviations
                if abs(deviations[k]) >= _DEVIATION_THRESHOLD
            ],
            llm_response="",
            summary=f"批次 {batch_no} vs 黄金批次对比",
            causes=[],
            suggestions=[],
            severity="low",
            model_used="",
            reference_cases=[],
            created_by="批次对比",
            session_id="",
            message_seq=0,
            role="batch_compare",
        )
        session.add(save_data)
        await session.commit()
    except Exception as e:
        logger.warning(f"批次对比保存失败: {e}")

    return success_response(
        data={
            "batch_no": batch_no,
            "stages": {
                "发酵放罐": stages["发酵放罐"],
                "酸化过滤": stages["酸化过滤"],
                "一次脱色": stages["一次脱色"],
                "脱色离心": stages["脱色离心"],
            },
            "deviations": deviations,
        }
    )
