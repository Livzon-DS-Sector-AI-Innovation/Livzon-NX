"""Administration notice ledger routes (公告通知台账).

平台原生公告台账：上传公告文件 → AI 识别元数据 → 人工确认导入。
权限口径：元数据列表/详情随页面 query 放行；识别/导入/编辑、公告内容
与原文下载归 operate（行政管理员经页面授权获得）；删除是已登记的
破坏性动作。台账响应永不包含公告内容字段，内容与原文仅经专用端点下发。
"""

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException
from app.core.upload_security import read_upload_secure, sniff_upload_mime
from app.modules.administration.notice_service import (
    NOTICE_ALLOWED_EXTS,
    NOTICE_MAX_BYTES,
    NoticeService,
)
from app.modules.administration.schemas import (
    NoticeContentResponse,
    NoticeItem,
    NoticeListResponse,
    NoticeParsePreview,
    NoticeUpdateInput,
)
from app.platform.identity.deps import RequireUser
from app.shared.schemas import ApiResponse, ApiResponseEnvelope

router = APIRouter()

MAX_PAGE_SIZE = 100


def _require_title(title: str) -> str:
    stripped = title.strip()
    if not stripped:
        raise AppException(message="公告标题不能为空", status_code=422)
    return stripped


@router.post(
    "/notices/parse",
    summary="解析公告文件（AI 识别元数据预览，不落库）",
    response_model=ApiResponseEnvelope[NoticeParsePreview],
)
async def parse_notice(
    _current_user: RequireUser,
    file: UploadFile = File(..., description="公告文件（PDF/Word/图片）"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[NoticeParsePreview]:
    file_name, content = await read_upload_secure(
        file,
        max_bytes=NOTICE_MAX_BYTES,
        allowed_extensions=NOTICE_ALLOWED_EXTS,
        what="公告文件",
    )
    preview = await NoticeService(db).parse_preview(file_name, content)
    return ApiResponseEnvelope(data=preview)


@router.post(
    "/notices",
    summary="导入公告（原文存档 + AI 提取正文，元数据以确认值为准）",
    response_model=ApiResponseEnvelope[NoticeItem],
)
async def import_notice(
    current_user: RequireUser,
    file: UploadFile = File(..., description="公告文件（PDF/Word/图片）"),
    notice_no: str = Form("", max_length=100),
    title: str = Form("", max_length=255),
    publisher: str = Form("", max_length=255),
    published_at: str | None = Form(default=None, description="YYYY-MM-DD"),
    category: str = Form("", max_length=50),
    remark: str = Form("", max_length=2000),
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[NoticeItem]:
    file_name, content = await read_upload_secure(
        file,
        max_bytes=NOTICE_MAX_BYTES,
        allowed_extensions=NOTICE_ALLOWED_EXTS,
        what="公告文件",
    )
    _require_title(title)
    service = NoticeService(db)
    notice = await service.import_notice(
        file_name=file_name,
        content=content,
        # 记录魔数嗅探出的真实类型，不信任客户端 Content-Type 头
        content_type=sniff_upload_mime(file_name, content),
        notice_no=notice_no,
        title=title,
        publisher=publisher,
        published_at=published_at,
        category=category,
        remark=remark,
        user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(notice)
    return ApiResponseEnvelope(data=service.to_notice_item(notice))


@router.get(
    "/notices",
    summary="公告台账列表（元数据，不含公告内容）",
    response_model=ApiResponseEnvelope[NoticeListResponse],
)
async def list_notices(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    keyword: str | None = Query(default=None, max_length=255),
    category: str | None = Query(default=None, max_length=50),
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[NoticeListResponse]:
    result = await NoticeService(db).list_notices(
        page=page, page_size=page_size, keyword=keyword, category=category
    )
    return ApiResponseEnvelope(data=result)


@router.get(
    "/notices/{notice_id}",
    summary="公告详情（元数据，不含公告内容）",
    response_model=ApiResponseEnvelope[NoticeItem],
)
async def get_notice(
    notice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[NoticeItem]:
    item = await NoticeService(db).get_notice_item(notice_id)
    return ApiResponseEnvelope(data=item)


@router.get(
    "/notices/{notice_id}/content",
    summary="查看公告内容（operate 专用端点）",
    response_model=ApiResponseEnvelope[NoticeContentResponse],
)
async def get_notice_content(
    _current_user: RequireUser,
    notice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[NoticeContentResponse]:
    content = await NoticeService(db).get_notice_content(notice_id)
    return ApiResponseEnvelope(data=content)


@router.get(
    "/notices/{notice_id}/file",
    summary="下载公告原文存档（operate 专用端点）",
    response_model=None,
)
async def download_notice_file(
    _current_user: RequireUser,
    notice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    data, content_type, file_name = await NoticeService(db).read_notice_file(notice_id)
    quoted_name = quote(file_name or "notice")
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_name}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.put(
    "/notices/{notice_id}",
    summary="编辑公告元数据与内容",
    response_model=ApiResponseEnvelope[NoticeItem],
)
async def update_notice(
    notice_id: uuid.UUID,
    payload: NoticeUpdateInput,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
) -> ApiResponseEnvelope[NoticeItem]:
    _require_title(payload.title)
    item = await NoticeService(db).update_notice(
        notice_id, payload, user_id=current_user.id
    )
    await db.commit()
    return ApiResponseEnvelope(data=item)


@router.delete(
    "/notices/{notice_id}",
    summary="删除公告（软删除，原文存档保留）",
    response_model=ApiResponse,
)
async def delete_notice(
    notice_id: uuid.UUID,
    current_user: RequireUser,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    await NoticeService(db).delete_notice(notice_id, user_id=current_user.id)
    await db.commit()
    return ApiResponse(data={"deleted": True})
