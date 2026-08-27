"""偏差（Deviation）API 路由（Q1 拆分自 quality_management.py）。"""

import logging
import uuid
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import (
    AppException,
)
from app.core.response import success_response
from app.modules.quality import repository as repo
from app.modules.quality import service
from app.modules.quality.api.deps import (
    IMPORT_FILE_MAX_SIZE,
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
from app.modules.quality.api.uploads import read_upload_with_limit
from app.modules.quality.schemas import (
    BatchUpdateStatusRequest,
    BatchUpdateStatusResponse,
    CapaListItem,
    CompleteAiAnalysisRequest,
    ConfirmProductionStatusRequest,
    CreateDeviationInvestigationPushRecordRequest,
    CreateDeviationRequest,
    DepartmentWeeklyConfirmationOut,
    DeviationDetail,
    DeviationInvestigationPushRecordDetail,
    DeviationInvestigationPushRecordListItem,
    DeviationListItem,
    DeviationReportRecordListItem,
    SubmitInvestigationRequest,
    SubmitReviewRequest,
    UpdateDeviationInvestigationPushRecordRequest,
    UpdateDeviationRequest,
)
from app.modules.quality.service import quality_import_export as ie_service
from app.modules.quality.service.deviation_ledger_export import (
    generate_deviation_ledger_export_docx,
)
from app.platform.identity.data_scope import resolve_user_department_scope
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/deviations",
    summary="获取偏差列表",
    response_model=ApiResponseEnvelope[list[DeviationListItem]],
)
async def list_deviations(
    status: str | None = None,
    level: str | None = None,
    department: str | None = None,
    keyword: str | None = None,
    deviation_code: str | None = None,
    product_keyword: str | None = None,
    has_occurred_before: bool | None = None,
    is_closed: bool | None = None,
    investigation_completed_from: str | None = None,
    investigation_completed_to: str | None = None,
    root_cause_keyword: str | None = None,
    corrective_actions_keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    assert current_user is not None
    from app.platform.identity.data_scope import resolve_user_department_scope

    scope = await resolve_user_department_scope(db, current_user)
    result = await service.get_deviation_list(
        db,
        status,
        level,
        department,
        keyword,
        deviation_code,
        product_keyword,
        has_occurred_before,
        is_closed,
        investigation_completed_from,
        investigation_completed_to,
        root_cause_keyword,
        corrective_actions_keyword,
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


@router.get("/deviations/export", summary="导出偏差数据")
async def export_deviations(
    status: str | None = None,
    level: str | None = None,
    department: str | None = None,
    keyword: str | None = None,
    deviation_code: str | None = None,
    product_keyword: str | None = None,
    has_occurred_before: bool | None = None,
    is_closed: bool | None = None,
    investigation_completed_from: str | None = None,
    investigation_completed_to: str | None = None,
    root_cause_keyword: str | None = None,
    corrective_actions_keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    assert current_user is not None
    scope = await resolve_user_department_scope(db, current_user)

    deviations, _ = await repo.get_deviations(
        db,
        status=status,
        level=level,
        department=department,
        keyword=keyword,
        page=1,
        page_size=10000,
        scope=scope,
    )

    # Convert Deviation objects to dicts
    items = []
    for d in deviations:
        items.append(
            {
                "deviation_code": d.deviation_code or "",
                "description": d.description or d.title or "",
                "title": d.title or "",
                "has_occurred_before": d.has_occurred_before,
                "previous_occurrence_code": d.previous_occurrence_code,
                "root_cause_analysis": d.root_cause_analysis or "",
                "level": d.level or "",
                "investigation_completed_at": d.investigation_completed_at,
                "corrective_actions": d.corrective_actions or "",
                "material_disposition": d.material_disposition or "",
                # 偏差没有 is_closed 字段，用 status 推断
                "status": d.status or "draft",
                "affected_items": d.affected_items or "",
                "batch_number": d.batch_number or "",
            }
        )

    data = generate_deviation_ledger_export_docx(items)
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_build_docx_download_headers(
            "偏差登记表.docx",
            "deviation-register.docx",
        ),
    )


@router.get(
    "/deviation-report-records",
    summary="获取偏差报告记录列表",
    response_model=ApiResponseEnvelope[list[DeviationReportRecordListItem]],
)
async def list_deviation_report_records_static(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.quality_feishu_pages.list_report_records(
        db,
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
    "/deviation-report-records/{record_id}",
    summary="获取偏差报告记录详情（飞书）",
    response_model=ApiResponseEnvelope[DeviationReportRecordListItem],
)
async def get_deviation_report_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.tracking_records.get_deviation_report_record_from_feishu(
        db, record_id
    )
    return success_response(data=result)


@router.post(
    "/deviation-report-records",
    summary="创建偏差报告记录",
    response_model=ApiResponseEnvelope[DeviationReportRecordListItem],
)
async def create_deviation_report_record(
    data: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.quality_feishu_pages.create_deviation_report_record(db, data)
    return success_response(data=result, message="创建成功")


@router.put(
    "/deviation-report-records/{record_id}",
    summary="更新偏差报告记录",
    response_model=ApiResponseEnvelope[DeviationReportRecordListItem],
)
async def update_deviation_report_record_api(
    record_id: str,
    data: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.quality_feishu_pages.update_deviation_report_record(
        db, record_id, data
    )
    return success_response(data=result, message="更新成功")


@router.delete(
    "/deviation-report-records/{record_id}",
    summary="删除偏差报告记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_deviation_report_record_api(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _require_user(current_user)
    try:
        await service.quality_feishu_pages.delete_deviation_report_record(
            db, record_id, actor_user_id=user_id
        )
        return success_response(data={"success": True}, message="删除成功")
    except AppException:
        raise
    except Exception as e:
        raise AppException(message=f"删除失败: {e}", status_code=500)


@router.patch(
    "/deviations/batch",
    summary="批量更新偏差状态",
    response_model=ApiResponseEnvelope[BatchUpdateStatusResponse],
)
async def batch_update_deviation_status(
    data: BatchUpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.batch_update_status(
        db, data.deviation_ids, data.target_status, user_id
    )
    return success_response(data=result)


@router.get(
    "/deviations/department-confirmations",
    summary="获取部门周确认列表",
    response_model=ApiResponseEnvelope[list[DepartmentWeeklyConfirmationOut]],
)
async def list_department_confirmations(
    week_key: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.get_department_confirmations(db, week_key, page, page_size)
    return success_response(
        data=result["items"],
        meta={
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    )


@router.post(
    "/deviations/department-confirmations",
    summary="确认部门生产状态",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def confirm_department_status(
    data: ConfirmProductionStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.confirm_production_status(db, data, user_id)
    return success_response(data=result)


@router.get(
    "/deviations/stopped-departments",
    summary="获取停产部门列表",
    response_model=ApiResponseEnvelope[list[str]],
)
async def get_stopped_departments(
    week_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    departments = await service.get_stopped_departments(db, week_key)
    return success_response(data=departments)


@router.get(
    "/deviations/{deviation_id}",
    summary="获取偏差详情",
    response_model=ApiResponseEnvelope[DeviationDetail],
)
async def get_deviation(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    detail = await service.get_deviation_detail(db, deviation_id)
    return success_response(data=detail.model_dump())


@router.get(
    "/deviations/{deviation_id}/related-capas",
    summary="获取偏差关联CAPA",
    response_model=ApiResponseEnvelope[list[CapaListItem]],
)
async def get_related_capas(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.get_related_capas_for_deviation(db, deviation_id)
    return success_response(data=result)


@router.post(
    "/deviations",
    summary="创建偏差",
    response_model=ApiResponseEnvelope[DeviationDetail],
)
async def create_deviation(
    data: CreateDeviationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.create_deviation(db, data, user_id)
    return success_response(data=result)


@router.put(
    "/deviations/{deviation_id}",
    summary="更新偏差",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def update_deviation(
    deviation_id: uuid.UUID,
    data: UpdateDeviationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.update_deviation(db, deviation_id, data, user_id)
    return success_response(data=result)


@router.delete(
    "/deviations/{deviation_id}",
    summary="删除偏差",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_deviation(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _require_user(current_user)
    result = await service.delete_deviation(db, deviation_id, deleted_by=user_id)
    return success_response(data=result)


@router.post(
    "/deviations/batch-delete",
    summary="批量删除偏差",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def batch_delete_deviations(
    data: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _require_user(current_user)

    ids = data.get("ids", [])
    if not ids:
        raise AppException(message="请选择要删除的记录")

    deleted = 0
    failed_ids = []

    for id_str in ids:
        try:
            await service.delete_deviation(db, uuid.UUID(id_str), deleted_by=user_id)
            deleted += 1
        except Exception as e:
            logger.warning(f"批量删除偏差失败 id={id_str}: {e}")
            failed_ids.append(id_str)

    return success_response(data={"deleted": deleted, "failed": failed_ids})


@router.post(
    "/deviations/{deviation_id}/submit",
    summary="提交偏差启动审核流程",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def submit_deviation_for_review(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.submit_for_review(db, deviation_id, user_id)
    return success_response(data=result)


@router.post(
    "/deviations/{deviation_id}/complete-ai-analysis",
    summary="完成AI分析",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def complete_ai_analysis(
    deviation_id: uuid.UUID,
    data: CompleteAiAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.complete_ai_analysis(
        db, deviation_id, data.ai_analysis, user_id
    )
    return success_response(data=result)


@router.post(
    "/deviations/{deviation_id}/submit-investigation",
    summary="提交调查报告",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def submit_investigation(
    deviation_id: uuid.UUID,
    data: SubmitInvestigationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.submit_investigation(db, deviation_id, data, user_id)
    return success_response(data=result)


@router.post(
    "/deviations/{deviation_id}/submit-review",
    summary="提交审核意见",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def submit_review(
    deviation_id: uuid.UUID,
    data: SubmitReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.submit_review(db, deviation_id, data, user_id)
    return success_response(data=result)


@router.post(
    "/deviations/{deviation_id}/submit-final-code",
    summary="提交最终编号",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def submit_final_code(
    deviation_id: uuid.UUID,
    final_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.submit_final_code(db, deviation_id, final_code, user_id)
    return success_response(data=result)


@router.post(
    "/deviations/{deviation_id}/resubmit",
    summary="重新提交偏差",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def resubmit_deviation(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.resubmit_deviation(db, deviation_id, user_id)
    return success_response(data=result)


# ============ CAPAs ============


@router.get(
    "/deviation-investigation-push-records",
    summary="获取偏差调查推送记录列表",
    response_model=ApiResponseEnvelope[list[DeviationInvestigationPushRecordListItem]],
)
async def list_deviation_investigation_push_records(
    deviation_id: uuid.UUID | None = None,
    deviation_code: str | None = None,
    push_round: str | None = None,
    submitter: str | None = None,
    department_head_result: str | None = None,
    qa_result: str | None = None,
    qa_head_result: str | None = None,
    submitted_at_from: str | None = None,
    submitted_at_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.get_deviation_investigation_push_record_list(
        db,
        deviation_id=deviation_id,
        deviation_code=deviation_code,
        push_round=push_round,
        submitter=submitter,
        department_head_result=department_head_result,
        qa_result=qa_result,
        qa_head_result=qa_head_result,
        submitted_at_from=submitted_at_from,
        submitted_at_to=submitted_at_to,
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
    "/deviation-investigation-push-records",
    summary="创建偏差调查推送记录",
    response_model=ApiResponseEnvelope[DeviationInvestigationPushRecordDetail],
)
async def create_deviation_investigation_push_record(
    data: CreateDeviationInvestigationPushRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    # Preserve the existing Feishu page write contract used by the migrated
    # page and by legacy clients. The split service remains available for
    # internal workflow operations.
    try:
        result = await service.quality_feishu_pages.create_investigation_push_record(
            db, data.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=400) from exc
    return success_response(data=result)


@router.put(
    "/deviation-investigation-push-records/{record_id}",
    summary="更新偏差调查推送记录",
    response_model=ApiResponseEnvelope[DeviationInvestigationPushRecordDetail],
)
async def update_deviation_investigation_push_record(
    record_id: str,
    data: UpdateDeviationInvestigationPushRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.update_deviation_investigation_push_record(
        db, record_id, data, user_id
    )
    return success_response(data=result)


@router.delete(
    "/deviation-investigation-push-records/{record_id}",
    summary="删除偏差调查推送记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_deviation_investigation_push_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _require_user(current_user)
    try:
        await service.quality_feishu_pages.delete_investigation_push_record(
            db, record_id, actor_user_id=user_id
        )
        return success_response(message="删除成功")
    except AppException:
        raise
    except Exception as e:
        raise AppException(message=f"删除失败: {e}", status_code=500)


@router.post(
    "/deviations/import/preview",
    summary="偏差导入预览",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def preview_deviation_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise AppException(message="请上传 Word 文件 (.docx)")
    content = await read_upload_with_limit(file, IMPORT_FILE_MAX_SIZE, "导入文件")
    result = await ie_service.preview_deviation_import(db, content)
    return success_response(data=result)


@router.post(
    "/deviations/import/confirm",
    summary="确认偏差导入",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def confirm_deviation_import(
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
    result = await ie_service.confirm_deviation_import(
        db, content, skip_duplicates, update_existing
    )
    return success_response(data=result)
