"""MC 霉酚酸 — MC 二次精制工段 API（湿粉→二次结晶→干粉 MC-F2）"""

from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.mc_refinement_models import (
    McRefinementInput,
    McRefinementRecord,
)
from app.modules.production.mc_refinement_schemas import (
    McRefinementInputCreate,
    McRefinementInputResponse,
    McRefinementInputUpdate,
    McRefinementRecordCreate,
    McRefinementRecordResponse,
    McRefinementRecordUpdate,
)
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])

# ═══════════ 二次精制主表 CRUD ═══════════


@router.get(
    "/mc/refinement-records/full-list", summary="MC精制台账完整数据（含投入明细）"
)
async def full_list_mc_refinement_records(
    workshop: str = Query("201-2"),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    """返回MC精制记录+投入明细的嵌套结构，用于台账页面"""
    from sqlalchemy import extract

    main_q = select(McRefinementRecord).where(
        McRefinementRecord.is_deleted.is_(False),
        McRefinementRecord.workshop == workshop,
    )
    if month is not None:
        main_q = main_q.where(extract("month", McRefinementRecord.input_date) == month)
    main_q = main_q.order_by(McRefinementRecord.input_date.asc().nulls_last())
    main_rows = await session.execute(main_q)
    records = main_rows.scalars().all()

    batch_nos = [r.batch_no for r in records]
    result = []
    if batch_nos:
        inputs_q = (
            select(McRefinementInput)
            .where(
                McRefinementInput.is_deleted.is_(False),
                McRefinementInput.refinement_batch.in_(batch_nos),
            )
            .order_by(
                McRefinementInput.refinement_batch, McRefinementInput.wet_batch_no
            )
        )
        inputs_rows = await session.execute(inputs_q)
        all_inputs = inputs_rows.scalars().all()

        inputs_map: dict[str, list] = {}
        for inp in all_inputs:
            inputs_map.setdefault(inp.refinement_batch, []).append(
                McRefinementInputResponse.model_validate(inp).model_dump()
            )

        for record in records:
            d = McRefinementRecordResponse.model_validate(record).model_dump()
            d["inputs"] = inputs_map.get(record.batch_no, [])
            result.append(d)

    return success_response(result)


@router.get("/mc/refinement-records", summary="MC二次精制记录列表")
async def list_mc_refinement_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    batch_no: str | None = Query(None),
    workshop: str = Query("201-2"),
    session: AsyncSession = Depends(get_db),
):
    query = select(McRefinementRecord).where(
        McRefinementRecord.is_deleted.is_(False),
        McRefinementRecord.workshop == workshop,
    )
    if batch_no:
        query = query.where(McRefinementRecord.batch_no.ilike(f"%{batch_no}%"))
    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()
    query = query.order_by(McRefinementRecord.input_date.desc().nulls_last())
    rows = await session.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [McRefinementRecordResponse.model_validate(r) for r in rows.scalars().all()]
    return paginated_response(items, page, page_size, total)


@router.post("/mc/refinement-records", summary="创建MC二次精制记录")
async def create_mc_refinement_record(
    data: McRefinementRecordCreate,
    session: AsyncSession = Depends(get_db),
):
    record = McRefinementRecord(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.commit()
    await session.refresh(record)
    return success_response(
        McRefinementRecordResponse.model_validate(record), message="创建成功"
    )


@router.put("/mc/refinement-records/{record_id}", summary="更新MC二次精制记录")
async def update_mc_refinement_record(
    record_id: UUID,
    data: McRefinementRecordUpdate,
    session: AsyncSession = Depends(get_db),
):
    record = await session.get(McRefinementRecord, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    await session.flush()
    return success_response(
        McRefinementRecordResponse.model_validate(record), message="更新成功"
    )


@router.delete("/mc/refinement-records/{record_id}", summary="删除MC二次精制记录")
async def delete_mc_refinement_record(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    record = await session.get(McRefinementRecord, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    inputs = await session.execute(
        select(McRefinementInput).where(
            McRefinementInput.refinement_batch == record.batch_no,
            McRefinementInput.is_deleted.is_(False),
        )
    )
    for inp in inputs.scalars().all():
        inp.is_deleted = True
    record.is_deleted = True
    await session.flush()
    return success_response(None, message="删除成功")


# ═══════════ 二次精制投入明细 CRUD ═══════════


@router.get("/mc/refinement-records/{batch_no}/inputs", summary="MC精制投入明细列表")
async def list_mc_refinement_inputs(
    batch_no: str,
    session: AsyncSession = Depends(get_db),
):
    query = select(McRefinementInput).where(
        McRefinementInput.is_deleted.is_(False),
        McRefinementInput.refinement_batch == batch_no,
    )
    rows = await session.execute(query)
    items = [McRefinementInputResponse.model_validate(r) for r in rows.scalars().all()]
    return success_response(items)


@router.post("/mc/refinement-inputs", summary="添加MC精制投入明细")
async def create_mc_refinement_input(
    data: McRefinementInputCreate,
    session: AsyncSession = Depends(get_db),
):
    record = McRefinementInput(**data.model_dump())
    session.add(record)
    await session.flush()
    await _recalc_refinement_totals(data.refinement_batch, session)
    await session.commit()
    await session.refresh(record)
    return success_response(
        McRefinementInputResponse.model_validate(record), message="添加成功"
    )


@router.put("/mc/refinement-inputs/{record_id}", summary="更新MC精制投入明细")
async def update_mc_refinement_input(
    record_id: UUID,
    data: McRefinementInputUpdate,
    session: AsyncSession = Depends(get_db),
):
    record = await session.get(McRefinementInput, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    old_batch = record.refinement_batch
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    await _recalc_refinement_totals(old_batch, session)
    await session.flush()
    return success_response(
        McRefinementInputResponse.model_validate(record), message="更新成功"
    )


@router.delete("/mc/refinement-inputs/{record_id}", summary="删除MC精制投入明细")
async def delete_mc_refinement_input(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    record = await session.get(McRefinementInput, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    batch = record.refinement_batch
    record.is_deleted = True
    await _recalc_refinement_totals(batch, session)
    await session.flush()
    return success_response(None, message="删除成功")


async def _recalc_refinement_totals(refinement_batch: str, session: AsyncSession):
    """重新计算主表的投入汇总和收率"""
    inputs_result = await session.execute(
        select(McRefinementInput).where(
            McRefinementInput.is_deleted.is_(False),
            McRefinementInput.refinement_batch == refinement_batch,
        )
    )
    inputs = inputs_result.scalars().all()

    total_input_weight = 0.0
    total_pure_qty = 0.0
    for inp in inputs:
        total_input_weight += inp.input_weight or 0
        pure = inp.pure_qty or (
            inp.input_weight * (1 - inp.moisture / 100) * inp.content / 100
        )
        total_pure_qty += pure

    main_result = await session.execute(
        select(McRefinementRecord).where(
            McRefinementRecord.batch_no == refinement_batch,
            McRefinementRecord.is_deleted.is_(False),
        )
    )
    main = main_result.scalar_one_or_none()
    if main:
        main.total_input_weight = total_input_weight
        main.total_pure_qty = total_pure_qty
        if main.dry_weight and total_pure_qty and total_pure_qty > 0:
            main.single_step_yield = round(main.dry_weight / total_pure_qty * 100, 2)
