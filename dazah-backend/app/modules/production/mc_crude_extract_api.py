"""MC 霉酚酸 — 粗提工段 API（发酵液→提炼→分罐→钠化/酸化→粗品）"""

from typing import Any
from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.production.mc_crude_extract_models import (
    FermentationLiquid,
    RefiningBatch,
    SubTankAcidStep,
    SubTankRecord,
    SubTankSodiumStep,
)
from app.modules.production.mc_crude_extract_schemas import (
    AcidStepCreate,
    AcidStepResponse,
    FermentationLiquidCreate,
    FermentationLiquidResponse,
    RefiningBatchCreate,
    RefiningBatchResponse,
    SodiumStepCreate,
    SodiumStepResponse,
    SubTankRecordResponse,
    SubTankRecordUpdate,
)
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


# ═══════════ full-list（嵌套结构）═══════════


@router.get("/mc/crude-extract/full-list", summary="粗提台账完整嵌套数据")
async def full_list(
    workshop: str = Query("201-2"),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
) -> Any:
    # 1. 发酵液
    fl_q = (
        select(FermentationLiquid)
        .where(FermentationLiquid.is_deleted.is_(False))
        .order_by(FermentationLiquid.create_date.asc().nulls_last())
    )
    fl_rows = (await session.execute(fl_q)).scalars().all()
    fl_map = {fl.batch_no: fl for fl in fl_rows}

    # 2. 提炼批次
    rb_q = select(RefiningBatch).where(
        RefiningBatch.is_deleted.is_(False), RefiningBatch.workshop == workshop
    )
    if month is not None:
        rb_q = rb_q.where(RefiningBatch.month == month)
    rb_q = rb_q.order_by(RefiningBatch.produce_date.asc().nulls_last())
    rb_rows = (await session.execute(rb_q)).scalars().all()

    if not rb_rows:
        return success_response([])

    # 3. 分罐
    parent_batches = [rb.batch_no for rb in rb_rows]
    st_q = (
        select(SubTankRecord)
        .where(
            SubTankRecord.is_deleted.is_(False),
            SubTankRecord.parent_batch.in_(parent_batches),
        )
        .order_by(SubTankRecord.parent_batch, SubTankRecord.tank_no)
    )
    st_rows = (await session.execute(st_q)).scalars().all()
    st_by_parent: dict[str, list[Any]] = {}
    st_ids = []
    for st in st_rows:
        st_by_parent.setdefault(st.parent_batch, []).append(st)
        st_ids.append(st.batch_no)

    # 4. 钠化
    sodium_map: dict[str, list[Any]] = {}
    if st_ids:
        na_q = (
            select(SubTankSodiumStep)
            .where(
                SubTankSodiumStep.is_deleted.is_(False),
                SubTankSodiumStep.sub_tank_id.in_(st_ids),
            )
            .order_by(SubTankSodiumStep.sub_tank_id, SubTankSodiumStep.seq_no)
        )
        for na in (await session.execute(na_q)).scalars().all():
            sodium_map.setdefault(na.sub_tank_id, []).append(
                SodiumStepResponse.model_validate(na).model_dump()
            )

    # 5. 酸化
    acid_map: dict[str, list[Any]] = {}
    if st_ids:
        ac_q = (
            select(SubTankAcidStep)
            .where(
                SubTankAcidStep.is_deleted.is_(False),
                SubTankAcidStep.sub_tank_id.in_(st_ids),
            )
            .order_by(SubTankAcidStep.sub_tank_id, SubTankAcidStep.seq_no)
        )
        for ac in (await session.execute(ac_q)).scalars().all():
            acid_map.setdefault(ac.sub_tank_id, []).append(
                AcidStepResponse.model_validate(ac).model_dump()
            )

    # 组装
    result = []
    for rb in rb_rows:
        fl = fl_map.get(rb.fermentation_no)
        sub_tanks = []
        for st in st_by_parent.get(rb.batch_no, []):
            sub_tanks.append(
                {
                    "sub_tank": SubTankRecordResponse.model_validate(st).model_dump(),
                    "sodium_steps": sodium_map.get(st.batch_no, []),
                    "acid_steps": acid_map.get(st.batch_no, []),
                }
            )
        result.append(
            {
                "fermentation": FermentationLiquidResponse.model_validate(
                    fl
                ).model_dump()
                if fl
                else None,
                "refining": RefiningBatchResponse.model_validate(rb).model_dump(),
                "sub_tanks": sub_tanks,
            }
        )

    return success_response(result)


# ═══════════ 发酵液 CRUD ═══════════


@router.get("/mc/crude-extract/fermentation-liquids", summary="发酵液列表")
async def list_fl(
    page_size: int = Query(200, ge=1), session: AsyncSession = Depends(get_db)
) -> Any:
    q = (
        select(FermentationLiquid)
        .where(FermentationLiquid.is_deleted.is_(False))
        .order_by(FermentationLiquid.create_date.desc().nulls_last())
        .limit(page_size)
    )
    rows = (await session.execute(q)).scalars().all()
    return success_response(
        [FermentationLiquidResponse.model_validate(r).model_dump() for r in rows]
    )


@router.post("/mc/crude-extract/fermentation-liquids", summary="创建发酵液")
async def create_fl(
    data: FermentationLiquidCreate, session: AsyncSession = Depends(get_db)
) -> Any:
    record = FermentationLiquid(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.commit()
    return success_response(
        FermentationLiquidResponse.model_validate(record).model_dump(),
        message="创建成功",
    )


# ═══════════ 提炼批次 ═══════════


@router.post(
    "/mc/crude-extract/refining-batches", summary="创建提炼批次（自动创建分罐-1/-2）"
)
async def create_rb(
    data: RefiningBatchCreate, session: AsyncSession = Depends(get_db)
) -> Any:
    record = RefiningBatch(**data.model_dump())
    session.add(record)
    # 自动创建两个分罐
    for tank_no in [1, 2]:
        st = SubTankRecord(
            parent_batch=data.batch_no,
            tank_no=tank_no,
            batch_no=f"{data.batch_no}-{tank_no}",
        )
        session.add(st)
    await session.flush()
    await session.commit()
    return success_response(
        RefiningBatchResponse.model_validate(record).model_dump(), message="创建成功"
    )


@router.delete("/mc/crude-extract/refining-batches/{record_id}", summary="删除提炼批次")
async def delete_rb(record_id: UUID, session: AsyncSession = Depends(get_db)) -> Any:
    rb = await session.get(RefiningBatch, record_id)
    if not rb:
        return success_response(None, message="记录不存在", status_code=404)
    # 级联删除分罐 + 钠化 + 酸化
    sts = (
        (
            await session.execute(
                select(SubTankRecord).where(
                    SubTankRecord.parent_batch == rb.batch_no,
                    SubTankRecord.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    st_ids = [st.batch_no for st in sts]
    for st in sts:
        st.is_deleted = True
    if st_ids:
        for m in [SubTankSodiumStep, SubTankAcidStep]:
            steps = (
                (
                    await session.execute(
                        select(m).where(
                            getattr(m, "sub_tank_id").in_(st_ids),
                            m.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for s in steps:
                s.is_deleted = True
    rb.is_deleted = True
    await session.flush()
    return success_response(None, message="删除成功")


# ═══════════ 分罐 CRUD ═══════════


@router.put("/mc/crude-extract/sub-tank-records/{record_id}", summary="更新分罐记录")
async def update_st(
    record_id: UUID, data: SubTankRecordUpdate, session: AsyncSession = Depends(get_db)
) -> Any:
    record = await session.get(SubTankRecord, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    await session.flush()
    return success_response({"id": str(record.id)}, message="更新成功")


# ═══════════ 钠化步骤 CRUD ═══════════


@router.post("/mc/crude-extract/sodium-steps", summary="添加钠化步骤")
async def create_sodium(
    data: SodiumStepCreate, session: AsyncSession = Depends(get_db)
) -> Any:
    record = SubTankSodiumStep(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.commit()
    return success_response(
        SodiumStepResponse.model_validate(record).model_dump(), message="添加成功"
    )


@router.put("/mc/crude-extract/sodium-steps/{record_id}", summary="更新钠化步骤")
async def update_sodium(
    record_id: UUID, data: dict[str, Any], session: AsyncSession = Depends(get_db)
) -> Any:
    record = await session.get(SubTankSodiumStep, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.items():
        setattr(record, k, v)
    await session.flush()
    return success_response({"id": str(record.id)}, message="更新成功")


# ═══════════ 酸化步骤 CRUD ═══════════


@router.post("/mc/crude-extract/acid-steps", summary="添加酸化步骤")
async def create_acid(
    data: AcidStepCreate, session: AsyncSession = Depends(get_db)
) -> Any:
    record = SubTankAcidStep(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.commit()
    return success_response(
        AcidStepResponse.model_validate(record).model_dump(), message="添加成功"
    )


@router.put("/mc/crude-extract/acid-steps/{record_id}", summary="更新酸化步骤")
async def update_acid(
    record_id: UUID, data: dict[str, Any], session: AsyncSession = Depends(get_db)
) -> Any:
    record = await session.get(SubTankAcidStep, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.items():
        setattr(record, k, v)
    await session.flush()
    return success_response({"id": str(record.id)}, message="更新成功")
