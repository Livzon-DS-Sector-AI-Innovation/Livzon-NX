"""一次脱色 API"""
from uuid import UUID
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel as BM, Field as F
from datetime import datetime as dt, date
from typing import Optional as O
from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.decolor1_models import Decolor1
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE
router = create_module_router(MODULES_BY_CODE["production"])

class CD(BM): seq_no:O[int]=None; batch_no:str; feed_volume:O[str]=None; feed_titer:O[float]=None; carbon_type:O[str]=None; dosage:O[str]=None; stirring_speed:O[float]=None; decolor_temp:O[float]=None; holding_time:O[float]=None; endpoint_transmittance:O[str]=None; decolor_volume:O[str]=None; color_before:O[str]=None; color_after:O[str]=None; color_removal_rate:O[float]=None; heavy_metal:O[str]=None; protein_impurity:O[str]=None; transmittance_data:O[str]=None; carbon_residue:O[str]=None
class RD(BM): id:UUID; seq_no:O[int]=None; batch_no:str; feed_volume:O[str]=None; feed_titer:O[float]=None; carbon_type:O[str]=None; dosage:O[str]=None; stirring_speed:O[float]=None; decolor_temp:O[float]=None; holding_time:O[float]=None; endpoint_transmittance:O[str]=None; decolor_volume:O[str]=None; color_before:O[str]=None; color_after:O[str]=None; color_removal_rate:O[float]=None; heavy_metal:O[str]=None; protein_impurity:O[str]=None; transmittance_data:O[str]=None; carbon_residue:O[str]=None; created_at:dt; updated_at:dt; model_config={"from_attributes":True}

@router.get("/decolor1", summary="一次脱色列表")
async def _list(page:int=Query(1,ge=1),ps:int=Query(20,ge=1,le=200),s:str|None=Query(None,alias="batch_no"),workshop:str=Query('203'),session:AsyncSession=Depends(get_db)):
    q=select(Decolor1).where(Decolor1.is_deleted==False, Decolor1.workshop==workshop)
    if s: q=q.where(Decolor1.batch_no.ilike(f"%{s}%"))
    total=(await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows=await session.execute(q.order_by(Decolor1.seq_no.asc()).offset((page-1)*ps).limit(ps))
    return paginated_response([RD.model_validate(r) for r in rows.scalars().all()],page,ps,total)
@router.post("/decolor1",summary="创建一次脱色")
async def _create(d:CD,session:AsyncSession=Depends(get_db)):
    r=Decolor1(**d.model_dump());session.add(r);await session.flush();await session.commit();await session.refresh(r)
    return success_response(RD.model_validate(r),message="创建成功")
@router.put("/decolor1/{rid}",summary="更新一次脱色")
async def _update(rid:UUID,d:CD,session:AsyncSession=Depends(get_db)):
    r=await session.get(Decolor1,rid)
    if not r or r.is_deleted:return success_response(None,message="记录不存在",status_code=404)
    for k,v in d.model_dump(exclude_unset=True).items():setattr(r,k,v)
    await session.flush();return success_response(RD.model_validate(r),message="更新成功")
@router.delete("/decolor1/{rid}",summary="删除一次脱色")
async def _delete(rid:UUID,session:AsyncSession=Depends(get_db)):
    r=await session.get(Decolor1,rid)
    if not r:return success_response(None,message="记录不存在",status_code=404)
    r.is_deleted=True;await session.flush();return success_response(None,message="删除成功")
