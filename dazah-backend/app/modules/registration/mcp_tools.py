"""Registration 模块暴露给 AI Agent 的 MCP Tools。

覆盖：授权书、证书、费用、知识库、申报进度。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.exceptions import AppException
from app.modules.registration.models.authorization import (
    AuthorizationFdaEntry,
    AuthorizationLetter,
)
from app.modules.registration.models.certificate import RegistrationCertificateEntry
from app.modules.registration.models.declaration_progress import (
    RegistrationDeclarationProgressVersion,
)
from app.modules.registration.models.fee import RegistrationFee
from app.modules.registration.models.knowledge import KnowledgeArticle
from app.platform.identity.models import User
from app.platform.mcp.deps import get_db, get_user
from app.platform.mcp.server import mcp


def _require_mcp_user() -> User:
    """校验 MCP 调用方身份，写操作必须登录（后端规范：所有业务 API 默认需要登录）。"""
    user = get_user()
    if user is None:
        raise AppException(message="需要登录才能执行写操作", status_code=401)
    return user


# ── Tool 1: 授权书 ────────────────────────────────────────


@mcp.tool()
async def registration_query_authorization_letters(
    product_name: str | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询授权书生成记录。

    Args:
        product_name: 产品名称，可选
        keyword: 搜索关键词，可选
    """
    db = get_db()
    stmt = select(AuthorizationLetter).where(
        AuthorizationLetter.is_deleted == False  # noqa: E712
    )

    if product_name:
        stmt = stmt.where(AuthorizationLetter.product_name.ilike(f"%{product_name}%"))
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (AuthorizationLetter.preparation_name.ilike(pattern))
            | (AuthorizationLetter.registration_number.ilike(pattern))
        )

    stmt = stmt.order_by(AuthorizationLetter.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "product_name": a.product_name or "",
            "registration_number": a.registration_number or "",
            "preparation_name": a.preparation_name or "",
            "preparation_unit": a.preparation_unit or "",
            "administration_route": a.administration_route or "",
            "remarks": a.remarks or "",
        }
        for a in items
    ]


# ── Tool 2: FDA 授权记录 ──────────────────────────────────


@mcp.tool()
async def registration_query_fda_entries(
    product_name: str | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询 FDA 授权记录。

    Args:
        product_name: 产品名称，可选
        keyword: 搜索关键词，可选
    """
    db = get_db()
    stmt = select(AuthorizationFdaEntry).where(
        AuthorizationFdaEntry.is_deleted == False  # noqa: E712
    )

    if product_name:
        stmt = stmt.where(AuthorizationFdaEntry.product_name.ilike(f"%{product_name}%"))
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (AuthorizationFdaEntry.company_name.ilike(pattern))
            | (AuthorizationFdaEntry.address.ilike(pattern))
        )

    stmt = stmt.limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "product_name": e.product_name or "",
            "company_name": e.company_name or "",
            "address": e.address or "",
            "reference_number": e.reference_number or "",
        }
        for e in items
    ]


# ── Tool 3: 证书 ──────────────────────────────────────────


@mcp.tool()
async def registration_query_certificates(
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询注册证书台账。

    Args:
        keyword: 搜索关键词（证照名称、证书编号、发证机关、产品范围），可选
    """
    db = get_db()
    stmt = select(RegistrationCertificateEntry).where(
        RegistrationCertificateEntry.is_deleted == False  # noqa: E712
    )

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (RegistrationCertificateEntry.certificate_name.ilike(pattern))
            | (RegistrationCertificateEntry.certificate_number.ilike(pattern))
            | (RegistrationCertificateEntry.issuing_authority.ilike(pattern))
            | (RegistrationCertificateEntry.product_scope.ilike(pattern))
        )

    stmt = stmt.order_by(RegistrationCertificateEntry.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "certificate_name": c.certificate_name or "",
            "certificate_number": c.certificate_number or "",
            "acceptance_number": c.acceptance_number or "",
            "approval_number": c.approval_number or "",
            "issuing_authority": c.issuing_authority or "",
            "issue_date": c.issue_date or "",
            "expiry_date": c.expiry_date or "",
            "validity_period": c.validity_period or "",
            "product_scope": c.product_scope or "",
            "quality_standard": c.quality_standard or "",
        }
        for c in items
    ]


# ── Tool 4: 费用 ──────────────────────────────────────────


@mcp.tool()
async def registration_query_fees(
    keyword: str | None = None,
    fee_type: str | None = None,
    payment_status: str | None = None,
    project_name: str | None = None,
    product_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询注册费用记录。

    Args:
        keyword: 搜索关键词（代理机构、开支内容、经办人），可选
        fee_type: 费用类型，可选
        payment_status: 支付状态，可选
        project_name: 关联项目名称，可选
        product_name: 产品名称，可选
    """
    db = get_db()
    stmt = select(RegistrationFee).where(
        RegistrationFee.is_deleted == False  # noqa: E712
    )

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (RegistrationFee.agency_name.ilike(pattern))
            | (RegistrationFee.expense_content.ilike(pattern))
            | (RegistrationFee.handler.ilike(pattern))
        )
    if fee_type:
        stmt = stmt.where(RegistrationFee.fee_type == fee_type)
    if payment_status:
        stmt = stmt.where(RegistrationFee.payment_status == payment_status)
    if project_name:
        stmt = stmt.where(RegistrationFee.project_name.ilike(f"%{project_name}%"))
    if product_name:
        stmt = stmt.where(RegistrationFee.product_name.ilike(f"%{product_name}%"))

    stmt = stmt.order_by(RegistrationFee.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(f.id),
            "fee_type": f.fee_type or "",
            "amount": str(f.amount) if f.amount else "0",
            "currency": f.currency or "CNY",
            "payment_status": f.payment_status or "",
            "payment_date": f.payment_date or "",
            "project_name": f.project_name or "",
            "product_name": f.product_name or "",
            "country": f.country or "",
            "agency_name": f.agency_name or "",
            "expense_content": f.expense_content or "",
            "handler": f.handler or "",
            "contract_received": f.contract_received,
            "invoice_settled": f.invoice_settled,
        }
        for f in items
    ]


# ── Tool 5: 知识库 ────────────────────────────────────────


@mcp.tool()
async def registration_query_knowledge_articles(
    keyword: str | None = None,
    tags: str | None = None,
    country: str | None = None,
    product: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询注册知识库文章。

    Args:
        keyword: 搜索关键词（标题、内容），可选
        tags: 标签（逗号分隔），可选
        country: 适用国家，可选
        product: 关联产品，可选
    """
    db = get_db()
    stmt = select(KnowledgeArticle).where(
        KnowledgeArticle.is_deleted == False,  # noqa: E712
        KnowledgeArticle.is_published == True,  # noqa: E712
    )

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (KnowledgeArticle.title.ilike(pattern))
            | (KnowledgeArticle.content.ilike(pattern))
            | (KnowledgeArticle.tags.ilike(pattern))
        )
    if tags:
        for tag in tags.split(","):
            stmt = stmt.where(KnowledgeArticle.tags.ilike(f"%{tag.strip()}%"))
    if country:
        stmt = stmt.where(KnowledgeArticle.country.ilike(f"%{country}%"))
    if product:
        stmt = stmt.where(KnowledgeArticle.product.ilike(f"%{product}%"))

    stmt = stmt.order_by(KnowledgeArticle.created_at.desc()).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "title": a.title or "",
            "tags": a.tags or "",
            "country": a.country or "",
            "product": a.product or "",
            "author": a.author or "",
            "view_count": a.view_count or 0,
            "published_at": a.published_at.isoformat() if a.published_at else "",
        }
        for a in items
    ]


# ── Tool 6: 申报进度 ──────────────────────────────────────


@mcp.tool()
async def registration_query_declaration_progress(
    keyword: str | None = None,
    sheet_key: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询申报进度台账。返回最新的版本记录。

    Args:
        keyword: 搜索关键词（项目名、产品名），可选
        sheet_key: 子表键，用于筛选特定子表，可选
    """
    db = get_db()
    # 查询最新版本号
    from sqlalchemy import func as sa_func

    subq = (
        select(
            RegistrationDeclarationProgressVersion.record_group_id,
            sa_func.max(RegistrationDeclarationProgressVersion.version_number).label(
                "max_version"
            ),
        )
        .where(
            RegistrationDeclarationProgressVersion.is_deleted == False  # noqa: E712
        )
        .group_by(RegistrationDeclarationProgressVersion.record_group_id)
        .subquery()
    )

    stmt = select(RegistrationDeclarationProgressVersion).join(
        subq,
        (
            RegistrationDeclarationProgressVersion.record_group_id
            == subq.c.record_group_id
        )
        & (RegistrationDeclarationProgressVersion.version_number == subq.c.max_version),
    )

    if sheet_key:
        stmt = stmt.where(RegistrationDeclarationProgressVersion.sheet_key == sheet_key)
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (RegistrationDeclarationProgressVersion.project_name.ilike(pattern))
            | (RegistrationDeclarationProgressVersion.product_name.ilike(pattern))
        )

    stmt = stmt.order_by(
        RegistrationDeclarationProgressVersion.created_at.desc()
    ).limit(30)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "sheet_name": p.sheet_name or "",
            "project_name": p.project_name or "",
            "product_name": p.product_name or "",
            "version_number": p.version_number if p.version_number else 0,
        }
        for p in items
    ]


# ═══════════════════ 写操作工具 ═══════════════════


# ── Tool 7: 创建费用记录 ──────────────────────────────────


@mcp.tool()
async def registration_create_fee(
    fee_type: str,
    amount: float,
    payment_status: str,
    operator_name: str,
    project_name: str = "",
    product_name: str = "",
    agency_name: str = "",
    expense_content: str = "",
    country: str = "",
    remarks: str = "",
) -> dict[str, str]:
    """
    创建一条注册费用记录。
    使用场景：登记注册相关的费用支出（检验费、代理费、注册费等）。

    Args:
        fee_type: 费用类型（如"检验费"、"代理费"、"注册费"）
        amount: 金额（数字）
        payment_status: 支付状态（如"已付"、"未付"、"待付"）
        operator_name: 经办人姓名（仅供参考，实际经办人以认证用户为准）
        project_name: 关联项目名称，可选
        product_name: 关联产品名称，可选
        agency_name: 代理机构名称，可选
        expense_content: 开支内容描述，可选
        country: 国家/地区，可选
        remarks: 备注，可选
    """
    user = _require_mcp_user()
    db = get_db()
    from decimal import Decimal

    from app.modules.registration.schemas.fee import FeeEntryCreate
    from app.modules.registration.service.fee import RegistrationFeeService

    data = FeeEntryCreate(
        fee_type=fee_type,
        amount=Decimal(str(amount)),
        payment_status=payment_status,
        handler=user.name,
        project_name=project_name or None,
        product_name=product_name or None,
        agency_name=agency_name or None,
        expense_content=expense_content or None,
        country=country or None,
        remarks=remarks or None,
    )
    service = RegistrationFeeService(db)
    result = await service.create_entry(data)
    return {
        "id": str(result.id),
        "message": f"费用记录已创建，金额: {amount}，类型: {fee_type}",
    }


# ── Tool 8: 创建证书记录 ──────────────────────────────────


@mcp.tool()
async def registration_create_certificate(
    certificate_name: str,
    operator_name: str,
    sheet_key: str = "domestic-gmp",
    certificate_number: str = "",
    issuing_authority: str = "",
    issue_date: str = "",
    expiry_date: str = "",
    product_scope: str = "",
) -> dict[str, str]:
    """
    创建一条注册证书台账记录。
    使用场景：新证书到货后通过飞书快速登记。

    Args:
        certificate_name: 证照名称（如"GMP证书"、"CEP证书"）
        operator_name: 操作人姓名（仅供参考，实际操作人以认证用户为准）
        sheet_key: 子表键，可选值：international-registr
        ation/domestic-registration/domestic-gmp
        /international-gmp，默认 domestic-gmp
        certificate_number: 证书编号，可选
        issuing_authority: 发证机关，可选
        issue_date: 发证日期（YYYY-MM-DD），可选
        expiry_date: 到期日期（YYYY-MM-DD），可选
        product_scope: 产品范围，可选
    """
    _require_mcp_user()
    allowed_sheet_keys = {
        "international-registration",
        "domestic-registration",
        "domestic-gmp",
        "international-gmp",
    }
    if sheet_key not in allowed_sheet_keys:
        raise AppException(
            message=(
                f"无效的 sheet_key：{sheet_key}，"
                f"可选值：{'/'.join(sorted(allowed_sheet_keys))}"
            ),
            status_code=400,
        )
    db = get_db()
    from app.modules.registration.schemas.certificate import (
        CertificateEntryCreate,
    )
    from app.modules.registration.service.certificate import (
        CertificateWorkbookService,
    )

    data = CertificateEntryCreate(
        sheet_key=sheet_key,
        certificate_name=certificate_name,
        certificate_number=certificate_number or None,
        issuing_authority=issuing_authority or None,
        issue_date=issue_date or None,
        validity_period=expiry_date or None,
        product_scope=product_scope or None,
    )
    service = CertificateWorkbookService(db)
    result = await service.create_entry(data)
    return {
        "id": str(result.id),
        "message": f"证书已登记: {certificate_name}",
    }
