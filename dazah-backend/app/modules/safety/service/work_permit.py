"""8 大特殊作业票流程引擎（提交/逐级审批/驳回重签/验票/验收/气体分析）。

状态机：draft → pending_approval（逐级 approve/confirm 节点）→ approved
（全部签批）→ active（作业前验票）→ completed（完工验收）；任一节点驳回 →
rejected（可编辑后重新提交，round+1 重走全链）；draft/pending/approved/active
可作废。节点实例保留历史轮次。

审批人解析：提交时节点改派 > work_permit_approver_configs 默认配置；
approve 节点必须有指派审批人；确认/验票/验收节点未指派时允许票创建人执行。
飞书通知在 service.work_permit_notify，失败不影响流程事务。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.core.redis import cache_delete, cache_get, cache_set
from app.modules.safety.models import (
    SpecialWorkCertificate,
    WorkPermit,
    WorkPermitApproverConfig,
    WorkPermitAttachment,
    WorkPermitGasAnalysis,
    WorkPermitNode,
    WorkPermitRelation,
    WorkPermitSetting,
)
from app.modules.safety.schemas.work_permit import (
    GasAnalysisCreate,
    GasAnalysisItem,
    PermitMeasureInput,
    PermitPersonInput,
    PermitPersonItem,
    PermitRelationItem,
    WorkPermitAttachmentItem,
    WorkPermitCreate,
    WorkPermitDetailResponse,
    WorkPermitListItem,
    WorkPermitListResponse,
    WorkPermitNodeItem,
    WorkPermitStatsResponse,
    WorkPermitUpdate,
)
from app.modules.safety.service.work_permit_templates import (
    CERTIFICATE_CATEGORY_LABELS,
    NODE_KIND_ACCEPT,
    NODE_KIND_APPROVE,
    NODE_KIND_CONFIRM,
    NODE_KIND_VERIFY,
    NODE_STATUS_APPROVED,
    NODE_STATUS_PENDING,
    NODE_STATUS_REJECTED,
    NODE_STATUS_WAITING,
    PERMIT_STATUS_ACTIVE,
    PERMIT_STATUS_APPROVED,
    PERMIT_STATUS_CANCELLED,
    PERMIT_STATUS_COMPLETED,
    PERMIT_STATUS_DRAFT,
    PERMIT_STATUS_PENDING,
    PERMIT_STATUS_REJECTED,
    PERSON_ROLE_CERT_CATEGORIES,
    PERSON_ROLE_LABELS,
    RISK_IDENTIFICATION_OPTIONS,
    VALIDITY_HOURS_DEFAULTS,
    active_nodes_for_level,
    gas_cycle_minutes_for,
    get_template,
)
from app.platform.audit.service import record_audit_log
from app.platform.identity.models import User

logger = logging.getLogger(__name__)

_VALID_NODE_KINDS = {
    NODE_KIND_APPROVE,
    NODE_KIND_CONFIRM,
    NODE_KIND_VERIFY,
    NODE_KIND_ACCEPT,
}
_SUBMITTABLE_STATUSES = {PERMIT_STATUS_DRAFT, PERMIT_STATUS_REJECTED}
_EDITABLE_STATUSES = {PERMIT_STATUS_DRAFT, PERMIT_STATUS_REJECTED}
_CANCELLABLE_STATUSES = {
    PERMIT_STATUS_DRAFT,
    PERMIT_STATUS_PENDING,
    PERMIT_STATUS_APPROVED,
    PERMIT_STATUS_ACTIVE,
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── 编号生成 ──


async def generate_permit_no(db: AsyncSession, permit_type: str) -> str:
    """生成票号 {前缀}-{yyyyMMdd}-{3位序号}；冲突时由调用方重试。"""
    template = get_template(permit_type)
    date_part = _utcnow().strftime("%Y%m%d")
    prefix = f"{template.no_prefix}-{date_part}-"
    result = await db.execute(
        select(WorkPermit.permit_no)
        .where(WorkPermit.permit_no.like(f"{prefix}%"))
        .order_by(WorkPermit.permit_no.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    seq = 1
    if last:
        try:
            seq = int(last.rsplit("-", 1)[-1]) + 1
        except ValueError:
            seq = 1
    return f"{prefix}{seq:03d}"


# ── 票面数据校验 ──


def validate_permit_payload(
    permit_type: str,
    permit_level: str,
    type_data: dict[str, Any] | None,
    persons: list[PermitPersonInput] | None,
    safety_measures: list[PermitMeasureInput] | None,
    risk_identifications: list[str] | None,
    *,
    strict: bool = False,
) -> list[str]:
    """校验票面数据与模板一致性，返回错误列表（strict=True 抛出异常）。"""
    template = get_template(permit_type)
    errors: list[str] = []
    if permit_level not in template.levels:
        errors.append(f"作业级别「{permit_level}」不属于 {template.name}")

    fields = {str(item["key"]): item for item in template.type_fields}
    data = type_data or {}
    unknown = {str(key) for key in set(data) - set(fields)}
    if unknown:
        errors.append(f"票面字段不存在: {','.join(sorted(unknown))}")
    for key, item in fields.items():
        if item.get("required") and not str(data.get(key) or "").strip():
            errors.append(f"「{item['label']}」为必填项")

    valid_roles = {item["role"] for item in template.person_roles}
    for person in persons or []:
        if person.role not in valid_roles:
            errors.append(f"人员角色「{person.role}」不属于 {template.name}")

    valid_measures = {item["key"] for item in template.measures}
    for measure in safety_measures or []:
        if measure.key not in valid_measures:
            errors.append(f"安全措施项「{measure.key}」不属于 {template.name}")

    valid_risks = set(RISK_IDENTIFICATION_OPTIONS)
    for risk in risk_identifications or []:
        if risk not in valid_risks:
            errors.append(f"风险辨识选项「{risk}」不在票面清单内")

    if strict and errors:
        raise AppException(status_code=422, message="；".join(errors[:5]))
    return errors


# ── 查询 ──


async def get_permit(db: AsyncSession, permit_id: UUID) -> WorkPermit:
    result = await db.execute(
        select(WorkPermit).where(
            WorkPermit.id == permit_id, WorkPermit.is_deleted.is_(False)
        )
    )
    permit = result.scalar_one_or_none()
    if permit is None:
        raise NotFoundException("作业票", str(permit_id))
    return permit


async def _user_name_map(
    db: AsyncSession, user_ids: list[UUID]
) -> dict[UUID, str]:
    ids = [uid for uid in set(user_ids) if uid is not None]
    if not ids:
        return {}
    result = await db.execute(select(User.id, User.name).where(User.id.in_(ids)))
    return {row[0]: row[1] for row in result.all()}


async def _load_settings(db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        select(WorkPermitSetting).where(WorkPermitSetting.is_deleted.is_(False))
    )
    return {row.setting_key: row.setting_value for row in result.scalars().all()}


def _setting_value(
    settings: dict[str, Any], key: str, default: Any
) -> Any:
    value = settings.get(key)
    return default if value is None else value


# 作业票运行参数键：作业人员证件强校验（False=软提示，True=提交拦截）
CERT_CHECK_STRICT_KEY = "cert_check_strict"


async def certificate_check_issues(
    db: AsyncSession, permit: WorkPermit
) -> list[str]:
    """按角色建议类别检查作业人员证件，返回问题文案列表。

    口径（PERSON_ROLE_CERT_CATEGORIES，30 天内到期不拦）：
    - 建议持证角色未关联证件；
    - 所选证件不存在或已删除；
    - 证件类别与角色建议不符；
    - 证件已过期或已吊销；
    - 证件持有人与作业人姓名不一致。
    """
    required: list[tuple[dict[str, Any], tuple[str, ...]]] = []
    for person in permit.persons or []:
        role = str(person.get("role") or "")
        categories = PERSON_ROLE_CERT_CATEGORIES.get(role)
        if categories:
            required.append((person, categories))
    if not required:
        return []

    cert_ids = {
        UUID(str(person.get("certificate_id")))
        for person, _ in required
        if person.get("certificate_id")
    }
    certs: dict[UUID, SpecialWorkCertificate] = {}
    if cert_ids:
        rows = await db.execute(
            select(SpecialWorkCertificate).where(
                SpecialWorkCertificate.id.in_(cert_ids),
                SpecialWorkCertificate.is_deleted.is_(False),
            )
        )
        certs = {cert.id: cert for cert in rows.scalars().all()}

    issues: list[str] = []
    for person, categories in required:
        name = str(person.get("name") or "未填写姓名")
        role_label = PERSON_ROLE_LABELS.get(
            str(person.get("role") or ""), "该角色"
        )
        cert_id = person.get("certificate_id")
        if not cert_id:
            issues.append(f"「{name}」{role_label}未关联证件")
            continue
        cert = certs.get(UUID(str(cert_id)))
        if cert is None:
            issues.append(f"「{name}」{role_label}关联的证件不存在或已删除")
            continue
        if cert.certificate_category not in categories:
            category_label = CERTIFICATE_CATEGORY_LABELS.get(
                cert.certificate_category, cert.certificate_category
            )
            suggested = "、".join(
                CERTIFICATE_CATEGORY_LABELS.get(item, item)
                for item in categories
            )
            issues.append(
                f"「{name}」{role_label}证件类别为「{category_label}」，"
                f"建议「{suggested}」"
            )
        if cert.status in ("expired", "revoked"):
            state = "已过期" if cert.status == "expired" else "已吊销"
            issues.append(f"「{name}」{role_label}证件{state}")
        elif cert.person_name and cert.person_name != name:
            issues.append(
                f"「{name}」{role_label}证件持有人为「{cert.person_name}」"
            )
    return issues


async def get_runtime_settings(db: AsyncSession) -> dict[str, Any]:
    """作业票运行参数（work_permit_settings 全量键值）。"""
    return await _load_settings(db)


async def upsert_runtime_setting(
    db: AsyncSession, key: str, value: Any, user_id: UUID | None
) -> None:
    result = await db.execute(
        select(WorkPermitSetting).where(
            WorkPermitSetting.setting_key == key,
            WorkPermitSetting.is_deleted.is_(False),
        )
    )
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = WorkPermitSetting(
            setting_key=key,
            setting_value=value,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(setting)
    else:
        setting.setting_value = value
        setting.updated_by = user_id
    await db.flush()


def _gas_due_info(
    permit: WorkPermit, analyses: list[WorkPermitGasAnalysis], settings: dict[str, Any]
) -> tuple[datetime | None, bool]:
    """计算下次复检到期时间与是否超期（仅作业中的周期复检票种）。"""
    if permit.status != PERMIT_STATUS_ACTIVE:
        return None, False
    cycle_map = _setting_value(settings, "gas_cycle_minutes", {}) or {}
    cycle = gas_cycle_minutes_for(permit.permit_type, cycle_map)
    if cycle is None:
        return None, False
    base: datetime | None = None
    for item in analyses:
        if item.phase == "on_duty":
            base = item.sampled_at if base is None else max(base, item.sampled_at)
    if base is None:
        base = permit.actual_start_time or permit.planned_start_time
    if base is None:
        return None, False
    due = base + timedelta(minutes=cycle)
    return due, due < _utcnow()


async def build_detail(
    db: AsyncSession, permit: WorkPermit
) -> WorkPermitDetailResponse:
    nodes_result = await db.execute(
        select(WorkPermitNode)
        .where(
            WorkPermitNode.permit_id == permit.id,
            WorkPermitNode.is_deleted.is_(False),
        )
        .order_by(WorkPermitNode.round, WorkPermitNode.seq)
    )
    nodes = list(nodes_result.scalars().all())
    gas_result = await db.execute(
        select(WorkPermitGasAnalysis)
        .where(
            WorkPermitGasAnalysis.permit_id == permit.id,
            WorkPermitGasAnalysis.is_deleted.is_(False),
        )
        .order_by(WorkPermitGasAnalysis.sampled_at)
    )
    analyses = list(gas_result.scalars().all())
    rel_result = await db.execute(
        select(WorkPermitRelation, WorkPermit)
        .join(
            WorkPermit,
            WorkPermit.id == WorkPermitRelation.related_permit_id,
        )
        .where(
            WorkPermitRelation.permit_id == permit.id,
            WorkPermitRelation.is_deleted.is_(False),
            WorkPermit.is_deleted.is_(False),
        )
    )
    att_result = await db.execute(
        select(WorkPermitAttachment)
        .where(
            WorkPermitAttachment.permit_id == permit.id,
            WorkPermitAttachment.is_deleted.is_(False),
        )
        .order_by(WorkPermitAttachment.created_at)
    )

    user_ids = [
        node.assigned_approver_id for node in nodes if node.assigned_approver_id
    ] + [node.acted_by for node in nodes if node.acted_by]
    name_map = await _user_name_map(db, user_ids)

    # 人员证件有效性快照
    cert_ids = [
        UUID(p["certificate_id"])
        for p in (permit.persons or [])
        if p.get("certificate_id")
    ]
    cert_status: dict[UUID, str] = {}
    if cert_ids:
        certs = await db.execute(
            select(SpecialWorkCertificate.id, SpecialWorkCertificate.status).where(
                SpecialWorkCertificate.id.in_(cert_ids)
            )
        )
        cert_status = {row[0]: row[1] for row in certs.all()}

    persons_out: list[dict[str, Any]] = []
    for p in permit.persons or []:
        item = dict(p)
        cert_id = p.get("certificate_id")
        if cert_id:
            status = cert_status.get(UUID(str(cert_id)))
            item["certificate_status"] = status
            item["certificate_valid"] = status == "valid"
        else:
            item["certificate_valid"] = None
        persons_out.append(item)

    settings = await _load_settings(db)
    next_due, overdue = _gas_due_info(permit, analyses, settings)

    detail = WorkPermitDetailResponse.model_validate(permit)
    detail.persons = [
        PermitPersonItem.model_validate(
            {
                "role": p.get("role", ""),
                "name": p.get("name", ""),
                "user_id": p.get("user_id"),
                "certificate_id": p.get("certificate_id"),
                "certificate_no": p.get("certificate_no"),
                "certificate_category": p.get("certificate_category"),
                "certificate_valid": p.get("certificate_valid"),
                "certificate_status": p.get("certificate_status"),
            }
        )
        for p in persons_out
    ]
    detail.nodes = [
        WorkPermitNodeItem(
            id=node.id,
            round=node.round,
            seq=node.seq,
            node_key=node.node_key,
            node_name=node.node_name,
            node_kind=node.node_kind,
            status=node.status,
            assigned_approver_id=node.assigned_approver_id,
            assigned_approver_name=(
                name_map.get(node.assigned_approver_id)
                if node.assigned_approver_id
                else None
            ),
            acted_by=node.acted_by,
            acted_by_name=name_map.get(node.acted_by) if node.acted_by else None,
            acted_at=node.acted_at,
            opinion=node.opinion,
        )
        for node in nodes
    ]
    detail.gas_analyses = [
        GasAnalysisItem(
            id=item.id,
            phase=item.phase,
            sampled_at=item.sampled_at,
            analysis_point=item.analysis_point,
            items=list(item.items or []),
            oxygen_value=item.oxygen_value,
            analyst_name=item.analyst_name,
            remark=item.remark,
        )
        for item in analyses
    ]
    detail.relations = [
        PermitRelationItem(
            related_permit_id=rel.related_permit_id,
            related_permit_no=related.permit_no,
            related_permit_type=related.permit_type,
            related_permit_status=related.status,
        )
        for rel, related in rel_result.all()
    ]
    detail.attachments = [
        WorkPermitAttachmentItem.model_validate(item)
        for item in att_result.scalars().all()
    ]
    detail.next_gas_due_at = next_due
    detail.gas_overdue = overdue
    return detail


# ── CRUD ──


async def create_permit(
    db: AsyncSession, data: WorkPermitCreate, current_user: User
) -> WorkPermit:
    validate_permit_payload(
        str(data.permit_type),
        data.permit_level,
        data.type_data,
        data.persons,
        data.safety_measures,
        data.risk_identifications,
        strict=True,
    )
    permit = WorkPermit(
        permit_no=await generate_permit_no(db, str(data.permit_type)),
        permit_type=str(data.permit_type),
        permit_level=data.permit_level,
        status=PERMIT_STATUS_DRAFT,
        apply_department=data.apply_department,
        apply_time=data.apply_time or _utcnow(),
        work_description=data.work_description,
        work_location=data.work_location,
        work_unit=data.work_unit,
        planned_start_time=data.planned_start_time,
        planned_end_time=data.planned_end_time,
        persons=[
            p.model_dump(exclude_none=True, mode="json") for p in data.persons
        ],
        risk_identifications=data.risk_identifications,
        safety_measures=[m.model_dump(exclude_none=True) for m in data.safety_measures],
        type_data=data.type_data,
        related_legacy_no_text=data.related_legacy_no_text,
        remark=data.remark,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(permit)
    await db.flush()
    await record_audit_log(
        db,
        action="create",
        resource_type="work_permit",
        resource_id=permit.id,
        user_id=current_user.id,
        new_value={"permit_no": permit.permit_no},
    )
    return permit


async def update_permit(
    db: AsyncSession, permit_id: UUID, data: WorkPermitUpdate, current_user: User
) -> WorkPermit:
    permit = await get_permit(db, permit_id)
    if permit.status not in _EDITABLE_STATUSES:
        raise AppException(
            status_code=409, message="仅草稿或已驳回的作业票可以编辑"
        )
    if permit.created_by != current_user.id and current_user.role != "admin":
        raise AppException(status_code=403, message="只有创建人或管理员可以编辑")

    patch = data.model_dump(exclude_none=True)
    if not patch:
        return permit
    level = patch.get("permit_level", permit.permit_level)
    type_data = patch.get("type_data", permit.type_data)
    persons_raw = patch.get("persons")
    measures_raw = patch.get("safety_measures")
    risks_raw = patch.get("risk_identifications")
    persons = (
        [PermitPersonInput.model_validate(p) for p in persons_raw]
        if persons_raw is not None
        else None
    )
    measures = (
        [PermitMeasureInput.model_validate(m) for m in measures_raw]
        if measures_raw is not None
        else None
    )
    validate_permit_payload(
        permit.permit_type,
        level,
        type_data,
        persons,
        measures,
        risks_raw,
        strict=True,
    )
    if persons_raw is not None:
        patch["persons"] = [
            p.model_dump(exclude_none=True) for p in persons or []
        ]
    if measures_raw is not None:
        patch["safety_measures"] = [
            m.model_dump(exclude_none=True) for m in measures or []
        ]
    patch["updated_by"] = current_user.id
    for field, value in patch.items():
        setattr(permit, field, value)
    await db.flush()
    await record_audit_log(
        db,
        action="update",
        resource_type="work_permit",
        resource_id=permit.id,
        user_id=current_user.id,
        old_value={"status": permit.status},
        new_value={"permit_no": permit.permit_no},
    )
    return permit


async def delete_permit(
    db: AsyncSession, permit_id: UUID, current_user: User
) -> None:
    permit = await get_permit(db, permit_id)
    if permit.status != PERMIT_STATUS_DRAFT:
        raise AppException(status_code=409, message="仅草稿作业票可以删除")
    if permit.created_by != current_user.id and current_user.role != "admin":
        raise AppException(status_code=403, message="只有创建人或管理员可以删除")
    permit.is_deleted = True
    permit.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="delete",
        resource_type="work_permit",
        resource_id=permit.id,
        user_id=current_user.id,
    )


# ── 审批人配置 ──


async def _approver_config_map(
    db: AsyncSession, permit_type: str
) -> dict[str, UUID | None]:
    result = await db.execute(
        select(WorkPermitApproverConfig).where(
            WorkPermitApproverConfig.permit_type == permit_type,
            WorkPermitApproverConfig.is_deleted.is_(False),
        )
    )
    return {
        row.node_key: row.approver_user_id for row in result.scalars().all()
    }


# ── 提交 / 审批 / 驳回 / 验票 / 验收 ──


def _resolve_actor_guard(
    node: WorkPermitNode,
    permit: WorkPermit,
    current_user: User,
) -> None:
    """校验当前用户可以处理该节点。"""
    if current_user.role == "admin":
        return
    if node.assigned_approver_id == current_user.id:
        return
    if (
        node.assigned_approver_id is None
        and permit.created_by == current_user.id
    ):
        return
    raise AppException(
        status_code=403, message=f"节点「{node.node_name}」未指派给你处理"
    )


async def _lock_permit(db: AsyncSession, permit_id: UUID) -> WorkPermit:
    result = await db.execute(
        select(WorkPermit)
        .where(WorkPermit.id == permit_id, WorkPermit.is_deleted.is_(False))
        .with_for_update()
    )
    permit = result.scalar_one_or_none()
    if permit is None:
        raise NotFoundException("作业票", str(permit_id))
    return permit


async def _acquire_submit_lock(permit_id: UUID) -> None:
    lock_key = f"safety:work_permit:submit_lock:{permit_id}"
    if await cache_get(lock_key):
        raise AppException(message="正在提交中，请勿重复操作")
    await cache_set(lock_key, "1", ex=30)


async def _validity_hours(
    settings: dict[str, Any], permit_type: str, permit_level: str
) -> float | None:
    configured = _setting_value(settings, "validity_hours", {}) or {}
    by_type = configured.get(permit_type) or VALIDITY_HOURS_DEFAULTS.get(
        permit_type
    )
    if by_type and permit_level in by_type:
        return float(by_type[permit_level])
    return None


async def submit_permit(
    db: AsyncSession,
    permit_id: UUID,
    assignments: dict[str, UUID | None],
    current_user: User,
) -> tuple[WorkPermit, list[str]]:
    """提交审批；返回 (作业票, 证件校验软提示)。

    cert_check_strict 开启时软提示升级为 422 拦截。
    提交锁在成功与失败路径统一释放（30s TTL 仅作进程崩溃兜底）。
    """
    await _acquire_submit_lock(permit_id)
    try:
        return await _submit_permit_locked(
            db, permit_id, assignments, current_user
        )
    finally:
        await cache_delete(f"safety:work_permit:submit_lock:{permit_id}")


async def _submit_permit_locked(
    db: AsyncSession,
    permit_id: UUID,
    assignments: dict[str, UUID | None],
    current_user: User,
) -> tuple[WorkPermit, list[str]]:
    permit = await _lock_permit(db, permit_id)
    if permit.status not in _SUBMITTABLE_STATUSES:
        raise AppException(status_code=409, message="当前状态不允许提交审批")
    if permit.created_by != current_user.id and current_user.role != "admin":
        raise AppException(status_code=403, message="只有创建人或管理员可以提交")

    settings = await _load_settings(db)
    validate_permit_payload(
        permit.permit_type,
        permit.permit_level,
        permit.type_data,
        [
            PermitPersonInput.model_validate(p)
            for p in (permit.persons or [])
        ],
        [
            PermitMeasureInput.model_validate(m)
            for m in (permit.safety_measures or [])
        ],
        permit.risk_identifications,
        strict=True,
    )
    if not permit.planned_start_time or not permit.planned_end_time:
        raise AppException(
            status_code=422, message="请填写作业实施时间（开始/结束）"
        )
    if permit.planned_end_time <= permit.planned_start_time:
        raise AppException(status_code=422, message="实施结束时间必须晚于开始时间")
    validity = await _validity_hours(
        settings, permit.permit_type, permit.permit_level
    )
    if validity is not None:
        span = (
            permit.planned_end_time - permit.planned_start_time
        ).total_seconds() / 3600
        if span > validity:
            raise AppException(
                status_code=422,
                message=(
                    f"实施时长 {span:.1f}h 超过 {permit.permit_level} 级"
                    f"{get_template(permit.permit_type).name}有效期 {validity:g}h"
                ),
            )

    # 人员证件校验：默认软提示随响应返回；cert_check_strict 开启时拦截
    cert_issues = await certificate_check_issues(db, permit)
    if cert_issues and _setting_value(settings, CERT_CHECK_STRICT_KEY, False):
        raise AppException(
            status_code=422,
            message="作业人员证件校验未通过：" + "；".join(cert_issues),
        )

    active = active_nodes_for_level(permit.permit_type, permit.permit_level)
    config_map = await _approver_config_map(db, permit.permit_type)
    new_round = permit.approval_round + 1

    for seq, node_tpl in enumerate(active, start=1):
        node_key = str(node_tpl["key"])
        approver_id = assignments.get(node_key)
        if approver_id is None:
            approver_id = config_map.get(node_key)
        if approver_id is None and node_tpl["kind"] == NODE_KIND_APPROVE:
            raise AppException(
                status_code=422,
                message=(
                    f"审批节点「{node_tpl['name']}」未指定审批人，"
                    "请在提交前指派或维护默认审批人配置"
                ),
            )
        node = WorkPermitNode(
            permit_id=permit.id,
            round=new_round,
            seq=seq,
            node_key=node_tpl["key"],
            node_name=node_tpl["name"],
            node_kind=node_tpl["kind"],
            status=(
                NODE_STATUS_PENDING if seq == 1 else NODE_STATUS_WAITING
            ),
            assigned_approver_id=approver_id,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(node)

    permit.approval_round = new_round
    permit.current_node_seq = 1
    permit.status = PERMIT_STATUS_PENDING
    permit.reject_opinion = None
    permit.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="submit",
        resource_type="work_permit",
        resource_id=permit.id,
        user_id=current_user.id,
        new_value={"round": new_round, "status": permit.status},
    )
    return permit, cert_issues


async def _current_node(
    db: AsyncSession, permit: WorkPermit
) -> WorkPermitNode:
    result = await db.execute(
        select(WorkPermitNode)
        .where(
            WorkPermitNode.permit_id == permit.id,
            WorkPermitNode.round == permit.approval_round,
            WorkPermitNode.seq == permit.current_node_seq,
            WorkPermitNode.is_deleted.is_(False),
        )
        .with_for_update()
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise AppException(status_code=409, message="当前没有待处理的审批节点")
    if node.status != NODE_STATUS_PENDING:
        raise AppException(
            status_code=409,
            message=f"节点「{node.node_name}」当前状态不允许该操作",
        )
    return node


async def approve_node(
    db: AsyncSession,
    permit_id: UUID,
    node_id: UUID,
    opinion: str | None,
    current_user: User,
) -> WorkPermit:
    permit = await _lock_permit(db, permit_id)
    if permit.status != PERMIT_STATUS_PENDING:
        raise AppException(status_code=409, message="作业票不在审批中")
    node = await _current_node(db, permit)
    if node.id != node_id:
        raise AppException(status_code=409, message="该节点不是当前待处理节点")
    if node.node_kind not in (NODE_KIND_APPROVE, NODE_KIND_CONFIRM):
        raise AppException(status_code=409, message="该节点不支持审批操作")
    _resolve_actor_guard(node, permit, current_user)

    now = _utcnow()
    node.opinion = opinion
    node.acted_by = current_user.id
    await _advance_with_count(db, permit, node, now)
    permit.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="approve",
        resource_type="work_permit_node",
        resource_id=node.id,
        user_id=current_user.id,
        new_value={"permit_no": permit.permit_no, "opinion": opinion},
    )
    return permit


async def _advance_with_count(
    db: AsyncSession, permit: WorkPermit, acted_node: WorkPermitNode, now: datetime
) -> None:
    """推进签批链；链尾的验票/验收节点不属于审批链（保持 waiting，
    由 verify/accept 动作按节点类型直接处理）。"""
    count_result = await db.execute(
        select(func.count(WorkPermitNode.id)).where(
            WorkPermitNode.permit_id == permit.id,
            WorkPermitNode.round == acted_node.round,
            WorkPermitNode.is_deleted.is_(False),
        )
    )
    total = count_result.scalar() or 0
    acted_node.status = NODE_STATUS_APPROVED
    acted_node.acted_at = now
    next_seq = acted_node.seq + 1
    next_kind: str | None = None
    if next_seq <= total:
        next_result = await db.execute(
            select(WorkPermitNode.node_kind).where(
                WorkPermitNode.permit_id == permit.id,
                WorkPermitNode.round == acted_node.round,
                WorkPermitNode.seq == next_seq,
            )
        )
        next_kind = next_result.scalar_one_or_none()

    if next_kind in (NODE_KIND_VERIFY, NODE_KIND_ACCEPT) or next_seq > total:
        # 审批链结束：验票/验收节点留给对应动作处理
        permit.current_node_seq = 0
        permit.status = PERMIT_STATUS_APPROVED
        return

    permit.current_node_seq = next_seq
    await db.execute(
        update(WorkPermitNode)
        .where(
            WorkPermitNode.permit_id == permit.id,
            WorkPermitNode.round == acted_node.round,
            WorkPermitNode.seq == next_seq,
        )
        .values(status=NODE_STATUS_PENDING)
    )


async def reject_node(
    db: AsyncSession,
    permit_id: UUID,
    node_id: UUID,
    opinion: str,
    current_user: User,
) -> WorkPermit:
    permit = await _lock_permit(db, permit_id)
    if permit.status != PERMIT_STATUS_PENDING:
        raise AppException(status_code=409, message="作业票不在审批中")
    node = await _current_node(db, permit)
    if node.id != node_id:
        raise AppException(status_code=409, message="该节点不是当前待处理节点")
    if node.node_kind not in (NODE_KIND_APPROVE, NODE_KIND_CONFIRM):
        raise AppException(status_code=409, message="该节点不支持驳回操作")
    _resolve_actor_guard(node, permit, current_user)

    now = _utcnow()
    node.status = NODE_STATUS_REJECTED
    node.opinion = opinion
    node.acted_by = current_user.id
    node.acted_at = now
    permit.status = PERMIT_STATUS_REJECTED
    permit.reject_opinion = opinion
    permit.current_node_seq = 0
    permit.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="reject",
        resource_type="work_permit_node",
        resource_id=node.id,
        user_id=current_user.id,
        new_value={"permit_no": permit.permit_no, "opinion": opinion},
    )
    return permit


async def verify_permit(
    db: AsyncSession, permit_id: UUID, current_user: User
) -> WorkPermit:
    permit = await _lock_permit(db, permit_id)
    if permit.status != PERMIT_STATUS_APPROVED:
        raise AppException(status_code=409, message="作业票尚未完成全部审批")
    node = await _current_verify_node(db, permit)
    _resolve_actor_guard(node, permit, current_user)
    now = _utcnow()
    node.status = NODE_STATUS_APPROVED
    node.acted_by = current_user.id
    node.acted_at = now
    permit.status = PERMIT_STATUS_ACTIVE
    permit.actual_start_time = now
    permit.current_node_seq = 0
    permit.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="verify",
        resource_type="work_permit",
        resource_id=permit.id,
        user_id=current_user.id,
    )
    return permit


async def _current_verify_node(
    db: AsyncSession, permit: WorkPermit
) -> WorkPermitNode:
    result = await db.execute(
        select(WorkPermitNode)
        .where(
            WorkPermitNode.permit_id == permit.id,
            WorkPermitNode.round == permit.approval_round,
            WorkPermitNode.node_kind == NODE_KIND_VERIFY,
            WorkPermitNode.is_deleted.is_(False),
        )
        .with_for_update()
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise AppException(
            status_code=409, message="该票种没有作业前验票环节，可直接开工并完工验收"
        )
    return node


async def accept_permit(
    db: AsyncSession,
    permit_id: UUID,
    type_data_patch: dict[str, Any] | None,
    current_user: User,
) -> WorkPermit:
    permit = await _lock_permit(db, permit_id)
    if permit.status != PERMIT_STATUS_ACTIVE and not (
        permit.status == PERMIT_STATUS_APPROVED
        and _has_no_verify(permit)
    ):
        raise AppException(
            status_code=409,
            message="仅作业中（或已批准且无验票环节）的作业票可以完工验收",
        )
    node = await _accept_node(db, permit)
    _resolve_actor_guard(node, permit, current_user)
    now = _utcnow()
    if type_data_patch:
        merged = dict(permit.type_data or {})
        merged.update(type_data_patch)
        permit.type_data = merged
    node.status = NODE_STATUS_APPROVED
    node.acted_by = current_user.id
    node.acted_at = now
    permit.status = PERMIT_STATUS_COMPLETED
    permit.actual_end_time = now
    permit.current_node_seq = 0
    permit.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="accept",
        resource_type="work_permit",
        resource_id=permit.id,
        user_id=current_user.id,
    )
    return permit


def _has_no_verify(permit: WorkPermit) -> bool:
    template = get_template(permit.permit_type)
    return all(n["kind"] != NODE_KIND_VERIFY for n in template.nodes)


async def _accept_node(db: AsyncSession, permit: WorkPermit) -> WorkPermitNode:
    result = await db.execute(
        select(WorkPermitNode)
        .where(
            WorkPermitNode.permit_id == permit.id,
            WorkPermitNode.round == permit.approval_round,
            WorkPermitNode.node_kind == NODE_KIND_ACCEPT,
            WorkPermitNode.is_deleted.is_(False),
        )
        .with_for_update()
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise NotFoundException("完工验收节点")
    return node


async def reassign_node(
    db: AsyncSession,
    permit_id: UUID,
    node_id: UUID,
    approver_user_id: UUID,
    current_user: User,
) -> WorkPermit:
    permit = await _lock_permit(db, permit_id)
    if current_user.role != "admin":
        raise AppException(status_code=403, message="仅管理员可以改派审批人")
    result = await db.execute(
        select(WorkPermitNode)
        .where(
            WorkPermitNode.id == node_id,
            WorkPermitNode.permit_id == permit.id,
            WorkPermitNode.round == permit.approval_round,
            WorkPermitNode.is_deleted.is_(False),
        )
        .with_for_update()
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise NotFoundException("审批节点")
    if node.status not in (NODE_STATUS_PENDING, NODE_STATUS_WAITING):
        raise AppException(status_code=409, message="仅未签字节点可以改派")
    node.assigned_approver_id = approver_user_id
    node.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="reassign",
        resource_type="work_permit_node",
        resource_id=node.id,
        user_id=current_user.id,
        new_value={"approver": str(approver_user_id)},
    )
    return permit


async def cancel_permit(
    db: AsyncSession, permit_id: UUID, current_user: User
) -> WorkPermit:
    permit = await _lock_permit(db, permit_id)
    if permit.status not in _CANCELLABLE_STATUSES:
        raise AppException(status_code=409, message="当前状态不允许作废")
    if permit.created_by != current_user.id and current_user.role != "admin":
        raise AppException(status_code=403, message="只有创建人或管理员可以作废")
    permit.status = PERMIT_STATUS_CANCELLED
    permit.current_node_seq = 0
    permit.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="cancel",
        resource_type="work_permit",
        resource_id=permit.id,
        user_id=current_user.id,
    )
    return permit


# ── 气体分析 ──


async def add_gas_analysis(
    db: AsyncSession,
    permit_id: UUID,
    data: GasAnalysisCreate,
    current_user: User,
) -> WorkPermitGasAnalysis:
    permit = await get_permit(db, permit_id)
    gas_allowed = (
        PERMIT_STATUS_PENDING,
        PERMIT_STATUS_APPROVED,
        PERMIT_STATUS_ACTIVE,
    )
    if permit.status not in gas_allowed:
        raise AppException(
            status_code=409, message="当前状态不允许录入气体分析"
        )
    if data.phase == "on_duty" and permit.status != PERMIT_STATUS_ACTIVE:
        raise AppException(
            status_code=409, message="作业期间复检需在验票开工（作业中）后录入"
        )
    item = WorkPermitGasAnalysis(
        permit_id=permit.id,
        phase=data.phase,
        sampled_at=data.sampled_at,
        analysis_point=data.analysis_point,
        items=[i.model_dump(exclude_none=True) for i in data.items],
        oxygen_value=data.oxygen_value,
        analyst_name=data.analyst_name or current_user.name,
        remark=data.remark,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(item)
    await db.flush()
    await record_audit_log(
        db,
        action="create",
        resource_type="work_permit_gas_analysis",
        resource_id=item.id,
        user_id=current_user.id,
        new_value={"permit_no": permit.permit_no, "phase": data.phase},
    )
    return item


async def delete_gas_analysis(
    db: AsyncSession, permit_id: UUID, analysis_id: UUID, current_user: User
) -> None:
    permit = await get_permit(db, permit_id)
    result = await db.execute(
        select(WorkPermitGasAnalysis).where(
            WorkPermitGasAnalysis.id == analysis_id,
            WorkPermitGasAnalysis.permit_id == permit.id,
            WorkPermitGasAnalysis.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundException("气体分析记录")
    if permit.created_by != current_user.id and current_user.role != "admin":
        raise AppException(status_code=403, message="只有创建人或管理员可以删除")
    if permit.status == PERMIT_STATUS_COMPLETED:
        raise AppException(status_code=409, message="已完工的作业票不允许删除检测记录")
    item.is_deleted = True
    await db.flush()


# ── 关联票 ──


async def add_relation(
    db: AsyncSession, permit_id: UUID, related_permit_id: UUID, current_user: User
) -> WorkPermitRelation:
    permit = await get_permit(db, permit_id)
    if related_permit_id == permit.id:
        raise AppException(status_code=422, message="不能关联自身")
    related = await get_permit(db, related_permit_id)
    exists = await db.execute(
        select(WorkPermitRelation.id).where(
            WorkPermitRelation.permit_id == permit.id,
            WorkPermitRelation.related_permit_id == related_permit_id,
            WorkPermitRelation.is_deleted.is_(False),
        )
    )
    if exists.scalar_one_or_none():
        raise AppException(status_code=409, message="该关联已存在")
    rel = WorkPermitRelation(
        permit_id=permit.id,
        related_permit_id=related_permit_id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(rel)
    await db.flush()
    await record_audit_log(
        db,
        action="create",
        resource_type="work_permit_relation",
        resource_id=rel.id,
        user_id=current_user.id,
        new_value={"related": related.permit_no},
    )
    return rel


async def remove_relation(
    db: AsyncSession, permit_id: UUID, related_permit_id: UUID
) -> None:
    result = await db.execute(
        select(WorkPermitRelation).where(
            WorkPermitRelation.permit_id == permit_id,
            WorkPermitRelation.related_permit_id == related_permit_id,
            WorkPermitRelation.is_deleted.is_(False),
        )
    )
    rel = result.scalar_one_or_none()
    if rel is None:
        raise NotFoundException("关联关系")
    rel.is_deleted = True
    await db.flush()


# ── 列表 / 统计 ──


async def list_permits(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    permit_type: str | None = None,
    permit_level: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> WorkPermitListResponse:
    conditions: list[ColumnElement[bool]] = [
        WorkPermit.is_deleted.is_(False)
    ]
    if permit_type:
        conditions.append(WorkPermit.permit_type == permit_type)
    if permit_level:
        conditions.append(WorkPermit.permit_level == permit_level)
    if status:
        conditions.append(WorkPermit.status == status)
    if date_from:
        conditions.append(WorkPermit.apply_time >= date_from)
    if date_to:
        conditions.append(WorkPermit.apply_time < date_to)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            WorkPermit.permit_no.ilike(like)
            | WorkPermit.work_description.ilike(like)
            | WorkPermit.work_location.ilike(like)
            | WorkPermit.apply_department.ilike(like)
        )
    total = await db.scalar(
        select(func.count(WorkPermit.id)).where(*conditions)
    )
    result = await db.execute(
        select(WorkPermit)
        .where(*conditions)
        .order_by(WorkPermit.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        WorkPermitListItem.model_validate(item) for item in result.scalars().all()
    ]
    return WorkPermitListResponse(
        items=items, total=total or 0, page=page, page_size=page_size
    )


async def get_stats(
    db: AsyncSession, current_user: User | None
) -> WorkPermitStatsResponse:
    result = await db.execute(
        select(WorkPermit.status, func.count(WorkPermit.id))
        .where(WorkPermit.is_deleted.is_(False))
        .group_by(WorkPermit.status)
    )
    counts = {row[0]: row[1] for row in result.all()}
    stats = WorkPermitStatsResponse(
        total=sum(counts.values()),
        draft=counts.get(PERMIT_STATUS_DRAFT, 0),
        pending_approval=counts.get(PERMIT_STATUS_PENDING, 0),
        approved=counts.get(PERMIT_STATUS_APPROVED, 0),
        active=counts.get(PERMIT_STATUS_ACTIVE, 0),
        completed=counts.get(PERMIT_STATUS_COMPLETED, 0),
        rejected=counts.get(PERMIT_STATUS_REJECTED, 0),
        cancelled=counts.get(PERMIT_STATUS_CANCELLED, 0),
    )
    if current_user is not None:
        my_pending = await db.scalar(
            select(func.count(WorkPermitNode.id)).where(
                WorkPermitNode.assigned_approver_id == current_user.id,
                WorkPermitNode.status == NODE_STATUS_PENDING,
                WorkPermitNode.is_deleted.is_(False),
            )
        )
        stats.my_pending_approvals = my_pending or 0
    return stats


# ── 附件辅助 ──


async def get_permit_with_access(
    db: AsyncSession, permit_id: UUID
) -> WorkPermit:
    return await get_permit(db, permit_id)


__all__ = [
    "CERT_CHECK_STRICT_KEY",
    "accept_permit",
    "add_gas_analysis",
    "add_relation",
    "approve_node",
    "build_detail",
    "cancel_permit",
    "certificate_check_issues",
    "create_permit",
    "delete_gas_analysis",
    "delete_permit",
    "generate_permit_no",
    "get_permit",
    "get_runtime_settings",
    "get_stats",
    "list_permits",
    "reject_node",
    "remove_relation",
    "reassign_node",
    "submit_permit",
    "update_permit",
    "upsert_runtime_setting",
    "validate_permit_payload",
    "verify_permit",
]
