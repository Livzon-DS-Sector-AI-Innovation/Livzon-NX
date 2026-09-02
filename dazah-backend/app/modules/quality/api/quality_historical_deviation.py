"""历史偏差 API 路由。"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.response import success_response
from app.modules.quality.api.deps import (
    QUALITY_QA_SCOPE_PERMISSIONS,
)
from app.modules.quality.api.deps import (
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import (
    current_user_id as _current_user_id,
)
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.schemas import (
    CreateHistoricalDeviationRequest,
    HistoricalDeviationAttachmentOut,
    HistoricalDeviationDetail,
    HistoricalDeviationListItem,
    UpdateHistoricalDeviationRequest,
)
from app.modules.quality.service.historical_deviation import (
    ai_extract_historical_deviation,
    create_historical_deviation,
    delete_historical_deviation,
    delete_historical_deviation_attachment,
    get_historical_deviation_attachment_content,
    get_historical_deviation_detail,
    get_historical_deviation_list,
    update_historical_deviation,
    upload_historical_deviation_attachment,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/historical-deviations",
    summary="获取历史偏差列表",
    response_model=ApiResponseEnvelope[list[HistoricalDeviationListItem]],
)
async def list_historical_deviations(
    keyword: str | None = Query(
        None, description="关键字（编号/偏差事件/偏差内容/调查结论）"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await get_historical_deviation_list(
        db, keyword=keyword, page=page, page_size=page_size
    )
    return success_response(
        data=[item.model_dump(mode="json") for item in result["items"]],
        meta={
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    )


@router.post(
    "/historical-deviations",
    summary="创建历史偏差",
    response_model=ApiResponseEnvelope[HistoricalDeviationDetail],
)
async def create_historical_deviation_api(
    data: CreateHistoricalDeviationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    result = await create_historical_deviation(db, data, user_id)
    return success_response(data=result.model_dump(mode="json"), message="创建成功")


@router.get(
    "/historical-deviations/{record_id}",
    summary="获取历史偏差详情",
    response_model=ApiResponseEnvelope[HistoricalDeviationDetail],
)
async def get_historical_deviation_api(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await get_historical_deviation_detail(db, record_id)
    return success_response(data=result.model_dump(mode="json"))


@router.put(
    "/historical-deviations/{record_id}",
    summary="更新历史偏差",
    response_model=ApiResponseEnvelope[HistoricalDeviationDetail],
)
async def update_historical_deviation_api(
    record_id: uuid.UUID,
    data: UpdateHistoricalDeviationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    result = await update_historical_deviation(db, record_id, data, user_id)
    return success_response(data=result.model_dump(mode="json"), message="更新成功")


@router.delete(
    "/historical-deviations/{record_id}",
    summary="删除历史偏差",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_historical_deviation_api(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    await delete_historical_deviation(db, record_id, user_id)
    return success_response(data={"success": True}, message="删除成功")


@router.post(
    "/historical-deviations/{record_id}/attachments",
    summary="上传历史偏差附件（word 自动转标准 MD）",
    response_model=ApiResponseEnvelope[HistoricalDeviationAttachmentOut],
)
async def upload_historical_deviation_attachment_api(
    record_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    result = await upload_historical_deviation_attachment(db, record_id, file, user_id)
    return success_response(data=result.model_dump(mode="json"), message="上传成功")


@router.delete(
    "/historical-deviations/{record_id}/attachments/{attachment_id}",
    summary="删除历史偏差附件",
    response_model=ApiResponseEnvelope[HistoricalDeviationDetail],
)
async def delete_historical_deviation_attachment_api(
    record_id: uuid.UUID,
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    result = await delete_historical_deviation_attachment(
        db, record_id, attachment_id, user_id
    )
    return success_response(data=result.model_dump(mode="json"), message="删除成功")


@router.get(
    "/historical-deviations/{record_id}/attachments/{storage_key:path}/content",
    summary="历史偏差附件内容（word 返回标准 MD；图片/PDF 返回原文件）",
)
async def get_historical_deviation_attachment_content_api(
    record_id: uuid.UUID,
    storage_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Response:
    _require_user(current_user)
    data, content_type = await get_historical_deviation_attachment_content(
        db, record_id, storage_key
    )
    if not data:
        raise AppException(status_code=404, message="附件内容不存在")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post(
    "/historical-deviations/{record_id}/ai-extract",
    summary="AI 提取历史偏差字段（偏差事件/偏差内容/调查结论）",
    response_model=ApiResponseEnvelope[HistoricalDeviationDetail],
)
async def ai_extract_historical_deviation_api(
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    result = await ai_extract_historical_deviation(db, record_id, user_id)
    return success_response(data=result.model_dump(mode="json"), message="AI 提取完成")
