"""MC 霉酚酸 — 提取工段 API（粗品→萃取→湿粉）"""

from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.mc_extraction_models import (
    ExtractionInput,
    ExtractionRecord,
)
from app.modules.production.mc_extraction_schemas import (
    ExtractionInputCreate,
    ExtractionInputResponse,
    ExtractionInputUpdate,
    ExtractionRecordCreate,
    ExtractionRecordResponse,
    ExtractionRecordUpdate,
)
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])

# ═══════════ 提取主表 CRUD ═══════════


@router.get(
    "/mc/extraction-records/full-list", summary="提取台账完整数据（含投入明细）"
)
async def full_list_extraction_records(
    workshop: str = Query("201-2"),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
):
    """返回提取记录+投入明细的嵌套结构，用于台账页面"""
    from sqlalchemy import extract

    main_q = select(ExtractionRecord).where(
        ExtractionRecord.is_deleted.is_(False),
        ExtractionRecord.workshop == workshop,
    )
    if month is not None:
        main_q = main_q.where(extract("month", ExtractionRecord.extract_date) == month)
    main_q = main_q.order_by(ExtractionRecord.extract_date.asc().nulls_last())
    main_rows = await session.execute(main_q)
    records = main_rows.scalars().all()

    # 一次查询所有投入明细
    batch_nos = [r.batch_no for r in records]
    result = []
    if batch_nos:
        inputs_q = (
            select(ExtractionInput)
            .where(
                ExtractionInput.is_deleted.is_(False),
                ExtractionInput.extraction_batch.in_(batch_nos),
            )
            .order_by(ExtractionInput.extraction_batch, ExtractionInput.seq_no)
        )
        inputs_rows = await session.execute(inputs_q)
        all_inputs = inputs_rows.scalars().all()

        # 按 batch_no 分组
        inputs_map: dict[str, list] = {}
        for inp in all_inputs:
            inputs_map.setdefault(inp.extraction_batch, []).append(
                ExtractionInputResponse.model_validate(inp).model_dump()
            )

        for record in records:
            d = ExtractionRecordResponse.model_validate(record).model_dump()
            d["inputs"] = inputs_map.get(record.batch_no, [])
            result.append(d)

    return success_response(result)


@router.get("/mc/extraction-records", summary="提取记录列表")
async def list_extraction_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    batch_no: str | None = Query(None),
    workshop: str = Query("201-2"),
    session: AsyncSession = Depends(get_db),
):
    query = select(ExtractionRecord).where(
        ExtractionRecord.is_deleted.is_(False),
        ExtractionRecord.workshop == workshop,
    )
    if batch_no:
        query = query.where(ExtractionRecord.batch_no.ilike(f"%{batch_no}%"))
    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()
    query = query.order_by(ExtractionRecord.extract_date.desc().nulls_last())
    rows = await session.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [ExtractionRecordResponse.model_validate(r) for r in rows.scalars().all()]
    return paginated_response(items, page, page_size, total)


@router.post("/mc/extraction-records", summary="创建提取记录")
async def create_extraction_record(
    data: ExtractionRecordCreate,
    session: AsyncSession = Depends(get_db),
):
    record = ExtractionRecord(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.commit()
    await session.refresh(record)
    return success_response(
        ExtractionRecordResponse.model_validate(record), message="创建成功"
    )


@router.put("/mc/extraction-records/{record_id}", summary="更新提取记录")
async def update_extraction_record(
    record_id: UUID,
    data: ExtractionRecordUpdate,
    session: AsyncSession = Depends(get_db),
):
    record = await session.get(ExtractionRecord, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    await session.flush()
    return success_response(
        ExtractionRecordResponse.model_validate(record), message="更新成功"
    )


@router.delete("/mc/extraction-records/{record_id}", summary="删除提取记录")
async def delete_extraction_record(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    record = await session.get(ExtractionRecord, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    # 同步软删除投入明细
    inputs = await session.execute(
        select(ExtractionInput).where(
            ExtractionInput.extraction_batch == record.batch_no,
            ExtractionInput.is_deleted.is_(False),
        )
    )
    for inp in inputs.scalars().all():
        inp.is_deleted = True
    record.is_deleted = True
    await session.flush()
    return success_response(None, message="删除成功")


# ═══════════ 提取投入明细 CRUD ═══════════


@router.get("/mc/extraction-records/{batch_no}/inputs", summary="提取投入明细列表")
async def list_extraction_inputs(
    batch_no: str,
    session: AsyncSession = Depends(get_db),
):
    query = (
        select(ExtractionInput)
        .where(
            ExtractionInput.is_deleted.is_(False),
            ExtractionInput.extraction_batch == batch_no,
        )
        .order_by(ExtractionInput.seq_no)
    )
    rows = await session.execute(query)
    items = [ExtractionInputResponse.model_validate(r) for r in rows.scalars().all()]
    return success_response(items)


@router.post("/mc/extraction-inputs", summary="添加提取投入明细")
async def create_extraction_input(
    data: ExtractionInputCreate,
    session: AsyncSession = Depends(get_db),
):
    record = ExtractionInput(**data.model_dump())
    session.add(record)
    await session.flush()
    # 自动更新主表汇总
    await _recalc_extraction_totals(data.extraction_batch, session)
    await session.commit()
    await session.refresh(record)
    return success_response(
        ExtractionInputResponse.model_validate(record), message="添加成功"
    )


@router.put("/mc/extraction-inputs/{record_id}", summary="更新提取投入明细")
async def update_extraction_input(
    record_id: UUID,
    data: ExtractionInputUpdate,
    session: AsyncSession = Depends(get_db),
):
    record = await session.get(ExtractionInput, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    old_batch = record.extraction_batch
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    await _recalc_extraction_totals(old_batch, session)
    await session.flush()
    return success_response(
        ExtractionInputResponse.model_validate(record), message="更新成功"
    )


@router.delete("/mc/extraction-inputs/{record_id}", summary="删除提取投入明细")
async def delete_extraction_input(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    record = await session.get(ExtractionInput, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    batch = record.extraction_batch
    record.is_deleted = True
    await _recalc_extraction_totals(batch, session)
    await session.flush()
    return success_response(None, message="删除成功")


async def _recalc_extraction_totals(extraction_batch: str, session: AsyncSession):
    """重新计算主表的投入汇总"""
    inputs_result = await session.execute(
        select(ExtractionInput).where(
            ExtractionInput.is_deleted.is_(False),
            ExtractionInput.extraction_batch == extraction_batch,
        )
    )
    inputs = inputs_result.scalars().all()

    total_crude_weight = 0.0
    total_converted_qty = 0.0
    for inp in inputs:
        total_crude_weight += inp.crude_weight or 0
        converted = inp.converted_qty or (
            inp.crude_weight * (1 - inp.crude_moisture / 100) * inp.crude_content / 100
        )
        total_converted_qty += converted

    main_result = await session.execute(
        select(ExtractionRecord).where(
            ExtractionRecord.batch_no == extraction_batch,
            ExtractionRecord.is_deleted.is_(False),
        )
    )
    main = main_result.scalar_one_or_none()
    if main:
        main.total_crude_weight = total_crude_weight
        main.total_converted_qty = total_converted_qty
        # 自动计算收率
        if main.dry_weight and total_converted_qty and total_converted_qty > 0:
            main.yield_rate = round(main.dry_weight / total_converted_qty * 100, 2)
