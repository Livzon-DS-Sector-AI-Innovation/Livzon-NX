"""MC 霉酚酸 - 批次血链表 API"""

import logging

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])

def fmt_val(v):
    return float(v) if v is not None else 0.0


class LineageNode(BaseModel):
    stage: str
    label: str
    batch_no: str
    detail: str = ""
    yield_rate: float | None = None
    quantity: float | None = None
    is_sibling: bool = False
    connects_to: str = ""


class StageGroup(BaseModel):
    stage: str
    label: str
    nodes: list[LineageNode]


class YieldDistItem(BaseModel):
    stage: str
    label: str
    count: int
    min: float
    q1: float
    median: float
    mean: float
    q3: float
    max: float
    below_80: int
    above_110: int


class MaterialReuseItem(BaseModel):
    upstream_type: str
    upstream_batch: str
    usage_count: int
    used_by: str


class CoverageItem(BaseModel):
    segment: str
    count: int


STAGE_LABELS = {
    "fermentation": "发酵液",
    "refining": "提炼放罐",
    "na_batch": "钠化批号",
    "sub_tank": "钠化批号",
    "crude_product": "粗品批号",
    "extraction": "萃取批号",
    "wet_powder": "一次精品批号",
    "refinement": "精制MC-F2",
    "single_batch_blend": "单批批号(混粉)",
    "single_batch_qc": "单批批号(入库)",
    "blending": "混粉成品",
    "front_batch": "前台批号",
    "qc": "入库",
}

STAGE_ORDER = [
    "fermentation",
    "refining",
    "sub_tank",
    "extraction",
    "refinement",
    "blending",
    "qc",
]


import re  # noqa: E402

# 非标批号标准化：去掉 (Fis)/(FIS)/（FIS）等客户定制标签
_FIS_RE = re.compile(r"[(（]\s*FIS\s*[)）]", re.IGNORECASE)


def _normalize_batch(bn: str) -> str:
    """返回 (标准化批号, 原始批号)"""
    return _FIS_RE.sub("", bn).strip()


async def _resolve_batch(stage, batch_no, session):
    norm = _normalize_batch(batch_no)
    if stage in ("na_batch", "crude_product"):
        row = (
            await session.execute(
                text(
                    "SELECT batch_no FROM production.sub_tank_records WHERE batch_no = :bn OR batch_no = 'MC-' || :bn LIMIT 1"  # noqa: E501
                ),
                {"bn": norm},
            )
        ).fetchone()
        if row:
            return ("sub_tank", row.batch_no)
        return (None, None)
    if stage == "wet_powder":
        n = _normalize_batch(batch_no)
        row = (
            await session.execute(
                text(
                    "SELECT batch_no FROM production.extraction_records WHERE batch_no LIKE '%' || :bn LIMIT 1"  # noqa: E501
                ),
                {"bn": norm},
            )
        ).fetchone()
        if row:
            return ("extraction", row.batch_no)
        return (None, None)
    if stage == "single_batch_blend":
        n = _normalize_batch(batch_no)
        if n.startswith("MC-F2") or n.startswith("MC-F2-"):
            return ("refinement", n)
        return ("blending", n)
    if stage == "single_batch_qc":
        n = _normalize_batch(batch_no)
        if n.startswith("MC-F2") or n.startswith("MC-F2-"):
            return ("refinement", n)
        return ("blending", n)
    if stage == "front_batch":
        row = (
            await session.execute(
                text(
                    "SELECT batch_no FROM production.qc_inspections WHERE front_batch_no = :bn LIMIT 1"  # noqa: E501
                ),
                {"bn": norm},
            )
        ).fetchone()
        if row:
            return ("qc", row.batch_no)
        return (None, None)
    # 直接工段（含 refinement），标准化后再查
    return (stage, norm if norm != batch_no else batch_no)


_SIBLING_SQL = """
    SELECT bl.upstream_type, bl.upstream_batch, bl.quantity,
           COALESCE(st.yield_rate, er.yield_rate, rr.single_step_yield) AS yield_rate
    FROM production.batch_lineage bl
    LEFT JOIN production.sub_tank_records st ON st.batch_no = bl.upstream_batch AND
        bl.upstream_type = 'sub_tank'
    LEFT JOIN production.extraction_records er ON er.batch_no = bl.upstream_batch AND
        bl.upstream_type = 'extraction'
    LEFT JOIN production.mc_refinement_records rr ON rr.batch_no = bl.upstream_batch
        AND bl.upstream_type = 'refinement'
    WHERE bl.downstream_batch = :batch AND bl.downstream_type = :stage
"""

_DOWNSTREAM_SQL = """
    SELECT bl.downstream_type, bl.downstream_batch, bl.quantity,
           COALESCE(st.yield_rate, er.yield_rate, rr.single_step_yield) AS yield_rate
    FROM production.batch_lineage bl
    LEFT JOIN production.sub_tank_records st ON st.batch_no = bl.downstream_batch AND
        bl.downstream_type = 'sub_tank'
    LEFT JOIN production.extraction_records er ON er.batch_no = bl.downstream_batch AND
        bl.downstream_type = 'extraction'
    LEFT JOIN production.mc_refinement_records rr ON rr.batch_no = bl.downstream_batch
        AND bl.downstream_type = 'refinement'
    WHERE bl.upstream_batch = :batch AND bl.upstream_type = :stage
"""


def _fmt_detail(item):
    p = []
    yr = item.get("y") or item.get("yield_rate")
    if yr and float(yr) > 0:
        p.append(f"yr{float(yr):.1f}%")
    qty = item.get("q") or item.get("quantity")
    if qty and float(qty) > 0:
        p.append(f"{float(qty):.0f}kg")
    return ", ".join(p)


@router.get("/mc/lineage/trace", summary="批次全链路追溯")
async def lineage_trace(
    batch_no: str = Query(...),
    stage: str = Query(...),
    include_siblings: bool = Query(False),
    session: AsyncSession = Depends(get_db),
):
    if stage not in STAGE_LABELS:
        raise HTTPException(400, f"Invalid: {stage}")
    real_stage, real_batch_no = await _resolve_batch(stage, batch_no, session)
    if real_stage is None:
        raise HTTPException(404, f"Not found: {batch_no}")

    async def rd(stg, bn):
        p = []
        yr = qty = None
        if stg in ("sub_tank", "extraction", "refinement"):
            dr = (
                await session.execute(
                    text(
                        {
                            "sub_tank": "SELECT yield_rate FROM production.sub_tank_records WHERE batch_no = :bn",  # noqa: E501
                            "extraction": "SELECT yield_rate FROM production.extraction_records WHERE batch_no = :bn",  # noqa: E501
                            "refinement": "SELECT single_step_yield AS yield_rate FROM production.mc_refinement_records WHERE batch_no = :bn",  # noqa: E501
                        }[stg]
                    ),
                    {"bn": bn},
                )
            ).fetchone()
            if dr and dr.yield_rate:
                yr = float(dr.yield_rate)
                p.append(f"yr{yr:.1f}%")
        qr = (
            await session.execute(
                text(
                    "SELECT quantity FROM production.batch_lineage WHERE downstream_batch = :bn AND downstream_type = :st LIMIT 1"  # noqa: E501
                ),
                {"bn": bn, "st": stg},
            )
        ).fetchone()
        if qr and qr.quantity:
            qty = float(qr.quantity)
            p.append(f"{qty:.0f}kg")
        return (", ".join(p), yr, qty)

    td, ty, tq = await rd(real_stage, real_batch_no)

    # --- upstream BFS ---
    upstream_layers = []
    cur = [(real_batch_no, real_stage)]
    seen = {(real_batch_no, real_stage)}
    while cur:
        nxt = []
        layer = []
        for cb, cs in cur:
            rows = (
                await session.execute(text(_SIBLING_SQL), {"batch": cb, "stage": cs})
            ).fetchall()
            for r in rows:
                k = (r.upstream_batch, r.upstream_type)
                if k not in seen:
                    seen.add(k)
                    layer.append(
                        {
                            "stage": r.upstream_type,
                            "batch_no": r.upstream_batch,
                            "y": float(r.yield_rate) if r.yield_rate else None,
                            "q": float(r.quantity) if r.quantity else None,
                        }
                    )
                    nxt.append(k)
        if layer:
            upstream_layers.append(layer)
        cur = nxt

    # --- downstream BFS ---
    downstream_layers = []
    cur = [(real_batch_no, real_stage)]
    seen_dn = {(real_batch_no, real_stage)}
    while cur:
        nxt = []
        layer = []
        for cb, cs in cur:
            rows = (
                await session.execute(text(_DOWNSTREAM_SQL), {"batch": cb, "stage": cs})
            ).fetchall()
            for r in rows:
                k = (r.downstream_batch, r.downstream_type)
                if k not in seen_dn:
                    seen_dn.add(k)
                    layer.append(
                        {
                            "stage": r.downstream_type,
                            "batch_no": r.downstream_batch,
                            "y": float(r.yield_rate) if r.yield_rate else None,
                            "q": float(r.quantity) if r.quantity else None,
                        }
                    )
                    nxt.append(k)
        if layer:
            downstream_layers.append(layer)
        cur = nxt

    # --- siblings ---
    sibling_nodes = []
    if include_siblings:
        mc = {(real_batch_no, real_stage)}
        for layer in upstream_layers:
            for it in layer:
                mc.add((it["batch_no"], it["stage"]))
        for layer in downstream_layers:
            for it in layer:
                mc.add((it["batch_no"], it["stage"]))
        ss = set()
        for layer in downstream_layers:
            for it in layer:
                rows = (
                    await session.execute(
                        text(_SIBLING_SQL),
                        {"batch": it["batch_no"], "stage": it["stage"]},
                    )
                ).fetchall()
                for r in rows:
                    k = (r.upstream_batch, r.upstream_type)
                    if k not in mc and k not in ss:
                        ss.add(k)
                        qq = float(r.quantity) if r.quantity else 0
                        sibling_nodes.append(
                            {
                                "stage": r.upstream_type,
                                "batch_no": r.upstream_batch,
                                "y": float(r.yield_rate) if r.yield_rate else None,
                                "q": float(r.quantity) if r.quantity else None,
                                "ct": f"{it['batch_no']} {qq:.0f}kg",
                            }
                        )
                        cur2 = [(r.upstream_batch, r.upstream_type)]
                        sd = {(r.upstream_batch, r.upstream_type)}
                        while cur2:
                            nx2 = []
                            for c2b, c2s in cur2:
                                rows2 = (
                                    await session.execute(
                                        text(_DOWNSTREAM_SQL),
                                        {"batch": c2b, "stage": c2s},
                                    )
                                ).fetchall()
                                for r2 in rows2:
                                    k2 = (r2.downstream_batch, r2.downstream_type)
                                    if k2 not in sd and k2 not in mc and k2 not in ss:
                                        ss.add(k2)
                                        sd.add(k2)
                                        sibling_nodes.append(
                                            {
                                                "stage": r2.downstream_type,
                                                "batch_no": r2.downstream_batch,
                                                "y": float(r2.yield_rate)
                                                if r2.yield_rate
                                                else None,
                                                "q": float(r2.quantity)
                                                if r2.quantity
                                                else None,
                                            }
                                        )
                                        nx2.append(k2)
                            cur2 = nx2

    # --- downstream connection map ---
    conn_map = {}
    all_keys = {(real_batch_no, real_stage)}
    for layer in upstream_layers:
        for it in layer:
            all_keys.add((it["batch_no"], it["stage"]))
    for layer in downstream_layers:
        for it in layer:
            all_keys.add((it["batch_no"], it["stage"]))
    for bk, bs in all_keys:
        rows = (
            await session.execute(
                text(
                    "SELECT downstream_batch, quantity FROM production.batch_lineage WHERE upstream_batch = :b AND upstream_type = :s"  # noqa: E501
                ),
                {"b": bk, "s": bs},
            )
        ).fetchall()
        conn_map[(bk, bs)] = [
            f"{r.downstream_batch} {float(r.quantity or 0):.0f}kg"
            for r in rows
            if r.downstream_batch
        ]

    # --- QC front batch ---
    qc_fm = {}
    qc_bs = []
    for layer in downstream_layers:
        for it in layer:
            if it["stage"] == "qc":
                qc_bs.append(it["batch_no"])
    if real_stage == "qc":
        qc_bs.append(real_batch_no)
    if qc_bs:
        qr = (
            await session.execute(
                text(
                    "SELECT batch_no, front_batch_no FROM production.qc_inspections WHERE batch_no = ANY(:bs)"  # noqa: E501
                ),
                {"bs": qc_bs},
            )
        ).fetchall()
        for r in qr:
            if r.front_batch_no:
                qc_fm[r.batch_no] = r.front_batch_no
    if real_stage == "qc" and real_batch_no in qc_fm:
        fb = qc_fm[real_batch_no]
        td = (td + ", " if td else "") + f"前台:{fb}"

    def mk_node(stg, bn, detail, y, q, sib=False, ct=""):
        d = detail
        if stg == "qc" and bn in qc_fm and "前台" not in (d or ""):
            d = (d + ", " if d else "") + f"前台:{qc_fm[bn]}"
        ct_final = ct or ", ".join(conn_map.get((bn, stg), []))
        return LineageNode(
            stage=stg,
            label=STAGE_LABELS.get(stg, stg),
            batch_no=bn,
            detail=d,
            yield_rate=y,
            quantity=q,
            is_sibling=sib,
            connects_to=ct_final,
        )

    # --- aggregate ---
    stage_nodes = {s: [] for s in STAGE_LABELS}
    for layer in reversed(upstream_layers):
        for it in layer:
            stage_nodes[it["stage"]].append(
                mk_node(it["stage"], it["batch_no"], _fmt_detail(it), it["y"], it["q"])
            )
    stage_nodes[real_stage].append(mk_node(real_stage, real_batch_no, td, ty, tq))
    for layer in downstream_layers:
        for it in layer:
            stage_nodes[it["stage"]].append(
                mk_node(it["stage"], it["batch_no"], _fmt_detail(it), it["y"], it["q"])
            )
    for it in sibling_nodes:
        stage_nodes[it["stage"]].append(
            mk_node(
                it["stage"],
                it["batch_no"],
                _fmt_detail(it),
                it["y"],
                it["q"],
                sib=True,
                ct=it.get("ct", ""),
            )
        )

    stages_out = []
    for s in STAGE_ORDER:
        ns = stage_nodes.get(s, [])
        if not ns:
            continue
        seen_s = set()
        uniq = []
        for n in ns:
            if n.batch_no not in seen_s:
                seen_s.add(n.batch_no)
                uniq.append(n)
        stages_out.append(StageGroup(stage=s, label=STAGE_LABELS.get(s, s), nodes=uniq))

    cum = 100.0
    mls = None
    mlv = 0.0
    for sg in stages_out:
        for n in sg.nodes:
            if n.yield_rate and n.yield_rate > 0:
                loss = cum * (1 - n.yield_rate / 100)
                if loss > mlv:
                    mlv = loss
                    mls = sg.stage
                cum *= n.yield_rate / 100
                break

    return success_response(
        data={
            "stages": [sg.model_dump(exclude_none=False) for sg in stages_out],
            "target_batch": batch_no,
            "target_stage": real_stage,
            "cumulative_yield": round(cum, 1),
            "max_loss_stage": mls,
        }
    )


@router.get("/mc/lineage/yield-distribution", summary="收率分布")
async def lineage_yield_distribution(session: AsyncSession = Depends(get_db)):
    rows = await session.execute(
        text("""
        SELECT stage, COUNT(*) AS n,
               ROUND(MIN(y)::numeric, 1) AS min_y,
               ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY y)::numeric, 1) AS q1,
               ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY y)::numeric, 1) AS
        median,
               ROUND(AVG(y)::numeric, 1) AS mean,
               ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY y)::numeric, 1) AS q3,
               ROUND(MAX(y)::numeric, 1) AS max_y,
               COUNT(*) FILTER (WHERE y < 80) AS below_80,
               COUNT(*) FILTER (WHERE y > 110) AS above_110
        FROM (
            SELECT 'sub_tank' AS stage, st.yield_rate AS y
            FROM production.batch_lineage bl
            JOIN production.sub_tank_records st ON st.batch_no = bl.upstream_batch
            WHERE bl.upstream_type = 'sub_tank' AND st.yield_rate IS NOT NULL
            UNION ALL
            SELECT 'extraction', er.yield_rate
            FROM production.batch_lineage bl
            JOIN production.extraction_records er ON er.batch_no = bl.upstream_batch
            WHERE bl.upstream_type = 'extraction' AND er.yield_rate IS NOT NULL
            UNION ALL
            SELECT 'refinement', rr.single_step_yield
            FROM production.batch_lineage bl
            JOIN production.mc_refinement_records rr ON rr.batch_no = bl.upstream_batch
            WHERE bl.upstream_type = 'refinement' AND rr.single_step_yield IS NOT NULL
        ) t GROUP BY stage ORDER BY mean
    """)
    )
    items = [
        YieldDistItem(
            stage=row.stage,
            label=STAGE_LABELS.get(row.stage, row.stage),
            count=row.n,
            min=float(row.min_y or 0),
            q1=float(row.q1 or 0),
            median=float(row.median or 0),
            mean=float(row.mean or 0),
            q3=float(row.q3 or 0),
            max=float(row.max_y or 0),
            below_80=row.below_80,
            above_110=row.above_110,
        )
        for row in rows
    ]
    return success_response(data=[i.model_dump() for i in items])


@router.get("/mc/lineage/material-reuse", summary="物料复用")
async def lineage_material_reuse(session: AsyncSession = Depends(get_db)):
    rows = await session.execute(
        text("""
        SELECT upstream_type, upstream_batch, COUNT(*) AS usage_count,
               STRING_AGG(downstream_batch, ', ') AS used_by
        FROM production.batch_lineage WHERE downstream_type = 'blending'
        GROUP BY upstream_type, upstream_batch HAVING COUNT(*) > 1 ORDER BY usage_count
        DESC
    """)
    )
    items = [
        MaterialReuseItem(
            upstream_type=row.upstream_type,
            upstream_batch=row.upstream_batch,
            usage_count=row.usage_count,
            used_by=row.used_by,
        )
        for row in rows
    ]
    return success_response(data=[i.model_dump() for i in items])


@router.get("/mc/lineage/coverage", summary="覆盖完整性")
async def lineage_coverage(session: AsyncSession = Depends(get_db)):
    seg_rows = await session.execute(
        text("""
        SELECT upstream_type || ' -> ' || downstream_type AS seg, COUNT(*) AS n
        FROM production.batch_lineage GROUP BY upstream_type, downstream_type ORDER BY
        seg
    """)
    )
    segments = [CoverageItem(segment=row.seg, count=row.n) for row in seg_rows]
    total_ei = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM production.extraction_inputs WHERE is_deleted = false"  # noqa: E501
            )
        )
    ).scalar() or 0
    missing = (
        await session.execute(
            text("""
        SELECT COUNT(*) FROM production.extraction_inputs ei
        WHERE ei.is_deleted = false AND NOT EXISTS (
            SELECT 1 FROM production.batch_lineage bl
            WHERE bl.upstream_batch IN (ei.crude_batch_no, 'MC-' || ei.crude_batch_no)
              AND bl.downstream_type = 'extraction')
    """)
        )
    ).scalar() or 0
    pct = round((total_ei - missing) / total_ei * 100, 1) if total_ei > 0 else 0
    return success_response(
        data={
            "segments": [s.model_dump() for s in segments],
            "extraction_coverage_pct": pct,
            "extraction_total": total_ei,
            "extraction_missing": missing,
        }
    )
