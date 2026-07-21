"""Holiday API endpoints."""

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.registration import service
from app.modules.registration.schemas.holiday import (
    HolidayCreate,
    HolidayResponse,
)

router = APIRouter()


@router.get("/", summary="获取节假日列表")
async def list_holidays(
    year: int | None = Query(None, description="年份筛选"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取节假日列表"""
    holidays = await service.get_holidays(db, year)
    data = [HolidayResponse.model_validate(h) for h in holidays]
    return success_response(data=data)


@router.post("/", summary="创建节假日")
async def create_holiday(
    data: HolidayCreate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """创建节假日"""
    holiday = await service.create_holiday(db, data)
    return success_response(data=HolidayResponse.model_validate(holiday))


@router.put("/{holiday_id}", summary="更新节假日")
async def update_holiday(
    holiday_id: uuid.UUID,
    data: HolidayCreate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """更新节假日"""
    holiday = await service.update_holiday(db, holiday_id, data)
    return success_response(data=HolidayResponse.model_validate(holiday))


@router.delete("/{holiday_id}", summary="删除节假日")
async def delete_holiday(
    holiday_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """删除节假日"""
    await service.delete_holiday(db, holiday_id)
    return success_response(message="删除成功")
