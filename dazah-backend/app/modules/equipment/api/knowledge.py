"""维修知识案例 API 路由."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.modules.equipment.schemas import (
    KnowledgeCaseResponse,
    KnowledgeSearchResponse,
)
from app.modules.equipment.service import (
    dismiss_case,
    list_cases,
    mark_case_used,
    search_similar_cases,
    verify_case,
)

router = APIRouter()


@router.get("/search", summary="相似案例检索（报修推荐）")
async def search_cases(
    q: str = Query(..., min_length=1, max_length=200, description="故障描述关键词"),
    equipment_id: uuid.UUID | None = Query(None, description="设备ID（本设备层）"),
    symptom_code: str | None = Query(None, description="故障现象代码"),
    top: int = Query(3, ge=1, le=10, description="返回条数"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    items = await search_similar_cases(
        db,
        query=q,
        equipment_id=equipment_id,
        symptom_code=symptom_code,
        top=top,
    )
    return success_response(
        data=KnowledgeSearchResponse(items=items).model_dump()
    )


@router.get("/cases", summary="案例列表（含草稿）")
async def get_cases(
    status: str | None = Query(
        None, pattern="^(draft|verified|dismissed)$", description="状态"
    ),
    equipment_id: uuid.UUID | None = Query(None, description="设备ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    cases, total = await list_cases(
        db,
        status=status,
        equipment_id=equipment_id,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        data=[KnowledgeCaseResponse.model_validate(c).model_dump() for c in cases],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/cases/{case_id}/verify", summary="确认案例入库")
async def verify_case_api(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    case = await verify_case(db, case_id, current_user.id)
    return success_response(
        data=KnowledgeCaseResponse.model_validate(case).model_dump()
    )


@router.post("/cases/{case_id}/dismiss", summary="忽略案例草稿")
async def dismiss_case_api(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    case = await dismiss_case(db, case_id, current_user.id)
    return success_response(
        data=KnowledgeCaseResponse.model_validate(case).model_dump()
    )


@router.post("/cases/{case_id}/use", summary="标记案例被采纳（计数）")
async def mark_used_api(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    await mark_case_used(db, case_id)
    return success_response(message="已记录")
