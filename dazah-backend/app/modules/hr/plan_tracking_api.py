"""培训计划跟踪 API"""

import logging
from io import BytesIO
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException, NotFoundException
from app.core.response import paginated_response, success_response
from app.modules.hr.plan_tracking_service import PlanTrackingService
from app.modules.hr.schemas import (
    PlanTrackingRecordCreate,
    PlanTrackingRecordResponse,
    PlanTrackingRecordUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plan-tracking", tags=["人事-培训计划跟踪"])


def _require_user(current_user: CurrentUser) -> Any:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")


@router.get("", summary="培训计划跟踪列表")
async def list_plan_tracking_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    plan_id: UUID | None = Query(None, description="关联年度计划ID"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    from app.modules.hr.api import _resolve_visible_scope

    alias_set = await _resolve_visible_scope(db, current_user)
    service = PlanTrackingService(db)
    records, total = await service.list_records(
        page=page, page_size=page_size, plan_id=plan_id, dept_alias_set=alias_set
    )
    return paginated_response(
        data=[
            PlanTrackingRecordResponse.model_validate(r).model_dump(mode="json")
            for r in records
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", summary="创建培训计划跟踪记录")
async def create_plan_tracking_record(
    data: PlanTrackingRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    service = PlanTrackingService(db)
    record = await service.create(data.model_dump(exclude_unset=True))
    return success_response(
        data=PlanTrackingRecordResponse.model_validate(record).model_dump(mode="json"),
        message="创建成功",
    )


@router.get("/export", summary="导出培训计划跟踪表")
async def export_plan_tracking(
    plan_id: UUID | None = Query(None, description="关联年度计划ID"),
    year: int | None = Query(None, description="年度"),
    month: int | None = Query(None, ge=1, le=12, description="月份"),
    plan_level: str | None = Query(None, description="计划级别: 公司级, 部门级"),
    department: str | None = Query(None, description="部门（部门级）"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """导出培训计划跟踪表 Excel 文档（APP11模板）"""
    from app.modules.hr.api import _assert_dept_in_scope

    alias_set = await _assert_dept_in_scope(db, current_user, department)
    from app.modules.hr.plan_tracking_document_generator import (
        generate_plan_tracking_excel,
    )

    service = PlanTrackingService(db)
    if year and month and plan_level:
        records = await service.sync_period(
            year=year,
            month=month,
            plan_level=plan_level,
            department=department,
            dept_alias_set=alias_set,
        )
    else:
        records, _ = await service.list_records(
            page=1, page_size=500, plan_id=plan_id, dept_alias_set=alias_set
        )

    buffer: BytesIO = generate_plan_tracking_excel(
        records, year=year, month=month, plan_level=plan_level
    )

    # 生成有意义的文件名：年度 + 月份 + 级别 + 培训计划跟踪表.xlsx
    if year and month and plan_level:
        base_name = f"{year}年{month}月{plan_level}培训计划跟踪表.xlsx"
    else:
        base_name = "APP11-SMP-HR-002-14 培训计划跟踪表.xlsx"

    # 使用 RFC 5987 编码确保中文文件名正确
    encoded_name = quote(base_name)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            (
                "Content-Type"
            ): "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
    )


@router.get("/period", summary="按年按月查询跟踪记录（幂等自动录入）")
async def list_plan_tracking_by_period(
    year: int = Query(..., description="年度"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    plan_level: str = Query("公司级", description="计划级别: 公司级, 部门级"),
    department: str | None = Query(None, description="部门（部门级）"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    """按 年+月+级别(+部门) 返回跟踪记录；若存在对应年度计划，当月明细自动补录."""
    from app.modules.hr.api import _assert_dept_in_scope

    alias_set = await _assert_dept_in_scope(db, current_user, department)
    service = PlanTrackingService(db)
    records = await service.sync_period(
        year=year,
        month=month,
        plan_level=plan_level,
        department=department,
        dept_alias_set=alias_set,
    )
    return success_response(
        data=[
            PlanTrackingRecordResponse.model_validate(r).model_dump(mode="json")
            for r in records
        ]
    )


@router.get("/{record_id}", summary="培训计划跟踪记录详情")
async def get_plan_tracking_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    service = PlanTrackingService(db)
    record = await service.get_by_id(record_id)
    if not record:
        raise NotFoundException(resource="培训计划跟踪记录", resource_id=str(record_id))
    return success_response(
        data=PlanTrackingRecordResponse.model_validate(record).model_dump(mode="json")
    )


@router.put("/{record_id}", summary="更新培训计划跟踪记录")
async def update_plan_tracking_record(
    record_id: UUID,
    data: PlanTrackingRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    service = PlanTrackingService(db)
    record = await service.update(record_id, data.model_dump(exclude_unset=True))
    if not record:
        raise NotFoundException(resource="培训计划跟踪记录", resource_id=str(record_id))
    return success_response(
        data=PlanTrackingRecordResponse.model_validate(record).model_dump(mode="json"),
        message="更新成功",
    )


@router.delete("/{record_id}", summary="删除培训计划跟踪记录")
async def delete_plan_tracking_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    _require_user(current_user)
    service = PlanTrackingService(db)
    deleted = await service.delete(record_id)
    if not deleted:
        raise NotFoundException(resource="培训计划跟踪记录", resource_id=str(record_id))
    return success_response(message="删除成功")
