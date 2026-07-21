"""Reference substance API endpoints."""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import error_response, success_response
from app.modules.registration.repository import reference_substance as repo
from app.modules.registration.schemas.reference_substance import (
    ReferenceSubstanceCreate,
    ReferenceSubstanceResponse,
    ReferenceSubstanceUpdate,
)

router = APIRouter()


@router.get("/", summary="获取对照品列表")
async def list_reference_substances(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取所有对照品记录"""
    substances = await repo.get_reference_substances(db)
    data = [ReferenceSubstanceResponse.model_validate(s) for s in substances]
    return success_response(data=data)


@router.post("/", summary="创建对照品")
async def create_reference_substance(
    payload: ReferenceSubstanceCreate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """创建对照品记录"""
    substance = await repo.create_reference_substance(db, payload.model_dump())
    await db.commit()
    return success_response(data=ReferenceSubstanceResponse.model_validate(substance))


@router.get("/{substance_id}", summary="获取对照品详情")
async def get_reference_substance(
    substance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取单个对照品记录"""
    substance = await repo.get_reference_substance_by_id(db, substance_id)
    if not substance:
        return error_response(message="对照品记录不存在", status_code=404)
    return success_response(data=ReferenceSubstanceResponse.model_validate(substance))


@router.put("/{substance_id}", summary="更新对照品")
async def update_reference_substance(
    substance_id: uuid.UUID,
    payload: ReferenceSubstanceUpdate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """更新对照品记录"""
    update_data = payload.model_dump(exclude_unset=True)
    substance = await repo.update_reference_substance(db, substance_id, update_data)
    if not substance:
        return error_response(message="对照品记录不存在", status_code=404)
    await db.commit()
    return success_response(data=ReferenceSubstanceResponse.model_validate(substance))


@router.delete("/{substance_id}", summary="删除对照品")
async def delete_reference_substance(
    substance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """软删除对照品记录"""
    deleted = await repo.delete_reference_substance(db, substance_id)
    if not deleted:
        return error_response(message="对照品记录不存在", status_code=404)
    await db.commit()
    return success_response(message="删除成功")
