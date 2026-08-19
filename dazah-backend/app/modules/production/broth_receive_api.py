"""发酵液接收记录 API"""

from uuid import UUID
from fastapi import Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.broth_receive_models import BrothReceive
from app.modules.production.broth_receive_schemas import BrothReceiveCreate, BrothReceiveResponse, BrothReceiveUpdate
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


@router.get("/broth-receives", summary="发酵液接收记录列表")
async def list_broth_receives(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
    received_batch: str | None = Query(None),
    workshop: str = Query('203'),
    session: AsyncSession = Depends(get_db),
):
    query = select(BrothReceive).where(BrothReceive.is_deleted == False, BrothReceive.workshop == workshop)
    if received_batch:
        query = query.where(BrothReceive.received_batch.ilike(f"%{received_batch}%"))
    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()
    query = query.order_by(BrothReceive.seq_no.asc().nulls_last(), BrothReceive.receive_time.desc().nulls_last())
    rows = await session.execute(query.offset((page-1)*page_size).limit(page_size))
    items = [BrothReceiveResponse.model_validate(r) for r in rows.scalars().all()]
    return paginated_response(items, page, page_size, total)


@router.post("/broth-receives", summary="创建发酵液接收记录")
async def create_broth_receive(data: BrothReceiveCreate, session: AsyncSession = Depends(get_db)):
    record = BrothReceive(**data.model_dump())
    session.add(record)
    await session.flush()
    await session.commit()
    await session.refresh(record)
    return success_response(BrothReceiveResponse.model_validate(record), message="创建成功")


@router.put("/broth-receives/{record_id}", summary="更新发酵液接收记录")
async def update_broth_receive(record_id: UUID, data: BrothReceiveUpdate, session: AsyncSession = Depends(get_db)):
    record = await session.get(BrothReceive, record_id)
    if not record or record.is_deleted:
        return success_response(None, message="记录不存在", status_code=404)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    await session.flush()
    return success_response(BrothReceiveResponse.model_validate(record), message="更新成功")


@router.delete("/broth-receives/{record_id}", summary="删除发酵液接收记录")
async def delete_broth_receive(record_id: UUID, session: AsyncSession = Depends(get_db)):
    record = await session.get(BrothReceive, record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    record.is_deleted = True
    await session.flush()
    return success_response(None, message="删除成功")
