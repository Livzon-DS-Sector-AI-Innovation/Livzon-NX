"""二次板框过滤 API"""

from datetime import datetime as dt
from uuid import UUID

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.filter2_models import Filter2
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


class CD(BaseModel):
    seq_no: int | None = None
    batch_no: str
    feed_volume: str | None = None
    filter_pressure: float | None = None
    filter_duration: float | None = None
    cloth_type: str | None = None
    cake_wet_weight: str | None = None
    cake_dry_weight: str | None = None
    crystal_purity: float | None = None
    crystal_titer: float | None = None
    filtrate_volume: str | None = None
    mother_liquor_titer: float | None = None
    wash_water: str | None = None
    combined_liquor: str | None = None
    wash_loss: float | None = None
    remarks: str | None = None


class RD(BaseModel):
    id: UUID
    seq_no: int | None = None
    batch_no: str
    feed_volume: str | None = None
    filter_pressure: float | None = None
    filter_duration: float | None = None
    cloth_type: str | None = None
    cake_wet_weight: str | None = None
    cake_dry_weight: str | None = None
    crystal_purity: float | None = None
    crystal_titer: float | None = None
    filtrate_volume: str | None = None
    mother_liquor_titer: float | None = None
    wash_water: str | None = None
    combined_liquor: str | None = None
    wash_loss: float | None = None
    remarks: str | None = None
    created_at: dt
    updated_at: dt
    model_config = {"from_attributes": True}


@router.get("/filter2", summary="二次板框过滤列表")
async def _list(
    page: int = Query(1, ge=1),
    ps: int = Query(20, ge=1, le=200),
    s: str | None = Query(None, alias="batch_no"),
    workshop: str = Query("203"),
    session: AsyncSession = Depends(get_db),
):
    q = select(Filter2).where(Filter2.is_deleted.is_(False), Filter2.workshop == workshop)  # noqa: E501
    if s:
        q = q.where(Filter2.batch_no.ilike(f"%{s}%"))
    total = (
        await session.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = await session.execute(
        q.order_by(Filter2.seq_no.asc()).offset((page - 1) * ps).limit(ps)
    )
    return paginated_response(
        [RD.model_validate(r) for r in rows.scalars().all()], page, ps, total
    )


@router.post("/filter2", summary="创建二次板框过滤")
async def _create(d: CD, session: AsyncSession = Depends(get_db)):
    r = Filter2(**d.model_dump())
    session.add(r)
    await session.flush()
    await session.commit()
    await session.refresh(r)
    return success_response(RD.model_validate(r), message="创建成功")


@router.put("/filter2/{rid}", summary="更新二次板框过滤")
async def _update(rid: UUID, d: CD, session: AsyncSession = Depends(get_db)):
    r = await session.get(Filter2, rid)
    if not r or r.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in d.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    await session.flush()
    return success_response(RD.model_validate(r), message="更新成功")


@router.delete("/filter2/{rid}", summary="删除二次板框过滤")
async def _delete(rid: UUID, session: AsyncSession = Depends(get_db)):
    r = await session.get(Filter2, rid)
    if not r:
        return success_response(None, message="记录不存在", status_code=404)
    r.is_deleted = True
    await session.flush()
    return success_response(None, message="删除成功")
