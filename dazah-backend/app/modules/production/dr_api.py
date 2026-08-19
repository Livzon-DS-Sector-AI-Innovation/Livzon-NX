"""DR 多拉菌素 — 萃取工段完整 API（四级嵌套：批次→罐→萃取→滤液）+ 仪表盘"""

import logging
from datetime import date, datetime
from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response, paginated_response
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE
from app.modules.production.dr_models import (
    DrFermentationBatch,
    DrFermentationTank,
    DrExtraction,
    DrFiltrate,
    DrChromatographyCrystal,
    DrFirstRefinement,
    DrSecondRefinement,
    DrThirdRefinement,
    DrFourthRefinement,
)

logger = logging.getLogger(__name__)

router = create_module_router(MODULES_BY_CODE["production"])


# ── 辅助 ──
def _clean_dict(obj) -> dict:
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}


# ═══════════════════════════════════════════════════════
# 萃取工段 — 四级嵌套全量数据（供 DRTable 组件）
# ═══════════════════════════════════════════════════════

@router.get("/dr/extraction/full", summary="DR 萃取工段完整嵌套数据")
async def get_dr_extraction_full(
    workshop: str = Query("201-3"),
    year: int | None = Query(None, ge=2020, le=2099, description="筛选年份"),
    month: int | None = Query(None, ge=1, le=12, description="筛选月份"),
    session: AsyncSession = Depends(get_db),
):
    """
    返回 批次→发酵罐→萃取→滤液 四级嵌套结构，供前端 DRTable 组件直接渲染。
    支持按年份/月份筛选（基于 tank_date 接罐日期字段）。
    """
    # 1. 查询所有发酵批次
    batch_q = select(DrFermentationBatch).where(
        DrFermentationBatch.is_deleted == False,
        DrFermentationBatch.workshop == workshop,
    )
    # 年月筛选：tank_date 格式为 "YYYY.MM.DD" 或 "YYYY-MM-DD"
    if year is not None:
        batch_q = batch_q.where(DrFermentationBatch.tank_date.like(f"{year}%"))
    if month is not None:
        batch_q = batch_q.where(DrFermentationBatch.tank_date.like(f"%.{month:02d}.%"))

    batch_q = batch_q.order_by(DrFermentationBatch.batch_no.asc())

    batch_rows = (await session.execute(batch_q)).scalars().all()
    batch_ids = [str(r.id) for r in batch_rows]

    if not batch_ids:
        return success_response([])

    # 2. 查询所有罐
    tank_q = select(DrFermentationTank).where(
        DrFermentationTank.is_deleted == False,
        DrFermentationTank.fermentation_batch_id.in_(batch_ids),
    ).order_by(DrFermentationTank.tank_no)
    tank_rows = (await session.execute(tank_q)).scalars().all()
    tank_ids = [str(r.id) for r in tank_rows]

    # 3. 查询所有萃取
    extr_q = select(DrExtraction).where(
        DrExtraction.is_deleted == False,
        DrExtraction.fermentation_tank_id.in_(tank_ids),
    ).order_by(DrExtraction.extraction_batch_no)
    extr_rows = (await session.execute(extr_q)).scalars().all()
    extr_ids = [str(r.id) for r in extr_rows]

    # 4. 查询所有滤液
    filtr_q = select(DrFiltrate).where(
        DrFiltrate.is_deleted == False,
        DrFiltrate.extraction_id.in_(extr_ids),
    ).order_by(DrFiltrate.tank_no)
    filtr_rows = (await session.execute(filtr_q)).scalars().all()

    # ── 组装嵌套结构 ──
    # 滤液按 extraction_id 分组
    filtr_map: dict[str, list] = {}
    for f in filtr_rows:
        filtr_map.setdefault(f.extraction_id, []).append(_clean_dict(f))

    # 萃取按 tank_id 分组
    extr_map: dict[str, list] = {}
    for e in extr_rows:
        eid = str(e.id)
        d = _clean_dict(e)
        d["filtrates"] = filtr_map.get(eid, [])
        extr_map.setdefault(e.fermentation_tank_id, []).append(d)

    # 罐按 batch_id 分组
    tank_map: dict[str, list] = {}
    for t in tank_rows:
        tid = str(t.id)
        d = _clean_dict(t)
        d["extractions"] = extr_map.get(tid, [])
        tank_map.setdefault(t.fermentation_batch_id, []).append(d)

    # 最终批次列表
    result = []
    for b in batch_rows:
        bid = str(b.id)
        d = _clean_dict(b)
        d["tanks"] = tank_map.get(bid, [])
        # 计算 rowspan（批号级 = 该批下所有滤液行数之和）
        d["rowspan"] = sum(
            len(extr.get("filtrates", []) or [])
            for tank in d["tanks"]
            for extr in tank.get("extractions", [])
        )
        # 杂质单独拎出来
        d["impurities"] = {
            "impurity_6": b.impurity_6,
            "impurity_1": b.impurity_1,
            "impurity_2": b.impurity_2,
            "impurity_7": b.impurity_7,
            "impurity_3": b.impurity_3,
            "impurity_4": b.impurity_4,
            "impurity_5": b.impurity_5,
            "rrt_068": b.rrt_068,
            "unknown_max_single": b.unknown_max_single,
            "total_impurities": b.total_impurities,
            "purity": b.purity,
        }
        # 同样计算罐级 rowspan
        for tank in d["tanks"]:
            tank["rowspan"] = sum(
                len(extr.get("filtrates", []) or [])
                for extr in tank.get("extractions", [])
            )
        result.append(d)

    return success_response(result)


@router.get("/dr/extraction/years", summary="DR 萃取工段可用年份列表")
async def get_dr_extraction_years(
    workshop: str = Query("201-3"),
    session: AsyncSession = Depends(get_db),
):
    """返回发酵批次 tank_date 中出现过的年份（升序），供前端动态生成年份下拉框。"""
    q = (
        select(func.substr(DrFermentationBatch.tank_date, 1, 4).label("yr"))
        .where(
            DrFermentationBatch.is_deleted == False,
            DrFermentationBatch.workshop == workshop,
            DrFermentationBatch.tank_date.isnot(None),
        )
        .distinct()
    )
    rows = (await session.execute(q)).scalars().all()
    years = sorted({int(y) for y in rows if y and str(y).isdigit()})
    return success_response(years)


# ═══════════════════════════════════════════════════════
# 发酵批次 CRUD
# ═══════════════════════════════════════════════════════

@router.get("/dr/fermentation-batches", summary="DR 发酵批次列表")
async def list_dr_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    batch_no: str | None = Query(None),
    workshop: str = Query("201-3"),
    session: AsyncSession = Depends(get_db),
):
    query = select(DrFermentationBatch).where(
        DrFermentationBatch.is_deleted == False,
        DrFermentationBatch.workshop == workshop,
    )
    if batch_no:
        query = query.where(DrFermentationBatch.batch_no.ilike(f"%{batch_no}%"))
    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()
    rows = await session.execute(
        query.order_by(DrFermentationBatch.batch_no.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return paginated_response(
        [_clean_dict(r) for r in rows.scalars().all()], page, page_size, total
    )


@router.post("/dr/fermentation-batches", summary="创建 DR 发酵批次")
async def create_dr_batch(data: dict, session: AsyncSession = Depends(get_db)):
    record = DrFermentationBatch(**data)
    session.add(record)
    await session.commit()
    return success_response({"id": str(record.id), "batch_no": record.batch_no}, message="创建成功")


@router.put("/dr/fermentation-batches/{record_id}", summary="更新 DR 发酵批次")
async def update_dr_batch(record_id: UUID, data: dict, session: AsyncSession = Depends(get_db)):
    record = await session.get(DrFermentationBatch, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.items():
        setattr(record, k, v)
    await session.commit()
    return success_response({"id": str(record.id)}, message="更新成功")


@router.delete("/dr/fermentation-batches/{record_id}", summary="删除 DR 发酵批次")
async def delete_dr_batch(record_id: UUID, session: AsyncSession = Depends(get_db)):
    record = await session.get(DrFermentationBatch, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    record.is_deleted = True
    await session.commit()
    return success_response(None, message="删除成功")


# ═══════════════════════════════════════════════════════
# 发酵罐 CRUD
# ═══════════════════════════════════════════════════════

@router.get("/dr/fermentation-batches/{batch_id}/tanks", summary="某批次下的发酵罐列表")
async def list_dr_tanks(batch_id: str, session: AsyncSession = Depends(get_db)):
    query = select(DrFermentationTank).where(
        DrFermentationTank.is_deleted == False,
        DrFermentationTank.fermentation_batch_id == batch_id,
    ).order_by(DrFermentationTank.tank_no)
    rows = await session.execute(query)
    return success_response([_clean_dict(r) for r in rows.scalars().all()])


@router.post("/dr/fermentation-tanks", summary="添加发酵罐")
async def create_dr_tank(data: dict, session: AsyncSession = Depends(get_db)):
    record = DrFermentationTank(**data)
    session.add(record)
    await session.commit()
    return success_response({"id": str(record.id)}, message="添加成功")


@router.put("/dr/fermentation-tanks/{record_id}", summary="更新发酵罐")
async def update_dr_tank(record_id: UUID, data: dict, session: AsyncSession = Depends(get_db)):
    record = await session.get(DrFermentationTank, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.items():
        setattr(record, k, v)
    await session.commit()
    return success_response({"id": str(record.id)}, message="更新成功")


@router.delete("/dr/fermentation-tanks/{record_id}", summary="删除发酵罐")
async def delete_dr_tank(record_id: UUID, session: AsyncSession = Depends(get_db)):
    record = await session.get(DrFermentationTank, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    record.is_deleted = True
    await session.commit()
    return success_response(None, message="删除成功")


# ═══════════════════════════════════════════════════════
# 萃取批次 CRUD
# ═══════════════════════════════════════════════════════

@router.get("/dr/tanks/{tank_id}/extractions", summary="某罐下的萃取批次列表")
async def list_dr_extractions(tank_id: str, session: AsyncSession = Depends(get_db)):
    query = select(DrExtraction).where(
        DrExtraction.is_deleted == False,
        DrExtraction.fermentation_tank_id == tank_id,
    ).order_by(DrExtraction.extraction_batch_no)
    rows = await session.execute(query)
    return success_response([_clean_dict(r) for r in rows.scalars().all()])


@router.post("/dr/extractions", summary="添加萃取批次")
async def create_dr_extraction(data: dict, session: AsyncSession = Depends(get_db)):
    record = DrExtraction(**data)
    session.add(record)
    await session.commit()
    return success_response({"id": str(record.id)}, message="添加成功")


@router.put("/dr/extractions/{record_id}", summary="更新萃取批次")
async def update_dr_extraction(record_id: UUID, data: dict, session: AsyncSession = Depends(get_db)):
    record = await session.get(DrExtraction, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.items():
        setattr(record, k, v)
    await session.commit()
    return success_response({"id": str(record.id)}, message="更新成功")


@router.delete("/dr/extractions/{record_id}", summary="删除萃取批次")
async def delete_dr_extraction(record_id: UUID, session: AsyncSession = Depends(get_db)):
    record = await session.get(DrExtraction, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    record.is_deleted = True
    await session.commit()
    return success_response(None, message="删除成功")


# ═══════════════════════════════════════════════════════
# 滤液 CRUD
# ═══════════════════════════════════════════════════════

@router.get("/dr/extractions/{extraction_id}/filtrates", summary="某萃取批次下的滤液列表")
async def list_dr_filtrates(extraction_id: str, session: AsyncSession = Depends(get_db)):
    query = select(DrFiltrate).where(
        DrFiltrate.is_deleted == False,
        DrFiltrate.extraction_id == extraction_id,
    ).order_by(DrFiltrate.tank_no)
    rows = await session.execute(query)
    return success_response([_clean_dict(r) for r in rows.scalars().all()])


@router.post("/dr/filtrates", summary="添加滤液记录")
async def create_dr_filtrate(data: dict, session: AsyncSession = Depends(get_db)):
    record = DrFiltrate(**data)
    session.add(record)
    await session.commit()
    return success_response({"id": str(record.id)}, message="添加成功")


@router.put("/dr/filtrates/{record_id}", summary="更新滤液记录")
async def update_dr_filtrate(record_id: UUID, data: dict, session: AsyncSession = Depends(get_db)):
    record = await session.get(DrFiltrate, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.items():
        setattr(record, k, v)
    await session.commit()
    return success_response({"id": str(record.id)}, message="更新成功")


@router.delete("/dr/filtrates/{record_id}", summary="删除滤液记录")
async def delete_dr_filtrate(record_id: UUID, session: AsyncSession = Depends(get_db)):
    record = await session.get(DrFiltrate, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    record.is_deleted = True
    await session.commit()
    return success_response(None, message="删除成功")


# ═══════════════════════════════════════════════════════
# DR 仪表盘
# ═══════════════════════════════════════════════════════

@router.get("/dr/dashboard/summary", summary="DR 仪表盘汇总数据")
async def get_dr_dashboard(
    month: str = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    workshop: str = Query("201-3"),
    session: AsyncSession = Depends(get_db),
):
    if month is None:
        now = datetime.now()
        month = f"{now.year}-{now.month:02d}"

    parts = month.split("-")
    year, mon = int(parts[0]), int(parts[1])
    start_date = date(year, mon, 1)
    if mon == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, mon + 1, 1)

    # 各工段批次计数（全部返回0，等数据导入后再有真实值）
    stages = {
        "crude": 0,
        "extraction": 0,
        "refinement": 0,
        "blending": 0,
        "qc": 0,
        "ba": None,  # 丁酯用库存
    }

    # 发酵批次计数
    batch_count_q = select(func.count(DrFermentationBatch.id)).where(
        DrFermentationBatch.is_deleted == False,
        DrFermentationBatch.workshop == workshop,
        DrFermentationBatch.created_at >= start_date,
        DrFermentationBatch.created_at < end_date,
    )
    monthly_batches = (await session.execute(batch_count_q)).scalar_one()

    # 产量趋势（全年按月）
    monthly_trend = []
    for m in range(1, 13):
        m_start = date(year, m, 1)
        m_end = date(year, m + 1, 1) if m < 12 else date(year + 1, 1, 1)
        # 暂用批次计数代替产量，后续按实际业务调整
        q = select(func.count(DrFermentationBatch.id)).where(
            DrFermentationBatch.is_deleted == False,
            DrFermentationBatch.workshop == workshop,
            DrFermentationBatch.created_at >= m_start,
            DrFermentationBatch.created_at < m_end,
        )
        count = (await session.execute(q)).scalar_one()
        monthly_trend.append({"month": m, "output_kg": count * 0})  # 产量待填充

    return success_response({
        "_month": month,
        "stages": stages,
        "monthly_output_kg": 0.0,
        "monthly_batches": monthly_batches,
        "avg_yield": 0.0,
        "pass_rate": 0,
        "flow": [
            {"key": "crude", "label": "过滤萃取", "in_progress": 0},
            {"key": "extraction", "label": "层析及一次结晶", "in_progress": 0},
            {"key": "refinement", "label": "一次精制", "in_progress": 0},
            {"key": "blending", "label": "二次精制", "in_progress": 0},
            {"key": "qc", "label": "三次精制", "in_progress": 0},
        ],
        "monthly_trend": monthly_trend,
        "rrt_pass_rates": [],
        "status_distribution": [
            {"status": "进行中", "count": monthly_batches, "color": "#1677ff"},
            {"status": "已完成", "count": 0, "color": "#52c41a"},
            {"status": "待审核", "count": 0, "color": "#fa8c16"},
        ],
        "ba_stock_kg": 0,
        "ba_batches": 0,
        "ba_monthly_consume": 0,
    })


# ═══════════════════════════════════════════════════════
# 通用 DR 台账记录 API（供 DRTablePage 组件）
# ═══════════════════════════════════════════════════════

DR_TABLES = {
    "dr_chromatography_crystal": DrChromatographyCrystal,
    "dr_first_refinement": DrFirstRefinement,
    "dr_second_refinement": DrSecondRefinement,
    "dr_third_refinement": DrThirdRefinement,
    "dr_fourth_refinement": DrFourthRefinement,
}

# 各台账表的排序字段（保证前端合并单元格时相同组相邻）
DR_ORDER_BY = {
    "dr_chromatography_crystal": ["row_no"],
    "dr_first_refinement": ["row_no"],
    "dr_second_refinement": ["row_no"],
    "dr_third_refinement": ["row_no"],
    "dr_fourth_refinement": ["row_no"],
}


@router.get("/dr/records/years", summary="DR 台账可用年份列表")
async def get_dr_record_years(
    table: str = Query("dr_chromatography_crystal", description="表名"),
    session: AsyncSession = Depends(get_db),
):
    """返回台账表 production_date 中出现过的年份（升序），供前端动态生成年份下拉框。"""
    model = DR_TABLES.get(table)
    if not model:
        return success_response(None, message=f"未知表: {table}", status_code=400)
    if not hasattr(model, "production_date"):
        return success_response([])

    # 提取 production_date 前 4 位作为年份（格式 YYYY.MM.DD），过滤掉 '-' 等非日期值
    q = (
        select(func.substr(model.production_date, 1, 4).label("yr"))
        .where(model.is_deleted == False, model.production_date.isnot(None))
        .distinct()
    )
    rows = (await session.execute(q)).scalars().all()
    years = sorted({int(y) for y in rows if y and str(y).isdigit()})
    return success_response(years)


@router.get("/dr/records", summary="DR 通用台账记录查询")
async def get_dr_records(
    table: str = Query(..., description="表名，如 dr_chromatography_crystal"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=5000),
    year: int | None = Query(None, ge=2020, le=2099, description="按生产日期筛选年份"),
    month: int | None = Query(None, ge=1, le=12, description="按生产日期筛选月份"),
    session: AsyncSession = Depends(get_db),
):
    model = DR_TABLES.get(table)
    if not model:
        return success_response(None, message=f"未知表: {table}", status_code=400)

    base_query = select(model).where(model.is_deleted == False)

    # 按生产日期筛选（production_date 格式为 YYYY.MM.DD）
    if hasattr(model, "production_date"):
        if year is not None:
            base_query = base_query.where(model.production_date.like(f"{year}%"))
        if month is not None:
            base_query = base_query.where(model.production_date.like(f"%.{month:02d}.%"))

    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await session.execute(count_q)).scalar_one()

    query = base_query
    order_keys = DR_ORDER_BY.get(table)
    if order_keys:
        query = query.order_by(*[getattr(model, k) for k in order_keys])

    rows = await session.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    items = [_clean_dict(r) for r in rows.scalars().all()]

    return success_response({"items": items, "total": total})
