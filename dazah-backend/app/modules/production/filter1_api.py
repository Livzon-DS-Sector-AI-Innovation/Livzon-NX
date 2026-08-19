"""一次板框过滤 API"""
from uuid import UUID
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel as BM, Field as F
from datetime import datetime as dt, date
from typing import Optional as O
from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.filter1_models import Filter1
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE
router = create_module_router(MODULES_BY_CODE["production"])

class CD(BM): seq_no:O[int]=None; batch_no:str; feed_volume:O[str]=None; feed_ph:O[float]=None; feed_temp:O[float]=None; feed_titer:O[float]=None; filter_pressure:O[float]=None; feed_flow:O[float]=None; filter_duration:O[float]=None; cloth_no:O[str]=None; filtrate_volume:O[str]=None; filtrate_titer:O[float]=None; cake_wet_weight:O[str]=None; cake_dry_weight:O[str]=None; cake_residue_titer:O[float]=None; pipe_residue:O[str]=None; cake_moisture:O[float]=None; filter_yield:O[float]=None; remarks:O[str]=None
class RD(BM): id:UUID; seq_no:O[int]=None; batch_no:str; feed_volume:O[str]=None; feed_ph:O[float]=None; feed_temp:O[float]=None; feed_titer:O[float]=None; filter_pressure:O[float]=None; feed_flow:O[float]=None; filter_duration:O[float]=None; cloth_no:O[str]=None; filtrate_volume:O[str]=None; filtrate_titer:O[float]=None; cake_wet_weight:O[str]=None; cake_dry_weight:O[str]=None; cake_residue_titer:O[float]=None; pipe_residue:O[str]=None; cake_moisture:O[float]=None; filter_yield:O[float]=None; remarks:O[str]=None; created_at:dt; updated_at:dt; model_config={"from_attributes":True}

@router.get("/filter1", summary="一次板框过滤列表")
async def _list(page:int=Query(1,ge=1),ps:int=Query(20,ge=1,le=200),s:str|None=Query(None,alias="batch_no"),workshop:str=Query('203'),session:AsyncSession=Depends(get_db)):
    q=select(Filter1).where(Filter1.is_deleted==False, Filter1.workshop==workshop)
    if s: q=q.where(Filter1.batch_no.ilike(f"%{s}%"))
    total=(await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows=await session.execute(q.order_by(Filter1.seq_no.asc()).offset((page-1)*ps).limit(ps))
    return paginated_response([RD.model_validate(r) for r in rows.scalars().all()],page,ps,total)
@router.post("/filter1",summary="创建一次板框过滤")
async def _create(d:CD,session:AsyncSession=Depends(get_db)):
    r=Filter1(**d.model_dump());session.add(r);await session.flush();await session.commit();await session.refresh(r)
    return success_response(RD.model_validate(r),message="创建成功")
@router.put("/filter1/{rid}",summary="更新一次板框过滤")
async def _update(rid:UUID,d:CD,session:AsyncSession=Depends(get_db)):
    r=await session.get(Filter1,rid)
    if not r or r.is_deleted:return success_response(None,message="记录不存在",status_code=404)
    for k,v in d.model_dump(exclude_unset=True).items():setattr(r,k,v)
    await session.flush();return success_response(RD.model_validate(r),message="更新成功")
@router.delete("/filter1/{rid}",summary="删除一次板框过滤")
async def _delete(rid:UUID,session:AsyncSession=Depends(get_db)):
    r=await session.get(Filter1,rid)
    if not r:return success_response(None,message="记录不存在",status_code=404)
    r.is_deleted=True;await session.flush();return success_response(None,message="删除成功")
