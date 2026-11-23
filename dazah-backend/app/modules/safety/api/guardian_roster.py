"""Safety API — 作业安全监护人名单端点。

列表（含车间汇总）/ 增删改 + Excel 导入（解析预览 + 整表替换落库）+
Excel 导出。导入与列表参照特种作业证件导入模式；名单以最新导入为准。
"""

from __future__ import annotations

import json
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException
from app.core.upload_security import read_upload_secure
from app.modules.safety.schemas.guardian_roster import (
    GuardianImportPreview,
    GuardianImportResult,
    GuardianRosterCreate,
    GuardianRosterListResponse,
    GuardianRosterResponse,
    GuardianRosterUpdate,
)
from app.modules.safety.service import guardian_roster as roster_service
from app.modules.safety.service.guardian_roster_import import (
    ALLOWED_EXTENSIONS as IMPORT_ALLOWED_EXTENSIONS,
)
from app.modules.safety.service.guardian_roster_import import (
    MAX_UPLOAD_SIZE as IMPORT_MAX_UPLOAD_SIZE,
)
from app.modules.safety.service.guardian_roster_import import (
    GuardianImportService,
)
from app.shared.schemas import ApiResponseEnvelope

guardian_roster_router = APIRouter()


@guardian_roster_router.get(
    "/guardian-roster",
    response_model=ApiResponseEnvelope[GuardianRosterListResponse],
    summary="监护人名单分页列表（车间筛选/关键字 + 车间人数汇总）",
)
async def list_guardian_roster(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    workshop: str | None = Query(None),
    keyword: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[GuardianRosterListResponse]:
    data = await roster_service.list_guardians(
        db,
        page=page,
        page_size=page_size,
        workshop=workshop,
        keyword=keyword,
    )
    return ApiResponseEnvelope(data=data)


@guardian_roster_router.post(
    "/guardian-roster",
    response_model=ApiResponseEnvelope[GuardianRosterResponse],
    summary="新建监护人",
)
async def create_guardian_roster(
    payload: GuardianRosterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[GuardianRosterResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    guardian = await roster_service.create_guardian(db, payload, current_user)
    await db.commit()
    await db.refresh(guardian)
    return ApiResponseEnvelope(data=GuardianRosterResponse.model_validate(guardian))


@guardian_roster_router.put(
    "/guardian-roster/{guardian_id}",
    response_model=ApiResponseEnvelope[GuardianRosterResponse],
    summary="更新监护人",
)
async def update_guardian_roster(
    guardian_id: UUID,
    payload: GuardianRosterUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[GuardianRosterResponse]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    guardian = await roster_service.update_guardian(
        db, guardian_id, payload, current_user
    )
    await db.commit()
    await db.refresh(guardian)
    return ApiResponseEnvelope(data=GuardianRosterResponse.model_validate(guardian))


@guardian_roster_router.delete(
    "/guardian-roster/{guardian_id}",
    response_model=ApiResponseEnvelope[None],
    summary="删除监护人（软删除）",
)
async def delete_guardian_roster(
    guardian_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[None]:
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    await roster_service.delete_guardian(db, guardian_id, current_user)
    await db.commit()
    return ApiResponseEnvelope(data=None, message="删除成功")


@guardian_roster_router.post(
    "/guardian-roster/import/parse",
    response_model=ApiResponseEnvelope[GuardianImportPreview],
    summary="解析监护人名单 Excel（预览子表与行数，不落库）",
)
async def parse_guardian_import(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[GuardianImportPreview]:
    file_name, content = await read_upload_secure(
        file,
        max_bytes=IMPORT_MAX_UPLOAD_SIZE,
        allowed_extensions=IMPORT_ALLOWED_EXTENSIONS,
        what="监护人名单导入文件",
    )
    try:
        preview = await GuardianImportService(db).preview(file_name, content, None)
    except ValueError as exc:
        raise AppException(status_code=400, message=str(exc)) from exc
    return ApiResponseEnvelope(data=GuardianImportPreview.model_validate(preview))


@guardian_roster_router.post(
    "/guardian-roster/import",
    response_model=ApiResponseEnvelope[GuardianImportResult],
    summary="导入监护人名单 Excel（以最新导入为准，整表替换）",
)
async def import_guardian_roster(
    file: UploadFile,
    sheets: str = Form(
        "", description="要导入的子表名 JSON 数组，空则导入全部子表（自动合并重复人员）"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[GuardianImportResult]:
    """整表替换：先软删现有名单，再写入本次解析合并后的人员。"""
    if current_user is None:
        raise AppException(status_code=401, message="请先登录")
    selected_sheets: list[str] | None = None
    if sheets:
        try:
            parsed_sheets = json.loads(sheets)
        except json.JSONDecodeError:
            raise AppException(status_code=400, message="子表参数格式错误") from None
        if not isinstance(parsed_sheets, list) or not all(
            isinstance(item, str) for item in parsed_sheets
        ):
            raise AppException(status_code=400, message="子表参数格式错误")
        selected_sheets = parsed_sheets

    file_name, content = await read_upload_secure(
        file,
        max_bytes=IMPORT_MAX_UPLOAD_SIZE,
        allowed_extensions=IMPORT_ALLOWED_EXTENSIONS,
        what="监护人名单导入文件",
    )
    try:
        result = await GuardianImportService(db).commit(
            file_name, content, selected_sheets, current_user.id
        )
    except ValueError as exc:
        raise AppException(status_code=400, message=str(exc)) from exc
    await db.commit()
    return ApiResponseEnvelope(data=GuardianImportResult.model_validate(result))


@guardian_roster_router.get(
    "/guardian-roster/export",
    response_model=None,
    summary="导出监护人名单 Excel（按当前筛选，车间→姓名排序）",
)
async def export_guardian_roster(
    workshop: str | None = Query(None),
    keyword: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    data, filename = await roster_service.export_guardians_xlsx(
        db, workshop=workshop, keyword=keyword
    )
    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (f"attachment; filename*=UTF-8''{quote(filename)}")
        },
    )
