"""人员特殊作业证件管理：CRUD、有效期状态计算、到期统计。

状态口径（保存时计算，与列表筛选一致）：
- ``valid``：有效期至 - 今天 > 30 天；
- ``expiring``：0 <= 剩余天数 <= 30；
- ``expired``：有效期至 < 今天；
- ``revoked``：人工标记吊销/注销（不做自动推算）。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.models import (
    SpecialWorkCertificate,
    SpecialWorkCertificateFile,
)
from app.modules.safety.schemas.work_certificate import (
    CertificateExpirySummaryResponse,
    SpecialWorkCertificateCreate,
    SpecialWorkCertificateListResponse,
    SpecialWorkCertificateResponse,
    SpecialWorkCertificateUpdate,
)
from app.modules.safety.service.work_permit_templates import (
    CERTIFICATE_CATEGORY_LABELS,
)
from app.platform.audit.service import record_audit_log
from app.platform.identity.models import User

logger = logging.getLogger(__name__)

EXPIRING_WINDOW_DAYS = 30
_VALID_STATUSES = {"valid", "expiring", "expired", "revoked"}


def compute_status(expiry_date: date | None, status_override: str = "") -> str:
    if status_override == "revoked":
        return "revoked"
    if expiry_date is None:
        return "valid"
    today = date.today()
    days = (expiry_date - today).days
    if days < 0:
        return "expired"
    if days <= EXPIRING_WINDOW_DAYS:
        return "expiring"
    return "valid"


def _validate_category(category: str) -> None:
    if category not in CERTIFICATE_CATEGORY_LABELS:
        raise AppException(status_code=422, message=f"未知证件类别「{category}」")


async def get_certificate(
    db: AsyncSession, certificate_id: UUID
) -> SpecialWorkCertificate:
    result = await db.execute(
        select(SpecialWorkCertificate).where(
            SpecialWorkCertificate.id == certificate_id,
            SpecialWorkCertificate.is_deleted.is_(False),
        )
    )
    cert = result.scalar_one_or_none()
    if cert is None:
        raise NotFoundException("证件", str(certificate_id))
    return cert


async def _ensure_no_conflict(
    db: AsyncSession,
    certificate_no: str | None,
    certificate_category: str,
    exclude_id: UUID | None = None,
) -> None:
    """证件号唯一口径与 DB 部分唯一索引一致：(证件号, 类别)。

    特种作业操作证号为「T+身份证号」，同一人跨类别（如焊接+高处）持同一
    证件号属正常业务，只在同类别内查重。
    """
    if not certificate_no:
        return
    query = select(SpecialWorkCertificate.id).where(
        SpecialWorkCertificate.certificate_no == certificate_no,
        SpecialWorkCertificate.certificate_category == certificate_category,
        SpecialWorkCertificate.is_deleted.is_(False),
    )
    if exclude_id:
        query = query.where(SpecialWorkCertificate.id != exclude_id)
    exists = await db.execute(query)
    if exists.scalar_one_or_none():
        raise AppException(
            status_code=409,
            message=f"证件号「{certificate_no}」在该类别下已存在",
        )


async def create_certificate(
    db: AsyncSession, data: SpecialWorkCertificateCreate, current_user: User
) -> SpecialWorkCertificate:
    _validate_category(data.certificate_category)
    await _ensure_no_conflict(
        db, data.certificate_no, data.certificate_category
    )
    cert = SpecialWorkCertificate(
        **data.model_dump(),
        status=compute_status(data.expiry_date, ""),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(cert)
    await db.flush()
    await record_audit_log(
        db,
        action="create",
        resource_type="special_work_certificate",
        resource_id=cert.id,
        user_id=current_user.id,
        new_value={"person": cert.person_name},
    )
    return cert


async def update_certificate(
    db: AsyncSession,
    certificate_id: UUID,
    data: SpecialWorkCertificateUpdate,
    current_user: User,
) -> SpecialWorkCertificate:
    cert = await get_certificate(db, certificate_id)
    patch = data.model_dump(exclude_none=True)
    if not patch:
        return cert
    category = patch.get("certificate_category")
    if category:
        _validate_category(str(category))
    if "certificate_no" in patch or category:
        new_no = patch.get("certificate_no", cert.certificate_no)
        new_category = str(category) if category else cert.certificate_category
        await _ensure_no_conflict(
            db, str(new_no) if new_no else None, new_category, certificate_id
        )
    for field, value in patch.items():
        setattr(cert, field, value)
    revoked = cert.status == "revoked"
    cert.status = compute_status(cert.expiry_date, "revoked" if revoked else "")
    cert.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="update",
        resource_type="special_work_certificate",
        resource_id=cert.id,
        user_id=current_user.id,
    )
    return cert


async def delete_certificate(
    db: AsyncSession, certificate_id: UUID, current_user: User
) -> None:
    cert = await get_certificate(db, certificate_id)
    cert.is_deleted = True
    cert.updated_by = current_user.id
    await db.flush()
    await record_audit_log(
        db,
        action="delete",
        resource_type="special_work_certificate",
        resource_id=cert.id,
        user_id=current_user.id,
    )


async def list_certificates(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    certificate_category: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    expiring_days: int | None = None,
) -> SpecialWorkCertificateListResponse:
    conditions: list[ColumnElement[bool]] = [
        SpecialWorkCertificate.is_deleted.is_(False)
    ]
    if certificate_category:
        conditions.append(
            SpecialWorkCertificate.certificate_category == certificate_category
        )
    if status:
        conditions.append(SpecialWorkCertificate.status == status)
    if expiring_days is not None:
        deadline = date.today() + timedelta(days=expiring_days)
        conditions.append(SpecialWorkCertificate.expiry_date.is_not(None))
        conditions.append(SpecialWorkCertificate.expiry_date <= deadline)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            SpecialWorkCertificate.person_name.ilike(like)
            | SpecialWorkCertificate.certificate_no.ilike(like)
            | SpecialWorkCertificate.department.ilike(like)
        )
    total = await db.scalar(
        select(func.count(SpecialWorkCertificate.id)).where(*conditions)
    )
    result = await db.execute(
        select(SpecialWorkCertificate)
        .where(*conditions)
        .order_by(SpecialWorkCertificate.expiry_date.asc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        to_response(cert) for cert in result.scalars().all()
    ]
    return SpecialWorkCertificateListResponse(
        items=items, total=total or 0, page=page, page_size=page_size
    )


def to_response(cert: SpecialWorkCertificate) -> SpecialWorkCertificateResponse:
    response = SpecialWorkCertificateResponse.model_validate(cert)
    response.certificate_category_label = CERTIFICATE_CATEGORY_LABELS.get(
        cert.certificate_category, cert.certificate_category
    )
    if cert.expiry_date is not None:
        response.days_to_expiry = (cert.expiry_date - date.today()).days
    return response


async def get_expiry_summary(db: AsyncSession) -> CertificateExpirySummaryResponse:
    result = await db.execute(
        select(SpecialWorkCertificate.status, func.count(SpecialWorkCertificate.id))
        .where(SpecialWorkCertificate.is_deleted.is_(False))
        .group_by(SpecialWorkCertificate.status)
    )
    counts: dict[str, int] = {row[0]: row[1] for row in result.all()}
    total = sum(counts.values())
    return CertificateExpirySummaryResponse(
        total=total,
        valid=counts.get("valid", 0),
        expiring_in_30d=counts.get("expiring", 0),
        expired=counts.get("expired", 0),
    )


async def add_certificate_file(
    db: AsyncSession,
    certificate_id: UUID,
    *,
    file_name: str,
    storage_key: str,
    content_type: str,
    size_bytes: int,
    user_id: UUID,
) -> SpecialWorkCertificateFile:
    cert = await get_certificate(db, certificate_id)
    file_obj = SpecialWorkCertificateFile(
        certificate_id=cert.id,
        file_name=file_name,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=size_bytes,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(file_obj)
    await db.flush()
    return file_obj


async def list_certificate_files(
    db: AsyncSession, certificate_id: UUID
) -> list[SpecialWorkCertificateFile]:
    result = await db.execute(
        select(SpecialWorkCertificateFile)
        .where(
            SpecialWorkCertificateFile.certificate_id == certificate_id,
            SpecialWorkCertificateFile.is_deleted.is_(False),
        )
        .order_by(SpecialWorkCertificateFile.created_at)
    )
    return list(result.scalars().all())


async def get_certificate_file(
    db: AsyncSession, certificate_id: UUID, file_id: UUID
) -> SpecialWorkCertificateFile:
    result = await db.execute(
        select(SpecialWorkCertificateFile).where(
            SpecialWorkCertificateFile.id == file_id,
            SpecialWorkCertificateFile.certificate_id == certificate_id,
            SpecialWorkCertificateFile.is_deleted.is_(False),
        )
    )
    file_obj = result.scalar_one_or_none()
    if file_obj is None:
        raise NotFoundException("证件附件")
    return file_obj


async def delete_certificate_file(
    db: AsyncSession,
    certificate_id: UUID,
    file_id: UUID,
    current_user: User,
) -> None:
    file_obj = await get_certificate_file(db, certificate_id, file_id)
    file_obj.is_deleted = True
    file_obj.updated_by = current_user.id
    await db.flush()


async def refresh_expired_statuses(db: AsyncSession) -> int:
    """按有效期刷新全部证件状态（供定时任务调用）。"""
    today = date.today()
    expiring_deadline = today + timedelta(days=EXPIRING_WINDOW_DAYS)
    changed = 0
    result = await db.execute(
        select(SpecialWorkCertificate).where(
            SpecialWorkCertificate.is_deleted.is_(False),
            SpecialWorkCertificate.status != "revoked",
        )
    )
    for cert in result.scalars().all():
        if cert.expiry_date is None:
            expected = "valid"
        elif cert.expiry_date < today:
            expected = "expired"
        elif cert.expiry_date <= expiring_deadline:
            expected = "expiring"
        else:
            expected = "valid"
        if cert.status != expected:
            cert.status = expected
            changed += 1
    if changed:
        await db.flush()
    return changed


async def certificates_due_for_expiry(
    db: AsyncSession, milestone_days: list[int]
) -> list[dict[str, Any]]:
    """返回命中的到期提醒候选：[{certificate, milestone_days}]。"""
    today = date.today()
    result = await db.execute(
        select(SpecialWorkCertificate).where(
            SpecialWorkCertificate.is_deleted.is_(False),
            SpecialWorkCertificate.status != "revoked",
            SpecialWorkCertificate.expiry_date.is_not(None),
        )
    )
    out: list[dict[str, Any]] = []
    for cert in result.scalars().all():
        if cert.expiry_date is None:
            continue
        days_left = (cert.expiry_date - today).days
        for milestone in milestone_days:
            if milestone > 0 and days_left == milestone:
                out.append({"certificate": cert, "milestone_days": milestone})
            elif milestone == 0 and days_left <= 0:
                out.append({"certificate": cert, "milestone_days": 0})
                break
    return out


__all__ = [
    "EXPIRING_WINDOW_DAYS",
    "add_certificate_file",
    "certificates_due_for_expiry",
    "compute_status",
    "create_certificate",
    "delete_certificate",
    "delete_certificate_file",
    "get_certificate",
    "get_certificate_file",
    "get_expiry_summary",
    "list_certificate_files",
    "list_certificates",
    "refresh_expired_statuses",
    "to_response",
    "update_certificate",
]
