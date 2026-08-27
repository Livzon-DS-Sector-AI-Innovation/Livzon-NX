"""FA 苯丙氨酸 - 批次血链表 API"""
import logging
from typing import Any

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
    note: str = ""


FA_STAGE_LABELS = {
    "fermentation": "发酵放罐",
    "acidification": "酸化过滤",
    "decolor1": "一次脱色",
    "decolor_centrifuge": "脱色离心",
}

FA_STAGE_NOTES = {
    "fermentation": "C/D 两个接收罐分装发酵液",
    "acidification": "调酸→陶瓷膜过滤，3轮膜滤套洗",
    "decolor1": "多罐脱色工艺参数相同（电导/碳量一致），只记首罐",
    "decolor_centrifuge": "脱色液分8份各自离心，母液内部回用",
}

FA_STAGE_ORDER = ["fermentation", "acidification", "decolor1", "decolor_centrifuge"]

_SIBLING_SQL = """
    SELECT bl.upstream_type, bl.upstream_batch, bl.quantity
    FROM production.fa_batch_lineage bl
    WHERE bl.downstream_batch = :batch AND bl.downstream_type = :stage
"""

_DOWNSTREAM_SQL = """
    SELECT bl.downstream_type, bl.downstream_batch, bl.quantity
    FROM production.fa_batch_lineage bl
    WHERE bl.upstream_batch = :batch AND bl.upstream_type = :stage
"""


async def _node_info(session: Any, stg: Any, bn: Any) -> Any:
    """查询节点的详细信息：detail文本, yield_rate, quantity"""
    p = []
    yr = None
    qty = None

    # 从血链表取 quantity
    qr = (
        await session.execute(
            text(
                "SELECT quantity FROM production.fa_batch_lineage WHERE downstream_batch = :bn AND downstream_type = :st LIMIT 1"  # noqa: E501
            ),
            {"bn": bn, "st": stg},
        )
    ).fetchone()
    if qr and qr.quantity:
        qty = float(qr.quantity)
        p.append(f"{qty:.0f}kg")

    if stg == "fermentation":
        fr = (
            await session.execute(
                text(
                    'SELECT "汇总总量_kg", "放罐体积_kl" FROM production.fa_fermentation_batches WHERE "发酵罐号" = :bn'  # noqa: E501
                ),
                {"bn": bn},
            )
        ).fetchone()
        if fr:
            if fr.放罐体积_kl:
                p.append(f"{float(fr.放罐体积_kl):.0f}kl")
            if fr.汇总总量_kg and not any("kg" in x for x in p):
                p.append(f"{float(fr.汇总总量_kg):.0f}kg")
    elif stg == "acidification":
        ar = (
            await session.execute(
                text(
                    'SELECT MAX("膜滤液产品量（kg）") as max_qty FROM production.fa_acidification_records WHERE "批号" = :bn'  # noqa: E501
                ),
                {"bn": bn},
            )
        ).fetchone()
        if ar and ar.max_qty:
            p.append(f"膜滤{float(ar.max_qty):.0f}kg")
    elif stg == "decolor1":
        dr = (
            await session.execute(
                text(
                    'SELECT "体积(kl)", "碳后含量(g/L)" FROM production.fa_decolor1_records WHERE "批号" = :bn'  # noqa: E501
                ),
                {"bn": bn},
            )
        ).fetchone()
        if dr:
            parts = []
            # 列名含括号，用索引访问
            if dr[0]:
                parts.append(f"{float(dr[0]):.0f}kl")
            if dr[1]:
                parts.append(f"碳后{float(dr[1]):.1f}g/L")
            if parts:
                p = parts + p  # 前面放的优先
    elif stg == "decolor_centrifuge":
        cr = (
            await session.execute(
                text(
                    'SELECT "进料体积（kl）", "收率" FROM production.fa_decolor_centrifuge_records WHERE "批号" = :bn'  # noqa: E501
                ),
                {"bn": bn},
            )
        ).fetchone()
        if cr:
            parts = []
            if cr[0]:
                parts.append(f"{float(cr[0]):.0f}kl")
            if cr[1]:
                yr = float(cr[1]) * 100
                parts.append(f"收率{yr:.1f}%")
            if parts:
                p = parts + p

    return (", ".join(p), yr, qty)


@router.get("/fa/lineage/trace", summary="FA 批次全链路追溯")
async def fa_lineage_trace(
    batch_no: str = Query(...),
    stage: str = Query(...),
    session: AsyncSession = Depends(get_db),
) -> Any:
    if stage not in FA_STAGE_LABELS:
        raise HTTPException(
            400, f"无效工段: {stage}，可选: {list(FA_STAGE_LABELS.keys())}"
        )

    real_stage = stage
    real_batch_no = batch_no

    # --- 目标节点详细信息 ---
    td, ty, tq = await _node_info(session, real_stage, real_batch_no)

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
                    d, y, q = await _node_info(
                        session, r.upstream_type, r.upstream_batch
                    )
                    layer.append(
                        {
                            "stage": r.upstream_type,
                            "batch_no": r.upstream_batch,
                            "d": d,
                            "y": y,
                            "q": q,
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
                    d, y, q = await _node_info(
                        session, r.downstream_type, r.downstream_batch
                    )
                    layer.append(
                        {
                            "stage": r.downstream_type,
                            "batch_no": r.downstream_batch,
                            "d": d,
                            "y": y,
                            "q": q,
                        }
                    )
                    nxt.append(k)
        if layer:
            downstream_layers.append(layer)
        cur = nxt

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
                    "SELECT downstream_batch, quantity FROM production.fa_batch_lineage WHERE upstream_batch = :b AND upstream_type = :s"  # noqa: E501
                ),
                {"b": bk, "s": bs},
            )
        ).fetchall()
        conn_map[(bk, bs)] = [
            f"{r.downstream_batch} {float(r.quantity or 0):.0f}kg"
            for r in rows
            if r.downstream_batch
        ]

    def mk_node(stg: Any, bn: Any, detail: Any, y: Any, q: Any) -> Any:
        ct_final = ", ".join(conn_map.get((bn, stg), []))
        return LineageNode(
            stage=stg,
            label=FA_STAGE_LABELS.get(stg, stg),
            batch_no=bn,
            detail=detail,
            yield_rate=y,
            quantity=q,
            is_sibling=False,
            connects_to=ct_final,
        )

    # --- aggregate ---
    stage_nodes: dict[str, list[LineageNode]] = {
        s: [] for s in FA_STAGE_LABELS
    }
    for layer in reversed(upstream_layers):
        for it in layer:
            stage_nodes[it["stage"]].append(
                mk_node(it["stage"], it["batch_no"], it["d"], it["y"], it["q"])
            )
    stage_nodes[real_stage].append(mk_node(real_stage, real_batch_no, td, ty, tq))
    for layer in downstream_layers:
        for it in layer:
            stage_nodes[it["stage"]].append(
                mk_node(it["stage"], it["batch_no"], it["d"], it["y"], it["q"])
            )

    stages_out = []
    for s in FA_STAGE_ORDER:
        ns = stage_nodes.get(s, [])
        if not ns:
            continue
        seen_s = set()
        uniq = []
        for n in ns:
            if n.batch_no not in seen_s:
                seen_s.add(n.batch_no)
                uniq.append(n)
        stages_out.append(
            StageGroup(
                stage=s,
                label=FA_STAGE_LABELS.get(s, s),
                nodes=uniq,
                note=FA_STAGE_NOTES.get(s, ""),
            )
        )

    return success_response(
        data={
            "stages": [sg.model_dump(exclude_none=False) for sg in stages_out],
            "target_batch": batch_no,
            "target_stage": real_stage,
            "cumulative_yield": 100,
            "max_loss_stage": None,
        }
    )
