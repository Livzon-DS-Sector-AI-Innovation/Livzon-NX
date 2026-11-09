"""Safety API — 8 大特殊作业票（新版作业票）端点。

流程：建票（草稿）→ 提交（生成逐级审批节点链）→ approve/reject →
验票（作业前）→ 作业期间气体复检录入 → 完工验收。
关联票/附件/气体分析等子资源挂在票详情下。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException, NotFoundException
from app.core.upload_security import read_upload_secure, sniff_upload_mime
from app.modules.safety.models import (
    WorkPermit,
    WorkPermitApproverConfig,
    WorkPermitAttachment,
    WorkPermitSetting,
)
from app.modules.safety.schemas.work_permit import (
    AcceptPermitInput,
    ActionResponse,
    ApproverConfigItem,
    ApproverConfigListResponse,
    ApproverConfigUpsertInput,
    GasAnalysisCreate,
    GasAnalysisItem,
    PermitNodeActionInput,
    WorkPermitAttachmentItem,
    WorkPermitCreate,
    WorkPermitDetailResponse,
    WorkPermitListResponse,
    WorkPermitMetaResponse,
    WorkPermitRejectInput,
    WorkPermitRelationInput,
    WorkPermitSettingsResponse,
    WorkPermitSettingsUpdate,
    WorkPermitStatsResponse,
    WorkPermitSubmitInput,
    WorkPermitUpdate,
)
from app.modules.safety.service import work_permit as permit_service
from app.modules.safety.service.work_permit_files import (
    WORK_PERMIT_ALLOWED_EXTS,
    WORK_PERMIT_ATTACHMENT_CATEGORIES,
    WORK_PERMIT_MAX_BYTES,
    build_permit_attachment_key,
    delete_object,
    read_object,
    store_object,
)
from app.modules.safety.service.work_permit_notify import (
    notify_after_transition,
)
from app.modules.safety.service.work_permit_templates import (
    CERTIFICATE_CATEGORIES,
    PERMIT_TEMPLATES,
    RISK_IDENTIFICATION_OPTIONS,
    _as_level_tuple,
    gas_cycle_minutes_for,
    level_options_for,
    measure_template_for,
    person_role_options_for,
    type_fields_for,
)
from app.platform.identity.models import User
from app.platform.storage.preview import resolve_preview_content
from app.shared.schemas import ApiResponseEnvelope

work_permits_router = APIRouter()


def _action_response(
    permit: WorkPermit, message: str = "", warnings: list[str] | None = None
) -> ActionResponse:
    return ActionResponse(
        permit_id=permit.id,
        permit_no=permit.permit_no,
        status=permit.status,
        current_node_seq=permit.current_node_seq,
        message=message,
        warnings=warnings or [],
    )


@work_permits_router.get(
    "/work-permits/meta",
    response_model=ApiResponseEnvelope[WorkPermitMetaResponse],
    summary="作业票模板元数据（票种/级别/节点/措施/字段）",
)
async def get_work_permit_meta(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitMetaResponse]:
    settings_result = await db.execute(
        select(WorkPermitSetting).where(WorkPermitSetting.is_deleted.is_(False))
    )
    cycle_overrides: dict[str, int] = {}
    for row in settings_result.scalars().all():
        if row.setting_key.startswith("gas_cycle_minutes.") and isinstance(
            row.setting_value, (int, float)
        ):
            cycle_overrides[row.setting_key.split(".", 1)[1]] = int(
                row.setting_value
            )

    gas_types: list[str] = [
        t.code for t in PERMIT_TEMPLATES.values() if t.gas_enabled
    ]
    cycle_minutes = {
        ptype: cycle
        for ptype in gas_types
        if (cycle := gas_cycle_minutes_for(ptype, cycle_overrides)) is not None
    }
    meta = WorkPermitMetaResponse(
        permit_types=[
            {
                "value": t.code,
                "label": t.name,
                "no_prefix": t.no_prefix,
            }
            for t in PERMIT_TEMPLATES.values()
        ],
        level_options={
            t.code: level_options_for(t.code) for t in PERMIT_TEMPLATES.values()
        },
        person_roles={
            t.code: person_role_options_for(t.code)
            for t in PERMIT_TEMPLATES.values()
        },
        measures={
            t.code: measure_template_for(t.code)
            for t in PERMIT_TEMPLATES.values()
        },
        type_fields={
            t.code: type_fields_for(t.code) for t in PERMIT_TEMPLATES.values()
        },
        nodes={
            t.code: [
                {
                    "key": node["key"],
                    "name": node["name"],
                    "kind": node["kind"],
                    "levels": [
                        str(level) for level in _as_level_tuple(node["levels"])
                    ]
                    if node["levels"] is not None
                    else None,
                }
                for node in t.nodes
            ]
            for t in PERMIT_TEMPLATES.values()
        },
        risk_identification_options=list(RISK_IDENTIFICATION_OPTIONS),
        gas_types=gas_types,
        gas_cycle_minutes=cycle_minutes,
        certificate_categories=list(CERTIFICATE_CATEGORIES),
    )
    return ApiResponseEnvelope(data=meta)


@work_permits_router.get(
    "/work-permits/stats",
    response_model=ApiResponseEnvelope[WorkPermitStatsResponse],
    summary="作业票状态统计（含待我审批数）",
)
async def get_work_permit_stats(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitStatsResponse]:
    stats = await permit_service.get_stats(db, current_user)
    return ApiResponseEnvelope(data=stats)


@work_permits_router.get(
    "/work-permits",
    response_model=ApiResponseEnvelope[WorkPermitListResponse],
    summary="作业票分页列表（票种/级别/状态/日期/关键字）",
)
async def list_work_permits(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    permit_type: str | None = Query(None),
    permit_level: str | None = Query(None),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitListResponse]:
    data = await permit_service.list_permits(
        db,
        page=page,
        page_size=page_size,
        permit_type=permit_type,
        permit_level=permit_level,
        status=status,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )
    return ApiResponseEnvelope(data=data)


@work_permits_router.post(
    "/work-permits",
    response_model=ApiResponseEnvelope[WorkPermitDetailResponse],
    summary="创建作业票草稿",
)
async def create_work_permit(
    payload: WorkPermitCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitDetailResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    permit = await permit_service.create_permit(db, payload, current_user)
    await db.commit()
    detail = await permit_service.build_detail(db, permit)
    return ApiResponseEnvelope(data=detail)


@work_permits_router.get(
    "/work-permits/{permit_id}",
    response_model=ApiResponseEnvelope[WorkPermitDetailResponse],
    summary="作业票详情（节点时间线/气体分析/关联票/附件）",
)
async def get_work_permit(
    permit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitDetailResponse]:
    permit = await permit_service.get_permit(db, permit_id)
    detail = await permit_service.build_detail(db, permit)
    return ApiResponseEnvelope(data=detail)


@work_permits_router.put(
    "/work-permits/{permit_id}",
    response_model=ApiResponseEnvelope[WorkPermitDetailResponse],
    summary="编辑作业票（仅草稿/已驳回）",
)
async def update_work_permit(
    permit_id: UUID,
    payload: WorkPermitUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitDetailResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    permit = await permit_service.update_permit(
        db, permit_id, payload, current_user
    )
    await db.commit()
    await db.refresh(permit)  # onupdate 服务端时间戳回填后再序列化
    detail = await permit_service.build_detail(db, permit)
    return ApiResponseEnvelope(data=detail)


@work_permits_router.delete(
    "/work-permits/{permit_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除作业票草稿（软删除）",
)
async def delete_work_permit(
    permit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    await permit_service.delete_permit(db, permit_id, current_user)
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


@work_permits_router.post(
    "/work-permits/{permit_id}/submit",
    response_model=ApiResponseEnvelope[ActionResponse],
    summary="提交审批（生成逐级审批节点链）",
)
async def submit_work_permit(
    permit_id: UUID,
    payload: WorkPermitSubmitInput,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ActionResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    assignments = {
        item.node_key: item.approver_user_id for item in payload.assignments
    }
    permit, cert_warnings = await permit_service.submit_permit(
        db, permit_id, assignments, current_user
    )
    await db.commit()
    await notify_after_transition(db, permit)
    return ApiResponseEnvelope(
        data=_action_response(permit, "已提交审批", cert_warnings)
    )


@work_permits_router.post(
    "/work-permits/{permit_id}/nodes/{node_id}/approve",
    response_model=ApiResponseEnvelope[ActionResponse],
    summary="审批同意（当前节点签批并推进）",
)
async def approve_work_permit_node(
    permit_id: UUID,
    node_id: UUID,
    payload: PermitNodeActionInput | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ActionResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    opinion = payload.opinion if payload else None
    permit = await permit_service.approve_node(
        db, permit_id, node_id, opinion, current_user
    )
    await db.commit()
    await notify_after_transition(db, permit)
    return ApiResponseEnvelope(data=_action_response(permit, "已签批"))


@work_permits_router.post(
    "/work-permits/{permit_id}/nodes/{node_id}/reject",
    response_model=ApiResponseEnvelope[ActionResponse],
    summary="审批驳回（整票驳回，修改后重新提交）",
)
async def reject_work_permit_node(
    permit_id: UUID,
    node_id: UUID,
    payload: WorkPermitRejectInput,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ActionResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    permit = await permit_service.reject_node(
        db, permit_id, node_id, payload.opinion, current_user
    )
    await db.commit()
    await notify_after_transition(db, permit, reject_opinion=payload.opinion)
    return ApiResponseEnvelope(data=_action_response(permit, "已驳回"))


@work_permits_router.post(
    "/work-permits/{permit_id}/verify",
    response_model=ApiResponseEnvelope[ActionResponse],
    summary="作业前验票（开工）",
)
async def verify_work_permit(
    permit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ActionResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    permit = await permit_service.verify_permit(db, permit_id, current_user)
    await db.commit()
    await notify_after_transition(db, permit)
    return ApiResponseEnvelope(data=_action_response(permit, "验票完成，开工"))


@work_permits_router.post(
    "/work-permits/{permit_id}/accept",
    response_model=ApiResponseEnvelope[ActionResponse],
    summary="完工验收（临时用电可带拆线确认字段）",
)
async def accept_work_permit(
    permit_id: UUID,
    payload: AcceptPermitInput | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ActionResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    patch = payload.type_data if payload else {}
    permit = await permit_service.accept_permit(
        db, permit_id, patch, current_user
    )
    await db.commit()
    await notify_after_transition(db, permit)
    return ApiResponseEnvelope(data=_action_response(permit, "完工验收完成"))


@work_permits_router.post(
    "/work-permits/{permit_id}/nodes/{node_id}/reassign",
    response_model=ApiResponseEnvelope[ActionResponse],
    summary="改派未签字节点审批人（管理员）",
)
async def reassign_work_permit_node(
    permit_id: UUID,
    node_id: UUID,
    payload: dict[str, str] | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ActionResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    approver_raw = (payload or {}).get("approver_user_id")
    if not approver_raw:
        raise AppException(status_code=422, message="缺少 approver_user_id")
    permit = await permit_service.reassign_node(
        db, permit_id, node_id, UUID(str(approver_raw)), current_user
    )
    await db.commit()
    await notify_after_transition(db, permit)
    return ApiResponseEnvelope(data=_action_response(permit, "已改派"))


@work_permits_router.post(
    "/work-permits/{permit_id}/cancel",
    response_model=ApiResponseEnvelope[ActionResponse],
    summary="作废作业票",
)
async def cancel_work_permit(
    permit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ActionResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    permit = await permit_service.cancel_permit(db, permit_id, current_user)
    await db.commit()
    return ApiResponseEnvelope(data=_action_response(permit, "已作废"))


@work_permits_router.post(
    "/work-permits/{permit_id}/gas-analyses",
    response_model=ApiResponseEnvelope[GasAnalysisItem],
    summary="录入气体分析（作业前/作业期间复检）",
)
async def add_gas_analysis(
    permit_id: UUID,
    payload: GasAnalysisCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[GasAnalysisItem]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    item = await permit_service.add_gas_analysis(
        db, permit_id, payload, current_user
    )
    await db.commit()
    await db.refresh(item)
    return ApiResponseEnvelope(data=GasAnalysisItem.model_validate(item))


@work_permits_router.delete(
    "/work-permits/{permit_id}/gas-analyses/{analysis_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除气体分析记录（软删除）",
)
async def delete_gas_analysis(
    permit_id: UUID,
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    await permit_service.delete_gas_analysis(
        db, permit_id, analysis_id, current_user
    )
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


@work_permits_router.post(
    "/work-permits/{permit_id}/relations",
    response_model=ApiResponseEnvelope[WorkPermitDetailResponse],
    summary="添加关联作业票",
)
async def add_work_permit_relation(
    permit_id: UUID,
    payload: WorkPermitRelationInput,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitDetailResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    await permit_service.add_relation(
        db, permit_id, payload.related_permit_id, current_user
    )
    await db.commit()
    permit = await permit_service.get_permit(db, permit_id)
    detail = await permit_service.build_detail(db, permit)
    return ApiResponseEnvelope(data=detail)


@work_permits_router.delete(
    "/work-permits/{permit_id}/relations/{related_permit_id}",
    response_model=ApiResponseEnvelope[WorkPermitDetailResponse],
    summary="移除关联作业票",
)
async def remove_work_permit_relation(
    permit_id: UUID,
    related_permit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitDetailResponse]:
    await permit_service.remove_relation(db, permit_id, related_permit_id)
    await db.commit()
    permit = await permit_service.get_permit(db, permit_id)
    detail = await permit_service.build_detail(db, permit)
    return ApiResponseEnvelope(data=detail)


@work_permits_router.post(
    "/work-permits/{permit_id}/attachments",
    response_model=ApiResponseEnvelope[WorkPermitAttachmentItem],
    summary="上传作业票附件（盲板位置图/简图/示意图/照片）",
)
async def upload_work_permit_attachment(
    permit_id: UUID,
    file: UploadFile,
    category: str = Query("other"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitAttachmentItem]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    if category not in WORK_PERMIT_ATTACHMENT_CATEGORIES:
        raise AppException(status_code=422, message="非法的附件类别")
    file_name, content = await read_upload_secure(
        file,
        max_bytes=WORK_PERMIT_MAX_BYTES,
        allowed_extensions=WORK_PERMIT_ALLOWED_EXTS,
        what="作业票附件",
    )
    content_type = sniff_upload_mime(file_name, content)
    permit = await permit_service.get_permit(db, permit_id)
    storage_key = store_object(
        "work-permits",
        build_permit_attachment_key(
            str(permit.id), Path(file_name).suffix.lower()
        ),
        content,
        content_type,
    )
    attachment = WorkPermitAttachment(
        permit_id=permit.id,
        category=category,
        file_name=file_name,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=len(content),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return ApiResponseEnvelope(
        data=WorkPermitAttachmentItem.model_validate(attachment)
    )


async def _get_attachment(
    db: AsyncSession, permit_id: UUID, attachment_id: UUID
) -> WorkPermitAttachment:
    result = await db.execute(
        select(WorkPermitAttachment).where(
            WorkPermitAttachment.id == attachment_id,
            WorkPermitAttachment.permit_id == permit_id,
            WorkPermitAttachment.is_deleted.is_(False),
        )
    )
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise NotFoundException("附件")
    return attachment


@work_permits_router.get(
    "/work-permits/{permit_id}/attachments/{attachment_id}/content",
    response_model=None,
    summary="下载作业票附件",
)
async def download_work_permit_attachment(
    permit_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    attachment = await _get_attachment(db, permit_id, attachment_id)
    stored = read_object("work-permits", attachment.storage_key)
    if stored is None:
        raise NotFoundException("附件文件")
    data, content_type = stored
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(attachment.file_name)}"
            )
        },
    )


@work_permits_router.get(
    "/work-permits/{permit_id}/attachments/{attachment_id}/preview",
    response_model=None,
    summary="作业票附件在线预览",
)
async def preview_work_permit_attachment(
    permit_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    attachment = await _get_attachment(db, permit_id, attachment_id)
    stored = read_object("work-permits", attachment.storage_key)
    if stored is None:
        raise NotFoundException("附件文件")
    data, _content_type = stored
    try:
        preview_data, preview_type, preview_name = resolve_preview_content(
            data, attachment.file_name
        )
    except ValueError as exc:
        raise AppException(message=str(exc), status_code=415) from exc
    return Response(
        content=preview_data,
        media_type=preview_type,
        headers={
            "Content-Disposition": (
                f"inline; filename*=UTF-8''{quote(preview_name)}"
            )
        },
    )


@work_permits_router.delete(
    "/work-permits/{permit_id}/attachments/{attachment_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除作业票附件（软删除）",
)
async def delete_work_permit_attachment(
    permit_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    attachment = await _get_attachment(db, permit_id, attachment_id)
    attachment.is_deleted = True
    attachment.updated_by = current_user.id
    await db.commit()
    delete_object("work-permits", attachment.storage_key)
    return ApiResponseEnvelope(data=None, message="删除成功")


# ── 审批人配置 ──


def _config_items(rows: Sequence[Any]) -> list[ApproverConfigItem]:
    return [
        ApproverConfigItem(
            id=config.id,
            permit_type=config.permit_type,
            node_key=config.node_key,
            node_name=config.node_name,
            approver_user_id=config.approver_user_id,
            approver_user_name=user_name,
            remark=config.remark,
        )
        for config, user_name in rows
    ]


@work_permits_router.get(
    "/work-permit-settings",
    response_model=ApiResponseEnvelope[WorkPermitSettingsResponse],
    summary="作业票运行参数（人员证件校验开关）",
)
async def get_work_permit_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitSettingsResponse]:
    settings = await permit_service.get_runtime_settings(db)
    return ApiResponseEnvelope(
        data=WorkPermitSettingsResponse(
            cert_check_strict=bool(
                settings.get(permit_service.CERT_CHECK_STRICT_KEY, False)
            )
        )
    )


@work_permits_router.put(
    "/work-permit-settings",
    response_model=ApiResponseEnvelope[WorkPermitSettingsResponse],
    summary="保存作业票运行参数（人员证件校验开关）",
)
async def update_work_permit_settings(
    payload: WorkPermitSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[WorkPermitSettingsResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    await permit_service.upsert_runtime_setting(
        db,
        permit_service.CERT_CHECK_STRICT_KEY,
        payload.cert_check_strict,
        current_user.id,
    )
    await db.commit()
    return ApiResponseEnvelope(
        data=WorkPermitSettingsResponse(
            cert_check_strict=payload.cert_check_strict
        )
    )


@work_permits_router.get(
    "/work-permit-configs",
    response_model=ApiResponseEnvelope[ApproverConfigListResponse],
    summary="节点默认审批人配置列表",
)
async def list_approver_configs(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ApproverConfigListResponse]:
    result = await db.execute(
        select(WorkPermitApproverConfig, User.name)
        .join(
            User,
            User.id == WorkPermitApproverConfig.approver_user_id,
            isouter=True,
        )
        .where(WorkPermitApproverConfig.is_deleted.is_(False))
        .order_by(
            WorkPermitApproverConfig.permit_type,
            WorkPermitApproverConfig.node_key,
        )
    )
    return ApiResponseEnvelope(
        data=ApproverConfigListResponse(items=_config_items(result.all()))
    )


@work_permits_router.put(
    "/work-permit-configs",
    response_model=ApiResponseEnvelope[ApproverConfigListResponse],
    summary="保存节点默认审批人（按票种+节点 upsert）",
)
async def upsert_approver_config(
    payload: ApproverConfigUpsertInput,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ApproverConfigListResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    template = PERMIT_TEMPLATES.get(str(payload.permit_type))
    if template is None:
        raise AppException(status_code=422, message="未知票种")
    node_tpl = next(
        (n for n in template.nodes if n["key"] == payload.node_key), None
    )
    if node_tpl is None:
        raise AppException(status_code=422, message="未知审批节点")
    if payload.approver_user_id is not None:
        exists = await db.execute(
            select(User.id).where(User.id == payload.approver_user_id)
        )
        if exists.scalar_one_or_none() is None:
            raise NotFoundException("用户", str(payload.approver_user_id))

    result = await db.execute(
        select(WorkPermitApproverConfig).where(
            WorkPermitApproverConfig.permit_type == str(payload.permit_type),
            WorkPermitApproverConfig.node_key == payload.node_key,
            WorkPermitApproverConfig.is_deleted.is_(False),
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        config = WorkPermitApproverConfig(
            permit_type=str(payload.permit_type),
            node_key=payload.node_key,
            node_name=node_tpl["name"],
            approver_user_id=payload.approver_user_id,
            remark=payload.remark,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(config)
    else:
        config.approver_user_id = payload.approver_user_id
        config.remark = payload.remark
        config.updated_by = current_user.id
    await db.commit()
    return await list_approver_configs(db=db, current_user=current_user)
