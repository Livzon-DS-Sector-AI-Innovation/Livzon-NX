import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import success_response
from app.platform.identity.deps import AdminUser

from .schemas import AuditCategory, GeneralAuditLogDetail, GeneralAuditLogPage
from .service import GeneralAuditLogService

router = APIRouter()


@router.get(
    "/logs",
    summary="管理员分页查询通用操作审计",
    response_model=GeneralAuditLogPage,
)
async def list_general_audit_logs(
    current_user: AdminUser,
    category: AuditCategory,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await GeneralAuditLogService().list_logs(
        db,
        category=category,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
        keyword=keyword,
        started_at=started_at,
        ended_at=ended_at,
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get(
    "/logs/{log_id}",
    summary="管理员查看通用操作审计详情",
    response_model=GeneralAuditLogDetail,
)
async def get_general_audit_log(
    log_id: uuid.UUID,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await GeneralAuditLogService().get_log(db, log_id=log_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit log not found")
    return success_response(data=result.model_dump(mode="json"))
