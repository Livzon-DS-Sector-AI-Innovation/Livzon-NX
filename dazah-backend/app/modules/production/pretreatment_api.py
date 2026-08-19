"""预处理工艺记录 API"""

from uuid import UUID
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.pretreatment_models import Pretreatment
from app.modules.production.pretreatment_schemas import PretreatmentCreate, PretreatmentResponse, PretreatmentUpdate
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


@router.get("/pretreatments", summary="预处理记录列表")
async def list_pretreatments(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
                              received_batch: str | None = None, workshop: str = Query('203'),
                              session: AsyncSession = Depends(get_db)):
    query = select(Pretreatment).where(Pretreatment.is_deleted == False, Pretreatment.workshop == workshop)
    if received_batch: query = query.where(Pretreatment.received_batch.ilike(f"%{received_batch}%"))
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = await session.execute(query.order_by(Pretreatment.seq_no.asc()).offset((page-1)*page_size).limit(page_size))
    return paginated_response([PretreatmentResponse.model_validate(r) for r in rows.scalars().all()], page, page_size, total)


@router.post("/pretreatments", summary="创建预处理记录")
async def create_pretreatment(data: PretreatmentCreate, session: AsyncSession = Depends(get_db)):
    r = Pretreatment(**data.model_dump()); session.add(r); await session.flush(); await session.commit(); await session.refresh(r)
    return success_response(PretreatmentResponse.model_validate(r), message="创建成功")


@router.put("/pretreatments/{record_id}", summary="更新预处理记录")
async def update_pretreatment(record_id: UUID, data: PretreatmentUpdate, session: AsyncSession = Depends(get_db)):
    r = await session.get(Pretreatment, record_id)
    if not r or r.is_deleted: return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(r, k, v)
    await session.flush(); return success_response(PretreatmentResponse.model_validate(r), message="更新成功")


@router.delete("/pretreatments/{record_id}", summary="删除预处理记录")
async def delete_pretreatment(record_id: UUID, session: AsyncSession = Depends(get_db)):
    r = await session.get(Pretreatment, record_id)
    if not r: return success_response(None, message="记录不存在", status_code=404)
    r.is_deleted = True; await session.flush(); return success_response(None, message="删除成功")
