"""Certificate dashboard API routes."""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import success_response
from app.modules.registration.api._common import require_user as _require_user
from app.modules.registration.schemas.certificate import (
    CertificateEntryCreate,
    CertificateEntryResponse,
    CertificateEntryUpdate,
    CertificateReminderRecipientOption,
    CertificateReminderSettingResponse,
    CertificateReminderSettingUpdate,
    CertificateSheetDetail,
    CertificateWorkbookDetail,
    CertificateWorkbookImportResult,
    CertificateWorkbookOverview,
)
from app.modules.registration.service.certificate import CertificateWorkbookService
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/overview",
    summary="获取证书管理仪表盘总览",
    response_model=ApiResponseEnvelope[CertificateWorkbookOverview],
)
async def get_certificate_overview(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    overview = await CertificateWorkbookService(db).get_overview()
    return success_response(data=overview)


@router.get(
    "/workbook",
    summary="获取整本药政证书台账详情",
    response_model=ApiResponseEnvelope[CertificateWorkbookDetail],
)
async def get_certificate_workbook(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    detail = await CertificateWorkbookService(db).get_workbook_detail()
    return success_response(data=detail)


@router.post(
    "/workbook/import",
    summary="导入整本药政证书台账",
    response_model=ApiResponseEnvelope[CertificateWorkbookImportResult],
)
async def import_certificate_workbook(
    current_user: CurrentUser,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await CertificateWorkbookService(db).import_workbook(file)
    return success_response(message="导入成功", data=result)


@router.get("/workbook/export", summary="导出整本药政证书台账")
async def export_certificate_workbook(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    file_path, download_name = await CertificateWorkbookService(db).export_workbook()
    return FileResponse(
        path=file_path,
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get(
    "/reminder-settings",
    summary="获取证书到期提醒配置",
    response_model=ApiResponseEnvelope[CertificateReminderSettingResponse],
)
async def get_certificate_reminder_settings(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    settings = await CertificateWorkbookService(db).get_reminder_settings()
    return success_response(data=settings)


@router.get(
    "/reminder-recipients",
    summary="获取证书到期提醒可选通知人",
    response_model=ApiResponseEnvelope[list[CertificateReminderRecipientOption]],
)
async def list_certificate_reminder_recipients(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    items = await CertificateWorkbookService(db).list_reminder_recipient_options()
    return success_response(data=items)


@router.put(
    "/reminder-settings",
    summary="更新证书到期提醒配置",
    response_model=ApiResponseEnvelope[CertificateReminderSettingResponse],
)
async def update_certificate_reminder_settings(
    data: CertificateReminderSettingUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    settings = await CertificateWorkbookService(db).update_reminder_settings(data)
    return success_response(message="提醒配置已保存", data=settings)


@router.get(
    "/sheets/{sheet_key}",
    summary="获取证书管理子表详情",
    response_model=ApiResponseEnvelope[CertificateSheetDetail],
)
async def get_certificate_sheet_detail(
    sheet_key: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    detail = await CertificateWorkbookService(db).get_sheet_detail(sheet_key)
    return success_response(data=detail)


@router.post(
    "/entries",
    summary="新增证书台账记录",
    response_model=ApiResponseEnvelope[CertificateEntryResponse],
)
async def create_certificate_entry(
    data: CertificateEntryCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await CertificateWorkbookService(db).create_entry(data)
    return success_response(message="新增成功", data=entry)


@router.put(
    "/entries/{entry_id}",
    summary="编辑证书台账记录",
    response_model=ApiResponseEnvelope[CertificateEntryResponse],
)
async def update_certificate_entry(
    entry_id: uuid.UUID,
    data: CertificateEntryUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await CertificateWorkbookService(db).update_entry(entry_id, data)
    return success_response(message="更新成功", data=entry)


@router.delete("/entries/{entry_id}", summary="删除证书台账记录")
async def delete_certificate_entry(
    entry_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await CertificateWorkbookService(db).delete_entry(entry_id)
    return success_response(message="删除成功")
