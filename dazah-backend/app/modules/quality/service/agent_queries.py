"""Scoped read services for quality Agent queries without API-layer access."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.modules.quality.models.document_catalog import DocumentDepartment
from app.modules.quality.models.oot_limit import OotLimitProduct
from app.modules.quality.schemas.document_catalog import DocumentEntryOut
from app.modules.quality.schemas.oot_limit import OotLimitProductOut
from app.modules.quality.service import document_catalog_crud, validation_review
from app.platform.identity.data_scope import (
    current_page_actor,
    current_page_data_scope,
    resolve_user_department_scope,
)
from app.platform.identity.rbac import resolve_user_permissions


async def list_documents(
    db: AsyncSession,
    *,
    department_id: UUID | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    actor = current_page_actor.get()
    if actor is None:
        raise ForbiddenException("文件目录查询缺少可信用户")
    scope = await resolve_user_department_scope(db, actor)
    scope_ids: list[str] | None = None if scope.is_all else []
    if not scope.is_all and scope.department_names:
        result = await db.execute(
            select(DocumentDepartment.id).where(
                DocumentDepartment.is_deleted.is_(False),
                DocumentDepartment.name.in_(scope.department_names),
            )
        )
        scope_ids = [str(value) for value in result.scalars().all()]
    rows, total = await document_catalog_crud.list_document_entries(
        db,
        department_id=department_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
        scope_dept_ids=scope_ids,
    )
    return {
        "items": [
            DocumentEntryOut.model_validate(row).model_dump(mode="json") for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def list_oot_limit_products(
    db: AsyncSession,
    *,
    keyword: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    query = select(OotLimitProduct).where(OotLimitProduct.is_deleted.is_(False))
    if keyword:
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(
            or_(
                OotLimitProduct.product_code.ilike(pattern),
                OotLimitProduct.product_name.ilike(pattern),
                OotLimitProduct.document_title.ilike(pattern),
                OotLimitProduct.version_label.ilike(pattern),
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.scalars(
        query.order_by(OotLimitProduct.product_code.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            OotLimitProductOut.model_validate(row).model_dump(mode="json")
            for row in result.all()
        ],
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }


async def list_validation_reviews(
    db: AsyncSession,
    *,
    keyword: str | None,
    status: str | None,
    review_mode: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    actor = current_page_actor.get()
    if actor is None:
        raise ForbiddenException("审核记录查询缺少可信用户")
    permissions = await resolve_user_permissions(db, actor.id)
    all_visible = bool(
        {"*", "quality:write", "quality:validation_qa:write"} & set(permissions)
    )
    if (current_page_data_scope.get() or {}).get("scope_type") == "self":
        all_visible = False
    rows, total = await validation_review.list_review_records(
        db,
        user_id=actor.id,
        all_visible=all_visible,
        keyword=keyword,
        status=status,
        review_mode=review_mode,
        page=page,
        page_size=page_size,
    )
    items = []
    for row in rows:
        files = await validation_review.get_review_files(db, row.id)
        items.append(validation_review.build_review_list_item(row, len(files)))
    return {"items": items, "total": total, "page": page, "page_size": page_size}
