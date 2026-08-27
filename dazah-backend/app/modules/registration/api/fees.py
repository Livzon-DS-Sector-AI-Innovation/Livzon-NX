"""Registration fee API routes."""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import success_response
from app.modules.registration.api._common import require_user as _require_user
from app.modules.registration.schemas.fee import (
    FeeDashboardResponse,
    FeeEntryCreate,
    FeeEntryResponse,
    FeeEntryUpdate,
    FeeOverview,
    InspectionContactCreate,
    InspectionContactResponse,
    InspectionContactUpdate,
)
from app.modules.registration.service.fee import RegistrationFeeService
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/overview",
    summary="获取费用统计概览",
    response_model=ApiResponseEnvelope[FeeOverview],
)
async def get_fee_overview(
    current_user: CurrentUser,
    year_from: int | None = Query(None, description="起始年份，如 2025"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    overview = await RegistrationFeeService(db).get_overview(year_from=year_from)
    return success_response(data=overview)


@router.get(
    "/dashboard",
    summary="获取费用仪表盘数据",
    response_model=ApiResponseEnvelope[FeeDashboardResponse],
)
async def get_fee_dashboard(
    current_user: CurrentUser,
    year_from: int | None = Query(None, description="起始年份，如 2025"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    dashboard = await RegistrationFeeService(db).get_dashboard(year_from=year_from)
    return success_response(data=dashboard)


@router.get(
    "/entries",
    summary="获取费用列表",
    response_model=ApiResponseEnvelope[list[FeeEntryResponse]],
)
async def list_fee_entries(
    current_user: CurrentUser,
    fee_type: str | None = Query(None, description="费用类型"),
    payment_status: str | None = Query(None, description="支付状态"),
    project_name: str | None = Query(None, description="项目名称"),
    product_name: str | None = Query(None, description="产品名称"),
    country: str | None = Query(None, description="国家/地区"),
    year: int | None = Query(None, description="年度"),
    year_from: int | None = Query(None, description="起始年份"),
    keyword: str | None = Query(None, description="关键词"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entries = await RegistrationFeeService(db).list_entries(
        fee_type=fee_type,
        payment_status=payment_status,
        project_name=project_name,
        product_name=product_name,
        country=country,
        year=year,
        year_from=year_from,
        keyword=keyword,
    )
    return success_response(data=entries)


@router.get(
    "/entries/{entry_id}",
    summary="获取费用详情",
    response_model=ApiResponseEnvelope[FeeEntryResponse],
)
async def get_fee_entry(
    entry_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await RegistrationFeeService(db).get_entry(entry_id)
    return success_response(data=entry)


@router.post(
    "/entries",
    summary="新增费用记录",
    response_model=ApiResponseEnvelope[FeeEntryResponse],
)
async def create_fee_entry(
    data: FeeEntryCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await RegistrationFeeService(db).create_entry(data)
    return success_response(message="新增成功", data=entry)


@router.put(
    "/entries/{entry_id}",
    summary="编辑费用记录",
    response_model=ApiResponseEnvelope[FeeEntryResponse],
)
async def update_fee_entry(
    entry_id: uuid.UUID,
    data: FeeEntryUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await RegistrationFeeService(db).update_entry(entry_id, data)
    return success_response(message="更新成功", data=entry)


@router.delete("/entries/{entry_id}", summary="删除费用记录")
async def delete_fee_entry(
    entry_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await RegistrationFeeService(db).delete_entry(entry_id)
    return success_response(message="删除成功")


# ── Inspection contact routes ─────────────────────────────────────────


@router.get(
    "/inspection-contacts",
    summary="获取外检联系列表",
    response_model=ApiResponseEnvelope[list[InspectionContactResponse]],
)
async def list_inspection_contacts(
    current_user: CurrentUser,
    keyword: str | None = Query(None, description="关键词"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    contacts = await RegistrationFeeService(db).list_inspection_contacts(
        keyword=keyword
    )
    return success_response(data=contacts)


@router.get(
    "/inspection-contacts/{contact_id}",
    summary="获取外检联系详情",
    response_model=ApiResponseEnvelope[InspectionContactResponse],
)
async def get_inspection_contact(
    contact_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    contact = await RegistrationFeeService(db).get_inspection_contact(contact_id)
    return success_response(data=contact)


@router.post(
    "/inspection-contacts",
    summary="新增外检联系记录",
    response_model=ApiResponseEnvelope[InspectionContactResponse],
)
async def create_inspection_contact(
    data: InspectionContactCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    contact = await RegistrationFeeService(db).create_inspection_contact(data)
    return success_response(message="新增成功", data=contact)


@router.put(
    "/inspection-contacts/{contact_id}",
    summary="编辑外检联系记录",
    response_model=ApiResponseEnvelope[InspectionContactResponse],
)
async def update_inspection_contact(
    contact_id: uuid.UUID,
    data: InspectionContactUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    contact = await RegistrationFeeService(db).update_inspection_contact(
        contact_id, data
    )
    return success_response(message="更新成功", data=contact)


@router.delete("/inspection-contacts/{contact_id}", summary="删除外检联系记录")
async def delete_inspection_contact(
    contact_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await RegistrationFeeService(db).delete_inspection_contact(contact_id)
    return success_response(message="删除成功")
