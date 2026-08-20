"""陶瓷膜过滤 5表 API — 匹配飞书字段结构"""

from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.ceramic_models import (
    CeramicEquipmentLog,
    CeramicFeed,
    CeramicMaterialSeparation,
    CeramicMembraneClean,
    CeramicMembraneOps,
)
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])
from datetime import date  # noqa: E402
from datetime import datetime as dt  # noqa: E402

from pydantic import BaseModel  # noqa: E402


class R(BaseModel):
    id: UUID
    created_at: dt
    updated_at: dt
    model_config = {"from_attributes": True}


class C0(BaseModel):
    seq_no: int | None = None
    feed_date: date | None = None
    batch_no: str
    feed_volume: float | None = None
    feed_concentration: float | None = None
    feed_temp: float | None = None
    ph_value: float | None = None
    tank_no: str | None = None
    material_name: str | None = None
    operator: str | None = None
    remarks: str | None = None


class R0(R):
    seq_no: int | None = None
    feed_date: date | None = None
    batch_no: str
    feed_volume: float | None = None
    feed_concentration: float | None = None
    feed_temp: float | None = None
    ph_value: float | None = None
    tank_no: str | None = None
    material_name: str | None = None
    operator: str | None = None
    remarks: str | None = None


class C1(BaseModel):
    seq_no: int | None = None
    clean_date: date | None = None
    membrane_no: str | None = None
    cleaner_type: str | None = None
    cleaner_concentration: float | None = None
    clean_temp: float | None = None
    clean_time: float | None = None
    clean_pressure: float | None = None
    flux_recovery: float | None = None
    operator: str | None = None
    remarks: str | None = None


class R1(R):
    seq_no: int | None = None
    clean_date: date | None = None
    membrane_no: str | None = None
    cleaner_type: str | None = None
    cleaner_concentration: float | None = None
    clean_temp: float | None = None
    clean_time: float | None = None
    clean_pressure: float | None = None
    flux_recovery: float | None = None
    operator: str | None = None
    remarks: str | None = None


class C2(BaseModel):
    seq_no: int | None = None
    run_date: date | None = None
    batch_no: str
    membrane_no: str | None = None
    run_pressure: float | None = None
    membrane_velocity: float | None = None
    tmp: float | None = None
    run_temp: float | None = None
    permeate_flux: float | None = None
    operator: str | None = None
    remarks: str | None = None


class R2(R):
    seq_no: int | None = None
    run_date: date | None = None
    batch_no: str
    membrane_no: str | None = None
    run_pressure: float | None = None
    membrane_velocity: float | None = None
    tmp: float | None = None
    run_temp: float | None = None
    permeate_flux: float | None = None
    operator: str | None = None
    remarks: str | None = None


class C3(BaseModel):
    seq_no: int | None = None
    record_date: date | None = None
    equipment_no: str | None = None
    run_status: str | None = None
    abnormal_type: str | None = None
    abnormal_desc: str | None = None
    action_taken: str | None = None
    action_result: str | None = None
    handler: str | None = None
    restore_time: date | None = None
    remarks: str | None = None


class R3(R):
    seq_no: int | None = None
    record_date: date | None = None
    equipment_no: str | None = None
    run_status: str | None = None
    abnormal_type: str | None = None
    abnormal_desc: str | None = None
    action_taken: str | None = None
    action_result: str | None = None
    handler: str | None = None
    restore_time: date | None = None
    remarks: str | None = None


class C4(BaseModel):
    seq_no: int | None = None
    sep_date: date | None = None
    batch_no: str
    separation_stage: str | None = None
    retentate_volume: float | None = None
    permeate_volume: float | None = None
    retentate_concentration: float | None = None
    permeate_concentration: float | None = None
    concentration_factor: float | None = None
    operator: str | None = None
    remarks: str | None = None


class R4(R):
    seq_no: int | None = None
    sep_date: date | None = None
    batch_no: str
    separation_stage: str | None = None
    retentate_volume: float | None = None
    permeate_volume: float | None = None
    retentate_concentration: float | None = None
    permeate_concentration: float | None = None
    concentration_factor: float | None = None
    operator: str | None = None
    remarks: str | None = None


def mk(tbl, m, c, resp_cls, sf):
    @router.get(f"/{tbl}", summary=f"{tbl}列表")
    async def _list(
        page: int = Query(1, ge=1),
        ps: int = Query(20, ge=1, le=200),
        s: str | None = Query(None, alias=sf),
        workshop: str = Query("203"),
        session: AsyncSession = Depends(get_db),
    ):
        q = select(m).where(m.is_deleted.is_(False), m.workshop == workshop)
        if s:
            q = q.where(getattr(m, sf).ilike(f"%{s}%"))
        total = (
            await session.execute(select(func.count()).select_from(q.subquery()))
        ).scalar_one()
        rows = await session.execute(
            q.order_by(m.seq_no.asc()).offset((page - 1) * ps).limit(ps)
        )
        return paginated_response(
            [resp_cls.model_validate(row) for row in rows.scalars().all()], page, ps, total  # noqa: E501
        )

    @router.post(f"/{tbl}", summary=f"创建{tbl}")
    async def _create(d: c, session: AsyncSession = Depends(get_db)):
        obj = m(**d.model_dump())
        session.add(obj)
        await session.flush()
        await session.commit()
        await session.refresh(obj)
        return success_response(resp_cls.model_validate(obj), message="创建成功")

    @router.put(f"/{tbl}/{{rid}}", summary=f"更新{tbl}")
    async def _update(rid: UUID, d: c, session: AsyncSession = Depends(get_db)):
        obj = await session.get(m, rid)
        if not obj or obj.is_deleted:
            return success_response(None, message="记录不存在", status_code=404)
        for k, v in d.model_dump(exclude_unset=True).items():
            setattr(obj, k, v)
        await session.flush()
        return success_response(resp_cls.model_validate(obj), message="更新成功")

    @router.delete(f"/{tbl}/{{rid}}", summary=f"删除{tbl}")
    async def _delete(rid: UUID, session: AsyncSession = Depends(get_db)):
        r = await session.get(m, rid)
        if not r:
            return success_response(None, message="记录不存在", status_code=404)
        r.is_deleted = True
        await session.flush()
        return success_response(None, message="删除成功")


mk("ceramic-feeds", CeramicFeed, C0, R0, "batch_no")
mk("ceramic-membrane-cleans", CeramicMembraneClean, C1, R1, "membrane_no")
mk("ceramic-membrane-ops", CeramicMembraneOps, C2, R2, "batch_no")
mk("ceramic-equipment-logs", CeramicEquipmentLog, C3, R3, "equipment_no")
mk("ceramic-material-separations", CeramicMaterialSeparation, C4, R4, "batch_no")
