"""Project ledger API routes."""

import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.response import success_response
from app.modules.registration.api._common import (
    cleanup_export_dir,
)
from app.modules.registration.api._common import (
    require_user as _require_user,
)
from app.modules.registration.schemas.project_ledger import (
    ProjectLedgerEntryInput,
    ProjectLedgerEntryResponse,
    ProjectLedgerRecordHistory,
    ProjectLedgerSheetDetail,
    ProjectLedgerWorkbookDetail,
    ProjectLedgerWorkbookImportResult,
    ProjectLedgerWorkbookOverview,
)
from app.modules.registration.service.project_ledger import ProjectLedgerWorkbookService
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/overview",
    summary="获取申报台账",
    response_model=ApiResponseEnvelope[ProjectLedgerWorkbookOverview],
)
async def get_project_ledger_overview(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    overview = await ProjectLedgerWorkbookService(db).get_overview()
    return success_response(data=overview)


@router.get(
    "/workbook",
    summary="获取申报台账工作簿",
    response_model=ApiResponseEnvelope[ProjectLedgerWorkbookDetail],
)
async def get_project_ledger_workbook(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    detail = await ProjectLedgerWorkbookService(db).get_workbook_detail()
    return success_response(data=detail)


@router.post(
    "/workbook/import",
    summary="导入申报台账工作簿",
    response_model=ApiResponseEnvelope[ProjectLedgerWorkbookImportResult],
)
async def import_project_ledger_workbook(
    current_user: CurrentUser,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await ProjectLedgerWorkbookService(db).import_workbook(file)
    return success_response(message="导入成功", data=result)


@router.get("/workbook/export", summary="导出申报台账工作簿")
async def export_project_ledger_workbook(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    file_path, download_name = await ProjectLedgerWorkbookService(db).export_workbook()
    return FileResponse(
        path=file_path,
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=BackgroundTask(cleanup_export_dir, str(Path(file_path).parent)),
    )


@router.get(
    "/sheets/{sheet_key}",
    summary="获取申报台账子表",
    response_model=ApiResponseEnvelope[ProjectLedgerSheetDetail],
)
async def get_project_ledger_sheet_detail(
    sheet_key: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    detail = await ProjectLedgerWorkbookService(db).get_sheet_detail(sheet_key)
    return success_response(data=detail)


@router.post(
    "/entries",
    summary="新增申报台账记录",
    response_model=ApiResponseEnvelope[ProjectLedgerEntryResponse],
)
async def create_project_ledger_entry(
    data: ProjectLedgerEntryInput,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await ProjectLedgerWorkbookService(db).create_entry(data)
    return success_response(message="新增成功", data=entry)


@router.put(
    "/entries/{record_id}",
    summary="编辑申报台账记录",
    response_model=ApiResponseEnvelope[ProjectLedgerEntryResponse],
)
async def update_project_ledger_entry(
    record_id: uuid.UUID,
    data: ProjectLedgerEntryInput,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await ProjectLedgerWorkbookService(db).update_entry(record_id, data)
    return success_response(message="更新成功", data=entry)


@router.get(
    "/entries/{record_id}/history",
    summary="获取申报台账记录历史",
    response_model=ApiResponseEnvelope[ProjectLedgerRecordHistory],
)
async def get_project_ledger_entry_history(
    record_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    history = await ProjectLedgerWorkbookService(db).get_entry_history(record_id)
    return success_response(data=history)


@router.post(
    "/entries/{record_id}/sub-records",
    summary="新增申报台账子记录",
    response_model=ApiResponseEnvelope[ProjectLedgerEntryResponse],
)
async def create_project_ledger_sub_record(
    record_id: uuid.UUID,
    data: ProjectLedgerEntryInput,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await ProjectLedgerWorkbookService(db).create_sub_record(record_id, data)
    return success_response(message="新增子记录成功", data=entry)


@router.delete("/entries/{record_id}", summary="删除申报台账记录")
async def delete_project_ledger_entry(
    record_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await ProjectLedgerWorkbookService(db).delete_entry(record_id)
    return success_response(message="删除成功")
