"""Safety API — 灭火器 / 消防栓点检端点。

数据面：器材台账（飞书镜像投影）+ 点检记录。页面上下文固定为
「灭火器及消防栓点检」页（请求需携带该页的 ``X-Dazah-Page-Key`` 头，
由页面 API 绑定校验）；扫码点检页复用同一页面键。
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException
from app.modules.safety.models import FireEquipment, FireInspectionRecord
from app.modules.safety.schemas.fire_equipment import (
    ChecklistItem,
    ChecklistResponse,
    CreateFireInspectionRequest,
    FireEquipmentColumn,
    FireEquipmentDetailResponse,
    FireEquipmentItem,
    FireEquipmentListResponse,
    FireEquipmentStats,
    FireInspectionListResponse,
    FireInspectionRecordItem,
    FireInspectionWritebackInitResponse,
)
from app.modules.safety.service import fire_equipment, page_table
from app.shared.schemas import ApiResponseEnvelope

fire_equipment_router = APIRouter()

EQUIPMENT_TYPE_LABELS = fire_equipment.EQUIPMENT_TYPE_LABELS


def _month_status(last_inspected_at: datetime | None, month_start: datetime) -> str:
    if last_inspected_at is not None and last_inspected_at >= month_start:
        return "inspected"
    return "uninspected"


EXPIRING_WINDOW_DAYS = 30


def _expiry_fields(
    expiry_date: date | None,
) -> tuple[date | None, int | None, str | None]:
    """有效期 → (日期, 剩余天数, 状态)；无日期返回 (None, None, None)。"""
    if expiry_date is None:
        return None, None, None
    days_left = (expiry_date - date.today()).days
    if days_left < 0:
        status = "expired"
    elif days_left <= EXPIRING_WINDOW_DAYS:
        status = "expiring"
    else:
        status = "ok"
    return expiry_date, days_left, status


def _equipment_item(
    row: FireEquipment, month_start: datetime
) -> FireEquipmentItem:
    expiry_date, expiry_days_left, expiry_status = _expiry_fields(
        row.expiry_date
    )
    return FireEquipmentItem(
        id=row.id,
        equipment_type=row.equipment_type,
        equipment_type_label=EQUIPMENT_TYPE_LABELS.get(
            row.equipment_type, row.equipment_type
        ),
        equipment_no=row.equipment_no,
        department=row.department,
        location=row.location,
        tab_name=row.tab_name,
        table_id=row.table_id,
        record_id=row.record_id,
        fields=row.fields or {},
        last_inspected_at=row.last_inspected_at,
        last_inspection_result=row.last_inspection_result,
        month_status=_month_status(row.last_inspected_at, month_start),
        expiry_date=expiry_date,
        expiry_days_left=expiry_days_left,
        expiry_status=expiry_status,
        last_synced_at=row.last_synced_at,
    )


def _inspection_item(row: FireInspectionRecord) -> FireInspectionRecordItem:
    return FireInspectionRecordItem(
        id=row.id,
        equipment_id=row.equipment_id,
        equipment_type=row.equipment_type,
        equipment_type_label=EQUIPMENT_TYPE_LABELS.get(
            row.equipment_type, row.equipment_type
        ),
        equipment_no=row.equipment_no,
        department=row.department,
        location=row.location,
        items=row.items or [],
        result=row.result,
        failed_items=row.failed_items or [],
        abnormal_action=row.abnormal_action,
        inspector_name=row.inspector_name,
        inspected_at=row.inspected_at,
        source=row.source,
        feishu_record_id=row.feishu_record_id,
        created_at=row.created_at,
    )


@fire_equipment_router.get(
    "/fire-equipment",
    response_model=ApiResponseEnvelope[FireEquipmentListResponse],
    summary="消防器材台账分页列表（编号/部门/位置/最近点检状态）",
)
async def list_fire_equipment(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    equipment_type: str | None = Query(
        None, description="器材类型: extinguisher=灭火器 / hydrant=消防栓"
    ),
    keyword: str | None = Query(None, description="编号/部门/位置/车间关键字"),
    table_id: str | None = Query(None, description="来源子表 table_id"),
    month_status: str | None = Query(
        None, description="本月点检状态: inspected=已检 / uninspected=未检"
    ),
    expiry_status: str | None = Query(
        None, description="有效期状态: expiring=30天内到期 / expired=已过期"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[FireEquipmentListResponse]:
    rows, total = await fire_equipment.list_fire_equipment(
        db,
        page=page,
        page_size=page_size,
        equipment_type=equipment_type,
        keyword=keyword,
        table_id=table_id,
        month_status=month_status,
        expiry_status=expiry_status,
    )
    # 动态列：当前结果页涉及子表的飞书字段，页面据此对齐多维表格
    columns = await fire_equipment.get_fire_equipment_columns(db, rows)
    month_start = fire_equipment.month_start_utc()
    return ApiResponseEnvelope(
        data=FireEquipmentListResponse(
            items=[_equipment_item(row, month_start) for row in rows],
            columns=[FireEquipmentColumn(**column) for column in columns],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@fire_equipment_router.get(
    "/fire-equipment/stats",
    response_model=ApiResponseEnvelope[FireEquipmentStats],
    summary="消防器材台账概览（类型分布 + 本月点检覆盖 + 同步状态）",
)
async def get_fire_equipment_stats(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[FireEquipmentStats]:
    stats = await fire_equipment.get_fire_equipment_stats(db)
    return ApiResponseEnvelope(data=FireEquipmentStats(**stats))


@fire_equipment_router.get(
    "/fire-equipment/checklist",
    response_model=ApiResponseEnvelope[ChecklistResponse],
    summary="点检检查卡检查项（灭火器 4 项 / 消防栓 8 项）",
)
async def get_fire_equipment_checklist(
    equipment_type: str = Query(..., description="extinguisher / hydrant"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ChecklistResponse]:
    items = fire_equipment.CHECK_ITEMS_BY_TYPE.get(equipment_type)
    if not items:
        raise AppException(
            message=f"未知的器材类型: {equipment_type}", status_code=400
        )
    return ApiResponseEnvelope(
        data=ChecklistResponse(
            equipment_type=equipment_type,
            items=[ChecklistItem(key=key, label=label) for key, label in items],
        )
    )

@fire_equipment_router.post(
    "/fire-equipment/sync",
    response_model=ApiResponseEnvelope[FireEquipmentStats],
    summary="立即同步飞书台账并重新投影消防器材（含待回写点检补写）",
)
async def sync_fire_equipment(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[FireEquipmentStats]:
    await page_table.sync_page_table_mirror(
        db, fire_equipment.FIRE_EQUIPMENT_PAGE_KEY
    )
    await fire_equipment.maybe_project_after_sync(
        db, fire_equipment.FIRE_EQUIPMENT_PAGE_KEY
    )
    await fire_equipment.retry_pending_inspection_writebacks(db)
    stats = await fire_equipment.get_fire_equipment_stats(db)
    return ApiResponseEnvelope(data=FireEquipmentStats(**stats))


@fire_equipment_router.post(
    "/fire-equipment/writeback-table/init",
    response_model=ApiResponseEnvelope[FireInspectionWritebackInitResponse],
    summary="一键初始化「点检记录」回写子表（已存在则复用）",
)
async def init_fire_inspection_writeback_table(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[FireInspectionWritebackInitResponse]:
    result = await fire_equipment.ensure_writeback_table(db)
    return ApiResponseEnvelope(
        data=FireInspectionWritebackInitResponse(**result)
    )


@fire_equipment_router.get(
    "/fire-inspection-records",
    response_model=ApiResponseEnvelope[FireInspectionListResponse],
    summary="点检记录台账分页列表（按点检时间倒序）",
)
async def list_fire_inspections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    equipment_type: str | None = Query(None),
    result: str | None = Query(None, description="pass=合格 / fail=不合格"),
    keyword: str | None = Query(
        None, description="编号/部门/位置/点检人关键字"
    ),
    inspected_from: datetime | None = Query(None),
    inspected_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[FireInspectionListResponse]:
    rows, total = await fire_equipment.list_fire_inspections(
        db,
        page=page,
        page_size=page_size,
        equipment_type=equipment_type,
        result=result,
        keyword=keyword,
        inspected_from=inspected_from,
        inspected_to=inspected_to,
    )
    return ApiResponseEnvelope(
        data=FireInspectionListResponse(
            items=[_inspection_item(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@fire_equipment_router.get(
    "/fire-equipment/{equipment_id}",
    response_model=ApiResponseEnvelope[FireEquipmentDetailResponse],
    summary="消防器材详情（含检查卡与最近点检记录，扫码页使用）",
)
async def get_fire_equipment_detail(
    equipment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[FireEquipmentDetailResponse]:
    equipment = await fire_equipment.get_fire_equipment(db, equipment_id)
    inspections = await fire_equipment.list_equipment_inspections(
        db, equipment.id
    )
    checklist = fire_equipment.CHECK_ITEMS_BY_TYPE.get(
        equipment.equipment_type, ()
    )
    return ApiResponseEnvelope(
        data=FireEquipmentDetailResponse(
            equipment=_equipment_item(
                equipment, fire_equipment.month_start_utc()
            ),
            checklist=[
                ChecklistItem(key=key, label=label) for key, label in checklist
            ],
            recent_inspections=[
                _inspection_item(row) for row in inspections
            ],
        )
    )


@fire_equipment_router.post(
    "/fire-equipment/{equipment_id}/inspections",
    response_model=ApiResponseEnvelope[FireInspectionRecordItem],
    summary="提交一次点检（检查项须覆盖整卡，结论自动汇总）",
)
async def create_fire_inspection(
    equipment_id: UUID,
    data: CreateFireInspectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[FireInspectionRecordItem]:
    record = await fire_equipment.create_fire_inspection(
        db,
        equipment_id,
        items=[item.model_dump() for item in data.items],
        abnormal_action=data.abnormal_action,
        inspected_at=data.inspected_at,
        inspector_id=current_user.id if current_user else None,
        inspector_name=(
            data.inspector_name
            or (current_user.name if current_user else "")
            or ""
        ),
        source=data.source,
    )
    fire_equipment.schedule_inspection_writeback(record.id)
    return ApiResponseEnvelope(data=_inspection_item(record))
