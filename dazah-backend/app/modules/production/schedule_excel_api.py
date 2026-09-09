"""排产计划 Excel 存档 API。

前端上传排产 Excel → 后端解析存档（全量行列/合并/列宽 + 原件），
支持历史列表回看、原件下载与删除。数据可被其他模块后续引用。
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.response import paginated_response, success_response
from app.core.upload_security import validate_upload_metadata
from app.modules.production import schedule_excel_service
from app.platform.identity.deps import CurrentUser
from app.shared.module_api import create_module_router
from app.shared.module_registry import MODULES_BY_CODE

router = create_module_router(MODULES_BY_CODE["production"])

_ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
_ALLOWED_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
_UPLOAD_SUB_DIR = "schedule_excel"


def _original_upload_dir() -> Path:
    base = Path(get_settings().UPLOAD_DIR)
    directory = base / _UPLOAD_SUB_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _ensure_archive_file(original_path: str) -> Path:
    """original_path 相对 uploads 根目录，返回真实文件路径并校验存在。"""
    base = Path(get_settings().UPLOAD_DIR).resolve()
    path = (base / original_path).resolve()
    if base not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="原始文件不存在")
    return path


@router.post(
    "/schedule-excel",
    summary="上传并存档排产计划 Excel",
)
async def upload_schedule_excel(
    file: UploadFile = File(..., description="排产计划 .xlsx / .xls 文件"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    filename = validate_upload_metadata(
        file,
        allowed_extensions=_ALLOWED_EXTENSIONS,
        allowed_mimes=_ALLOWED_MIMES,
    )
    extension = Path(filename).suffix.lower()

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="排产 Excel 不能超过 10MB")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        parsed = schedule_excel_service.parse_workbook_bytes(data)
    except Exception as exc:  # noqa: BLE001 - 解析失败统一转业务错误
        raise HTTPException(
            status_code=400, detail=f"Excel 解析失败：{exc}"
        ) from exc

    object_name = f"{uuid.uuid4().hex}{extension}"
    relative_path = f"{_UPLOAD_SUB_DIR}/{object_name}"
    (_original_upload_dir() / object_name).write_bytes(data)

    archive = await schedule_excel_service.create_archive(
        db,
        file_name=filename,
        sheet_name=parsed["sheet_name"],
        original_path=relative_path,
        rows=parsed["rows"],
        merges=parsed["merges"],
        col_widths=parsed["col_widths"],
        row_count=parsed["row_count"],
        col_count=parsed["col_count"],
        created_by=current_user.id if current_user else None,
    )
    return success_response(
        data=schedule_excel_service.serialize_archive(
            archive,
            created_by_name=current_user.name if current_user else None,
        ),
        message="排产 Excel 已存档",
    )


@router.get("/schedule-excel", summary="排产计划存档列表")
async def list_schedule_excel_archives(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Any:
    items, total = await schedule_excel_service.list_archives(
        db, page=page, page_size=page_size
    )
    return paginated_response(
        [
            schedule_excel_service.serialize_archive_summary(
                archive, created_by_name=name
            )
            for archive, name in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/schedule-excel/{archive_id}", summary="排产计划存档详情（含完整表格）")
async def get_schedule_excel_archive(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    archive = await schedule_excel_service.get_archive(db, archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="存档记录不存在")
    created_by_name = await schedule_excel_service.get_user_name(
        db, archive.created_by
    )
    return success_response(
        data=schedule_excel_service.serialize_archive(
            archive, created_by_name=created_by_name
        )
    )


@router.get(
    "/schedule-excel/{archive_id}/file",
    summary="下载排产 Excel 原件",
)
async def download_schedule_excel_file(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    archive = await schedule_excel_service.get_archive(db, archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="存档记录不存在")
    path = _ensure_archive_file(archive.original_path)
    return FileResponse(
        path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if path.suffix == ".xlsx"
            else "application/vnd.ms-excel"
        ),
        filename=archive.file_name,
    )


@router.delete("/schedule-excel/{archive_id}", summary="删除排产计划存档")
async def delete_schedule_excel_archive(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> Any:
    archive = await schedule_excel_service.get_archive(db, archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="存档记录不存在")
    await schedule_excel_service.delete_archive(
        db, archive, deleted_by=current_user.id if current_user else None
    )
    return success_response(data=None, message="存档已删除")
