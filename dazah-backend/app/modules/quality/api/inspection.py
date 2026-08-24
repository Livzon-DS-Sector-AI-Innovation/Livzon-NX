"""Inspection API endpoints."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException, NotFoundException
from app.core.response import paginated_response, success_response
from app.modules.quality.api.deps import require_user as _require_user
from app.modules.quality.models.inspection import InspectionRecord
from app.modules.quality.schemas.inspection import (
    CreateInspectionRequest,
    InspectionRecordOut,
    UpdateInspectionRequest,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get(
    "/inspections",
    summary="获取检验记录列表",
    response_model=ApiResponseEnvelope[list[InspectionRecordOut]],
)
async def list_inspections(
    current_user: CurrentUser = None,
    inspection_type: str | None = Query(None, description="检验类型"),
    conclusion: str | None = Query(None, description="检验结论"),
    department: str | None = Query(None, description="检验部门"),
    keyword: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    assert current_user is not None
    from app.platform.identity.data_scope import (
        department_in_clause,
        resolve_user_department_scope,
    )

    scope = await resolve_user_department_scope(db, current_user)
    base_query = select(InspectionRecord).where(InspectionRecord.is_deleted.is_(False))
    count_query = (
        select(func.count())
        .select_from(InspectionRecord)
        .where(InspectionRecord.is_deleted.is_(False))
    )

    filters = []
    if inspection_type:
        filters.append(InspectionRecord.inspection_type == inspection_type)
    if conclusion:
        filters.append(InspectionRecord.conclusion == conclusion)
    if department:
        filters.append(InspectionRecord.department == department)
    # 部门数据隔离（后台可配置可见部门范围）
    scope_clause = department_in_clause(InspectionRecord.department, scope)
    if scope_clause is not None:
        filters.append(scope_clause)
    if keyword:
        pattern = f"%{_escape_like(keyword)}%"
        filters.append(
            or_(
                InspectionRecord.inspection_no.ilike(pattern),
                InspectionRecord.product_name.ilike(pattern),
                InspectionRecord.batch_no.ilike(pattern),
                InspectionRecord.inspection_item.ilike(pattern),
            )
        )

    if filters:
        base_query = base_query.where(*filters)
        count_query = count_query.where(*filters)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    base_query = (
        base_query.order_by(InspectionRecord.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items_result = await db.execute(base_query)
    items = items_result.scalars().all()

    return paginated_response(
        data=[
            InspectionRecordOut.model_validate(item).model_dump(mode="json")
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/inspections/{record_id}",
    summary="获取检验记录详情",
    response_model=ApiResponseEnvelope[InspectionRecordOut],
)
async def get_inspection(
    record_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await db.execute(
        select(InspectionRecord).where(
            InspectionRecord.id == record_id,
            InspectionRecord.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundException("检验记录", str(record_id))
    return success_response(
        data=InspectionRecordOut.model_validate(item).model_dump(mode="json")
    )


@router.post(
    "/inspections",
    summary="创建检验记录",
    response_model=ApiResponseEnvelope[InspectionRecordOut],
)
async def create_inspection(
    data: CreateInspectionRequest = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    record = InspectionRecord(**data.model_dump())
    db.add(record)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppException(message="检验编号已存在", status_code=409) from exc
    await db.commit()
    logger.info(
        "Inspection record created", extra={"inspection_no": record.inspection_no}
    )
    return success_response(
        data=InspectionRecordOut.model_validate(record).model_dump(mode="json"),
        message="创建成功",
    )


@router.put(
    "/inspections/{record_id}",
    summary="更新检验记录",
    response_model=ApiResponseEnvelope[InspectionRecordOut],
)
async def update_inspection(
    record_id: uuid.UUID,
    data: UpdateInspectionRequest = Body(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await db.execute(
        select(InspectionRecord).where(
            InspectionRecord.id == record_id,
            InspectionRecord.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundException("检验记录", str(record_id))

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)

    await db.flush()
    await db.commit()

    # UPDATE 后必须 re-fetch（规范要求：禁止 db.refresh）
    re_result = await db.execute(
        select(InspectionRecord).where(InspectionRecord.id == record_id)
    )
    item = re_result.scalar_one()

    return success_response(
        data=InspectionRecordOut.model_validate(item).model_dump(mode="json"),
        message="更新成功",
    )


@router.delete(
    "/inspections/{record_id}",
    summary="删除检验记录",
    response_model=ApiResponseEnvelope[dict[str, Any]],
)
async def delete_inspection(
    record_id: uuid.UUID,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await db.execute(
        select(InspectionRecord).where(
            InspectionRecord.id == record_id,
            InspectionRecord.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundException("检验记录", str(record_id))

    item.is_deleted = True
    await db.flush()
    await db.commit()
    return success_response(message="已删除")
