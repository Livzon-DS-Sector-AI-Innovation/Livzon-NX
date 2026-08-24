"""Declaration progress API routes."""

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
from app.modules.registration.schemas.declaration_progress import (
    DeclarationProgressEntryInput,
    DeclarationProgressEntryResponse,
    DeclarationProgressRecordHistory,
    DeclarationProgressSheetDetail,
    DeclarationProgressWorkbookDetail,
    DeclarationProgressWorkbookImportResult,
    DeclarationProgressWorkbookOverview,
)
from app.modules.registration.service.declaration_progress import (
    DeclarationProgressWorkbookService,
)
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/overview",
    summary="获取申报进度",
    response_model=ApiResponseEnvelope[DeclarationProgressWorkbookOverview],
)
async def get_declaration_progress_overview(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    overview = await DeclarationProgressWorkbookService(db).get_overview()
    return success_response(data=overview)


@router.get(
    "/workbook",
    summary="获取申报进度工作簿",
    response_model=ApiResponseEnvelope[DeclarationProgressWorkbookDetail],
)
async def get_declaration_progress_workbook(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    detail = await DeclarationProgressWorkbookService(db).get_workbook_detail()
    return success_response(data=detail)


@router.post(
    "/workbook/import",
    summary="导入申报进度工作簿",
    response_model=ApiResponseEnvelope[DeclarationProgressWorkbookImportResult],
)
async def import_declaration_progress_workbook(
    current_user: CurrentUser,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    result = await DeclarationProgressWorkbookService(db).import_workbook(file)
    return success_response(message="导入成功", data=result)


@router.get("/workbook/export", summary="导出申报进度工作簿")
async def export_declaration_progress_workbook(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    file_path, download_name = await DeclarationProgressWorkbookService(
        db
    ).export_workbook()
    return FileResponse(
        path=file_path,
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get(
    "/sheets/{sheet_key}",
    summary="获取申报进度子表",
    response_model=ApiResponseEnvelope[DeclarationProgressSheetDetail],
)
async def get_declaration_progress_sheet_detail(
    sheet_key: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    detail = await DeclarationProgressWorkbookService(db).get_sheet_detail(sheet_key)
    return success_response(data=detail)


@router.post(
    "/entries",
    summary="新增申报进度记录",
    response_model=ApiResponseEnvelope[DeclarationProgressEntryResponse],
)
async def create_declaration_progress_entry(
    data: DeclarationProgressEntryInput,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await DeclarationProgressWorkbookService(db).create_entry(data)
    return success_response(message="新增成功", data=entry)


@router.put(
    "/entries/{record_id}",
    summary="编辑申报进度记录",
    response_model=ApiResponseEnvelope[DeclarationProgressEntryResponse],
)
async def update_declaration_progress_entry(
    record_id: uuid.UUID,
    data: DeclarationProgressEntryInput,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await DeclarationProgressWorkbookService(db).update_entry(record_id, data)
    return success_response(message="更新成功", data=entry)


@router.get(
    "/entries/{record_id}/history",
    summary="获取申报进度记录历史",
    response_model=ApiResponseEnvelope[DeclarationProgressRecordHistory],
)
async def get_declaration_progress_entry_history(
    record_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    history = await DeclarationProgressWorkbookService(db).get_entry_history(record_id)
    return success_response(data=history)


@router.post(
    "/entries/{record_id}/sub-records",
    summary="新增申报进度子记录",
    response_model=ApiResponseEnvelope[DeclarationProgressEntryResponse],
)
async def create_declaration_progress_sub_record(
    record_id: uuid.UUID,
    data: DeclarationProgressEntryInput,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    entry = await DeclarationProgressWorkbookService(db).create_sub_record(
        record_id, data
    )
    return success_response(message="新增子记录成功", data=entry)


@router.delete("/entries/{record_id}", summary="删除申报进度记录")
async def delete_declaration_progress_entry(
    record_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await DeclarationProgressWorkbookService(db).delete_entry(record_id)
    return success_response(message="删除成功")
