"""Drug API endpoints."""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.modules.registration import service
from app.modules.registration.models.review import ReviewNode
from app.modules.registration.schemas.drug import (
    DrugCreate,
    DrugResponse,
    DrugUpdate,
    DrugWithNodesResponse,
)
from app.modules.registration.schemas.review import ReviewNodeConfig

router = APIRouter()


@router.get("/", summary="获取药品列表")
async def list_drugs(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取所有药品及其审评节点"""
    drugs = await service.get_drugs(db)
    data = [DrugWithNodesResponse.model_validate(d) for d in drugs]
    return success_response(data=data)


@router.post("/", summary="创建药品")
async def create_drug(
    data: DrugCreate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """创建新药品"""
    drug = await service.create_drug(db, data)
    return success_response(data=DrugResponse.model_validate(drug))


@router.get("/nodes", summary="获取审评节点配置")
async def get_review_nodes() -> JSONResponse:
    """获取10个审评节点的配置信息"""
    nodes = [ReviewNodeConfig(**n) for n in ReviewNode.get_all()]
    return success_response(data=nodes)


@router.get("/{drug_id}", summary="获取药品详情")
async def get_drug(
    drug_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取单个药品及其审评节点"""
    drug = await service.get_drug(db, drug_id)
    return success_response(data=DrugWithNodesResponse.model_validate(drug))


@router.put("/{drug_id}", summary="更新药品")
async def update_drug(
    drug_id: uuid.UUID,
    data: DrugUpdate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """更新药品信息及审评节点"""
    drug = await service.update_drug(db, drug_id, data)
    return success_response(data=DrugWithNodesResponse.model_validate(drug))


@router.delete("/{drug_id}", summary="删除药品")
async def delete_drug(
    drug_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """删除药品"""
    await service.delete_drug(db, drug_id)
    return success_response(message="删除成功")
