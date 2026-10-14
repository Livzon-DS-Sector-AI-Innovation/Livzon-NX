from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.platform.identity.deps import require_current_user, require_system_admin
from app.platform.identity.models import User
from app.platform.system import feedback_service as service
from app.platform.system.feedback_schemas import (
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackStatus,
    FeedbackUpdate,
)

# Personal endpoints use the existing identity/me login-only policy. The admin
# inbox additionally enforces system-admin identity, excluding ordinary admins.
router = APIRouter(prefix="/identity", tags=["平台问题反馈"])


@router.post(
    "/me/feedback",
    response_model=FeedbackResponse,
    status_code=201,
    summary="提交问题反馈",
)
async def submit_feedback(
    feedback_id: UUID = Form(...),
    description: str = Form(..., min_length=10, max_length=5000),
    occurred_at: datetime = Form(...),
    page_path: str = Form("", max_length=500),
    screenshots: list[UploadFile] = File(...),
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    return await service.create_feedback(
        db, user, feedback_id, description, occurred_at, page_path, screenshots
    )


@router.get("/me/feedback", response_model=FeedbackListResponse, summary="查看本人反馈")
async def my_feedback(
    status: FeedbackStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedbackListResponse:
    return await service.list_feedback(db, user.id, status, page, page_size)


@router.get(
    "/admin/feedback", response_model=FeedbackListResponse, summary="系统管理员接收反馈"
)
async def admin_feedback(
    status: FeedbackStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    _admin: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db),
) -> FeedbackListResponse:
    return await service.list_feedback(db, None, status, page, page_size)


@router.patch(
    "/admin/feedback/{feedback_id}",
    response_model=FeedbackResponse,
    summary="处理问题反馈",
)
async def process_feedback(
    feedback_id: UUID,
    payload: FeedbackUpdate,
    admin: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    return await service.update_feedback(db, feedback_id, admin, payload)


async def screenshot_response(
    db: AsyncSession, feedback_id: UUID, screenshot_id: UUID, owner_id: UUID | None
) -> Response:
    image = await service.get_screenshot(db, feedback_id, screenshot_id, owner_id)
    return Response(
        image.content,
        media_type=image.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/me/feedback/{feedback_id}/screenshots/{screenshot_id}", summary="查看本人反馈截图"
)
async def my_screenshot(
    feedback_id: UUID,
    screenshot_id: UUID,
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    return await screenshot_response(db, feedback_id, screenshot_id, user.id)


@router.get(
    "/admin/feedback/{feedback_id}/screenshots/{screenshot_id}",
    summary="系统管理员查看反馈截图",
)
async def admin_screenshot(
    feedback_id: UUID,
    screenshot_id: UUID,
    _admin: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    return await screenshot_response(db, feedback_id, screenshot_id, None)
