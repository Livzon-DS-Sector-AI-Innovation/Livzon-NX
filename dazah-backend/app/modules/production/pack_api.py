"""包装 API"""
from uuid import UUID
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel as BM, Field as F
from datetime import datetime as dt, date
from typing import Optional as O
from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.pack_models import Pack
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE
router = create_module_router(MODULES_BY_CODE["production"])

class CD(BM): seq_no:O[int]=None; batch_no:str; feed_weight:O[str]=None; incoming_batch:O[str]=None; incoming_titer:O[float]=None; incoming_moisture:O[float]=None; impurity_report:O[str]=None; pack_spec:O[str]=None; barrel_count:O[float]=None; per_barrel_weight:O[str]=None; total_net_weight:O[str]=None; sample_weight:O[str]=None; retain_weight:O[str]=None; reject_weight:O[str]=None; screen_loss:O[str]=None; spill_loss:O[str]=None; total_yield:O[float]=None; pack_date:O[str]=None; operator:O[str]=None; outer_pack_no:O[str]=None; warehouse_qty:O[str]=None; remarks:O[str]=None
class RD(BM): id:UUID; seq_no:O[int]=None; batch_no:str; feed_weight:O[str]=None; incoming_batch:O[str]=None; incoming_titer:O[float]=None; incoming_moisture:O[float]=None; impurity_report:O[str]=None; pack_spec:O[str]=None; barrel_count:O[float]=None; per_barrel_weight:O[str]=None; total_net_weight:O[str]=None; sample_weight:O[str]=None; retain_weight:O[str]=None; reject_weight:O[str]=None; screen_loss:O[str]=None; spill_loss:O[str]=None; total_yield:O[float]=None; pack_date:O[str]=None; operator:O[str]=None; outer_pack_no:O[str]=None; warehouse_qty:O[str]=None; remarks:O[str]=None; created_at:dt; updated_at:dt; model_config={"from_attributes":True}

@router.get("/pack", summary="包装列表")
async def _list(page:int=Query(1,ge=1),ps:int=Query(20,ge=1,le=200),s:str|None=Query(None,alias="batch_no"),workshop:str=Query('203'),session:AsyncSession=Depends(get_db)):
    q=select(Pack).where(Pack.is_deleted==False, Pack.workshop==workshop)
    if s: q=q.where(Pack.batch_no.ilike(f"%{s}%"))
    total=(await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows=await session.execute(q.order_by(Pack.seq_no.asc()).offset((page-1)*ps).limit(ps))
    return paginated_response([RD.model_validate(r) for r in rows.scalars().all()],page,ps,total)
@router.post("/pack",summary="创建包装")
async def _create(d:CD,session:AsyncSession=Depends(get_db)):
    r=Pack(**d.model_dump());session.add(r);await session.flush();await session.commit();await session.refresh(r)
    return success_response(RD.model_validate(r),message="创建成功")
@router.put("/pack/{rid}",summary="更新包装")
async def _update(rid:UUID,d:CD,session:AsyncSession=Depends(get_db)):
    r=await session.get(Pack,rid)
    if not r or r.is_deleted:return success_response(None,message="记录不存在",status_code=404)
    for k,v in d.model_dump(exclude_unset=True).items():setattr(r,k,v)
    await session.flush();return success_response(RD.model_validate(r),message="更新成功")
@router.delete("/pack/{rid}",summary="删除包装")
async def _delete(rid:UUID,session:AsyncSession=Depends(get_db)):
    r=await session.get(Pack,rid)
    if not r:return success_response(None,message="记录不存在",status_code=404)
    r.is_deleted=True;await session.flush();return success_response(None,message="删除成功")
