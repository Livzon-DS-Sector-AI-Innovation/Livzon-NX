"""陶瓷膜过滤 5表 API — 匹配飞书字段结构"""
from uuid import UUID
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.ceramic_models import *
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE
router = create_module_router(MODULES_BY_CODE["production"])
from pydantic import BaseModel as BM, Field as F
from datetime import datetime as dt, date
from typing import Optional as O
class R(BM): id:UUID; created_at:dt; updated_at:dt; model_config={"from_attributes":True}

class C0(BM): seq_no:O[int]=None; feed_date:O[date]=None; batch_no:str; feed_volume:O[float]=None; feed_concentration:O[float]=None; feed_temp:O[float]=None; ph_value:O[float]=None; tank_no:O[str]=None; material_name:O[str]=None; operator:O[str]=None; remarks:O[str]=None
class R0(R): seq_no:O[int]=None; feed_date:O[date]=None; batch_no:str; feed_volume:O[float]=None; feed_concentration:O[float]=None; feed_temp:O[float]=None; ph_value:O[float]=None; tank_no:O[str]=None; material_name:O[str]=None; operator:O[str]=None; remarks:O[str]=None

class C1(BM): seq_no:O[int]=None; clean_date:O[date]=None; membrane_no:O[str]=None; cleaner_type:O[str]=None; cleaner_concentration:O[float]=None; clean_temp:O[float]=None; clean_time:O[float]=None; clean_pressure:O[float]=None; flux_recovery:O[float]=None; operator:O[str]=None; remarks:O[str]=None
class R1(R): seq_no:O[int]=None; clean_date:O[date]=None; membrane_no:O[str]=None; cleaner_type:O[str]=None; cleaner_concentration:O[float]=None; clean_temp:O[float]=None; clean_time:O[float]=None; clean_pressure:O[float]=None; flux_recovery:O[float]=None; operator:O[str]=None; remarks:O[str]=None

class C2(BM): seq_no:O[int]=None; run_date:O[date]=None; batch_no:str; membrane_no:O[str]=None; run_pressure:O[float]=None; membrane_velocity:O[float]=None; tmp:O[float]=None; run_temp:O[float]=None; permeate_flux:O[float]=None; operator:O[str]=None; remarks:O[str]=None
class R2(R): seq_no:O[int]=None; run_date:O[date]=None; batch_no:str; membrane_no:O[str]=None; run_pressure:O[float]=None; membrane_velocity:O[float]=None; tmp:O[float]=None; run_temp:O[float]=None; permeate_flux:O[float]=None; operator:O[str]=None; remarks:O[str]=None

class C3(BM): seq_no:O[int]=None; record_date:O[date]=None; equipment_no:O[str]=None; run_status:O[str]=None; abnormal_type:O[str]=None; abnormal_desc:O[str]=None; action_taken:O[str]=None; action_result:O[str]=None; handler:O[str]=None; restore_time:O[date]=None; remarks:O[str]=None
class R3(R): seq_no:O[int]=None; record_date:O[date]=None; equipment_no:O[str]=None; run_status:O[str]=None; abnormal_type:O[str]=None; abnormal_desc:O[str]=None; action_taken:O[str]=None; action_result:O[str]=None; handler:O[str]=None; restore_time:O[date]=None; remarks:O[str]=None

class C4(BM): seq_no:O[int]=None; sep_date:O[date]=None; batch_no:str; separation_stage:O[str]=None; retentate_volume:O[float]=None; permeate_volume:O[float]=None; retentate_concentration:O[float]=None; permeate_concentration:O[float]=None; concentration_factor:O[float]=None; operator:O[str]=None; remarks:O[str]=None
class R4(R): seq_no:O[int]=None; sep_date:O[date]=None; batch_no:str; separation_stage:O[str]=None; retentate_volume:O[float]=None; permeate_volume:O[float]=None; retentate_concentration:O[float]=None; permeate_concentration:O[float]=None; concentration_factor:O[float]=None; operator:O[str]=None; remarks:O[str]=None

def mk(tbl, M, C, R, sf):
    @router.get(f"/{tbl}", summary=f"{tbl}列表")
    async def _list(page:int=Query(1,ge=1),ps:int=Query(20,ge=1,le=200),s:str|None=Query(None,alias=sf),workshop:str=Query('203'),session:AsyncSession=Depends(get_db)):
        q=select(M).where(M.is_deleted==False, M.workshop==workshop)
        if s: q=q.where(getattr(M,sf).ilike(f"%{s}%"))
        total=(await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        rows=await session.execute(q.order_by(M.seq_no.asc()).offset((page-1)*ps).limit(ps))
        return paginated_response([R.model_validate(r) for r in rows.scalars().all()],page,ps,total)
    @router.post(f"/{tbl}",summary=f"创建{tbl}")
    async def _create(d:C,session:AsyncSession=Depends(get_db)):
        r=M(**d.model_dump());session.add(r);await session.flush();await session.commit();await session.refresh(r)
        return success_response(R.model_validate(r),message="创建成功")
    @router.put(f"/{tbl}/{{rid}}",summary=f"更新{tbl}")
    async def _update(rid:UUID,d:C,session:AsyncSession=Depends(get_db)):
        r=await session.get(M,rid)
        if not r or r.is_deleted:return success_response(None,message="记录不存在",status_code=404)
        for k,v in d.model_dump(exclude_unset=True).items():setattr(r,k,v)
        await session.flush();return success_response(R.model_validate(r),message="更新成功")
    @router.delete(f"/{tbl}/{{rid}}",summary=f"删除{tbl}")
    async def _delete(rid:UUID,session:AsyncSession=Depends(get_db)):
        r=await session.get(M,rid)
        if not r:return success_response(None,message="记录不存在",status_code=404)
        r.is_deleted=True;await session.flush();return success_response(None,message="删除成功")

mk("ceramic-feeds",CeramicFeed,C0,R0,"batch_no")
mk("ceramic-membrane-cleans",CeramicMembraneClean,C1,R1,"membrane_no")
mk("ceramic-membrane-ops",CeramicMembraneOps,C2,R2,"batch_no")
mk("ceramic-equipment-logs",CeramicEquipmentLog,C3,R3,"equipment_no")
mk("ceramic-material-separations",CeramicMaterialSeparation,C4,R4,"batch_no")
