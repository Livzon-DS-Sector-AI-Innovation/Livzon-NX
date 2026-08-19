"""DR 多拉菌素 — 批次追溯 API（基于各工段表隐式关联，无 batch_lineage 血链表）

关联规则（每行一个投料批；层析表 extraction_batch_no 一行一个萃取批）：
  发酵批 dr_fermentation_batches.batch_no        (DR-26026)
    → 萃取批 dr_extractions.extraction_batch_no  (DR-26026-1)
    → 层析批 dr_chromatography_crystal.chromatography_batch_no（独立编号；extraction_batch_no 关联萃取批；产出 wet_powder_batch_no=DR-F1-xxx）
    → 一次精制 dr_first_refinement.refinement_batch_no (DR-F1-xxx 沿用湿粉批号)
    → 二次精制 dr_second_refinement.refinement_batch_no (DR-F2-xxx; feed_batch_no=DR-F1-xxx)
    → 三次精制 dr_third_refinement.refinement_batch_no  (DR-F3-xxx; feed_batch_no=DR-F2-xxx)
    → 四次精制 dr_fourth_refinement.refinement_batch_no (DR-GB-xxx; feed_batch_no=DR-F3-xxx)

断链典型（追溯自动标注 broken_links）：
  DR-F2-241013  三次投料、二次表无记录          → "二次精制表无记录"
  四次母液回收粉/DR-H1/DR-HF4 纯文本/回收粉标签  → "回收粉/母液标签，无独立台账"
  DR-24002-4    层析投料、萃取表无记录          → "萃取表无记录"
"""

import logging
import re
from typing import Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

logger = logging.getLogger(__name__)
router = create_module_router(MODULES_BY_CODE["production"])


# ── 模型 ──────────────────────────────────────────────

class FeedItem(BaseModel):
    """该批的一行投料明细（兄弟批全列）；qty 为折纯 kg，无量（层析/一次精制投料）为 0"""
    batch_no: str
    stage: str = ""
    label: str = ""
    qty: float = 0.0


class LineageNode(BaseModel):
    stage: str
    label: str
    batch_no: str
    detail: str = ""
    yield_rate: Optional[float] = None
    quantity: Optional[float] = None
    is_sibling: bool = False
    sib_group: str = ""                                    # 同源组标识（同组节点用虚线串联；如发酵批号）
    connects_to: str = ""
    broken: bool = False
    broken_reason: str = ""
    feeds: list[FeedItem] = Field(default_factory=list)  # 投入明细（混批全部兄弟批）
    input_total: float = 0.0                             # 投入合计（折纯 kg）
    loss_kg: Optional[float] = None                      # 本段损耗（投入−产出折纯 kg；仅精制/干燥段）
    loss_rate: Optional[float] = None                    # 本段损耗率 %（loss/投入×100）
    loss_level: str = ""                                 # 损耗等级 green<5 / yellow<10 / red≥10
    loss_breakdown: Optional[dict] = None                # 损耗去向拆解：母液带走/回收粉/其他
    #   {"mother_liquor_kg": float|None,  母液带走（可回收，产品随母液离开）
    #    "recovery_powder_kg": float|None, 回收粉（可回用）
    #    "other_kg": float|None}           其他损失 = 总损耗 − 母液 − 回收粉


class StageGroup(BaseModel):
    stage: str
    label: str
    nodes: list[LineageNode]


class BrokenLink(BaseModel):
    stage: str
    label: str
    batch_no: str
    reason: str


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


# ── 工段常量 ──────────────────────────────────────────

DR_STAGE_ORDER = [
    "fermentation", "extraction", "chromatography",
    "first_refinement", "second_refinement", "third_refinement", "fourth_refinement",
]

DR_STAGE_LABELS = {
    "fermentation": "发酵批",
    "extraction": "萃取批",
    "chromatography": "层析及一次结晶",
    "first_refinement": "一次精制",
    "second_refinement": "二次精制",
    "third_refinement": "三次精制",
    "fourth_refinement": "四次精制",
}

# 每个工段对应的表与产出批号列
_MAIN_TABLES = {
    "fermentation": ("dr_fermentation_batches", "batch_no"),
    "extraction": ("dr_extractions", "extraction_batch_no"),
    "chromatography": ("dr_chromatography_crystal", "chromatography_batch_no"),
    "first_refinement": ("dr_first_refinement", "refinement_batch_no"),
    "second_refinement": ("dr_second_refinement", "refinement_batch_no"),
    "third_refinement": ("dr_third_refinement", "refinement_batch_no"),
    "fourth_refinement": ("dr_fourth_refinement", "refinement_batch_no"),
}

# 追溯目标工段（下拉）：收率分布展示标签
_DIST_LABELS = {
    "extraction": "萃取",
    "chromatography": "层析",
    "crystallization": "结晶",
    "second_refinement": "二次精制",
    "third_refinement": "三次精制",
    "fourth_refinement": "四次精制",
}

F = lambda v: float(v) if v is not None else 0.0


def _to_f1(bn: str) -> str:
    """湿粉批号 → 一次精制规范批号：层析表 wet_powder_batch_no 部分无 DR-F1- 前缀
    （如 DR-24019-1），而一次精制表 refinement_batch_no 统一 DR-F1-xxx。
    归一化：DR-x → DR-F1-x；已带前缀保持原样。"""
    b = bn.strip()
    if b.startswith("DR-F1-"):
        return b
    if b.startswith("DR-"):
        return "DR-F1-" + b[3:]
    return b


def _f1_to_dr(bn: str) -> str:
    """一次精制批号 → 层析湿粉原始格式：DR-F1-x → DR-x（反查层析表用）"""
    b = bn.strip()
    if b.startswith("DR-F1-"):
        return "DR-" + b[6:]
    return b


async def _feed_pure_from_upstream(session, feed_batch_no: str) -> float:
    """投料批号的折纯量（kg）——三次/四次精制表 feed_pure_kg 常为空，
    顺链取上游产出折纯补全：
      DR-F1-x → dr_first_refinement.feed_pure_kg（一次精制无产出字段，用投料折纯）
      DR-F2-x → dr_second_refinement.product_pure_kg
      DR-F3-x → dr_third_refinement.product_pure_kg
    返回 0.0 表示查不到（断链/回收粉标签）。"""
    b = feed_batch_no.strip()
    if b.startswith("DR-F1-"):
        row = (await session.execute(text(
            "SELECT feed_pure_kg FROM production.dr_first_refinement "
            "WHERE refinement_batch_no = :bn AND is_deleted = false LIMIT 1"
        ), {"bn": b})).fetchone()
        return F(row.feed_pure_kg) if row else 0.0
    if b.startswith("DR-F2-"):
        row = (await session.execute(text(
            "SELECT product_pure_kg FROM production.dr_second_refinement "
            "WHERE refinement_batch_no = :bn AND is_deleted = false LIMIT 1"
        ), {"bn": b})).fetchone()
        return F(row.product_pure_kg) if row else 0.0
    if b.startswith("DR-F3-"):
        row = (await session.execute(text(
            "SELECT product_pure_kg FROM production.dr_third_refinement "
            "WHERE refinement_batch_no = :bn AND is_deleted = false LIMIT 1"
        ), {"bn": b})).fetchone()
        return F(row.product_pure_kg) if row else 0.0
    return 0.0


async def _loss_breakdown_from(session, stage: str, batch_no: str) -> tuple[float, float]:
    """该精制批的损耗去向（kg）：(母液带走, 回收粉) —— 表存字段聚合。
      dr_first/second/third_refinement 有 mother_liquor_product_kg（母液带走产品量）
      dr_second_refinement 另有 recovery_powder_pure_kg（回收粉折纯）
      dr_fourth_refinement 无去向字段 → (0, 0)
    返回 (0,0) 表示无记录/字段缺失（拆不出来就归入"其他损失"）。"""
    b = batch_no.strip()
    ml, rp = 0.0, 0.0
    if stage == "first_refinement":
        row = (await session.execute(text(
            "SELECT SUM(mother_liquor_product_kg) FROM production.dr_first_refinement "
            "WHERE refinement_batch_no = :bn AND is_deleted = false"
        ), {"bn": b})).fetchone()
        ml = F(row[0]) if row and row[0] is not None else 0.0
    elif stage == "second_refinement":
        row = (await session.execute(text(
            "SELECT SUM(mother_liquor_product_kg) AS ml, SUM(recovery_powder_pure_kg) AS rp "
            "FROM production.dr_second_refinement "
            "WHERE refinement_batch_no = :bn AND is_deleted = false"
        ), {"bn": b})).fetchone()
        if row:
            ml = F(row.ml) if row.ml is not None else 0.0
            rp = F(row.rp) if row.rp is not None else 0.0
    elif stage == "third_refinement":
        row = (await session.execute(text(
            "SELECT SUM(mother_liquor_product_kg) FROM production.dr_third_refinement "
            "WHERE refinement_batch_no = :bn AND is_deleted = false"
        ), {"bn": b})).fetchone()
        ml = F(row[0]) if row and row[0] is not None else 0.0
    # fourth_refinement 无 mother_liquor/recovery 字段 → (0,0)
    return ml, rp


# ── 批号识别 ──────────────────────────────────────────

def _detect_stage(batch_no: str) -> Optional[str]:
    """按前缀识别工段；DR-xxx 类歧义返回 None 由数据库探测"""
    b = batch_no.strip().upper()
    if b.startswith("DR-GB"):
        return "fourth_refinement"
    if b.startswith("DR-F3"):
        return "third_refinement"
    if b.startswith("DR-F2"):
        return "second_refinement"
    if b.startswith("DR-F1"):
        return "first_refinement"
    if b.startswith("DR-H"):
        return None  # 回收粉特殊标签
    return None  # DR-26026 / DR-26026-1 歧义，DB 探测


async def _stage_exists(session, stage: str, batch_no: str) -> bool:
    table, col = _MAIN_TABLES[stage]
    r = (await session.execute(text(
        f"SELECT 1 FROM production.{table} WHERE {col} = :bn AND is_deleted = false LIMIT 1"
    ), {"bn": batch_no})).fetchone()
    return r is not None


async def _resolve(session, stage: str, batch_no: str):
    """解析批号归属工段：stage 明确优先，否则前缀/全表探测"""
    b = batch_no.strip()
    if stage and stage in DR_STAGE_LABELS and await _stage_exists(session, stage, b):
        return stage, b
    d = _detect_stage(b)
    if d and await _stage_exists(session, d, b):
        return d, b
    # 逐表探测（DR-xxx 歧义：发酵→萃取→层析→…，萃取优先于层析同名批）
    for st in DR_STAGE_ORDER:
        if await _stage_exists(session, st, b):
            return st, b
    return None, None


def _split_feeds(feed_str: str) -> list[str]:
    """拆分行内多个投料（+、顿号、逗号连接；/ 是批号一部分不拆）"""
    return [p.strip() for p in re.split(r"[＋+、,，]", feed_str) if p.strip()]


def _feed_stage(feed_batch_no: str) -> str:
    """投料批号归属工段；回收粉/文本标签归 recovery（无台账）"""
    b = feed_batch_no.strip()
    if b.startswith("DR-F2"):
        return "second_refinement"
    if b.startswith("DR-F1"):
        return "first_refinement"
    if b.startswith("DR-F3"):
        return "third_refinement"
    if b.startswith("DR-GB"):
        return "fourth_refinement"
    return "recovery"


# ── 节点 detail（收率×100，DR 存小数） ─────────────────

async def _node_info(session, stage: str, batch_no: str):
    """返回 (detail, yield_pct, quantity)"""
    b = batch_no.strip()
    if stage == "extraction":
        rows = (await session.execute(text(
            "SELECT total_qty, single_batch_yield FROM production.dr_extractions "
            "WHERE extraction_batch_no = :bn AND is_deleted = false"
        ), {"bn": b})).fetchall()
        if not rows:
            return "", None, None
        qty = sum(F(r.total_qty) for r in rows)
        yr = next((F(r.single_batch_yield) * 100 for r in rows if r.single_batch_yield), None)
        d = f"合计 {qty:.2f}kg" if qty else ""
        if yr is not None:
            d = (d + ", " if d else "") + f"单批收率 {yr:.1f}%"
        return d, yr, qty

    if stage == "chromatography":
        rows = (await session.execute(text(
            "SELECT product_qty_kg, total_product_qty_kg, chromatography_yield, crystallization_yield "
            "FROM production.dr_chromatography_crystal "
            "WHERE chromatography_batch_no = :bn AND is_deleted = false"
        ), {"bn": b})).fetchall()
        if not rows:
            return "", None, None
        qty = sum(F(r.product_qty_kg) for r in rows)
        cy = next((F(r.chromatography_yield) * 100 for r in rows if r.chromatography_yield), None)
        cry = next((F(r.crystallization_yield) * 100 for r in rows if r.crystallization_yield), None)
        parts = []
        if cy is not None:
            parts.append(f"层析 {cy:.1f}%")
        if cry is not None:
            parts.append(f"结晶 {cry:.1f}%")
        if qty:
            parts.append(f"{qty:.2f}kg")
        return ", ".join(parts), cry if cry is not None else cy, qty

    if stage == "first_refinement":
        row = (await session.execute(text(
            "SELECT feed_pure_kg FROM production.dr_first_refinement "
            "WHERE refinement_batch_no = :bn AND is_deleted = false LIMIT 1"
        ), {"bn": b})).fetchone()
        if not row:
            return "", None, None
        q = F(row.feed_pure_kg)
        return (f"折纯 {q:.2f}kg" if q else ""), None, q

    if stage == "second_refinement":
        row = (await session.execute(text(
            "SELECT product_pure_kg, batch_yield FROM production.dr_second_refinement "
            "WHERE refinement_batch_no = :bn AND is_deleted = false LIMIT 1"
        ), {"bn": b})).fetchone()
        if not row:
            return "", None, None
        q = F(row.product_pure_kg)
        yr = F(row.batch_yield) * 100 if row.batch_yield else None
        d = f"收率 {yr:.1f}%" if yr is not None else ""
        d = (d + ", " if d and q else "") + (f"折纯 {q:.2f}kg" if q else "")
        return d, yr, q

    if stage == "third_refinement":
        row = (await session.execute(text(
            "SELECT product_pure_kg, yield_rate FROM production.dr_third_refinement "
            "WHERE refinement_batch_no = :bn AND is_deleted = false LIMIT 1"
        ), {"bn": b})).fetchone()
        if not row:
            return "", None, None
        q = F(row.product_pure_kg)
        yr = F(row.yield_rate) * 100 if row.yield_rate else None
        d = f"收率 {yr:.1f}%" if yr is not None else ""
        d = (d + ", " if d and q else "") + (f"折纯 {q:.2f}kg" if q else "")
        return d, yr, q

    if stage == "fourth_refinement":
        row = (await session.execute(text(
            "SELECT dry_weight_kg, yield_rate FROM production.dr_fourth_refinement "
            "WHERE refinement_batch_no = :bn AND is_deleted = false LIMIT 1"
        ), {"bn": b})).fetchone()
        if not row:
            return "", None, None
        q = F(row.dry_weight_kg)
        yr = F(row.yield_rate) * 100 if row.yield_rate else None
        d = f"收率 {yr:.1f}%" if yr is not None else ""
        d = (d + ", " if d and q else "") + (f"干粉 {q:.2f}kg" if q else "")
        return d, yr, q

    return "", None, None


# ── 断链检测 ──────────────────────────────────────────

async def _broken_reason(session, stage: str, batch_no: str) -> Optional[str]:
    """节点在自身工段表无记录（无源头的投料/回收粉标签）→ 断链原因"""
    b = batch_no.strip()
    if stage == "recovery":
        return "回收粉/母液标签，无独立台账"
    if stage not in _MAIN_TABLES:
        return None
    table, col = _MAIN_TABLES[stage]
    r = (await session.execute(text(
        f"SELECT 1 FROM production.{table} WHERE {col} = :bn AND is_deleted = false LIMIT 1"
    ), {"bn": b})).fetchone()
    if r:
        return None
    # 表内无记录 → 投料无源头，按工段给具体断链原因
    reasons = {
        "extraction": "萃取表无记录",
        "first_refinement": "一次精制表无记录",
        "second_refinement": "二次精制表无记录",
        "third_refinement": "三次精制表无记录",
        "fourth_refinement": "四次精制表无记录",
    }
    return reasons.get(stage)


# ── 上下游关联 ────────────────────────────────────────

async def _upstream(session, stage: str, batch_no: str):
    """谁生产了 B。返回 [(upstage, upbatch, feed_pure_kg)]"""
    b = batch_no.strip()
    if stage == "extraction":
        # 萃取批 → 发酵批（经罐→批次外键）
        row = (await session.execute(text(
            "SELECT t.fermentation_batch_id FROM production.dr_extractions e "
            "JOIN production.dr_fermentation_tanks t ON t.id::text = e.fermentation_tank_id "
            "WHERE e.extraction_batch_no = :bn AND e.is_deleted = false LIMIT 1"
        ), {"bn": b})).fetchone()
        if row and row.fermentation_batch_id:
            br = (await session.execute(text(
                "SELECT batch_no FROM production.dr_fermentation_batches WHERE id::text = :id LIMIT 1"
            ), {"id": row.fermentation_batch_id})).fetchone()
            if br and br.batch_no:
                return [("fermentation", br.batch_no, None)]
        return []

    if stage == "chromatography":
        # 层析批 → 吃的各萃取批（逐行）
        rows = (await session.execute(text(
            "SELECT DISTINCT extraction_batch_no FROM production.dr_chromatography_crystal "
            "WHERE chromatography_batch_no = :bn AND is_deleted = false AND extraction_batch_no IS NOT NULL "
            "AND TRIM(extraction_batch_no) <> ''"
        ), {"bn": b})).fetchall()
        return [("extraction", r.extraction_batch_no, None) for r in rows]

    if stage == "first_refinement":
        # 一次精制 → 层析批（湿粉产出反查）。层析表 wet_powder_batch_no 可能无 DR-F1- 前缀，
        # 用双格式匹配（DR-F1-24019-1 / DR-24019-1）。
        bn1 = b
        bn2 = _f1_to_dr(b)
        rows = (await session.execute(text(
            "SELECT DISTINCT chromatography_batch_no FROM production.dr_chromatography_crystal "
            "WHERE (wet_powder_batch_no = :bn OR wet_powder_batch_no = :bn2) AND is_deleted = false"
        ), {"bn": bn1, "bn2": bn2})).fetchall()
        return [("chromatography", r.chromatography_batch_no, None) for r in rows]

    feed_cols = {
        "second_refinement": ("dr_second_refinement", "refinement_batch_no", "DR-F1"),
        "third_refinement": ("dr_third_refinement", "refinement_batch_no", "DR-F2"),
        "fourth_refinement": ("dr_fourth_refinement", "refinement_batch_no", "DR-F3"),
    }
    if stage in feed_cols:
        table, col, _ = feed_cols[stage]
        rows = (await session.execute(text(
            f"SELECT feed_batch_no, feed_pure_kg FROM production.{table} "
            f"WHERE {col} = :bn AND is_deleted = false AND feed_batch_no IS NOT NULL "
            "AND TRIM(feed_batch_no) <> ''"
        ), {"bn": b})).fetchall()
        out = []
        for r in rows:
            for fb in _split_feeds(r.feed_batch_no):
                fp = F(r.feed_pure_kg)
                # 三次/四次表 feed_pure_kg 常为空 → 顺链取上游产出折纯补全
                if fp <= 0:
                    fp = await _feed_pure_from_upstream(session, fb)
                out.append((_feed_stage(fb), fb, fp))
        return out

    return []


def _to_feeds(up_rows) -> list[FeedItem]:
    """把 _upstream 返回的 [(upstage, upbatch, feed_pure_kg)] 转成投入明细。
    qty 只有二次/三次/四次精制有（折纯量）；层析/一次精制投料无量 → 0（仅作多投料源标注）"""
    out = []
    for us, ub, fpkg in up_rows:
        out.append(FeedItem(batch_no=ub, stage=us,
                            label=DR_STAGE_LABELS.get(us, us), qty=F(fpkg) or 0.0))
    return out


async def _downstream(session, stage: str, batch_no: str):
    """B 被谁使用。返回 [(downstage, downbatch, qty)]"""
    b = batch_no.strip()
    if stage == "fermentation":
        # 发酵批 → 萃取批（批号前缀；与层析批同名歧义，仅查萃取表）
        rows = (await session.execute(text(
            "SELECT DISTINCT extraction_batch_no FROM production.dr_extractions "
            "WHERE extraction_batch_no LIKE :pat AND is_deleted = false"
        ), {"pat": b + "-%"})).fetchall()
        return [("extraction", r.extraction_batch_no, None) for r in rows]

    if stage == "extraction":
        # 萃取批 → 层析批（被哪些层析批投料）
        rows = (await session.execute(text(
            "SELECT DISTINCT chromatography_batch_no FROM production.dr_chromatography_crystal "
            "WHERE extraction_batch_no = :bn AND is_deleted = false"
        ), {"bn": b})).fetchall()
        return [("chromatography", r.chromatography_batch_no, None) for r in rows]

    if stage == "chromatography":
        # 层析批 → 一次精制（湿粉产出）。wet_powder_batch_no 可能无 DR-F1- 前缀，
        # 归一化为一次精制表规范批号 DR-F1-xxx（如 DR-24019-1 → DR-F1-24019-1）。
        rows = (await session.execute(text(
            "SELECT DISTINCT wet_powder_batch_no FROM production.dr_chromatography_crystal "
            "WHERE chromatography_batch_no = :bn AND is_deleted = false AND wet_powder_batch_no IS NOT NULL"
        ), {"bn": b})).fetchall()
        return [("first_refinement", _to_f1(r.wet_powder_batch_no), None) for r in rows]

    down_map = {
        "first_refinement": ("dr_second_refinement", "second_refinement"),
        "second_refinement": ("dr_third_refinement", "third_refinement"),
        "third_refinement": ("dr_fourth_refinement", "fourth_refinement"),
    }
    if stage in down_map:
        table, dst = down_map[stage]
        rows = (await session.execute(text(
            f"SELECT DISTINCT refinement_batch_no FROM production.{table} "
            f"WHERE TRIM(feed_batch_no) = :bn AND is_deleted = false"
        ), {"bn": b})).fetchall()
        return [(dst, r.refinement_batch_no, None) for r in rows]

    return []


async def _siblings(session, stage: str, batch_no: str, hint_fbatch: str = ""):
    """与 batch_no 同源（共享最近共同上游）的兄弟批。

    返回 (group_key, members)：
      - group_key: 同源组标识（=共同来源批号，如发酵批号/萃取批号）；无兄弟返回 None
      - members: 同源组全部成员 [(stage, batch_no)]，含 batch_no 自身

    萃取→同发酵批的其他萃取；层析→吃同一萃取的其他层析；一次→同一层析的其他 F1。
    二/三/四次精制暂不横向展开（同级通过混批投料行已体现）。

    hint_fbatch：萃取撞名（批号被多发酵批复用）时，主链向上已确定发酵批，
    用它对齐 group_key，避免 sib_group 指向不在追溯图里的批号导致前端画不出虚线。"""
    b = batch_no.strip()

    if stage == "extraction":
        # 目标所在发酵批（可多个发酵罐/批）
        fids = [r.fermentation_batch_id for r in (await session.execute(text(
            "SELECT DISTINCT t.fermentation_batch_id FROM production.dr_extractions e "
            "JOIN production.dr_fermentation_tanks t ON t.id::text = e.fermentation_tank_id "
            "WHERE e.extraction_batch_no = :bn AND e.is_deleted = false"
        ), {"bn": b})).fetchall() if r.fermentation_batch_id]
        if not fids:
            return None, []
        # 撞名防御：优先用主链发酵批（与追溯图发酵节点一致）
        if hint_fbatch:
            hid = (await session.execute(text(
                "SELECT id::text AS id FROM production.dr_fermentation_batches "
                "WHERE batch_no = :bn AND is_deleted = false LIMIT 1"
            ), {"bn": hint_fbatch})).fetchone()
            if hid and hid.id in fids:
                fids = [hid.id]
        fid = fids[0]
        # 组内全部萃取（含自身）
        members: set[str] = set()
        for fid in fids:
            rows = (await session.execute(text(
                "SELECT DISTINCT e.extraction_batch_no FROM production.dr_extractions e "
                "JOIN production.dr_fermentation_tanks t ON t.id::text = e.fermentation_tank_id "
                "WHERE t.fermentation_batch_id = :fid AND e.is_deleted = false "
                "AND e.extraction_batch_no IS NOT NULL AND TRIM(e.extraction_batch_no) <> '' "
                "AND e.extraction_batch_no <> '-'"
            ), {"fid": fid})).fetchall()
            members.update(r.extraction_batch_no for r in rows)
        if len(members) <= 1:
            return None, []
        # group_key = 共同发酵批号
        frow = (await session.execute(text(
            "SELECT batch_no FROM production.dr_fermentation_batches "
            "WHERE id::text = :fid AND is_deleted = false LIMIT 1"
        ), {"fid": fids[0]})).fetchone()
        gk = frow.batch_no if frow else "同源发酵批"
        return gk, [("extraction", x) for x in sorted(members)]

    if stage == "chromatography":
        # 层析 B 吃的各萃取 → 每个萃取的所有层析（含自身）
        exs = [r.extraction_batch_no for r in (await session.execute(text(
            "SELECT DISTINCT extraction_batch_no FROM production.dr_chromatography_crystal "
            "WHERE chromatography_batch_no = :bn AND is_deleted = false AND extraction_batch_no IS NOT NULL "
            "AND TRIM(extraction_batch_no) <> ''"
        ), {"bn": b})).fetchall()]
        if not exs:
            return None, []
        members: set[str] = set()
        for e in exs:
            rows = (await session.execute(text(
                "SELECT DISTINCT chromatography_batch_no FROM production.dr_chromatography_crystal "
                "WHERE extraction_batch_no = :e AND is_deleted = false AND chromatography_batch_no IS NOT NULL "
                "AND TRIM(chromatography_batch_no) <> ''"
            ), {"e": e})).fetchall()
            members.update(r.chromatography_batch_no for r in rows)
        if len(members) <= 1:
            return None, []
        gk = "、".join(sorted(exs))
        return gk, [("chromatography", x) for x in sorted(members)]

    if stage == "first_refinement":
        # 一次 B 的层析父级 → 该层析产出的所有湿粉(F1)（含自身）。
        # 层析 wet_powder_batch_no 可能无 DR-F1- 前缀 → 双格式匹配 + 归一化输出。
        bn1 = b
        bn2 = _f1_to_dr(b)
        cs = [r.chromatography_batch_no for r in (await session.execute(text(
            "SELECT DISTINCT chromatography_batch_no FROM production.dr_chromatography_crystal "
            "WHERE (wet_powder_batch_no = :bn OR wet_powder_batch_no = :bn2) AND is_deleted = false"
        ), {"bn": bn1, "bn2": bn2})).fetchall()]
        if not cs:
            return None, []
        members: set[str] = set()
        for c in cs:
            rows = (await session.execute(text(
                "SELECT DISTINCT wet_powder_batch_no FROM production.dr_chromatography_crystal "
                "WHERE chromatography_batch_no = :c AND is_deleted = false AND wet_powder_batch_no IS NOT NULL "
                "AND TRIM(wet_powder_batch_no) <> ''"
            ), {"c": c})).fetchall()
            members.update(_to_f1(r.wet_powder_batch_no) for r in rows)
        if len(members) <= 1:
            return None, []
        gk = "、".join(sorted(cs))
        return gk, [("first_refinement", x) for x in sorted(members)]

    return None, []


# ── 追溯主端点 ────────────────────────────────────────

@router.get("/dr/lineage/trace", summary="DR 批次全链路追溯（主链+跨批投料全显示）")
async def dr_lineage_trace(
    batch_no: str = Query(...),
    stage: str = Query("", description="工段：fermentation/extraction/chromatography/first_refinement/second_refinement/third_refinement/fourth_refinement"),
    session: AsyncSession = Depends(get_db),
):
    if not batch_no or not batch_no.strip() or batch_no.strip() == "-":
        raise HTTPException(404, "DR 批次号不能为空")
    real_stage, real_batch = await _resolve(session, stage, batch_no)
    if real_stage is None:
        raise HTTPException(404, f"DR 批次未找到: {batch_no}")

    broken_links: list[dict] = []
    broken_seen: set[str] = set()

    def _note_broken(st, bn, reason):
        key = f"{st}|{bn}"
        if key not in broken_seen:
            broken_seen.add(key)
            broken_links.append({
                "stage": st, "label": DR_STAGE_LABELS.get(st, "回收粉/母液"),
                "batch_no": bn, "reason": reason,
            })

    # ── 受限 BFS：主链向上递归 + 主链向下递归 + 下游节点投料行全显示（不递归投料批）──
    # 设计要点（收敛扩散）：全向 BFS 会在共享边（萃取批被多层析批用、投料批被多三次批用）
    # 处把兄弟链整条拉入。改为方向性展开——
    #   ① 主链向上：target → 一次 → 层析 → 萃取 → 发酵，每层展开全部生产者（层析吃多萃取全列、跨发酵批全列），不查生产者的下游
    #   ② 主链向下：target → 三次 → 四次，每层展开全部使用者
    #   ③ 下游节点（三次/四次）的投料行全显示：DR-F2-241013、四次母液回收粉等跨批投料以断链节点列出，但不递归展开其上下游
    nodes: dict[str, dict] = {s: {} for s in DR_STAGE_LABELS}  # stage -> {batch_no: meta}
    recovery_nodes: dict[str, dict] = {}

    def _add_recovery(bn):
        reason = "回收粉/母液标签，无独立台账"
        _note_broken("recovery", bn, reason)
        recovery_nodes[bn] = {"broken_reason": reason}

    async def _add_node(st, bn, is_sibling=False, sib_group=""):
        if st == "recovery":
            _add_recovery(bn)
            return
        d, y, q = await _node_info(session, st, bn)
        br = await _broken_reason(session, st, bn)
        if br:
            _note_broken(st, bn, br)
        nodes[st][bn] = {"detail": d, "yield_rate": y, "quantity": q,
                         "broken": bool(br), "broken_reason": br,
                         "is_sibling": is_sibling, "sib_group": sib_group}

    # target 节点
    td, ty, tq = await _node_info(session, real_stage, real_batch)
    treason = await _broken_reason(session, real_stage, real_batch)
    if treason:
        _note_broken(real_stage, real_batch, treason)
    nodes[real_stage][real_batch] = {"detail": td, "yield_rate": ty, "quantity": tq,
                                     "broken": bool(treason), "broken_reason": treason,
                                     "is_sibling": False, "sib_group": ""}

    seen = {(real_stage, real_batch)}
    # 各节点投入明细（混批全部兄弟批 + 折纯量），组装时填进 LineageNode.feeds
    feeds_map: dict[tuple, list[FeedItem]] = {}

    # ① 主链向上：只展开生产者，不查其下游
    queue_up = [(real_stage, real_batch)]
    main_ferm: str = ""  # 主链发酵批号（萃取撞名时供同源组对齐）
    while queue_up:
        cs, cb = queue_up.pop(0)
        up_rows = await _upstream(session, cs, cb)
        feeds_map[(cs, cb)] = _to_feeds(up_rows)
        for us, ub, _ in up_rows:
            if us == "fermentation" and not main_ferm:
                main_ferm = ub
            if (us, ub) not in seen:
                seen.add((us, ub))
                await _add_node(us, ub)
                queue_up.append((us, ub))

    # ②③ 主链向下：展开使用者；三次/四次的投料行全显示但投料批不入队（不递归展开其上下游）
    queue_down = [(real_stage, real_batch)]
    # 同源兄弟批（如搜索萃取时同发酵的其他萃取）：整组标 sib_group 供前端虚线串联，
    # 兄弟批标 is_sibling + 作为向下种子展开各自去向
    sib_group_key, sib_members = await _siblings(session, real_stage, real_batch, hint_fbatch=main_ferm)
    for sst, sbn in sib_members:
        is_self = (sst == real_stage and sbn == real_batch)
        if (sst, sbn) not in seen:
            seen.add((sst, sbn))
            await _add_node(sst, sbn, is_sibling=not is_self, sib_group=sib_group_key)
            if not is_self:
                queue_down.append((sst, sbn))
        else:
            # 目标节点已在 seen/已初始化：补标同源组
            if sst in nodes and sbn in nodes[sst]:
                nodes[sst][sbn]["sib_group"] = sib_group_key
    while queue_down:
        cs, cb = queue_down.pop(0)
        # 二次/三次/四次精制有 feed_batch_no 投料行：全展开兄弟批，并记录投入明细
        if cs in ("second_refinement", "third_refinement", "fourth_refinement"):
            up_rows = await _upstream(session, cs, cb)
            feeds_map[(cs, cb)] = _to_feeds(up_rows)
            for us, ub, _ in up_rows:
                if (us, ub) not in seen:
                    seen.add((us, ub))
                    await _add_node(us, ub)  # 跨批投料/回收粉标签/断链节点；不入队
        for ds, dbn, _ in await _downstream(session, cs, cb):
            if (ds, dbn) not in seen:
                seen.add((ds, dbn))
                await _add_node(ds, dbn)
                queue_down.append((ds, dbn))

    # ── 连接关系（connects_to：每个节点 → 其下游批次）──
    conn_map: dict[tuple, list] = {}
    for cs, cb in seen:
        for ds, dbn, _ in await _downstream(session, cs, cb):
            if (ds, dbn) in seen:
                conn_map.setdefault((cs, cb), []).append(dbn)

    # ── 组装 stage groups ──
    stages_out = []
    for s in DR_STAGE_ORDER:
        nlist = []
        for bn, meta in nodes[s].items():
            ct = ", ".join(conn_map.get((s, bn), [])) if conn_map.get((s, bn)) else ""
            feeds = feeds_map.get((s, bn), [])
            input_total = round(sum(f.qty for f in feeds), 2)
            # 本段损耗（投入折纯 − 产出折纯/干粉；只对精制/干燥段，同口径可算）
            loss_kg, loss_rate, loss_level = None, None, ""
            if s in ("second_refinement", "third_refinement", "fourth_refinement"):
                out_q = meta.get("quantity")
                if input_total > 0 and out_q is not None and out_q > 0:
                    lk = round(input_total - out_q, 2)
                    if lk != 0:
                        lr = round(lk / input_total * 100, 1)
                        loss_kg, loss_rate = lk, lr
                        loss_level = "green" if lr < 5 else ("yellow" if lr < 10 else "red")
            # 损耗去向拆解（母液带走 + 回收粉 + 其他损失；精制段均查）
            loss_breakdown = None
            if s in ("first_refinement", "second_refinement", "third_refinement", "fourth_refinement"):
                ml, rp = await _loss_breakdown_from(session, s, bn)
                recorded = (ml > 0) or (rp > 0)
                bd = {"mother_liquor_kg": None, "recovery_powder_kg": None,
                      "other_kg": None, "recorded": recorded}
                if ml > 0:
                    bd["mother_liquor_kg"] = round(ml, 2)
                if rp > 0:
                    bd["recovery_powder_kg"] = round(rp, 2)
                if loss_kg is not None and recorded:
                    other = round(loss_kg - ml - rp, 2)
                    bd["other_kg"] = other if other > 0 else round(other, 2)
                if recorded or (loss_kg is not None and s != "first_refinement"):
                    loss_breakdown = bd
            nlist.append(LineageNode(
                stage=s, label=DR_STAGE_LABELS[s], batch_no=bn,
                detail=meta["detail"], yield_rate=meta["yield_rate"],
                quantity=meta["quantity"], connects_to=ct,
                broken=meta["broken"], broken_reason=meta["broken_reason"] or "",
                is_sibling=meta.get("is_sibling", False),
                sib_group=meta.get("sib_group", ""),
                feeds=feeds, input_total=input_total,
                loss_kg=loss_kg, loss_rate=loss_rate, loss_level=loss_level,
                loss_breakdown=loss_breakdown,
            ))
        # 排序：断链放最后
        nlist.sort(key=lambda n: (1 if n.broken else 0, n.batch_no))
        if nlist:
            stages_out.append(StageGroup(stage=s, label=DR_STAGE_LABELS[s], nodes=nlist))
    # 回收粉/母液独立分组（无台账的投料标签）
    if recovery_nodes:
        rn = [LineageNode(stage="recovery", label="回收粉/母液", batch_no=bn,
                          broken=True, broken_reason=meta["broken_reason"] or "")
              for bn, meta in recovery_nodes.items()]
        rn.sort(key=lambda n: n.batch_no)
        stages_out.append(StageGroup(stage="recovery", label="回收粉/母液", nodes=rn))

    # ── 累积收率递推（取每工段第一条有收率的节点）──
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

    return success_response(data={
        "stages": [sg.model_dump(exclude_none=False) for sg in stages_out],
        "target_batch": real_batch,
        "target_stage": real_stage,
        "cumulative_yield": round(cum, 1),
        "max_loss_stage": mls,
        "broken_links": broken_links,
    })


# ── 收率分布 ──────────────────────────────────────────

@router.get("/dr/lineage/yield-distribution", summary="DR 收率分布（按工段箱线统计）")
async def dr_yield_distribution(session: AsyncSession = Depends(get_db)):
    rows = (await session.execute(text("""
        SELECT stage, COUNT(*) AS n,
               ROUND(MIN(y)::numeric, 1) AS min_y,
               ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY y)::numeric, 1) AS q1,
               ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY y)::numeric, 1) AS median,
               ROUND(AVG(y)::numeric, 1) AS mean,
               ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY y)::numeric, 1) AS q3,
               ROUND(MAX(y)::numeric, 1) AS max_y,
               COUNT(*) FILTER (WHERE y < 80) AS below_80,
               COUNT(*) FILTER (WHERE y > 110) AS above_110
        FROM (
            SELECT 'extraction' AS stage, ROUND(single_batch_yield::numeric * 100, 1)::float8 AS y
            FROM production.dr_extractions WHERE is_deleted = false AND single_batch_yield IS NOT NULL
            UNION ALL
            SELECT 'chromatography', ROUND(chromatography_yield::numeric * 100, 1)::float8
            FROM production.dr_chromatography_crystal WHERE is_deleted = false AND chromatography_yield IS NOT NULL
            UNION ALL
            SELECT 'crystallization', ROUND(crystallization_yield::numeric * 100, 1)::float8
            FROM production.dr_chromatography_crystal WHERE is_deleted = false AND crystallization_yield IS NOT NULL
            UNION ALL
            SELECT 'second_refinement', ROUND(batch_yield::numeric * 100, 1)::float8
            FROM production.dr_second_refinement WHERE is_deleted = false AND batch_yield IS NOT NULL
            UNION ALL
            SELECT 'third_refinement', ROUND(yield_rate::numeric * 100, 1)::float8
            FROM production.dr_third_refinement WHERE is_deleted = false AND yield_rate IS NOT NULL
            UNION ALL
            SELECT 'fourth_refinement', ROUND(yield_rate::numeric * 100, 1)::float8
            FROM production.dr_fourth_refinement WHERE is_deleted = false AND yield_rate IS NOT NULL
        ) t
        GROUP BY stage
    """))).fetchall()
    items = [YieldDistItem(stage=r.stage, label=_DIST_LABELS.get(r.stage, r.stage),
        count=r.n, min=float(r.min_y or 0), q1=float(r.q1 or 0),
        median=float(r.median or 0), mean=float(r.mean or 0),
        q3=float(r.q3 or 0), max=float(r.max_y or 0),
        below_80=r.below_80, above_110=r.above_110) for r in rows]
    return success_response(data=[i.model_dump() for i in items])


# ── 物料复用 ──────────────────────────────────────────

@router.get("/dr/lineage/material-reuse", summary="DR 物料复用（被多个下游批复用的投料）")
async def dr_material_reuse(session: AsyncSession = Depends(get_db)):
    rows = (await session.execute(text("""
        SELECT up_type, feed_batch_no AS up_batch, usage_count, used_by FROM (
            -- 三次精制投料被多个三次批使用
            SELECT 'third_refinement' AS up_type, feed_batch_no, COUNT(DISTINCT refinement_batch_no) AS usage_count,
                   STRING_AGG(DISTINCT refinement_batch_no, ', ' ORDER BY refinement_batch_no) AS used_by
            FROM production.dr_third_refinement
            WHERE feed_batch_no IS NOT NULL AND TRIM(feed_batch_no) <> '' AND is_deleted = false
            GROUP BY feed_batch_no HAVING COUNT(DISTINCT refinement_batch_no) > 1
            UNION ALL
            -- 四次精制投料被多个四次批使用
            SELECT 'fourth_refinement', feed_batch_no, COUNT(DISTINCT refinement_batch_no),
                   STRING_AGG(DISTINCT refinement_batch_no, ', ' ORDER BY refinement_batch_no)
            FROM production.dr_fourth_refinement
            WHERE feed_batch_no IS NOT NULL AND TRIM(feed_batch_no) <> '' AND is_deleted = false
            GROUP BY feed_batch_no HAVING COUNT(DISTINCT refinement_batch_no) > 1
            UNION ALL
            -- 萃取批液被多个层析批使用
            SELECT 'chromatography', extraction_batch_no, COUNT(DISTINCT chromatography_batch_no),
                   STRING_AGG(DISTINCT chromatography_batch_no, ', ' ORDER BY chromatography_batch_no)
            FROM production.dr_chromatography_crystal
            WHERE extraction_batch_no IS NOT NULL AND TRIM(extraction_batch_no) <> '' AND is_deleted = false
            GROUP BY extraction_batch_no HAVING COUNT(DISTINCT chromatography_batch_no) > 1
        ) t ORDER BY usage_count DESC
    """))).fetchall()
    items = [MaterialReuseItem(upstream_type=r.up_type, upstream_batch=r.up_batch,
        usage_count=r.usage_count, used_by=r.used_by) for r in rows]
    return success_response(data=[i.model_dump() for i in items])


# ── 覆盖完整性（断链统计） ────────────────────────────

@router.get("/dr/lineage/coverage", summary="DR 覆盖完整性与断链清单")
async def dr_coverage(session: AsyncSession = Depends(get_db)):
    # 各工段产出批数
    segs = []
    for s, (table, col) in _MAIN_TABLES.items():
        if s == "fermentation":
            n = (await session.execute(text(
                "SELECT COUNT(DISTINCT batch_no) FROM production.dr_fermentation_batches WHERE is_deleted = false"
            ))).scalar() or 0
            segs.append(CoverageItem(segment="发酵批", count=n))
        elif s in ("extraction", "chromatography"):
            n = (await session.execute(text(
                f"SELECT COUNT(DISTINCT {col}) FROM production.{table} WHERE is_deleted = false"
            ))).scalar() or 0
            segs.append(CoverageItem(segment=DR_STAGE_LABELS[s], count=n))
        else:
            n = (await session.execute(text(
                f"SELECT COUNT(DISTINCT {col}) FROM production.{table} WHERE is_deleted = false"
            ))).scalar() or 0
            segs.append(CoverageItem(segment=DR_STAGE_LABELS[s], count=n))

    # 断链清单
    async def _missing(src_table, src_col, tgt_table, tgt_col, prefix=None):
        """源表投料批号在目标表查不到（可带前缀过滤）"""
        prefix_sql = f"AND {src_col} LIKE :pre" if prefix else ""
        rows = (await session.execute(text(f"""
            SELECT DISTINCT {src_col} FROM production.{src_table}
            WHERE is_deleted = false AND {src_col} IS NOT NULL AND TRIM({src_col}) <> ''
            AND NOT EXISTS (
                SELECT 1 FROM production.{tgt_table}
                WHERE {tgt_col} = production.{src_table}.{src_col} AND is_deleted = false
            )
            {prefix_sql}
        """), {"pre": prefix + "%"} if prefix else {})).fetchall()
        return [r[0] for r in rows]

    # 层析投料萃取表查不到（DR-24002-4 类）
    missing_extraction = await _missing("dr_chromatography_crystal", "extraction_batch_no",
                                        "dr_extractions", "extraction_batch_no")
    # 三次投料（DR-F2）二次表查不到（DR-F2-241013 类）
    missing_second = await _missing("dr_third_refinement", "feed_batch_no",
                                    "dr_second_refinement", "refinement_batch_no", prefix="DR-F2")
    # 四次投料（DR-F3）三次表查不到
    missing_third = await _missing("dr_fourth_refinement", "feed_batch_no",
                                   "dr_third_refinement", "refinement_batch_no", prefix="DR-F3")
    # 特殊投料标签（非 DR-F1/F2/F3/GB 前缀：回收粉/母液文本）
    special_rows = (await session.execute(text("""
        SELECT DISTINCT feed_batch_no FROM production.dr_third_refinement
        WHERE is_deleted = false AND feed_batch_no IS NOT NULL AND TRIM(feed_batch_no) <> ''
        AND feed_batch_no NOT LIKE 'DR-F2%' AND feed_batch_no NOT LIKE 'DR-F1%'
        UNION
        SELECT DISTINCT feed_batch_no FROM production.dr_fourth_refinement
        WHERE is_deleted = false AND feed_batch_no IS NOT NULL AND TRIM(feed_batch_no) <> ''
        AND feed_batch_no NOT LIKE 'DR-F3%' AND feed_batch_no NOT LIKE 'DR-F2%'
        AND feed_batch_no NOT LIKE 'DR-F1%'
    """))).fetchall()
    special_feeds = [r[0] for r in special_rows]

    return success_response(data={
        "segments": [s.model_dump() for s in segs],
        "broken": {
            "extraction_feeds_not_in_extraction": {"count": len(missing_extraction), "batches": missing_extraction},
            "third_feeds_not_in_second": {"count": len(missing_second), "batches": missing_second},
            "fourth_feeds_not_in_third": {"count": len(missing_third), "batches": missing_third},
            "special_feeds": {"count": len(special_feeds), "batches": special_feeds},
        },
    })


# ── 单批全程损耗漏斗 ─────────────────────────────────

class FunnelLayer(BaseModel):
    """损耗漏斗的一层（一个工段聚合）"""
    stage: str
    label: str
    batch_count: int = 0                    # 该层批数
    batches: list[str] = []                 # 批号列表
    input_pure: Optional[float] = None      # 投入折纯 kg（层析层为 None：起点）
    output_pure: Optional[float] = None     # 产出折纯/干粉 kg
    segment_yield: Optional[float] = None   # 本段收率 %（output/input×100）
    segment_loss: Optional[float] = None    # 本段损耗 kg（input−output）
    note: str = ""                          # 口径/断链说明


class FunnelResult(BaseModel):
    target_batch: str
    target_stage: str
    layers: list[FunnelLayer]
    overall_yield: Optional[float] = None   # 全程收率 %（最终干粉/层析湿粉）
    overall_loss: Optional[float] = None    # 全程损耗 kg（层析湿粉−最终干粉）
    notes: list[str] = []                   # 全局说明（断链/口径）


async def _wet_powder_roots(session, stage: str, batch_no: str) -> set[str]:
    """从目标批号向上定位"层析湿粉"起点批号集合。
    若目标在层析之前（发酵/萃取），向下展开找层析；否则向上回溯到层析。
    层析湿粉折纯是全程损耗的可比口径起点（萃取液为另一口径不参与）。"""
    if stage == "chromatography":
        return {batch_no}
    roots: set[str] = set()
    seen = {(stage, batch_no)}
    queue = [(stage, batch_no)]
    # ① 向上找层析（F1/F2/F3/GB → 层析）
    while queue:
        cs, cb = queue.pop(0)
        up = await _upstream(session, cs, cb)
        for us, ub, _ in up:
            if (us, ub) in seen:
                continue
            seen.add((us, ub))
            if us == "chromatography":
                roots.add(ub)
            elif us in ("fermentation", "extraction"):
                continue  # 发酵/萃取不是折纯起点，不再上溯
            else:
                queue.append((us, ub))
    if roots:
        return roots
    # ② 目标在层析之前（发酵/萃取）→ 向下展开到层析
    seen = {(stage, batch_no)}
    queue = [(stage, batch_no)]
    while queue:
        cs, cb = queue.pop(0)
        down = await _downstream(session, cs, cb)
        for ds, dbn, _ in down:
            if (ds, dbn) in seen:
                continue
            seen.add((ds, dbn))
            if ds == "chromatography":
                roots.add(dbn)
            elif ds in ("extraction", "fermentation", "chromatography"):
                queue.append((ds, dbn))
    return roots


async def _chain_layers(session, roots: set[str]) -> dict[str, set[str]]:
    """从层析起点向下展开各工段批号集合（层析→F1→F2→F3→GB）"""
    layers: dict[str, set[str]] = {"chromatography": set(roots)}
    queue = [("chromatography", b) for b in roots]
    seen = set(queue)
    while queue:
        cs, cb = queue.pop(0)
        for ds, dbn, _ in await _downstream(session, cs, cb):
            if (ds, dbn) in seen:
                continue
            seen.add((ds, dbn))
            layers.setdefault(ds, set()).add(dbn)
            if ds in ("first_refinement", "second_refinement", "third_refinement", "fourth_refinement"):
                queue.append((ds, dbn))
    return layers


async def _layer_output(session, stage: str, batches: set[str]) -> float:
    """该工段批号集合的产出量（折纯/干粉 kg）。层析=湿粉折纯；F1=投料折纯(无独立产出)；
    F2/F3=产出折纯；F4=干粉。"""
    if not batches:
        return 0.0
    lst = list(batches)
    col = {
        "chromatography": "wet_powder_pure_kg",
        "first_refinement": "feed_pure_kg",      # 一次精制无产出字段，投料折纯即其量
        "second_refinement": "product_pure_kg",
        "third_refinement": "product_pure_kg",
        "fourth_refinement": "dry_weight_kg",    # 干粉（最终产品）
    }.get(stage)
    if not col:
        return 0.0
    r = (await session.execute(text(
        f"SELECT COALESCE(SUM({col}), 0) FROM production.{_MAIN_TABLES[stage][0]} "
        "WHERE is_deleted = false AND " + _MAIN_TABLES[stage][1] + " = ANY(:lst)"
    ), {"lst": lst})).scalar() or 0
    return float(r)


async def _layer_input(session, stage: str, batches: set[str]) -> float:
    """该工段批号集合的投入折纯 kg——二次/三次/四次精制为混批节点，
    用 _upstream 展开全部兄弟投料（含跨批 + feed_pure 链补），避免单批起点漏掉兄弟批。"""
    if not batches:
        return 0.0
    total = 0.0
    for bn in batches:
        for us, ub, fpkg in await _upstream(session, stage, bn):
            if us in ("first_refinement", "second_refinement", "third_refinement"):
                total += fpkg
    return round(total, 2)


@router.get("/dr/lineage/loss-funnel", summary="DR 单批全程损耗漏斗（层析湿粉→干粉，逐段对账）")
async def dr_loss_funnel(
    batch_no: str = Query(...),
    stage: str = Query("", description="工段：fermentation/extraction/chromatography/first_refinement/second_refinement/third_refinement/fourth_refinement"),
    session: AsyncSession = Depends(get_db),
):
    if not batch_no or not batch_no.strip() or batch_no.strip() == "-":
        raise HTTPException(404, "DR 批次号不能为空")
    real_stage, real_batch = await _resolve(session, stage, batch_no)
    if real_stage is None:
        raise HTTPException(404, f"DR 批次未找到: {batch_no}")

    # 层析湿粉起点（折纯可比口径）
    roots = await _wet_powder_roots(session, real_stage, real_batch)
    if not roots:
        return success_response(data=FunnelResult(
            target_batch=real_batch, target_stage=real_stage, layers=[],
            notes=["未找到层析湿粉起点（数据未闭合或非 DR 批次）"],
        ).model_dump())

    layers_map = await _chain_layers(session, roots)
    stage_order = ["chromatography", "first_refinement", "second_refinement",
                   "third_refinement", "fourth_refinement"]
    layers: list[FunnelLayer] = []
    prev_output: Optional[float] = None   # 上一层产出 = 本层投入（折纯可比）
    for st in stage_order:
        batches = layers_map.get(st, set())
        if not batches:
            break  # 断链：本层无批号，后续层停止
        out = await _layer_output(session, st, batches)
        note = ""
        if st == "fourth_refinement":
            note = "干粉口径（四次精制最终产品）"
        elif st == "first_refinement":
            note = "一次精制无产出字段，量=投料折纯"
        # 投入：F2/F3/F4 为混批节点 → 展开全部兄弟投料（_layer_input）；
        # 层析为起点（无投入）；F1 用上一层产出（层析湿粉）作投入基准
        if st == "chromatography":
            inp = None
        elif st == "first_refinement":
            inp = prev_output
        else:
            inp = await _layer_input(session, st, batches) or prev_output
        seg_yield, seg_loss = None, None
        if inp is not None and inp > 0:
            seg_loss = round(inp - out, 2)
            seg_yield = round(out / inp * 100, 1)
            if seg_yield and seg_yield > 110:
                note = (note + "，" if note else "") + "产出大于投入（混批含外来批，非本段异常）"
        layers.append(FunnelLayer(
            stage=st, label=DR_STAGE_LABELS.get(st, st),
            batch_count=len(batches), batches=sorted(batches),
            input_pure=round(inp, 2) if inp is not None else None,
            output_pure=round(out, 2),
            segment_yield=seg_yield, segment_loss=seg_loss, note=note,
        ))
        prev_output = out

    # 全程收率：最终干粉 / 层析湿粉
    overall_yield = None
    overall_loss = None
    notes: list[str] = []
    if layers:
        start = layers[0].output_pure
        end = layers[-1].output_pure
        if start and start > 0:
            overall_yield = round(end / start * 100, 1)
            overall_loss = round(start - end, 2)
        if len(layers) < len(stage_order):
            notes.append("链在 " + layers[-1].label + " 处中断（数据未闭合），后续工段未对账")
        # 中间批次起点（F1/F2/F3/GB）时，下游混批含兄弟批 → 全程收率不代表单批
        if overall_yield is not None and (overall_yield > 100 or overall_loss is not None and overall_loss < 0):
            notes.append("从中间批次起点时，下游混批含兄弟批的料，全程收率/损耗不代表该批单批——"
                         "建议从发酵批或层析批号查看全程")

    return success_response(data=FunnelResult(
        target_batch=real_batch, target_stage=real_stage,
        layers=[l.model_dump() for l in layers],
        overall_yield=overall_yield, overall_loss=overall_loss, notes=notes,
    ).model_dump())


# ── 车间损耗统计（按工段×月） ─────────────────────────

class LossStatItem(BaseModel):
    stage: str
    label: str
    year_month: str
    count: int
    avg_yield: float       # 平均收率 %（yield_rate×100）
    min_yield: float
    max_yield: float


class UnclosedItem(BaseModel):
    stage: str
    label: str
    batch_no: str
    feed_batch_no: str
    reason: str


class LossStatsResult(BaseModel):
    by_segment_month: list[LossStatItem]
    unclosed: list[UnclosedItem]


@router.get("/dr/lineage/loss-stats", summary="DR 损耗统计（按工段×月平均收率 + 未闭合投料）")
async def dr_loss_stats(session: AsyncSession = Depends(get_db)):
    # 各精制工段按年月聚合收率（存小数×100）
    rows = (await session.execute(text("""
        SELECT stage, ym, COUNT(*) AS n,
               ROUND(AVG(y)::numeric, 1) AS avg_y,
               ROUND(MIN(y)::numeric, 1) AS min_y,
               ROUND(MAX(y)::numeric, 1) AS max_y
        FROM (
            SELECT 'second_refinement' AS stage,
                   split_part(production_date, '.', 1) || '.' || split_part(production_date, '.', 2) AS ym,
                   ROUND(batch_yield::numeric * 100, 1)::float8 AS y
            FROM production.dr_second_refinement
            WHERE is_deleted = false AND batch_yield IS NOT NULL
              AND production_date IS NOT NULL AND production_date <> ''
            UNION ALL
            SELECT 'third_refinement',
                   split_part(production_date, '.', 1) || '.' || split_part(production_date, '.', 2),
                   ROUND(yield_rate::numeric * 100, 1)::float8
            FROM production.dr_third_refinement
            WHERE is_deleted = false AND yield_rate IS NOT NULL
              AND production_date IS NOT NULL AND production_date <> ''
            UNION ALL
            SELECT 'fourth_refinement',
                   split_part(production_date, '.', 1) || '.' || split_part(production_date, '.', 2),
                   ROUND(yield_rate::numeric * 100, 1)::float8
            FROM production.dr_fourth_refinement
            WHERE is_deleted = false AND yield_rate IS NOT NULL
              AND production_date IS NOT NULL AND production_date <> ''
        ) t
        GROUP BY stage, ym
        ORDER BY ym, stage
    """))).fetchall()
    items = [LossStatItem(stage=r.stage, label=DR_STAGE_LABELS.get(r.stage, r.stage),
        year_month=r.ym, count=r.n, avg_yield=float(r.avg_y or 0),
        min_yield=float(r.min_y or 0), max_yield=float(r.max_y or 0)) for r in rows]

    # 未闭合投料（feed_batch_no 在上游表查不到）
    unclosed: list[UnclosedItem] = []
    # 三次投料（DR-F2）→ 二次表无记录
    for r in (await session.execute(text("""
        SELECT DISTINCT refinement_batch_no, feed_batch_no
        FROM production.dr_third_refinement
        WHERE is_deleted = false AND feed_batch_no IS NOT NULL AND TRIM(feed_batch_no) <> ''
        AND feed_batch_no LIKE 'DR-F2%'
        AND NOT EXISTS (
            SELECT 1 FROM production.dr_second_refinement
            WHERE refinement_batch_no = production.dr_third_refinement.feed_batch_no AND is_deleted = false
        )
    """))).fetchall():
        unclosed.append(UnclosedItem(stage="third_refinement", label="三次精制",
            batch_no=r.refinement_batch_no, feed_batch_no=r.feed_batch_no, reason="三次投料在二次表查不到"))
    # 四次投料（DR-F3）→ 三次表无记录
    for r in (await session.execute(text("""
        SELECT DISTINCT refinement_batch_no, feed_batch_no
        FROM production.dr_fourth_refinement
        WHERE is_deleted = false AND feed_batch_no IS NOT NULL AND TRIM(feed_batch_no) <> ''
        AND feed_batch_no LIKE 'DR-F3%'
        AND NOT EXISTS (
            SELECT 1 FROM production.dr_third_refinement
            WHERE refinement_batch_no = production.dr_fourth_refinement.feed_batch_no AND is_deleted = false
        )
    """))).fetchall():
        unclosed.append(UnclosedItem(stage="fourth_refinement", label="四次精制",
            batch_no=r.refinement_batch_no, feed_batch_no=r.feed_batch_no, reason="四次投料在三次表查不到"))

    return success_response(data=LossStatsResult(
        by_segment_month=items, unclosed=unclosed,
    ).model_dump())
