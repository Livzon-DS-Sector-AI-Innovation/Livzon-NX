"""部门联系人/统计/附件审阅 API 路由（Q1 拆分自 quality_management.py）。"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import success_response
from app.modules.quality import service
from app.modules.quality.api.deps import (
    current_user_id as _current_user_id,
)
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.schemas import (
    AttachmentReviewOut,
    CapaStatistics,
    ChangeStatistics,
    CreateAttachmentReviewRequest,
    CreateDepartmentContactRequest,
    DepartmentContactOut,
    DeviationStatistics,
    UpdateDepartmentContactRequest,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/department-contacts",
    summary="获取部门联系人列表",
    response_model=ApiResponseEnvelope[list[DepartmentContactOut]],
)
async def list_department_contacts(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    assert current_user is not None
    from app.platform.identity.data_scope import resolve_user_department_scope

    scope = await resolve_user_department_scope(db, current_user)
    result = await service.get_department_contact_list(db, page, page_size, scope=scope)
    return success_response(data=result)


@router.get(
    "/department-contacts/feishu",
    summary="直接获取飞书部门联系人列表",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def list_department_contacts_from_feishu(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.get_department_contact_list_from_feishu(db, page, page_size)
    return success_response(data=result)


@router.post(
    "/department-contacts",
    summary="创建部门联系人",
    response_model=ApiResponseEnvelope[DepartmentContactOut],
)
async def upsert_department_contact(
    data: CreateDepartmentContactRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.upsert_department_contact(db, data, None, user_id)
    return success_response(data=result)


@router.put(
    "/department-contacts/{contact_id}",
    summary="更新部门联系人",
    response_model=ApiResponseEnvelope[DepartmentContactOut],
)
async def update_department_contact(
    contact_id: uuid.UUID,
    data: UpdateDepartmentContactRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.update_department_contact(db, contact_id, data)
    return success_response(data=result)


@router.delete(
    "/department-contacts/{contact_id}",
    summary="删除部门联系人",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_department_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.delete_department_contact(db, contact_id)
    return success_response(data=result)


# ============ Statistics ============


@router.get(
    "/statistics/deviations",
    summary="获取偏差统计",
    response_model=ApiResponseEnvelope[DeviationStatistics],
)
async def get_deviation_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    assert current_user is not None
    from app.platform.identity.data_scope import resolve_user_department_scope

    scope = await resolve_user_department_scope(db, current_user)
    stats = await service.get_deviation_statistics(db, scope=scope)
    return success_response(data=stats.model_dump())


@router.get(
    "/statistics/capas",
    summary="获取CAPA统计",
    response_model=ApiResponseEnvelope[CapaStatistics],
)
async def get_capa_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    assert current_user is not None
    from app.platform.identity.data_scope import resolve_user_department_scope

    scope = await resolve_user_department_scope(db, current_user)
    stats = await service.get_capa_statistics(db, scope=scope)
    return success_response(data=stats.model_dump())


@router.get(
    "/statistics/changes",
    summary="获取变更统计",
    response_model=ApiResponseEnvelope[ChangeStatistics],
)
async def get_change_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    assert current_user is not None
    from app.platform.identity.data_scope import resolve_user_department_scope

    scope = await resolve_user_department_scope(db, current_user)
    stats = await service.get_change_statistics(db, scope=scope)
    return success_response(data=stats.model_dump())


# ============ Attachment Reviews ============


@router.get(
    "/attachment-reviews",
    summary="获取附件审阅列表",
    response_model=ApiResponseEnvelope[list[AttachmentReviewOut]],
)
async def list_attachment_reviews(
    deviation_id: uuid.UUID | None = None,
    capa_id: uuid.UUID | None = None,
    attachment_url: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    items = await service.list_attachment_reviews(
        db, deviation_id, capa_id, attachment_url
    )
    return success_response(data=items)


@router.post(
    "/attachment-reviews",
    summary="创建附件审阅",
    response_model=ApiResponseEnvelope[AttachmentReviewOut],
)
async def create_attachment_review(
    data: CreateAttachmentReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.create_attachment_review(db, data, user_id)
    return success_response(data=result)


@router.delete(
    "/attachment-reviews/{review_id}",
    summary="删除附件审阅",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_attachment_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    await service.delete_attachment_review(db, review_id)
    return success_response(data={"success": True})


# ============ CAPA Import/Export ============
