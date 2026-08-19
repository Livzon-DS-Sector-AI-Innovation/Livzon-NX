"""二次重结晶脱色 API"""
from uuid import UUID
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel as BM, Field as F
from datetime import datetime as dt, date
from typing import Optional as O
from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.recrystallize_models import Recrystallize
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE
router = create_module_router(MODULES_BY_CODE["production"])

class CD(BM): seq_no:O[int]=None; batch_no:str; feed_volume:O[str]=None; feed_titer:O[float]=None; solvent_amount:O[str]=None; water_amount:O[str]=None; solvent_ratio:O[str]=None; carbon_dosage:O[float]=None; dissolve_temp:O[float]=None; holding_time:O[float]=None; cooling_rate:O[float]=None; crystal_temp:O[float]=None; crystal_time:O[float]=None; color_hazen:O[float]=None; transmittance:O[float]=None; crystal_size:O[float]=None; mother_liquor_titer:O[float]=None; remarks:O[str]=None
class RD(BM): id:UUID; seq_no:O[int]=None; batch_no:str; feed_volume:O[str]=None; feed_titer:O[float]=None; solvent_amount:O[str]=None; water_amount:O[str]=None; solvent_ratio:O[str]=None; carbon_dosage:O[float]=None; dissolve_temp:O[float]=None; holding_time:O[float]=None; cooling_rate:O[float]=None; crystal_temp:O[float]=None; crystal_time:O[float]=None; color_hazen:O[float]=None; transmittance:O[float]=None; crystal_size:O[float]=None; mother_liquor_titer:O[float]=None; remarks:O[str]=None; created_at:dt; updated_at:dt; model_config={"from_attributes":True}

@router.get("/recrystallize", summary="二次重结晶脱色列表")
async def _list(page:int=Query(1,ge=1),ps:int=Query(20,ge=1,le=200),s:str|None=Query(None,alias="batch_no"),workshop:str=Query('203'),session:AsyncSession=Depends(get_db)):
    q=select(Recrystallize).where(Recrystallize.is_deleted==False, Recrystallize.workshop==workshop)
    if s: q=q.where(Recrystallize.batch_no.ilike(f"%{s}%"))
    total=(await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows=await session.execute(q.order_by(Recrystallize.seq_no.asc()).offset((page-1)*ps).limit(ps))
    return paginated_response([RD.model_validate(r) for r in rows.scalars().all()],page,ps,total)
@router.post("/recrystallize",summary="创建二次重结晶脱色")
async def _create(d:CD,session:AsyncSession=Depends(get_db)):
    r=Recrystallize(**d.model_dump());session.add(r);await session.flush();await session.commit();await session.refresh(r)
    return success_response(RD.model_validate(r),message="创建成功")
@router.put("/recrystallize/{rid}",summary="更新二次重结晶脱色")
async def _update(rid:UUID,d:CD,session:AsyncSession=Depends(get_db)):
    r=await session.get(Recrystallize,rid)
    if not r or r.is_deleted:return success_response(None,message="记录不存在",status_code=404)
    for k,v in d.model_dump(exclude_unset=True).items():setattr(r,k,v)
    await session.flush();return success_response(RD.model_validate(r),message="更新成功")
@router.delete("/recrystallize/{rid}",summary="删除二次重结晶脱色")
async def _delete(rid:UUID,session:AsyncSession=Depends(get_db)):
    r=await session.get(Recrystallize,rid)
    if not r:return success_response(None,message="记录不存在",status_code=404)
    r.is_deleted=True;await session.flush();return success_response(None,message="删除成功")
