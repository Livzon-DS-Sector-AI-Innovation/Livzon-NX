"""HR推送设置 API - 推送模板管理、接收人配置、推送记录、手动测试"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import paginated_response, success_response
from app.modules.hr.push_settings_schemas import (
    PushLogResponse,
    PushRecipientResponse,
    PushRecipientUpdate,
    PushTemplateResponse,
    PushTemplateUpdate,
    PushTestRequest,
)
from app.modules.hr.push_settings_service import (
    PushSettingsService,
    ensure_push_templates_seeded,
)

router = APIRouter(prefix="/hr-settings", tags=["人事-推送设置"])


def _require_user(current_user: CurrentUser) -> None:
    """规范合规：所有业务API默认需要登录"""
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")


def get_service(db: AsyncSession = Depends(get_db)) -> PushSettingsService:
    return PushSettingsService(session=db)


def _require_session(service: PushSettingsService) -> AsyncSession:
    if service.session is None:
        raise AppException(status_code=503, message="推送设置数据库不可用")
    return service.session


# ─── 推送模板 ───


@router.get("/push-templates", summary="获取推送模板列表")
async def list_push_templates(
    entity_code: str = Query("recruitment", description="业务实体"),
    current_user: CurrentUser = None,
    service: PushSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    # 首次访问时自动播种种子数据
    session = _require_session(service)
    await ensure_push_templates_seeded(session)
    await session.commit()
    templates = await service.list_push_templates(entity_code)
    return success_response(
        data=[PushTemplateResponse.model_validate(t) for t in templates]
    )


@router.put("/push-templates/{template_id}", summary="更新推送模板")
async def update_push_template(
    template_id: UUID,
    data: PushTemplateUpdate,
    current_user: CurrentUser = None,
    service: PushSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    template = await service.update_push_template(
        template_id, data.model_dump(exclude_unset=True)
    )
    await _require_session(service).commit()
    return success_response(
        data=PushTemplateResponse.model_validate(template),
        message="模板更新成功",
    )


@router.post("/push-templates/test", summary="手动测试推送")
async def test_push(
    data: PushTestRequest,
    current_user: CurrentUser = None,
    service: PushSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    result = await service.test_push(
        data.template_id, data.recipient, data.test_variables
    )
    return success_response(data=result)


# ─── 推送接收人配置 ───


@router.get("/push-recipients", summary="获取推送接收人配置列表")
async def list_push_recipients(
    entity_code: str = Query("recruitment", description="业务实体"),
    current_user: CurrentUser = None,
    service: PushSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    session = _require_session(service)
    await ensure_push_templates_seeded(session)
    await session.commit()
    recipients = await service.list_push_recipients(entity_code)
    return success_response(
        data=[PushRecipientResponse.model_validate(r) for r in recipients]
    )


@router.put("/push-recipients/{recipient_id}", summary="更新推送接收人配置")
async def update_push_recipient(
    recipient_id: UUID,
    data: PushRecipientUpdate,
    current_user: CurrentUser = None,
    service: PushSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    recipient = await service.update_push_recipient(
        recipient_id, data.model_dump(exclude_unset=True)
    )
    await _require_session(service).commit()
    return success_response(
        data=PushRecipientResponse.model_validate(recipient),
        message="接收人配置更新成功",
    )


# ─── 推送记录 ───


@router.get("/push-logs", summary="获取推送记录列表")
async def list_push_logs(
    entity_code: str = Query("recruitment", description="业务实体"),
    scene_code: str | None = Query(None, description="场景筛选"),
    channel: str | None = Query(None, description="渠道筛选: email/feishu"),
    status: str | None = Query(None, description="状态筛选: success/failed"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = None,
    service: PushSettingsService = Depends(get_service),
) -> Any:
    _require_user(current_user)
    logs, total = await service.list_push_logs(
        entity_code=entity_code,
        scene_code=scene_code,
        channel=channel,
        status=status,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        data=[PushLogResponse.model_validate(log) for log in logs],
        page=page,
        page_size=page_size,
        total=total,
    )
