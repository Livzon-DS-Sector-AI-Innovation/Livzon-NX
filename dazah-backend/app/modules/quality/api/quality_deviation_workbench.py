"""偏差工作台 API 路由。"""

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
    try_acquire_action_lock,
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
    CreateDeviationWorkbenchRequest,
    DeviationWorkbenchAttachmentIn,
    DeviationWorkbenchReportDetail,
    DeviationWorkbenchReportListItem,
    DeviationWorkbenchSettingsOut,
    UpdateDeviationWorkbenchSettingsRequest,
)
from app.modules.quality.service.deviation_workbench import (
    analyze_workbench,
    delete_workbench_attachment_files,
    delete_workbench_report,
    get_workbench_report_detail,
    get_workbench_settings,
    list_workbench_reports,
    read_workbench_attachment_content,
    update_workbench_settings,
    upload_workbench_attachment,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/deviation-workbench/settings",
    summary="获取偏差工作台提示词设置",
    response_model=ApiResponseEnvelope[DeviationWorkbenchSettingsOut],
)
async def get_deviation_workbench_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await get_workbench_settings(db)
    return success_response(data=result.model_dump(mode="json"))


@router.put(
    "/deviation-workbench/settings",
    summary="更新偏差工作台提示词设置",
    response_model=ApiResponseEnvelope[DeviationWorkbenchSettingsOut],
)
async def update_deviation_workbench_settings(
    data: UpdateDeviationWorkbenchSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    result = await update_workbench_settings(db, data, user_id)
    return success_response(data=result.model_dump(mode="json"), message="设置已更新")


@router.post(
    "/deviation-workbench/attachments",
    summary="上传偏差工作台附件（返回描述符供生成时引用）",
    response_model=ApiResponseEnvelope[DeviationWorkbenchAttachmentIn],
)
async def upload_deviation_workbench_attachment(
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
    result = await upload_workbench_attachment(db, file, user_id)
    return success_response(data=result.model_dump(mode="json"), message="上传成功")


@router.delete(
    "/deviation-workbench/attachments",
    summary="清理未消费的工作台附件对象（原件+转换MD+图片资产）",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_deviation_workbench_attachments(
    keys: list[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    delete_workbench_attachment_files(keys)
    return success_response(data={"deleted": len(keys)}, message="已清理")


@router.post(
    "/deviation-workbench/analyze",
    summary="生成偏差调查报告",
    response_model=ApiResponseEnvelope[DeviationWorkbenchReportDetail],
)
async def analyze_deviation_workbench(
    data: CreateDeviationWorkbenchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    if not await try_acquire_action_lock(f"workbench-analyze:{user_id}", timeout=300):
        raise AppException(message="调查报告正在生成中，请勿重复操作")
    try:
        result = await analyze_workbench(db, data, user_id)
    finally:
        from app.modules.quality.api.deps import release_action_lock

        await release_action_lock(f"workbench-analyze:{user_id}")
    return success_response(data=result.model_dump(mode="json"))


@router.get(
    "/deviation-workbench/reports",
    summary="获取偏差工作台记录台账",
    response_model=ApiResponseEnvelope[list[DeviationWorkbenchReportListItem]],
)
async def list_deviation_workbench_reports(
    keyword: str | None = Query(None, description="关键字（编号/偏差摘要/报告正文）"),
    source_type: str | None = Query(None, description="信息来源：report_record/manual"),
    status: str | None = Query(None, description="状态：processing/completed/failed"),
    date_from: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    date_to: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await list_workbench_reports(
        db,
        keyword=keyword,
        source_type=source_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return success_response(
        data=[item.model_dump(mode="json") for item in result["items"]],
        meta={
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    )


@router.get(
    "/deviation-workbench/reports/{report_id}",
    summary="获取偏差工作台记录详情",
    response_model=ApiResponseEnvelope[DeviationWorkbenchReportDetail],
)
async def get_deviation_workbench_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await get_workbench_report_detail(db, report_id)
    return success_response(data=result.model_dump(mode="json"))


@router.delete(
    "/deviation-workbench/reports/{report_id}",
    summary="删除偏差工作台记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_deviation_workbench_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    await delete_workbench_report(db, report_id, user_id)
    return success_response(data={"success": True}, message="删除成功")


@router.get(
    "/deviation-workbench/attachments/{storage_key:path}/content",
    summary="偏差工作台附件内容（word 返回标准 MD；图片/PDF 返回原文件）",
)
async def get_deviation_workbench_attachment_content(
    storage_key: str,
    current_user: CurrentUser = None,
) -> Response:
    _require_user(current_user)
    data, content_type = read_workbench_attachment_content(storage_key)
    if not data:
        raise AppException(status_code=404, message="附件内容不存在")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
