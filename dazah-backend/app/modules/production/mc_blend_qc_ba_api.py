"""MC 霉酚酸 — 混粉/QC检验/丁酯盘点 统一 API"""

from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.mc_blend_models import BlendingInput, BlendingRecord
from app.modules.production.mc_qc_ba_models import (
    ButylAcetateRecord,
    QcInspection,
    QcInspectionInput,
    QcInspectionItem,
)
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


# ── 辅助：清理 SQLAlchemy __dict__ 中的内部状态 ──
def _clean_dict(obj) -> dict:
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}


# ═══════════════════════════════════════════════════════
# 混粉主表 CRUD
# ═══════════════════════════════════════════════════════


@router.get("/mc/blending-records/full-list", summary="混粉台账完整数据（含投入明细）")
async def full_list_blending(
    workshop: str = Query("201-2"),
    month: int | None = Query(
        None, description="筛选月份 (1-12)，按批号 MC-YYMMxx 的 MM 位匹配"
    ),
    session: AsyncSession = Depends(get_db),
):
    """返回混粉记录+投入明细的嵌套结构"""
    from sqlalchemy import func as sa_func

    conditions = [
        BlendingRecord.is_deleted.is_(False),
        BlendingRecord.workshop == workshop,
    ]
    if month is not None and 1 <= month <= 12:
        month_str = f"{month:02d}"
        conditions.append(sa_func.substring(BlendingRecord.batch_no, 6, 2) == month_str)

    main_q = (
        select(BlendingRecord)
        .where(*conditions)
        .order_by(BlendingRecord.batch_no.asc())
    )
    main_rows = await session.execute(main_q)
    records = main_rows.scalars().all()

    batch_nos = [r.batch_no for r in records]
    result = []
    if batch_nos:
        inputs_q = (
            select(BlendingInput)
            .where(
                BlendingInput.is_deleted.is_(False),
                BlendingInput.blend_batch.in_(batch_nos),
            )
            .order_by(BlendingInput.blend_batch, BlendingInput.seq_no)
        )
        inputs_rows = await session.execute(inputs_q)
        all_inputs = inputs_rows.scalars().all()

        inputs_map: dict[str, list] = {}
        for inp in all_inputs:
            d = {k: v for k, v in inp.__dict__.items() if not k.startswith("_")}
            inputs_map.setdefault(inp.blend_batch, []).append(d)

        for record in records:
            d = {k: v for k, v in record.__dict__.items() if not k.startswith("_")}
            d["inputs"] = inputs_map.get(record.batch_no, [])
            result.append(d)

    return success_response(result)


@router.get("/mc/blending-records", summary="混粉记录列表")
async def list_blending(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    batch_no: str | None = Query(None),
    workshop: str = Query("201-2"),
    session: AsyncSession = Depends(get_db),
):
    query = select(BlendingRecord).where(
        BlendingRecord.is_deleted.is_(False), BlendingRecord.workshop == workshop
    )
    if batch_no:
        query = query.where(BlendingRecord.batch_no.ilike(f"%{batch_no}%"))
    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()
    rows = await session.execute(
        query.order_by(BlendingRecord.batch_no.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return paginated_response(
        [_clean_dict(r) for r in rows.scalars().all()], page, page_size, total
    )


@router.post("/mc/blending-records", summary="创建混粉记录")
async def create_blending(data: dict, session: AsyncSession = Depends(get_db)):
    record = BlendingRecord(**data)
    session.add(record)
    await session.commit()
    return success_response(
        {"id": str(record.id), "batch_no": record.batch_no}, message="创建成功"
    )


@router.put("/mc/blending-records/{record_id}", summary="更新混粉记录")
async def update_blending(
    record_id: UUID, data: dict, session: AsyncSession = Depends(get_db)
):
    record = await session.get(BlendingRecord, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.items():
        setattr(record, k, v)
    await session.commit()
    return success_response({"id": str(record.id)}, message="更新成功")


@router.delete("/mc/blending-records/{record_id}", summary="删除混粉记录")
async def delete_blending(record_id: UUID, session: AsyncSession = Depends(get_db)):
    record = await session.get(BlendingRecord, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    record.is_deleted = True
    await session.commit()
    return success_response(None, message="删除成功")


# ═══════════ 混粉投入明细 ═══════════


@router.get("/mc/blending-records/{batch_no}/inputs", summary="混粉投入明细")
async def list_blending_inputs(batch_no: str, session: AsyncSession = Depends(get_db)):
    query = select(BlendingInput).where(
        BlendingInput.is_deleted.is_(False), BlendingInput.blend_batch == batch_no
    )
    rows = await session.execute(query)
    return success_response([_clean_dict(r) for r in rows.scalars().all()])


@router.post("/mc/blending-inputs", summary="添加混粉投入")
async def create_blending_input(data: dict, session: AsyncSession = Depends(get_db)):
    record = BlendingInput(**data)
    session.add(record)
    await session.commit()
    return success_response({"id": str(record.id)}, message="添加成功")


@router.delete("/mc/blending-inputs/{record_id}", summary="删除混粉投入")
async def delete_blending_input(
    record_id: UUID, session: AsyncSession = Depends(get_db)
):
    record = await session.get(BlendingInput, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    record.is_deleted = True
    await session.commit()
    return success_response(None, message="删除成功")


# ═══════════ 混粉杂质加权计算 ═══════════


@router.post("/mc/blending-records/{batch_no}/calculate", summary="加权杂质计算")
async def calculate_blending_impurities(
    batch_no: str, session: AsyncSession = Depends(get_db)
):
    """根据投入明细计算加权平均杂质（5个RRT点位 + 总杂 + 含量）"""
    inputs_result = await session.execute(
        select(BlendingInput).where(
            BlendingInput.is_deleted.is_(False), BlendingInput.blend_batch == batch_no
        )
    )
    inputs = inputs_result.scalars().all()
    if not inputs:
        return success_response(None, message="没有投入明细", status_code=400)

    fields = [
        "rrt_053",
        "rrt_0755",
        "rrt_094_096",
        "rrt_103_106",
        "rrt_201",
        "total_impurity",
        "content",
    ]
    result = {}
    total_weight = sum(inp.input_weight for inp in inputs)

    for field in fields:
        weighted_sum = sum(
            (getattr(inp, field) or 0) * inp.input_weight for inp in inputs
        )
        result[field] = round(weighted_sum / total_weight, 4) if total_weight > 0 else 0

    # 更新主表计算结果
    main = await session.execute(
        select(BlendingRecord).where(
            BlendingRecord.batch_no == batch_no, BlendingRecord.is_deleted.is_(False)
        )
    )
    main = main.scalar_one_or_none()
    if main:
        for field, value in result.items():
            setattr(main, field, value)
        main.total_weight = total_weight
        if main.pack_spec:
            try:
                spec_kg = float(main.pack_spec.replace("kg", ""))
                main.barrel_count = (
                    int(main.total_weight / spec_kg)
                    + (1 if main.total_weight % spec_kg > 0 else 0)
                    if main.total_weight
                    else None
                )
            except Exception:
                pass
        main.status = 2  # 计算完成
        await session.commit()

    # 检查杂质超限警告
    limits = {
        "rrt_053": 0.05,
        "rrt_0755": 0.07,
        "rrt_094_096": 0.14,
        "rrt_103_106": 0.075,
        "rrt_201": 0.08,
        "total_impurity": 0.6,
    }
    warnings = {
        k: round(v, 4) for k, v in result.items() if k in limits and v > limits[k]
    }
    if result.get("content") and result["content"] < 99:
        warnings["content"] = round(result["content"], 2)

    return success_response(
        {"impurities": result, "total_weight": total_weight, "warnings": warnings}
    )


# ═══════════════════════════════════════════════════════
# QC检验 CRUD
# ═══════════════════════════════════════════════════════


@router.get("/mc/qc-inspections/full-list", summary="QC台账完整数据（含投入明细）")
async def full_list_qc(
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    """返回QC检验+投入明细的嵌套结构"""
    from sqlalchemy import extract

    main_q = select(QcInspection).where(
        QcInspection.is_deleted.is_(False),
    )
    if month is not None:
        main_q = main_q.where(extract("month", QcInspection.input_date) == month)
    main_q = main_q.order_by(QcInspection.input_date.asc().nulls_last())
    main_rows = await session.execute(main_q)
    records = main_rows.scalars().all()

    batch_nos = [r.batch_no for r in records]
    result = []
    if batch_nos:
        inputs_q = (
            select(QcInspectionInput)
            .where(
                QcInspectionInput.is_deleted.is_(False),
                QcInspectionInput.qc_batch.in_(batch_nos),
            )
            .order_by(QcInspectionInput.qc_batch, QcInspectionInput.input_batch)
        )
        inputs_rows = await session.execute(inputs_q)
        all_inputs = inputs_rows.scalars().all()

        inputs_map: dict[str, list] = {}
        for inp in all_inputs:
            d = {k: v for k, v in inp.__dict__.items() if not k.startswith("_")}
            inputs_map.setdefault(inp.qc_batch, []).append(d)

        for record in records:
            d = {k: v for k, v in record.__dict__.items() if not k.startswith("_")}
            d["inputs"] = inputs_map.get(record.batch_no, [])
            result.append(d)

    return success_response(result)


# QC投入明细
@router.get("/mc/qc-inputs/{qc_batch}", summary="QC投入明细列表")
async def list_qc_inputs(qc_batch: str, session: AsyncSession = Depends(get_db)):
    query = select(QcInspectionInput).where(
        QcInspectionInput.is_deleted.is_(False), QcInspectionInput.qc_batch == qc_batch
    )
    rows = await session.execute(query)
    return success_response(
        [
            {k: v for k, v in _clean_dict(r).items() if not k.startswith("_")}
            for r in rows.scalars().all()
        ]
    )


@router.post("/mc/qc-inputs", summary="添加QC投入明细")
async def create_qc_input(data: dict, session: AsyncSession = Depends(get_db)):
    record = QcInspectionInput(**data)
    session.add(record)
    await session.commit()
    return success_response({"id": str(record.id)}, message="添加成功")


@router.put("/mc/qc-inputs/{record_id}", summary="更新QC投入明细")
async def update_qc_input(
    record_id: UUID, data: dict, session: AsyncSession = Depends(get_db)
):
    record = await session.get(QcInspectionInput, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.items():
        setattr(record, k, v)
    await session.commit()
    return success_response({"id": str(record.id)}, message="更新成功")


@router.delete("/mc/qc-inputs/{record_id}", summary="删除QC投入明细")
async def delete_qc_input(record_id: UUID, session: AsyncSession = Depends(get_db)):
    record = await session.get(QcInspectionInput, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    record.is_deleted = True
    await session.commit()
    return success_response(None, message="删除成功")


@router.get("/mc/qc-inspections", summary="QC检验列表")
async def list_qc(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
):
    query = (
        select(QcInspection)
        .where(QcInspection.is_deleted.is_(False))
        .order_by(QcInspection.created_at.desc())
    )
    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()
    rows = await session.execute(query.offset((page - 1) * page_size).limit(page_size))
    return paginated_response(
        [_clean_dict(r) for r in rows.scalars().all()], page, page_size, total
    )


@router.post("/mc/qc-inspections", summary="创建QC检验单")
async def create_qc(data: dict, session: AsyncSession = Depends(get_db)):
    # 转换字符串日期
    for field in ("input_date", "blend_date"):
        if field in data and data[field] and isinstance(data[field], str):
            from datetime import date as dt_date

            data[field] = dt_date.fromisoformat(data[field])
    record = QcInspection(**data)
    session.add(record)
    await session.commit()
    return success_response({"qc_id": record.qc_id}, message="创建成功")


@router.put("/mc/qc-inspections/{record_id}", summary="更新QC检验单")
async def update_qc(
    record_id: UUID, data: dict, session: AsyncSession = Depends(get_db)
):
    record = await session.get(QcInspection, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for field in ("input_date", "blend_date"):
        if field in data and data[field] and isinstance(data[field], str):
            from datetime import date as dt_date

            data[field] = dt_date.fromisoformat(data[field])
    for k, v in data.items():
        setattr(record, k, v)
    await session.commit()
    return success_response({"qc_id": record.qc_id}, message="更新成功")


# QC检验明细
@router.get("/mc/qc-inspections/{qc_id}/items", summary="QC检验明细")
async def list_qc_items(qc_id: str, session: AsyncSession = Depends(get_db)):
    query = select(QcInspectionItem).where(
        QcInspectionItem.is_deleted.is_(False), QcInspectionItem.inspection_id == qc_id
    )
    rows = await session.execute(query)
    return success_response([_clean_dict(r) for r in rows.scalars().all()])


@router.post("/mc/qc-inspection-items", summary="添加QC检验项目")
async def create_qc_item(data: dict, session: AsyncSession = Depends(get_db)):
    item = QcInspectionItem(**data)
    # 自动计算偏差
    if item.theory_value is not None and item.actual_value is not None:
        item.deviation = round(item.actual_value - item.theory_value, 4)
    session.add(item)
    await session.commit()
    return success_response(
        {"id": str(item.id), "deviation": item.deviation, "is_blocked": item.is_blocked}
    )


# ═══════════════════════════════════════════════════════
# 丁酯台账（飞书同步交叉表）
# ═══════════════════════════════════════════════════════


@router.get("/mc/ba-records", summary="丁酯台账交叉表数据")
async def get_ba_records(session: AsyncSession = Depends(get_db)):
    """返回丁酯交叉表数据：日期列、设备行、消耗/入库值矩阵"""
    records = (
        (
            await session.execute(
                select(ButylAcetateRecord)
                .where(ButylAcetateRecord.is_deleted.is_(False))
                .order_by(ButylAcetateRecord.check_date, ButylAcetateRecord.equipment)
            )
        )
        .scalars()
        .all()
    )

    # 收集所有唯一日期和设备
    dates: list[str] = []
    seen_dates: set[str] = set()
    equipment_list: list[str] = []
    seen_eq: set[str] = set()

    for r in records:
        ds = r.check_date.isoformat()
        if ds not in seen_dates:
            seen_dates.add(ds)
            dates.append(ds)
        if r.equipment not in seen_eq:
            seen_eq.add(r.equipment)
            equipment_list.append(r.equipment)

    # 构建矩阵：{equipment: {date: consumption}}
    matrix: dict[str, dict[str, float | None]] = {eq: {} for eq in equipment_list}
    inbound: dict[str, float | None] = {}
    checks: dict[str, float | None] = {}
    for r in records:
        ds = r.check_date.isoformat()
        if r.is_check:
            checks[ds] = r.consumption
        elif r.is_inbound:
            inbound[ds] = r.consumption
        else:
            matrix[r.equipment][ds] = r.consumption

    return success_response(
        {
            "dates": dates,
            "equipment": equipment_list,
            "matrix": matrix,
            "inbound": inbound,
            "checks": checks,
        }
    )
