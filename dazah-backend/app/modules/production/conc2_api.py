"""二次浓缩 API"""

from datetime import datetime as dt
from uuid import UUID

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.conc2_models import Conc2
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


class CD(BaseModel):
    seq_no: int | None = None
    batch_no: str
    feed_volume: str | None = None
    vacuum_degree: float | None = None
    evap_temp: float | None = None
    steam_pressure: float | None = None
    endpoint_refraction: float | None = None
    endpoint_density: float | None = None
    conc_volume: str | None = None
    conc_titer: float | None = None
    conc_factor: float | None = None
    condensate_volume: str | None = None
    bottom_residue: str | None = None
    evap_loss_rate: float | None = None
    conc_yield: float | None = None
    remarks: str | None = None


class RD(BaseModel):
    id: UUID
    seq_no: int | None = None
    batch_no: str
    feed_volume: str | None = None
    vacuum_degree: float | None = None
    evap_temp: float | None = None
    steam_pressure: float | None = None
    endpoint_refraction: float | None = None
    endpoint_density: float | None = None
    conc_volume: str | None = None
    conc_titer: float | None = None
    conc_factor: float | None = None
    condensate_volume: str | None = None
    bottom_residue: str | None = None
    evap_loss_rate: float | None = None
    conc_yield: float | None = None
    remarks: str | None = None
    created_at: dt
    updated_at: dt
    model_config = {"from_attributes": True}


@router.get("/conc2", summary="二次浓缩列表")
async def _list(
    page: int = Query(1, ge=1),
    ps: int = Query(20, ge=1, le=200),
    s: str | None = Query(None, alias="batch_no"),
    workshop: str = Query("203"),
    session: AsyncSession = Depends(get_db),
):
    q = select(Conc2).where(not Conc2.is_deleted, Conc2.workshop == workshop)
    if s:
        q = q.where(Conc2.batch_no.ilike(f"%{s}%"))
    total = (
        await session.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = await session.execute(
        q.order_by(Conc2.seq_no.asc()).offset((page - 1) * ps).limit(ps)
    )
    return paginated_response(
        [RD.model_validate(r) for r in rows.scalars().all()], page, ps, total
    )


@router.post("/conc2", summary="创建二次浓缩")
async def _create(d: CD, session: AsyncSession = Depends(get_db)):
    r = Conc2(**d.model_dump())
    session.add(r)
    await session.flush()
    await session.commit()
    await session.refresh(r)
    return success_response(RD.model_validate(r), message="创建成功")


@router.put("/conc2/{rid}", summary="更新二次浓缩")
async def _update(rid: UUID, d: CD, session: AsyncSession = Depends(get_db)):
    r = await session.get(Conc2, rid)
    if not r or r.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in d.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    await session.flush()
    return success_response(RD.model_validate(r), message="更新成功")


@router.delete("/conc2/{rid}", summary="删除二次浓缩")
async def _delete(rid: UUID, session: AsyncSession = Depends(get_db)):
    r = await session.get(Conc2, rid)
    if not r:
        return success_response(None, message="记录不存在", status_code=404)
    r.is_deleted = True
    await session.flush()
    return success_response(None, message="删除成功")
