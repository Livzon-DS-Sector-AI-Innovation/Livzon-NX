"""摇瓶种子制备记录 API routes."""
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.modules.production.seed_culture_schemas import (
    PersonMonthlyRow,
    SeedCultureCreate,
    SeedCultureResponse,
    SeedCultureUpdate,
)
from app.modules.production.seed_culture_service import SeedCultureService
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])


def get_seed_culture_service(
    session: AsyncSession = Depends(get_db),
) -> SeedCultureService:
    return SeedCultureService(session)


@router.get("/seed-cultures", summary="种子培养记录列表")
async def list_seed_cultures(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    batch_no: str | None = Query(None, description="摇瓶批号搜索"),
    product_name: str | None = Query(None, description="产品名称"),
    svc: SeedCultureService = Depends(get_seed_culture_service),
) -> Any:
    items, total = await svc.list_records(
        page=page, page_size=page_size, batch_no=batch_no, product_name=product_name
    )
    return paginated_response(
        [SeedCultureResponse.model_validate(i) for i in items], page, page_size, total
    )


@router.get(
    "/seed-cultures/person-monthly",
    summary="人员月度工作统计（月度绩效依据）",
)
async def seed_culture_person_monthly(
    month: str = Query(..., description="统计月份 YYYY-MM"),
    product_name: str = Query("盐酸林可霉素", description="产品名称"),
    svc: SeedCultureService = Depends(get_seed_culture_service),
) -> Any:
    try:
        rows = await svc.person_monthly(product_name, month)
    except ValueError:
        raise HTTPException(status_code=400, detail="month 格式应为 YYYY-MM")
    return success_response([PersonMonthlyRow.model_validate(r) for r in rows])


@router.get("/seed-cultures/{record_id}", summary="种子培养记录详情")
async def get_seed_culture(
    record_id: UUID, svc: SeedCultureService = Depends(get_seed_culture_service)
) -> Any:
    record = await svc.get_record(record_id)
    if not record:
        return success_response(None, message="记录不存在", status_code=404)
    return success_response(SeedCultureResponse.model_validate(record))


@router.post("/seed-cultures", summary="创建种子培养记录")
async def create_seed_culture(
    data: SeedCultureCreate, svc: SeedCultureService = Depends(get_seed_culture_service)
) -> Any:
    record = await svc.create_record(data.model_dump())
    return success_response(
        SeedCultureResponse.model_validate(record), message="创建成功"
    )


@router.put("/seed-cultures/{record_id}", summary="更新种子培养记录")
async def update_seed_culture(
    record_id: UUID,
    data: SeedCultureUpdate,
    svc: SeedCultureService = Depends(get_seed_culture_service),
) -> Any:
    record = await svc.update_record(record_id, data.model_dump(exclude_unset=True))
    return success_response(
        SeedCultureResponse.model_validate(record), message="更新成功"
    )


@router.delete("/seed-cultures/{record_id}", summary="删除种子培养记录")
async def delete_seed_culture(
    record_id: UUID, svc: SeedCultureService = Depends(get_seed_culture_service)
) -> Any:
    await svc.delete_record(record_id)
    return success_response(None, message="删除成功")
