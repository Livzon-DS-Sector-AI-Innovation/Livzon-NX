"""备件采购建议与维修成本 API 路由（方案C）."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.modules.equipment.schemas.purchase_suggestion import (
    LaborRateCreate,
    LaborRateUpdate,
    PurchaseSuggestionArrivalRequest,
    PurchaseSuggestionQtyUpdate,
    PurchaseSuggestionSubmitRequest,
    PurchaseSuggestionSubmitResult,
)
from app.modules.equipment.service import (
    cancel_suggestion,
    create_labor_rate,
    delete_labor_rate,
    list_labor_rates,
    list_suggestions,
    register_arrival,
    scan_and_suggest,
    submit_to_procurement,
    update_labor_rate,
    update_suggest_qty,
)

router = APIRouter()


# ── 采购建议 ────────────────────────────────────────────────────────


@router.get("", summary="采购建议列表")
async def get_suggestions(
    status: str | None = Query(
        None,
        pattern="^(suggested|submitted|partial|done|cancelled)$",
        description="状态",
    ),
    workshop: str | None = Query(
        None,
        pattern=r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$",
        description="车间代码",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    items, total = await list_suggestions(
        db, status=status, workshop_code=workshop, page=page, page_size=page_size
    )
    return paginated_response(
        data=items, page=page, page_size=page_size, total=total
    )


@router.post("/scan", summary="手动触发安全线扫描（管理调试用）")
async def run_scan(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    stats = await scan_and_suggest(db)
    return success_response(data=stats)


@router.put("/{suggestion_id}/qty", summary="调整建议采购数量")
async def update_qty(
    suggestion_id: uuid.UUID,
    data: PurchaseSuggestionQtyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    sug = await update_suggest_qty(db, suggestion_id, data.suggest_qty)
    return success_response(
        data={
            "id": str(sug.id),
            "suggest_qty": sug.suggest_qty,
            "status": sug.status,
        }
    )


@router.post("/submit", summary="批量提交采购（生成采购草稿单）")
async def submit(
    data: PurchaseSuggestionSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    result = await submit_to_procurement(db, data.suggestion_ids, current_user.id)
    return success_response(
        data=PurchaseSuggestionSubmitResult(**result).model_dump()
    )


@router.post("/{suggestion_id}/arrival", summary="登记到货（入库并推进状态）")
async def arrival(
    suggestion_id: uuid.UUID,
    data: PurchaseSuggestionArrivalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    sug = await register_arrival(
        db, suggestion_id, data.arrived_qty, user_id=current_user.id
    )
    return success_response(
        data={
            "id": str(sug.id),
            "arrived_qty": sug.arrived_qty,
            "status": sug.status,
        }
    )


@router.post("/{suggestion_id}/cancel", summary="取消建议")
async def cancel(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    sug = await cancel_suggestion(db, suggestion_id, current_user.id)
    return success_response(
        data={"id": str(sug.id), "status": sug.status}
    )


# ── 维修成本 ────────────────────────────────────────────────────────


@router.get("/labor-rates", summary="工时费率列表")
async def get_labor_rates(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    return success_response(data=await list_labor_rates(db))


@router.post("/labor-rates", summary="新增工时费率")
async def add_labor_rate(
    data: LaborRateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    rate = await create_labor_rate(
        db,
        scope=data.scope,
        hourly_rate=data.hourly_rate,
        effective_from=data.effective_from,
        role_id=data.role_id,
        person_id=data.person_id,
        remark=data.remark,
        operator_id=current_user.id,
    )
    return success_response(data={"id": str(rate.id)})


@router.put("/labor-rates/{rate_id}", summary="编辑工时费率")
async def edit_labor_rate(
    rate_id: uuid.UUID,
    data: LaborRateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    rate = await update_labor_rate(
        db,
        rate_id,
        hourly_rate=data.hourly_rate,
        effective_from=data.effective_from,
        remark=data.remark,
        operator_id=current_user.id,
    )
    return success_response(data={"id": str(rate.id)})


@router.delete("/labor-rates/{rate_id}", summary="删除工时费率")
async def remove_labor_rate(
    rate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    if current_user is None:
        raise AppException(message="需要登录后操作")
    await delete_labor_rate(db, rate_id, operator_id=current_user.id)
    return success_response(message="删除成功")
