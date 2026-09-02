"""变更与变更行动计划 API 路由（Q1 拆分自 quality_management.py）。"""

import logging
import uuid
from io import BytesIO
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import (
    AppException,
)
from app.core.response import paginated_response, success_response
from app.modules.quality import repository as repo
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
    ChangeActionPlanDetail,
    ChangeActionPlanListItem,
    ChangeActionPlanPersonOption,
    ChangeActionPlanReminderConfirmResult,
    ChangeActionPlanReminderRunResult,
    ChangeActionPlanSyncResult,
    ChangeDetail,
    ChangeListItem,
    CreateChangeActionPlanRequest,
    CreateChangeRequest,
    UpdateChangeActionPlanRequest,
    UpdateChangeRequest,
)
from app.modules.quality.service import quality_import_export as ie_service
from app.modules.quality.service.change_ledger_export import (
    generate_change_ledger_export_docx,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/changes",
    summary="获取变更列表",
    response_model=ApiResponseEnvelope[list[ChangeListItem]],
)
async def list_changes(
    change_code: str | None = None,
    change_type: str = Query("technical", description="台账类型: technical/file"),
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
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    assert current_user is not None
    scope = await _resolve_quality_list_scope(db, current_user)
    result = await service.get_change_list(
        db,
        change_code,
        change_type,
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
        scope=scope,
    )
    return paginated_response(
        data=result["items"],
        page=result["page"],
        page_size=result["page_size"],
        total=result["total"],
    )


@router.get(
    "/change-action-plans",
    summary="获取变更计划列表",
    response_model=ApiResponseEnvelope[list[ChangeActionPlanListItem]],
)
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
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
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
    return success_response(
        data=result["items"],
        meta={
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        },
    )


@router.post(
    "/change-action-plans",
    summary="创建变更计划",
    response_model=ApiResponseEnvelope[ChangeActionPlanDetail],
)
async def create_change_action_plan(
    data: CreateChangeActionPlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.create_change_action_plan_record(db, data, user_id)
    return success_response(data=result)


@router.get(
    "/change-action-plans/person-options",
    summary="搜索变更计划人员候选",
    response_model=ApiResponseEnvelope[list[ChangeActionPlanPersonOption]],
)
async def search_change_action_plan_persons(
    keyword: str = Query(..., min_length=1, description="姓名/手机号/邮箱关键词"),
    limit: int = Query(20, ge=1, le=50, description="返回条数"),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    try:
        result = await service.search_change_action_plan_person_options(keyword, limit)
        return success_response(data=[item.model_dump() for item in result])
    except RuntimeError as e:
        raise AppException(message=str(e), status_code=502)


@router.post(
    "/change-action-plans/sync-from-feishu",
    summary="从飞书同步变更计划",
    response_model=ApiResponseEnvelope[ChangeActionPlanSyncResult],
)
async def sync_change_action_plans_from_feishu(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    try:
        result = await service.sync_change_action_plans_from_feishu(db, user_id)
        return success_response(data=result.model_dump())
    except RuntimeError as e:
        raise AppException(message=str(e))


@router.post(
    "/change-action-plans/reminders/run",
    summary="立即执行变更计划提醒",
    response_model=ApiResponseEnvelope[ChangeActionPlanReminderRunResult],
)
async def run_change_action_plan_reminders(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.run_change_action_plan_reminders_now(db)
    return success_response(data=result.model_dump())


@router.put(
    "/change-action-plans/{plan_id}",
    summary="更新变更计划",
    response_model=ApiResponseEnvelope[ChangeActionPlanDetail],
)
async def update_change_action_plan(
    plan_id: uuid.UUID,
    data: UpdateChangeActionPlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["change_qa"],
    )
    try:
        result = await service.update_change_action_plan_record(
            db, plan_id, data, user_id
        )
        return success_response(data=result)
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=400) from exc


@router.post(
    "/change-action-plans/{plan_id}/reminders/send",
    summary="手动发送单条变更计划提醒",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def send_change_action_plan_reminder(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    try:
        result = await service.send_change_action_plan_reminder_for_plan(db, plan_id)
        return success_response(data=result)
    except RuntimeError as e:
        raise AppException(message=str(e))


@router.post(
    "/change-action-plans/{plan_id}/reminders/confirm",
    summary="确认变更计划提醒",
    response_model=ApiResponseEnvelope[ChangeActionPlanReminderConfirmResult],
)
async def confirm_change_action_plan_reminder(
    plan_id: uuid.UUID,
    confirmed_by: str = Query("系统确认", description="确认人"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.confirm_change_action_plan_reminder(
        db,
        plan_id,
        confirmed_by=confirmed_by,
    )
    return success_response(data=result.model_dump())


@router.get(
    "/change-action-plans/{plan_id}/reminders/confirm-page",
    summary="飞书确认变更计划提醒",
    response_class=HTMLResponse,
)
async def confirm_change_action_plan_reminder_page(
    plan_id: uuid.UUID,
    confirmed_by: str = Query("飞书确认", description="确认人"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> HTMLResponse:
    _require_user(current_user)
    html_content = await service.render_change_action_plan_reminder_confirmation_page(
        db,
        plan_id,
        confirmed_by=confirmed_by,
    )
    return HTMLResponse(content=html_content)


@router.delete(
    "/change-action-plans/{plan_id}",
    summary="删除变更计划",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_change_action_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["change_qa"],
    )
    result = await service.delete_change_action_plan_record(db, plan_id)
    return success_response(data=result)


@router.post(
    "/change-action-plans/{plan_id}/sync-to-feishu",
    summary="同步变更计划到飞书",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def sync_change_action_plan_to_feishu(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.sync_change_action_plan_to_feishu(db, plan_id)
    return success_response(data=result)


@router.post(
    "/changes", summary="创建变更", response_model=ApiResponseEnvelope[ChangeDetail]
)
async def create_change(
    data: CreateChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    user_id = _current_user_id(_require_user(current_user))
    result = await service.create_change(db, data, user_id)
    return success_response(data=result)


@router.post(
    "/changes/batch-delete",
    summary="批量删除变更",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def batch_delete_changes(
    data: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["change_qa"],
    )

    ids = data.get("ids", [])
    if not ids:
        raise AppException(message="请选择要删除的记录")

    deleted = 0
    failed_ids = []

    for id_str in ids:
        try:
            await service.delete_change(db, uuid.UUID(id_str))
            deleted += 1
        except Exception as e:
            logger.warning(f"批量删除变更失败 id={id_str}: {e}")
            failed_ids.append(id_str)

    return success_response(data={"deleted": deleted, "failed": failed_ids})


@router.post(
    "/changes/sync-from-feishu",
    summary="从飞书同步变更台账",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def sync_changes_from_feishu(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    result = await service.quality_feishu_pages.sync_changes_from_feishu(db)
    return success_response(data=result)


@router.post(
    "/changes/import/preview",
    summary="变更导入预览",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def preview_change_import(
    file: UploadFile = File(...),
    change_type: str = Query("technical", description="台账类型: technical/file"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise AppException(message="请上传 Word 文件 (.docx)")
    content = await read_upload_with_limit(file, IMPORT_FILE_MAX_SIZE, "导入文件")
    result = await ie_service.preview_change_import(
        db, content, change_type=change_type
    )
    return success_response(data=result)


@router.post(
    "/changes/import/confirm",
    summary="确认变更导入",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def confirm_change_import(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="是否跳过重复记录"),
    update_existing: bool = Query(False, description="是否更新已存在记录"),
    change_type: str = Query("technical", description="台账类型: technical/file"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    if not file.filename or not file.filename.endswith((".docx", ".doc")):
        raise AppException(message="请上传 Word 文件 (.docx)")
    content = await read_upload_with_limit(file, IMPORT_FILE_MAX_SIZE, "导入文件")
    result = await ie_service.confirm_change_import(
        db, content, skip_duplicates, update_existing, change_type=change_type
    )
    return success_response(data=result)


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
    change_type: str = Query("technical", description="台账类型: technical/file"),
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
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    assert current_user is not None
    department_scope = await _resolve_quality_list_scope(db, current_user)

    if scope == "single":
        if change_id is None:
            raise HTTPException(
                status_code=400, detail="scope=single 时必须提供 change_id"
            )
        items = [
            (await service.get_change_detail(db, change_id)).model_dump(mode="json")
        ]
    elif scope == "selected":
        if not change_ids:
            raise HTTPException(
                status_code=400, detail="scope=selected 时必须提供 change_ids"
            )
        items = [
            (await service.get_change_detail(db, selected_id)).model_dump(mode="json")
            for selected_id in change_ids
        ]
    else:
        # Fetch all matching changes (no pagination for export).
        from app.modules.quality.service.quality_import_export import _parse_date_value

        changes, _ = await repo.get_changes(
            db,
            change_code=change_code,
            change_type=change_type,
            applicant_department=applicant_department,
            change_object=change_object,
            change_level=change_level,
            application_date_from=_parse_date_value(application_date_from),
            application_date_to=_parse_date_value(application_date_to),
            planned_approval_date_from=_parse_date_value(planned_approval_date_from),
            planned_approval_date_to=_parse_date_value(planned_approval_date_to),
            execution_date_from=_parse_date_value(execution_date_from),
            execution_date_to=_parse_date_value(execution_date_to),
            closure_date_from=_parse_date_value(closure_date_from),
            closure_date_to=_parse_date_value(closure_date_to),
            content_keyword=content_keyword,
            page=1,
            page_size=10000,
            scope=department_scope,
        )

        items = []
        for idx, change in enumerate(changes, start=1):
            items.append(
                {
                    "serial_number": change.serial_number or str(idx),
                    "change_code": change.change_code or "",
                    "applicant_department": change.applicant_department or "",
                    "change_object": change.change_object or "",
                    "change_content": change.change_content or "",
                    "change_level": change.change_level or "",
                    "application_date": change.application_date,
                    "planned_approval_date": change.planned_approval_date,
                    "execution_date": change.execution_date,
                    "closure_date": change.closure_date,
                    "status": "正在进行" if change.closure_date is None else "",
                }
            )

    data = generate_change_ledger_export_docx(items)
    if scope == "single" and items:
        filename_utf8 = filename_ascii = (
            f"{(items[0].get('change_code') or 'change-ledger').strip()}.docx"
        )
    else:
        filename_utf8, filename_ascii = "变更管理台账.docx", "change-controls.docx"
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=_build_docx_download_headers(
            filename_utf8,
            filename_ascii,
        ),
    )


@router.get(
    "/changes/next-code",
    summary="获取下一个变更控制号",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def get_next_change_code(
    change_type: str = Query("technical", description="台账类型: technical/file"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    from app.modules.quality.service.quality_change import generate_next_change_code

    code = await generate_next_change_code(db, change_type=change_type)
    return success_response(data={"code": code})


@router.get(
    "/changes/{change_id}/action-plans",
    summary="获取变更详情下的变更计划",
    response_model=ApiResponseEnvelope[list[ChangeActionPlanListItem]],
)
async def list_change_action_plans_by_change(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> JSONResponse:
    _require_user(current_user)
    result = await service.get_change_action_plans_for_change(db, change_id)
    return success_response(data=result)


@router.get(
    "/changes/{change_id}",
    summary="获取变更详情",
    response_model=ApiResponseEnvelope[ChangeDetail],
)
async def get_change(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    detail = await service.get_change_detail(db, change_id)
    return success_response(data=detail.model_dump())


@router.put(
    "/changes/{change_id}",
    summary="更新变更",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def update_change(
    change_id: uuid.UUID,
    data: UpdateChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    user_id = _current_user_id(_require_user(current_user))
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["change_qa"],
    )
    result = await service.update_change(db, change_id, data, user_id)
    return success_response(data=result)


@router.delete(
    "/changes/{change_id}",
    summary="删除变更",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_change(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    user_id = _require_user(current_user)
    await _assert_quality_edit_scope(
        db,
        current_user,
        scope_permission=QUALITY_QA_SCOPE_PERMISSIONS["change_qa"],
    )
    result = await service.delete_change(db, change_id, deleted_by=user_id)
    return success_response(data=result)
