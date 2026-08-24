"""质量 AI 分析 API 路由（Q1 拆分自 quality_management.py）。"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import (
    AppException,
)
from app.core.response import success_response
from app.modules.quality import service
from app.modules.quality.api.deps import (
    current_user_id as _current_user_id,
)
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.api.deps import (
    try_acquire_action_lock,
)
from app.modules.quality.schemas import (
    ApplyDeviationAiSessionRequest,
    DeviationAiSessionAttachmentOut,
    DeviationAiSessionOut,
    QualityAiAnalysisLogOut,
    QualityAiApplyRequest,
    UpdateDeviationAiSessionRequest,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ai/deviations/{deviation_id}/analyze",
    summary="AI分析偏差",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def analyze_deviation_ai(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    try:
        result = await service.analyze_deviation_record(db, deviation_id, user_id)
        return success_response(data=result.model_dump())
    except RuntimeError as e:
        raise AppException(message=str(e), status_code=502)


@router.get(
    "/ai/deviations/{deviation_id}/session",
    summary="获取偏差当前AI会话",
    response_model=ApiResponseEnvelope[DeviationAiSessionOut],
)
async def get_deviation_ai_session(
    deviation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    resolved_id = await service.quality_ai._resolve_deviation_id(db, deviation_id)
    result: DeviationAiSessionOut = await service.get_or_create_deviation_ai_session(
        db, resolved_id
    )
    return success_response(data=result.model_dump(mode="json"))


@router.put(
    "/ai/deviations/{deviation_id}/session",
    summary="更新偏差当前AI会话",
    response_model=ApiResponseEnvelope[DeviationAiSessionOut],
)
async def update_deviation_ai_session(
    deviation_id: str,
    data: UpdateDeviationAiSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    resolved_id = await service.quality_ai._resolve_deviation_id(db, deviation_id)
    result = await service.update_deviation_ai_session(
        db,
        resolved_id,
        data.supplement_text,
        user_id,
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post(
    "/ai/deviations/{deviation_id}/session/attachments",
    summary="上传偏差AI会话附件",
    response_model=ApiResponseEnvelope[DeviationAiSessionAttachmentOut],
)
async def upload_deviation_ai_session_attachment(
    deviation_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    resolved_id = await service.quality_ai._resolve_deviation_id(db, deviation_id)
    result = await service.upload_deviation_ai_session_attachment(
        db,
        resolved_id,
        file,
        user_id,
    )
    return success_response(data=result.model_dump(mode="json"))


@router.delete(
    "/ai/deviations/{deviation_id}/session/attachments/{attachment_id}",
    summary="删除偏差AI会话附件",
    response_model=ApiResponseEnvelope[DeviationAiSessionOut],
)
async def delete_deviation_ai_session_attachment(
    deviation_id: str,
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    resolved_id = await service.quality_ai._resolve_deviation_id(db, deviation_id)
    result = await service.delete_deviation_ai_session_attachment(
        db,
        resolved_id,
        attachment_id,
        user_id,
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post(
    "/ai/deviations/{deviation_id}/session/regenerate",
    summary="重新生成偏差当前AI结果",
    response_model=ApiResponseEnvelope[DeviationAiSessionOut],
)
async def regenerate_deviation_ai_session(
    deviation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    if not await try_acquire_action_lock(f"ai-regenerate:{deviation_id}", timeout=300):
        raise AppException(message="AI 分析正在生成中，请勿重复操作")
    try:
        resolved_id = await service.quality_ai._resolve_deviation_id(db, deviation_id)
        result = await service.regenerate_deviation_ai_session(
            db,
            resolved_id,
            user_id,
        )
        return success_response(data=result.model_dump(mode="json"))
    except RuntimeError as e:
        raise AppException(message=str(e), status_code=502)


@router.post(
    "/ai/deviations/{deviation_id}/session/apply",
    summary="应用偏差当前AI结果",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def apply_deviation_ai_session(
    deviation_id: str,
    data: ApplyDeviationAiSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    resolved_id = await service.quality_ai._resolve_deviation_id(db, deviation_id)
    result = await service.apply_deviation_ai_session(
        db,
        resolved_id,
        data.section,
        data.field_keys,
        user_id,
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post(
    "/ai/deviations/{deviation_id}/suggest-capa",
    summary="AI生成偏差CAPA建议",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def suggest_deviation_capa_ai(
    deviation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    try:
        resolved_id = await service.quality_ai._resolve_deviation_id(db, deviation_id)
        result = await service.suggest_capa_for_deviation(db, resolved_id, user_id)
        return success_response(data=result.model_dump())
    except RuntimeError as e:
        raise AppException(message=str(e), status_code=502)


@router.post(
    "/ai/capas/{capa_id}/analyze",
    summary="AI分析CAPA",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def analyze_capa_ai(
    capa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    try:
        result = await service.analyze_capa_record(db, capa_id, user_id)
        return success_response(data=result.model_dump())
    except RuntimeError as e:
        raise AppException(message=str(e), status_code=502)


@router.post(
    "/ai/changes/{change_id}/analyze",
    summary="AI分析变更",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def analyze_change_ai(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    try:
        result = await service.analyze_change_record(db, change_id, user_id)
        return success_response(data=result.model_dump())
    except RuntimeError as e:
        raise AppException(message=str(e), status_code=502)


@router.get(
    "/ai/logs",
    summary="获取AI分析日志",
    response_model=ApiResponseEnvelope[list[QualityAiAnalysisLogOut]],
)
async def list_ai_logs(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.list_ai_logs(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data=result["items"],
        meta={
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    )


@router.get(
    "/ai/logs/{log_id}",
    summary="获取AI分析日志详情",
    response_model=ApiResponseEnvelope[QualityAiAnalysisLogOut],
)
async def get_ai_log(
    log_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.get_ai_log_detail(db, log_id)
    return success_response(data=result.model_dump())


@router.post(
    "/ai/logs/{log_id}/apply",
    summary="应用AI建议到字段",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def apply_ai_log(
    log_id: uuid.UUID,
    data: QualityAiApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.apply_ai_log(db, log_id, data.field_keys, user_id)
    return success_response(data=result.model_dump())
