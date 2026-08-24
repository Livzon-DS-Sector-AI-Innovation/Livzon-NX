"""Quality management API endpoints."""

import uuid
from io import BytesIO
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.upload_security import read_upload_secure
from app.modules.quality import service
from app.modules.quality.schemas import (
    ApplyDeviationAiSessionRequest,
    BatchUpdateStatusRequest,
    CapaApprovalRequest,
    CapaDeptHeadConfirmRequest,
    CapaEvaluationRequest,
    CompleteAiAnalysisRequest,
    CompletePartRequest,
    ConfirmProductionStatusRequest,
    CreateAttachmentReviewRequest,
    CreateCapaPlanTrackRequest,
    CreateCapaRequest,
    CreateChangeActionPlanRequest,
    CreateChangeRequest,
    CreateDepartmentContactRequest,
    CreateDeviationInvestigationPushRecordRequest,
    CreateDeviationRequest,
    DeviationAiSessionOut,
    ExecutionTrack,
    LinkDeviationRequest,
    QualityAiApplyRequest,
    QualityFeishuAppSettingsDetail,
    QualityFeishuEntityFieldMappingBundle,
    QualityFeishuEntitySettingItem,
    QualityFeishuSettingsTestResult,
    QualityFeishuTableOption,
    SubmitInvestigationRequest,
    SubmitReviewRequest,
    UpdateCapaPlanTrackRequest,
    UpdateCapaRequest,
    UpdateChangeActionPlanRequest,
    UpdateChangeRequest,
    UpdateDepartmentContactRequest,
    UpdateDeviationAiSessionRequest,
    UpdateDeviationRequest,
    UpdateQualityFeishuAppSettingsRequest,
    UpdateQualityFeishuEntitySettingRequest,
)
from app.modules.quality.service import (
    change_ledger_export,
    deviation_ledger_export,
    quality_feishu_pages,
)
from app.modules.quality.service import quality_import_export as ie_service
from app.platform.identity.deps import CurrentUser

router = APIRouter()


def _build_docx_download_headers(
    filename_utf8: str, fallback_ascii: str
) -> dict[str, str]:
    encoded = quote(filename_utf8)
    return {
        "Content-Disposition": (
            f"attachment; filename={fallback_ascii}; filename*=UTF-8''{encoded}"
        )
    }


async def _resolve_change_export_items(
    db: AsyncSession,
    scope: Literal["single", "selected", "filtered"],
    change_id: uuid.UUID | None,
    change_ids: list[uuid.UUID] | None,
    change_code: str | None,
    applicant_department: str | None,
    change_object: str | None,
    change_level: str | None,
    application_date_from: str | None,
    application_date_to: str | None,
    planned_approval_date_from: str | None,
    planned_approval_date_to: str | None,
    execution_date_from: str | None,
    execution_date_to: str | None,
    closure_date_from: str | None,
    closure_date_to: str | None,
    content_keyword: str | None,
) -> list[dict[str, Any]]:
    if scope == "single":
        if change_id is None:
            raise HTTPException(
                status_code=400, detail="scope=single 时必须提供 change_id"
            )
        detail = await service.get_change_detail(db, change_id)
        return [detail.model_dump(mode="json")]

    if scope == "selected":
        if not change_ids:
            raise HTTPException(
                status_code=400, detail="scope=selected 时必须提供 change_ids"
            )
        items: list[dict[str, Any]] = []
        for selected_change_id in change_ids:
            detail = await service.get_change_detail(db, selected_change_id)
            items.append(detail.model_dump(mode="json"))
        return items

    result = await service.get_change_list(
        db,
        change_code,
        None,
        applicant_department,
        change_object,
        change_level,
        application_date_from,
        application_date_to,
        planned_approval_date_from,
        planned_approval_date_to,
        execution_date_from,
        execution_date_to,
        closure_date_from,
        closure_date_to,
        content_keyword,
        1,
        10000,
    )
    raw_items = result["items"]
    return [dict(item) for item in raw_items if isinstance(item, dict)]


def _build_change_export_filename(
    scope: Literal["single", "selected", "filtered"], items: list[dict[str, Any]]
) -> tuple[str, str]:
    if scope == "single" and items:
        change_code = (items[0].get("change_code") or "change-ledger").strip()
        return f"{change_code}.docx", f"{change_code}.docx"
    return "变更管理台账.docx", "change-controls.docx"


# ============ Deviations ============


@router.get("/deviations", summary="获取偏差列表")
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
) -> Any:
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
    )
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.get("/deviations/report-records", summary="获取偏差报告记录列表")
async def list_deviation_report_records(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.get_deviation_report_record_list(
        db,
        page=page,
        page_size=page_size,
    )
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.get("/deviation-report-records", summary="获取偏差报告记录列表")
async def list_deviation_report_records_static(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await quality_feishu_pages.list_report_records(
        db,
        page=page,
        page_size=page_size,
    )
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.post(
    "/deviation-report-records/{record_id}/ensure-deviation",
    summary="按飞书报告记录准备平台偏差供AI工作台使用",
)
async def ensure_deviation_from_report_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.ensure_deviation_from_report_record(db, record_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/deviations/batch", summary="批量更新偏差状态")
async def batch_update_deviation_status(
    data: BatchUpdateStatusRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    result = await service.batch_update_status(
        db, data.deviation_ids, data.target_status, "system"
    )
    return {"data": result}


@router.get("/deviations/department-confirmations", summary="获取部门周确认列表")
async def list_department_confirmations(
    week_key: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.get_department_confirmations(db, week_key, page, page_size)
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.post("/deviations/department-confirmations", summary="确认部门生产状态")
async def confirm_department_status(
    data: ConfirmProductionStatusRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    result = await service.confirm_production_status(db, data, "system")
    return {"data": result}


@router.get("/deviations/stopped-departments", summary="获取停产部门列表")
async def get_stopped_departments(
    week_key: str, db: AsyncSession = Depends(get_db)
) -> Any:
    departments = await service.get_stopped_departments(db, week_key)
    return {"data": departments}


@router.get("/deviations/{deviation_id}", summary="获取偏差详情")
async def get_deviation(
    deviation_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        detail = await service.get_deviation_detail(db, deviation_id)
        return {"data": detail.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/deviations/{deviation_id}/related-capas", summary="获取偏差关联CAPA")
async def get_related_capas(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.get_related_capas_for_deviation(db, deviation_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/deviations", summary="创建偏差")
async def create_deviation(
    data: CreateDeviationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    try:
        result = await service.create_deviation(
            db,
            data,
            str(current_user.id) if current_user else "system",
            current_user,
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/deviations/{deviation_id}", summary="更新偏差")
async def update_deviation(
    deviation_id: uuid.UUID,
    data: UpdateDeviationRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.update_deviation(db, deviation_id, data, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/deviations/{deviation_id}", summary="删除偏差")
async def delete_deviation(
    deviation_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.delete_deviation(db, deviation_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/deviations/batch-delete", summary="批量删除偏差")
async def batch_delete_deviations(
    data: dict[str, Any], db: AsyncSession = Depends(get_db)
) -> Any:
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的记录")
    deleted = 0
    for id_str in ids:
        try:
            await service.delete_deviation(db, uuid.UUID(id_str))
            deleted += 1
        except Exception:
            pass
    return {"data": {"deleted": deleted}}


@router.post("/deviations/{deviation_id}/submit", summary="提交偏差启动审核流程")
async def submit_deviation_for_review(
    deviation_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.submit_for_review(db, deviation_id, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deviations/{deviation_id}/complete-ai-analysis", summary="完成AI分析")
async def complete_ai_analysis(
    deviation_id: uuid.UUID,
    data: CompleteAiAnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.complete_ai_analysis(
            db, deviation_id, data.ai_analysis, "system"
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deviations/{deviation_id}/submit-investigation", summary="提交调查报告")
async def submit_investigation(
    deviation_id: uuid.UUID,
    data: SubmitInvestigationRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.submit_investigation(db, deviation_id, data, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deviations/{deviation_id}/submit-review", summary="提交审核意见")
async def submit_review(
    deviation_id: uuid.UUID,
    data: SubmitReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.submit_review(db, deviation_id, data, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deviations/{deviation_id}/submit-final-code", summary="提交最终编号")
async def submit_final_code(
    deviation_id: uuid.UUID, final_code: str, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.submit_final_code(db, deviation_id, final_code, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deviations/{deviation_id}/resubmit", summary="重新提交偏差")
async def resubmit_deviation(
    deviation_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.resubmit_deviation(db, deviation_id, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ CAPAs ============


@router.get("/changes", summary="获取变更列表")
async def list_changes(
    change_code: str | None = None,
    applicant_department: str | None = None,
    change_object: str | None = None,
    change_level: str | None = None,
    application_date_from: str | None = None,
    application_date_to: str | None = None,
    planned_approval_date_from: str | None = None,
    planned_approval_date_to: str | None = None,
    execution_date_from: str | None = None,
    execution_date_to: str | None = None,
    closure_date_from: str | None = None,
    closure_date_to: str | None = None,
    content_keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.get_change_list(
        db,
        change_code,
        None,
        applicant_department,
        change_object,
        change_level,
        application_date_from,
        application_date_to,
        planned_approval_date_from,
        planned_approval_date_to,
        execution_date_from,
        execution_date_to,
        closure_date_from,
        closure_date_to,
        content_keyword,
        page,
        page_size,
    )
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.get("/change-action-plans", summary="获取变更计划列表", response_model=None)
async def list_change_action_plans(
    change_id: uuid.UUID | None = None,
    change_code: str | None = None,
    project_name: str | None = None,
    related_work: str | None = None,
    owner_name: str | None = None,
    director_name: str | None = None,
    status: str | None = None,
    delay_flag: str | None = None,
    sync_status: str | None = None,
    deadline_date_from: str | None = None,
    deadline_date_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.get_change_action_plan_list(
        db,
        change_id=change_id,
        change_code=change_code,
        project_name=project_name,
        related_work=related_work,
        owner_name=owner_name,
        director_name=director_name,
        status=status,
        delay_flag=delay_flag,
        sync_status=sync_status,
        deadline_date_from=deadline_date_from,
        deadline_date_to=deadline_date_to,
        page=page,
        page_size=page_size,
    )
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.post("/change-action-plans", summary="创建变更计划")
async def create_change_action_plan(
    data: CreateChangeActionPlanRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.create_change_action_plan_record(db, data, "system")
    return {"data": result}


@router.get("/change-action-plans/person-options", summary="搜索变更计划人员候选")
async def search_change_action_plan_persons(
    keyword: str = Query(..., min_length=1, description="姓名/手机号/邮箱关键词"),
    limit: int = Query(20, ge=1, le=50, description="返回条数"),
) -> Any:
    try:
        result = await service.search_change_action_plan_person_options(keyword, limit)
        return {"data": [item.model_dump() for item in result]}
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/change-action-plans/sync-from-feishu", summary="从飞书同步变更计划")
async def sync_change_action_plans_from_feishu(
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.sync_change_action_plans_from_feishu(db, "system")
        return {"data": result.model_dump()}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/change-action-plans/reminders/run", summary="立即执行变更计划提醒")
async def run_change_action_plan_reminders(
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.run_change_action_plan_reminders_now(db)
    return {"data": result.model_dump()}


@router.put("/change-action-plans/{plan_id}", summary="更新变更计划")
async def update_change_action_plan(
    plan_id: uuid.UUID,
    data: UpdateChangeActionPlanRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.update_change_action_plan_record(
            db, plan_id, data, "system"
        )
        return {"data": result}
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


@router.post(
    "/change-action-plans/{plan_id}/reminders/send", summary="手动发送单条变更计划提醒"
)
async def send_change_action_plan_reminder(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.send_change_action_plan_reminder_for_plan(db, plan_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/change-action-plans/{plan_id}/reminders/confirm", summary="确认变更计划提醒"
)
async def confirm_change_action_plan_reminder(
    plan_id: uuid.UUID,
    confirmed_by: str = Query("系统确认", description="确认人"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.confirm_change_action_plan_reminder(
            db,
            plan_id,
            confirmed_by=confirmed_by,
        )
        return {"data": result.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/change-action-plans/{plan_id}/reminders/confirm-page",
    summary="飞书确认变更计划提醒",
    response_class=HTMLResponse,
)
async def confirm_change_action_plan_reminder_page(
    plan_id: uuid.UUID,
    confirmed_by: str = Query("飞书确认", description="确认人"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        html_content = (
            await service.render_change_action_plan_reminder_confirmation_page(
                db,
                plan_id,
                confirmed_by=confirmed_by,
            )
        )
        return HTMLResponse(content=html_content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/change-action-plans/{plan_id}", summary="删除变更计划")
async def delete_change_action_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.delete_change_action_plan_record(db, plan_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/deviation-investigation-push-records", summary="获取偏差调查推送记录列表")
async def list_deviation_investigation_push_records(
    deviation_id: str | None = None,
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
) -> Any:
    result = await quality_feishu_pages.list_investigation_push_records(
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
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.post("/deviation-investigation-push-records", summary="创建偏差调查推送记录")
async def create_deviation_investigation_push_record(
    data: CreateDeviationInvestigationPushRecordRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await quality_feishu_pages.create_investigation_push_record(
            db,
            data.model_dump(exclude_none=True),
        )
        return {"data": result}
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


@router.put(
    "/deviation-investigation-push-records/{record_id}", summary="更新偏差调查推送记录"
)
async def update_deviation_investigation_push_record(
    record_id: str,
    data: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await quality_feishu_pages.update_investigation_push_record(
            db,
            record_id,
            data,
        )
        return {"data": result}
    except ValueError as e:
        detail = str(e)
        status_code = 404 if "不存在" in detail or "not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail)


@router.delete(
    "/deviation-investigation-push-records/{record_id}", summary="删除偏差调查推送记录"
)
async def delete_deviation_investigation_push_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        await quality_feishu_pages.delete_investigation_push_record(db, record_id)
        return {"data": {"success": True}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/deviation-ledger-records", summary="获取偏差台账飞书列表")
async def list_deviation_ledger_records(
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
) -> Any:
    result = await quality_feishu_pages.list_deviation_ledger_records(
        db,
        keyword=keyword,
        deviation_code=deviation_code,
        product_keyword=product_keyword,
        has_occurred_before=has_occurred_before,
        is_closed=is_closed,
        investigation_completed_from=investigation_completed_from,
        investigation_completed_to=investigation_completed_to,
        root_cause_keyword=root_cause_keyword,
        corrective_actions_keyword=corrective_actions_keyword,
        page=page,
        page_size=page_size,
    )
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.get("/deviation-ledger-records/export", summary="导出偏差台账飞书数据")
async def export_deviation_ledger_records(
    record_ids: list[str] | None = Query(default=None),
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
) -> Any:
    result = await quality_feishu_pages.list_deviation_ledger_records(
        db,
        record_ids=record_ids,
        keyword=keyword,
        deviation_code=deviation_code,
        product_keyword=product_keyword,
        has_occurred_before=has_occurred_before,
        is_closed=is_closed,
        investigation_completed_from=investigation_completed_from,
        investigation_completed_to=investigation_completed_to,
        root_cause_keyword=root_cause_keyword,
        corrective_actions_keyword=corrective_actions_keyword,
        page=1,
        page_size=10000,
    )
    data = deviation_ledger_export.generate_deviation_ledger_export_docx(
        result["items"]
    )
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_build_docx_download_headers(
            "偏差台账.docx",
            "deviation-ledger.docx",
        ),
    )


@router.get(
    "/deviation-ledger-records/{record_id}/export",
    summary="导出单条偏差台账飞书数据",
)
async def export_deviation_ledger_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        item = await quality_feishu_pages.get_deviation_ledger_record(db, record_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    filename = (item.get("deviation_code") or record_id or "deviation-ledger").strip()
    data = deviation_ledger_export.generate_deviation_ledger_export_docx([item])
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_build_docx_download_headers(
            f"{filename}.docx",
            f"{filename}.docx",
        ),
    )


@router.get("/deviation-ledger-records/{record_id}", summary="获取偏差台账飞书详情")
async def get_deviation_ledger_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await quality_feishu_pages.get_deviation_ledger_record(db, record_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/deviation-ledger-records", summary="创建偏差台账飞书记录")
async def create_deviation_ledger_record(
    data: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await quality_feishu_pages.create_deviation_ledger_record(db, data)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/deviation-ledger-records/{record_id}", summary="更新偏差台账飞书记录")
async def update_deviation_ledger_record(
    record_id: str,
    data: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await quality_feishu_pages.update_deviation_ledger_record(
            db,
            record_id,
            data,
        )
        return {"data": result}
    except ValueError as e:
        detail = str(e)
        status_code = 404 if "不存在" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail)


@router.delete("/deviation-ledger-records/{record_id}", summary="删除偏差台账飞书记录")
async def delete_deviation_ledger_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        await quality_feishu_pages.delete_deviation_ledger_record(db, record_id)
        return {"data": {"success": True}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/capa-plan-tracks", summary="获取CAPA计划跟踪列表")
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
) -> Any:
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
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.post("/capa-plan-tracks", summary="创建CAPA计划跟踪")
async def create_capa_plan_track(
    data: CreateCapaPlanTrackRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.create_capa_plan_track(db, data, "system")
        return {"data": result}
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


@router.put("/capa-plan-tracks/{track_id}", summary="更新CAPA计划跟踪")
async def update_capa_plan_track(
    track_id: uuid.UUID,
    data: UpdateCapaPlanTrackRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.update_capa_plan_track(db, track_id, data, "system")
        return {"data": result}
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


@router.post("/feishu-sync/deviations/{deviation_id}", summary="同步偏差到飞书Base")
async def sync_deviation_record_to_feishu(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.sync_deviation_to_feishu(db, deviation_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/feishu-sync/capas/{capa_id}", summary="同步CAPA到飞书Base")
async def sync_capa_record_to_feishu(
    capa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.sync_capa_to_feishu(db, capa_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/feishu-sync/capa-plan-tracks/{track_id}", summary="同步CAPA计划跟踪到飞书Base"
)
async def sync_capa_plan_track_record_to_feishu(
    track_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.sync_capa_plan_track_to_feishu(db, track_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/feishu-sync/pull", summary="从飞书Base回拉质量数据")
async def pull_quality_records_from_feishu(
    entity_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.pull_quality_records_from_feishu(
            db, entity_code=entity_code
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/feishu-sync/conflicts", summary="获取质量模块飞书同步冲突列表")
async def list_quality_sync_conflicts(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.get_quality_sync_conflicts(db, limit=limit)
    return {
        "data": result,
        "meta": {
            "total": len(result),
            "limit": limit,
        },
    }


@router.get(
    "/feishu-settings/app",
    summary="获取质量模块飞书应用配置",
    response_model=QualityFeishuAppSettingsDetail,
)
async def get_quality_feishu_app_settings(
    db: AsyncSession = Depends(get_db),
) -> QualityFeishuAppSettingsDetail:
    return await service.get_quality_feishu_app_settings(db)


@router.put(
    "/feishu-settings/app",
    summary="保存质量模块飞书应用配置",
    response_model=QualityFeishuAppSettingsDetail,
)
async def save_quality_feishu_app_settings(
    data: UpdateQualityFeishuAppSettingsRequest,
    db: AsyncSession = Depends(get_db),
) -> QualityFeishuAppSettingsDetail:
    try:
        return await service.update_quality_feishu_app_settings(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/feishu-settings/app/test",
    summary="测试质量模块飞书应用连接",
    response_model=QualityFeishuSettingsTestResult,
)
async def test_quality_feishu_app_settings(
    db: AsyncSession = Depends(get_db),
) -> QualityFeishuSettingsTestResult:
    try:
        return await service.test_quality_feishu_app_settings(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/feishu-settings/entities",
    summary="获取质量模块飞书实体配置",
    response_model=list[QualityFeishuEntitySettingItem],
)
async def list_quality_feishu_entity_settings(
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await service.list_quality_feishu_entity_settings(db)


@router.get(
    "/feishu-settings/entities/{entity_code}/tables",
    summary="读取质量模块飞书实体可选表列表",
    response_model=list[QualityFeishuTableOption],
)
async def list_quality_feishu_entity_tables(
    entity_code: str,
    app_token: str | None = Query(None),
    table_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        kwargs = {"app_token": app_token}
        if table_id is not None:
            kwargs["table_id"] = table_id
        return await service.list_quality_feishu_tables(
            db,
            entity_code,
            **kwargs,
        )
    except ValueError as e:
        detail = str(e)
        status_code = 404 if "不存在" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="读取飞书表列表失败，请检查飞书应用信息、App Token 和 Base Table ID",
        )


@router.get(
    "/feishu-settings/entities/{entity_code}/field-mapping",
    summary="读取质量模块飞书实体字段对齐配置",
    response_model=QualityFeishuEntityFieldMappingBundle,
)
async def get_quality_feishu_entity_field_mapping_bundle(
    entity_code: str,
    app_token: str | None = Query(None),
    table_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> QualityFeishuEntityFieldMappingBundle:
    try:
        return await service.get_quality_feishu_entity_field_mapping_bundle(
            db,
            entity_code,
            app_token=app_token,
            table_id=table_id,
        )
    except ValueError as e:
        detail = str(e)
        status_code = 404 if "不存在" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail)


@router.put(
    "/feishu-settings/entities/{entity_code}",
    summary="保存质量模块飞书实体配置",
    response_model=QualityFeishuEntitySettingItem,
)
async def save_quality_feishu_entity_setting(
    entity_code: str,
    data: UpdateQualityFeishuEntitySettingRequest,
    db: AsyncSession = Depends(get_db),
) -> QualityFeishuEntitySettingItem:
    try:
        return await service.update_quality_feishu_entity_setting(db, entity_code, data)
    except ValueError as e:
        detail = str(e)
        status_code = 404 if "不存在" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail)


@router.post(
    "/feishu-settings/entities/{entity_code}/test",
    summary="测试质量模块飞书实体配置",
    response_model=QualityFeishuSettingsTestResult,
)
async def test_quality_feishu_entity_setting(
    entity_code: str,
    db: AsyncSession = Depends(get_db),
) -> QualityFeishuSettingsTestResult:
    try:
        return await service.test_quality_feishu_entity_setting(db, entity_code)
    except ValueError as e:
        detail = str(e)
        status_code = 404 if "不存在" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail)


@router.post(
    "/change-action-plans/{plan_id}/sync-to-feishu", summary="同步变更计划到飞书"
)
async def sync_change_action_plan_to_feishu(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.sync_change_action_plan_to_feishu(db, plan_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/changes/sync-from-feishu", summary="从飞书同步变更数据")
async def sync_changes_from_feishu(
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await quality_feishu_pages.sync_changes_from_feishu(db)
    return {"data": result}


@router.get("/changes/next-code", summary="获取下一个变更控制号")
async def get_next_change_code(
    db: AsyncSession = Depends(get_db),
) -> Any:
    code = await service.generate_next_change_code(db)
    return {"data": {"code": code}}


@router.post("/changes", summary="创建变更")
async def create_change(
    data: CreateChangeRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.create_change(db, data, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/changes/batch-delete", summary="批量删除变更")
async def batch_delete_changes(
    data: dict[str, Any], db: AsyncSession = Depends(get_db)
) -> Any:
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的记录")
    deleted = 0
    for id_str in ids:
        try:
            await service.delete_change(db, uuid.UUID(id_str))
            deleted += 1
        except Exception:
            pass
    return {"data": {"deleted": deleted}}


@router.post("/changes/import/preview", summary="变更导入预览")
async def preview_change_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise HTTPException(status_code=400, detail="请上传 Word 文件 (.docx)")
    _, content = await read_upload_secure(
        file,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions={".docx", ".doc"},
        what="质量导入文件",
    )
    result = await ie_service.preview_change_import(db, content)
    return {"data": result}


@router.post("/changes/import/confirm", summary="确认变更导入")
async def confirm_change_import(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="是否跳过重复记录"),
    update_existing: bool = Query(False, description="是否更新已存在记录"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise HTTPException(status_code=400, detail="请上传 Word 文件 (.docx)")
    _, content = await read_upload_secure(
        file,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions={".docx", ".doc"},
        what="质量导入文件",
    )
    result = await ie_service.confirm_change_import(
        db, content, skip_duplicates, update_existing
    )
    return {"data": result}


@router.get("/changes/export", summary="导出变更数据")
async def export_changes(
    scope: Literal["single", "selected", "filtered"] = Query(
        "filtered", description="导出范围：single/selected/filtered"
    ),
    change_id: uuid.UUID | None = Query(
        None, description="scope=single 时导出的变更 ID"
    ),
    change_ids: list[uuid.UUID] | None = Query(
        default=None, description="scope=selected 时导出的变更 ID 列表"
    ),
    change_code: str | None = None,
    applicant_department: str | None = None,
    change_object: str | None = None,
    change_level: str | None = None,
    application_date_from: str | None = None,
    application_date_to: str | None = None,
    planned_approval_date_from: str | None = None,
    planned_approval_date_to: str | None = None,
    execution_date_from: str | None = None,
    execution_date_to: str | None = None,
    closure_date_from: str | None = None,
    closure_date_to: str | None = None,
    content_keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        items = await _resolve_change_export_items(
            db,
            scope,
            change_id,
            change_ids,
            change_code,
            applicant_department,
            change_object,
            change_level,
            application_date_from,
            application_date_to,
            planned_approval_date_from,
            planned_approval_date_to,
            execution_date_from,
            execution_date_to,
            closure_date_from,
            closure_date_to,
            content_keyword,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    data = change_ledger_export.generate_change_ledger_export_docx(items)
    filename_utf8, fallback_ascii = _build_change_export_filename(scope, items)
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_build_docx_download_headers(
            filename_utf8,
            fallback_ascii,
        ),
    )


@router.get("/changes/{change_id}/action-plans", summary="获取变更详情下的变更计划")
async def list_change_action_plans_by_change(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.get_change_action_plans_for_change(db, change_id)
    return {"data": result}


@router.get("/changes/{change_id}", summary="获取变更详情")
async def get_change(change_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        detail = await service.get_change_detail(db, change_id)
        return {"data": detail.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/changes/{change_id}", summary="更新变更")
async def update_change(
    change_id: uuid.UUID, data: UpdateChangeRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.update_change(db, change_id, data, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/changes/{change_id}", summary="删除变更")
async def delete_change(
    change_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.delete_change(db, change_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/ai/deviations/{deviation_id}/analyze", summary="AI分析偏差")
async def analyze_deviation_ai(
    deviation_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.analyze_deviation_record(db, deviation_id, "system")
        return {"data": result.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/ai/deviations/{deviation_id}/session", summary="获取偏差当前AI会话")
async def get_deviation_ai_session(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result: DeviationAiSessionOut = (
            await service.get_or_create_deviation_ai_session(db, deviation_id)
        )
        return {"data": result.model_dump(mode="json")}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/ai/deviations/{deviation_id}/session", summary="更新偏差当前AI会话")
async def update_deviation_ai_session(
    deviation_id: uuid.UUID,
    data: UpdateDeviationAiSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.update_deviation_ai_session(
            db,
            deviation_id,
            data.supplement_text,
            "system",
        )
        return {"data": result.model_dump(mode="json")}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/ai/deviations/{deviation_id}/session/attachments",
    summary="上传偏差AI会话附件",
)
async def upload_deviation_ai_session_attachment(
    deviation_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.upload_deviation_ai_session_attachment(
            db,
            deviation_id,
            file,
            "system",
        )
        return {"data": result.model_dump(mode="json")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/ai/deviations/{deviation_id}/session/attachments/{attachment_id}",
    summary="删除偏差AI会话附件",
)
async def delete_deviation_ai_session_attachment(
    deviation_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.delete_deviation_ai_session_attachment(
            db,
            deviation_id,
            attachment_id,
            "system",
        )
        return {"data": result.model_dump(mode="json")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/ai/deviations/{deviation_id}/session/regenerate",
    summary="重新生成偏差当前AI结果",
)
async def regenerate_deviation_ai_session(
    deviation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.regenerate_deviation_ai_session(
            db,
            deviation_id,
            "system",
        )
        return {"data": result.model_dump(mode="json")}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post(
    "/ai/deviations/{deviation_id}/session/apply", summary="应用偏差当前AI结果"
)
async def apply_deviation_ai_session(
    deviation_id: uuid.UUID,
    data: ApplyDeviationAiSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.apply_deviation_ai_session(
            db,
            deviation_id,
            data.section,
            data.field_keys,
            "system",
        )
        return {"data": result.model_dump(mode="json")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ai/deviations/{deviation_id}/suggest-capa", summary="AI生成偏差CAPA建议")
async def suggest_deviation_capa_ai(
    deviation_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.suggest_capa_for_deviation(db, deviation_id, "system")
        return {"data": result.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/ai/capas/{capa_id}/analyze", summary="AI分析CAPA")
async def analyze_capa_ai(
    capa_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.analyze_capa_record(db, capa_id, "system")
        return {"data": result.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/ai/changes/{change_id}/analyze", summary="AI分析变更")
async def analyze_change_ai(
    change_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.analyze_change_record(db, change_id, "system")
        return {"data": result.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/ai/logs", summary="获取AI分析日志")
async def list_ai_logs(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.list_ai_logs(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.get("/ai/logs/{log_id}", summary="获取AI分析日志详情")
async def get_ai_log(log_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        result = await service.get_ai_log_detail(db, log_id)
        return {"data": result.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/ai/logs/{log_id}/apply", summary="应用AI建议到字段")
async def apply_ai_log(
    log_id: uuid.UUID,
    data: QualityAiApplyRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.apply_ai_log(db, log_id, data.field_keys, "system")
        return {"data": result.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/capas", summary="获取CAPA列表")
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
) -> Any:
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
    )
    return {
        "data": result["items"],
        "meta": {
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    }


@router.get("/capas/departments", summary="获取所有部门列表")
async def get_capa_departments(db: AsyncSession = Depends(get_db)) -> Any:
    departments = await service.get_capa_departments(db)
    return {"data": departments}


@router.get("/capas/auto-fill/{deviation_id}", summary="从偏差自动填充CAPA表单")
async def auto_fill_capa_from_deviation(
    deviation_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.auto_fill_from_deviation(db, deviation_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/capas/{capa_id}", summary="获取CAPA详情")
async def get_capa(capa_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        detail = await service.get_capa_detail(db, capa_id)
        return {"data": detail.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/capas", summary="创建CAPA")
async def create_capa(
    data: CreateCapaRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    result = await service.create_capa(db, data, "system")
    return {"data": result}


@router.put("/capas/{capa_id}", summary="更新CAPA")
async def update_capa(
    capa_id: uuid.UUID, data: UpdateCapaRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.update_capa(db, capa_id, data, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/capas/{capa_id}", summary="删除CAPA")
async def delete_capa(capa_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        result = await service.delete_capa(db, capa_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/capas/batch-delete", summary="批量删除CAPA")
async def batch_delete_capas(
    data: dict[str, Any], db: AsyncSession = Depends(get_db)
) -> Any:
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的记录")
    deleted = 0
    for id_str in ids:
        try:
            await service.delete_capa(db, uuid.UUID(id_str))
            deleted += 1
        except Exception:
            pass
    return {"data": {"deleted": deleted}}


@router.post("/capas/{capa_id}/link-deviation", summary="关联偏差到CAPA")
async def link_capa_to_deviation(
    capa_id: uuid.UUID,
    data: LinkDeviationRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.link_deviation(
            db, capa_id, uuid.UUID(str(data.deviation_id)), "system"
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capas/{capa_id}/complete-part", summary="完成CAPA部分")
async def complete_capa_part(
    capa_id: uuid.UUID,
    data: CompletePartRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.complete_part(db, capa_id, data.part, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capas/{capa_id}/submit", summary="提交CAPA审核")
async def submit_capa_for_review(
    capa_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.submit_capa(db, capa_id, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capas/{capa_id}/confirm-dept-head", summary="部门主管确认CAPA")
async def confirm_capa_by_dept_head(
    capa_id: uuid.UUID,
    data: CapaDeptHeadConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.confirm_dept_head(db, capa_id, data, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capas/{capa_id}/approve", summary="QA审批CAPA")
async def approve_capa(
    capa_id: uuid.UUID,
    data: CapaApprovalRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.approve_capa(db, capa_id, data, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capas/{capa_id}/resubmit", summary="重新提交CAPA")
async def resubmit_capa(capa_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        result = await service.resubmit_capa(db, capa_id, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capas/{capa_id}/add-execution-track", summary="添加CAPA执行记录")
async def add_capa_execution_track(
    capa_id: uuid.UUID,
    data: ExecutionTrack,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.add_execution_track(
            db, capa_id, data.model_dump(), "system"
        )
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capas/{capa_id}/delete-execution-track", summary="删除CAPA执行记录")
async def delete_capa_execution_track(
    capa_id: uuid.UUID,
    index: int,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.delete_execution_track(db, capa_id, index, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capas/{capa_id}/confirm-execution", summary="确认CAPA执行完成")
async def confirm_capa_execution(
    capa_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.confirm_execution(db, capa_id, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capas/{capa_id}/submit-evaluation", summary="提交CAPA效果评价")
async def submit_capa_evaluation(
    capa_id: uuid.UUID,
    data: CapaEvaluationRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.submit_evaluation(db, capa_id, data, "system")
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Department Contacts ============


@router.get("/department-contacts", summary="获取部门联系人列表")
async def list_department_contacts(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.get_department_contact_list(db, page, page_size)
    return {"data": result}


@router.get("/department-contacts/feishu", summary="直接获取飞书部门联系人列表")
async def list_department_contacts_from_feishu(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.get_department_contact_list_from_feishu(db, page, page_size)
    return {"data": result}


@router.post("/department-contacts", summary="创建部门联系人")
async def upsert_department_contact(
    data: CreateDepartmentContactRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.upsert_department_contact(db, data, None, "system")
    return {"data": result}


@router.put("/department-contacts/{contact_id}", summary="更新部门联系人")
async def update_department_contact(
    contact_id: uuid.UUID,
    data: UpdateDepartmentContactRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        result = await service.update_department_contact(db, contact_id, data)
        return {"data": result}
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


@router.delete("/department-contacts/{contact_id}", summary="删除部门联系人")
async def delete_department_contact(
    contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await service.delete_department_contact(db, contact_id)
        return {"data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============ Statistics ============


@router.get("/statistics/deviations", summary="获取偏差统计")
async def get_deviation_statistics(db: AsyncSession = Depends(get_db)) -> Any:
    stats = await service.get_deviation_statistics(db)
    return {"data": stats.model_dump()}


@router.get("/statistics/capas", summary="获取CAPA统计")
async def get_capa_statistics(db: AsyncSession = Depends(get_db)) -> Any:
    stats = await service.get_capa_statistics(db)
    return {"data": stats.model_dump()}


@router.get("/statistics/changes", summary="获取变更统计")
async def get_change_statistics(db: AsyncSession = Depends(get_db)) -> Any:
    stats = await service.get_change_statistics(db)
    return {"data": stats.model_dump()}


# ============ Attachment Reviews ============


@router.get("/attachment-reviews", summary="获取附件审阅列表")
async def list_attachment_reviews(
    deviation_id: uuid.UUID | None = None,
    capa_id: uuid.UUID | None = None,
    attachment_url: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    items = await service.list_attachment_reviews(
        db, deviation_id, capa_id, attachment_url
    )
    return {"data": items}


@router.post("/attachment-reviews", summary="创建附件审阅")
async def create_attachment_review(
    data: CreateAttachmentReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await service.create_attachment_review(db, data, "system")
    return {"data": result}


@router.delete("/attachment-reviews/{review_id}", summary="删除附件审阅")
async def delete_attachment_review(
    review_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        await service.delete_attachment_review(db, review_id)
        return {"data": {"success": True}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============ CAPA Import/Export ============


@router.post("/capas/import/preview", summary="CAPA导入预览")
async def preview_capa_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise HTTPException(status_code=400, detail="请上传 Word 文件 (.docx)")
    _, content = await read_upload_secure(
        file,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions={".docx", ".doc"},
        what="质量导入文件",
    )
    result = await ie_service.preview_capa_import(db, content)
    return {"data": result}


@router.post("/capas/import/confirm", summary="确认 CAPA 导入")
async def confirm_capa_import(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="是否跳过重复记录"),
    update_existing: bool = Query(False, description="是否更新已存在记录"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise HTTPException(status_code=400, detail="请上传 Word 文件 (.docx)")
    _, content = await read_upload_secure(
        file,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions={".docx", ".doc"},
        what="质量导入文件",
    )
    result = await ie_service.confirm_capa_import(
        db, content, skip_duplicates, update_existing
    )
    return {"data": result}


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
) -> Any:
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


@router.post("/deviations/import/preview", summary="偏差导入预览")
async def preview_deviation_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise HTTPException(status_code=400, detail="请上传 Word 文件 (.docx)")
    _, content = await read_upload_secure(
        file,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions={".docx", ".doc"},
        what="质量导入文件",
    )
    result = await ie_service.preview_deviation_import(db, content)
    return {"data": result}


@router.post("/deviations/import/confirm", summary="确认偏差导入")
async def confirm_deviation_import(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="是否跳过重复记录"),
    update_existing: bool = Query(False, description="是否更新已存在记录"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise HTTPException(status_code=400, detail="请上传 Word 文件 (.docx)")
    _, content = await read_upload_secure(
        file,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions={".docx", ".doc"},
        what="质量导入文件",
    )
    result = await ie_service.confirm_deviation_import(
        db, content, skip_duplicates, update_existing
    )
    return {"data": result}


@router.get("/deviations/export", summary="导出偏差数据")
async def export_deviations(
    status: str | None = None,
    level: str | None = None,
    department: str | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    data = await ie_service.export_deviations(
        db, None, status, level, department, keyword
    )
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_build_docx_download_headers(
            "偏差登记表.docx",
            "deviation-register.docx",
        ),
    )
