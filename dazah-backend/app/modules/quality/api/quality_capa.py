"""CAPA 与 CAPA 计划跟踪 API 路由（Q1 拆分自 quality_management.py）。"""

import logging
import uuid
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import (
    AppException,
)
from app.core.response import success_response
from app.modules.quality import service
from app.modules.quality.api.deps import (
    IMPORT_FILE_MAX_SIZE,
    QUALITY_QA_SCOPE_PERMISSIONS,
)
from app.modules.quality.api.deps import (
    assert_quality_edit_scope as _assert_quality_edit_scope,
)
from app.modules.quality.api.deps import (
    build_docx_download_headers as _build_docx_download_headers,
)
from app.modules.quality.api.deps import (
    current_user_id as _current_user_id,
)
from app.modules.quality.api.deps import (
    require_user as _require_user,
)
from app.modules.quality.api.deps import (
    resolve_quality_list_scope as _resolve_quality_list_scope,
)
from app.modules.quality.api.uploads import read_upload_with_limit
from app.modules.quality.schemas import (
    CapaApprovalRequest,
    CapaAutoFillFromDeviation,
    CapaDeptHeadConfirmRequest,
    CapaDetail,
    CapaEvaluationRequest,
    CapaListItem,
    CapaPlanTrackDetail,
    CapaPlanTrackListItem,
    CompletePartRequest,
    CreateCapaPlanTrackRequest,
    CreateCapaRequest,
    ExecutionTrack,
    LinkDeviationRequest,
    UpdateCapaPlanTrackRequest,
    UpdateCapaRequest,
)
from app.modules.quality.service import quality_import_export as ie_service
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/capa-plan-tracks",
    summary="获取CAPA计划跟踪列表",
    response_model=ApiResponseEnvelope[list[CapaPlanTrackListItem]],
)
async def list_capa_plan_tracks(
    capa_id: uuid.UUID | None = None,
    capa_code: str | None = None,
    progress: str | None = None,
    owner_name: str | None = None,
    reminder_status: str | None = None,
    due_date_from: str | None = None,
    due_date_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.get_capa_plan_track_list(
        db,
        capa_id=capa_id,
        capa_code=capa_code,
        progress=progress,
        owner_name=owner_name,
        reminder_status=reminder_status,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
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


@router.post(
    "/capa-plan-tracks",
    summary="创建CAPA计划跟踪",
    response_model=ApiResponseEnvelope[CapaPlanTrackDetail],
)
async def create_capa_plan_track(
    data: CreateCapaPlanTrackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.create_capa_plan_track(db, data, user_id)
    return success_response(data=result)


@router.put(
    "/capa-plan-tracks/{track_id}",
    summary="更新CAPA计划跟踪",
    response_model=ApiResponseEnvelope[CapaPlanTrackDetail],
)
async def update_capa_plan_track(
    track_id: uuid.UUID,
    data: UpdateCapaPlanTrackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    result = await service.update_capa_plan_track(db, track_id, data, user_id)
    return success_response(data=result)


@router.delete(
    "/capa-plan-tracks/{track_id}",
    summary="删除CAPA计划跟踪",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_capa_plan_track(
    track_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    await service.delete_capa_plan_track(db, track_id)
    return success_response(message="删除成功")


@router.get(
    "/capas",
    summary="获取CAPA列表",
    response_model=ApiResponseEnvelope[list[CapaListItem]],
)
async def list_capas(
    status: str | None = None,
    source: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
    capa_code: str | None = None,
    affected_product: str | None = None,
    source_code: str | None = None,
    evaluation_result: str | None = None,
    closure_date_from: str | None = None,
    closure_date_to: str | None = None,
    department: str | None = None,
    qa_confirmer: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    assert current_user is not None
    scope = await _resolve_quality_list_scope(db, current_user)
    result = await service.get_capa_list(
        db,
        status,
        source,
        category,
        keyword,
        capa_code,
        affected_product,
        source_code,
        evaluation_result,
        closure_date_from,
        closure_date_to,
        department,
        qa_confirmer,
        page,
        page_size,
        scope=scope,
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
    "/capas/departments",
    summary="获取所有部门列表",
    response_model=ApiResponseEnvelope[list[str]],
)
async def get_capa_departments(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    departments = await service.get_capa_departments(db)
    return success_response(data=departments)


@router.get(
    "/capas/auto-fill/{deviation_id}",
    summary="从偏差自动填充CAPA表单",
    response_model=ApiResponseEnvelope[CapaAutoFillFromDeviation],
)
async def auto_fill_capa_from_deviation(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.auto_fill_from_deviation(db, deviation_id)
    return success_response(data=result)


@router.get(
    "/capas/{capa_id}",
    summary="获取CAPA详情",
    response_model=ApiResponseEnvelope[CapaDetail],
)
async def get_capa(
    capa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    detail = await service.get_capa_detail(db, capa_id)
    return success_response(data=detail.model_dump())


@router.post(
    "/capas", summary="创建CAPA", response_model=ApiResponseEnvelope[CapaDetail]
)
async def create_capa(
    data: CreateCapaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.create_capa(db, data, user_id)
    return success_response(data=result)


@router.put(
    "/capas/{capa_id}",
    summary="更新CAPA",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def update_capa(
    capa_id: uuid.UUID,
    data: UpdateCapaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    result = await service.update_capa(db, capa_id, data, user_id)
    return success_response(data=result)


@router.delete(
    "/capas/{capa_id}",
    summary="删除CAPA",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_capa(
    capa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )
    result = await service.delete_capa(db, capa_id, deleted_by=user_id)
    return success_response(data=result)


@router.post(
    "/capas/batch-delete",
    summary="批量删除CAPA",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def batch_delete_capas(
    data: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["system_qa"],
    )

    ids = data.get("ids", [])
    if not ids:
        raise AppException(message="请选择要删除的记录")

    deleted = 0
    failed_ids = []

    for id_str in ids:
        try:
            await service.delete_capa(db, uuid.UUID(id_str), deleted_by=user_id)
            deleted += 1
        except Exception as e:
            logger.warning(f"批量删除CAPA失败 id={id_str}: {e}")
            failed_ids.append(id_str)

    return success_response(data={"deleted": deleted, "failed": failed_ids})


@router.post(
    "/capas/{capa_id}/link-deviation",
    summary="关联偏差到CAPA",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def link_capa_to_deviation(
    capa_id: uuid.UUID,
    data: LinkDeviationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.link_deviation(
        db, capa_id, uuid.UUID(str(data.deviation_id)), user_id
    )
    return success_response(data=result)


@router.post(
    "/capas/{capa_id}/complete-part",
    summary="完成CAPA部分",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def complete_capa_part(
    capa_id: uuid.UUID,
    data: CompletePartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.complete_part(db, capa_id, data.part, user_id)
    return success_response(data=result)


@router.post(
    "/capas/{capa_id}/submit",
    summary="提交CAPA审核",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def submit_capa_for_review(
    capa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.submit_capa(db, capa_id, user_id)
    return success_response(data=result)


@router.post(
    "/capas/{capa_id}/confirm-dept-head",
    summary="部门主管确认CAPA",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def confirm_capa_by_dept_head(
    capa_id: uuid.UUID,
    data: CapaDeptHeadConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.confirm_dept_head(db, capa_id, data, user_id)
    return success_response(data=result)


@router.post(
    "/capas/{capa_id}/approve",
    summary="QA审批CAPA",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def approve_capa(
    capa_id: uuid.UUID,
    data: CapaApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.approve_capa(db, capa_id, data, user_id)
    return success_response(data=result)


@router.post(
    "/capas/{capa_id}/resubmit",
    summary="重新提交CAPA",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def resubmit_capa(
    capa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.resubmit_capa(db, capa_id, user_id)
    return success_response(data=result)


@router.post(
    "/capas/{capa_id}/add-execution-track",
    summary="添加CAPA执行记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def add_capa_execution_track(
    capa_id: uuid.UUID,
    data: ExecutionTrack,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.add_execution_track(db, capa_id, data.model_dump(), user_id)
    return success_response(data=result)


@router.post(
    "/capas/{capa_id}/delete-execution-track",
    summary="删除CAPA执行记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_capa_execution_track(
    capa_id: uuid.UUID,
    index: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.delete_execution_track(db, capa_id, index, user_id)
    return success_response(data=result)


@router.post(
    "/capas/{capa_id}/confirm-execution",
    summary="确认CAPA执行完成",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def confirm_capa_execution(
    capa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.confirm_execution(db, capa_id, user_id)
    return success_response(data=result)


@router.post(
    "/capas/{capa_id}/submit-evaluation",
    summary="提交CAPA效果评价",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def submit_capa_evaluation(
    capa_id: uuid.UUID,
    data: CapaEvaluationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.submit_evaluation(db, capa_id, data, user_id)
    return success_response(data=result)


# ============ Department Contacts ============


@router.post(
    "/capas/sync-from-feishu",
    summary="从飞书同步CAPA台账",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def sync_capas_from_feishu(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    result = await service.quality_feishu_pages.sync_capas_from_feishu(db)
    return success_response(data=result)


@router.post(
    "/capa-plan-tracks/sync-from-feishu",
    summary="从飞书同步CAPA计划跟踪",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def sync_capa_plan_tracks_from_feishu(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    result = await service.quality_feishu_pages.sync_capa_plan_tracks_from_feishu(db)
    return success_response(data=result)


@router.post(
    "/capas/import/preview",
    summary="CAPA导入预览",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def preview_capa_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise AppException(message="请上传 Word 文件 (.docx)")
    content = await read_upload_with_limit(file, IMPORT_FILE_MAX_SIZE, "导入文件")
    result = await ie_service.preview_capa_import(db, content)
    return success_response(data=result)


@router.post(
    "/capas/import/confirm",
    summary="确认 CAPA 导入",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def confirm_capa_import(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="是否跳过重复记录"),
    update_existing: bool = Query(False, description="是否更新已存在记录"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise AppException(message="请上传 Word 文件 (.docx)")
    content = await read_upload_with_limit(file, IMPORT_FILE_MAX_SIZE, "导入文件")
    result = await ie_service.confirm_capa_import(
        db, content, skip_duplicates, update_existing
    )
    return success_response(data=result)


@router.get("/capas/export/template", summary="下载CAPA导入模板")
async def export_capa_template(
    current_user: CurrentUser = None,
) -> StreamingResponse:
    _require_user(current_user)
    import io
    import urllib.parse

    buffer = ie_service.export_capas_template()
    filename = urllib.parse.quote("CAPA导入模板.docx")
    return StreamingResponse(
        io.BytesIO(buffer),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/capas/export", summary="导出CAPA数据")
async def export_capas(
    status: str | None = None,
    source: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
    capa_code: str | None = None,
    affected_product: str | None = None,
    source_code: str | None = None,
    evaluation_result: str | None = None,
    closure_date_from: str | None = None,
    closure_date_to: str | None = None,
    department: str | None = None,
    qa_confirmer: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    data = await ie_service.export_capas(
        db,
        None,
        status,
        source,
        category,
        keyword,
        capa_code,
        affected_product,
        source_code,
        evaluation_result,
        closure_date_from,
        closure_date_to,
        department,
        qa_confirmer,
    )
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_build_docx_download_headers(
            "CAPA登记汇总表.docx",
            "capa-register.docx",
        ),
    )


# ============ Deviation Import/Export ============
