"""Safety API — 页面飞书多维表格镜像端点。

两组接口：

- ``/page-feishu-configs/*``：页面与多维表格的绑定配置，归「安全飞书设置」页
  （页面权限 ``safety:system-config:safety-feishu-settings``）；路径里的
  ``page_key`` 是「要配置哪个镜像页」，不是调用者所在页面。
- ``/page-tables/{page_key}/*``：镜像页的数据读写。这里的 ``page_key`` 必须与
  请求的授权页面上下文一致——它出现在 URL 里，而权限校验用的是请求头携带的
  页面标识，若不一致，持有 A 页权限的用户就能用 B 的 page_key 读到别人的表。
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.modules.safety.schemas.page_table import (
    PageFeishuConfigItem,
    PageFeishuConfigListResponse,
    PageFeishuConfigTestResult,
    PageTableAttachmentUploadResponse,
    PageTableRecord,
    PageTableRecordsResponse,
    PageTableStatsResponse,
    ResolvedPageFeishuUrl,
    ResolvePageFeishuUrlRequest,
    UpdatePageFeishuConfigRequest,
    UpdatePageTableRecordRequest,
)
from app.modules.safety.service import attachment_thumbnail, page_table
from app.platform.identity.data_scope import current_page_key
from app.shared.schemas import ApiResponseEnvelope

page_table_router = APIRouter()


def _require_page_context(page_key: str) -> None:
    """数据接口的 URL page_key 必须与本次请求已授权的页面一致。"""
    authorized = current_page_key.get()
    if not authorized or authorized != page_key:
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "请求的表格页面与当前页面上下文不一致",
        )


# ── 配置 ──


@page_table_router.get(
    "/page-feishu-configs",
    response_model=ApiResponseEnvelope[PageFeishuConfigListResponse],
    summary="列出支持飞书表格镜像的页面及其绑定",
)
async def list_page_feishu_configs(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[PageFeishuConfigListResponse]:
    result = await page_table.list_page_feishu_configs(db)
    return ApiResponseEnvelope(data=result)


@page_table_router.put(
    "/page-feishu-configs/{page_key}",
    response_model=ApiResponseEnvelope[PageFeishuConfigItem],
    summary="保存页面的飞书多维表格绑定",
)
async def save_page_feishu_config(
    page_key: str,
    data: UpdatePageFeishuConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[PageFeishuConfigItem]:
    result = await page_table.save_page_feishu_config(db, page_key, data)
    return ApiResponseEnvelope(data=result)


@page_table_router.post(
    "/page-feishu-configs/{page_key}/test",
    response_model=ApiResponseEnvelope[PageFeishuConfigTestResult],
    summary="测试页面的飞书多维表格绑定",
)
async def test_page_feishu_config(
    page_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[PageFeishuConfigTestResult]:
    result = await page_table.test_page_feishu_config(db, page_key)
    return ApiResponseEnvelope(data=result)


@page_table_router.post(
    "/page-feishu-configs/resolve",
    response_model=ApiResponseEnvelope[ResolvedPageFeishuUrl],
    summary="解析多维表格链接并列出子表",
)
async def resolve_page_feishu_url(
    data: ResolvePageFeishuUrlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[ResolvedPageFeishuUrl]:
    result = await page_table.resolve_page_feishu_url(db, data.url)
    return ApiResponseEnvelope(data=result)


# ── 数据 ──


@page_table_router.get(
    "/page-tables/{page_key}/records",
    response_model=ApiResponseEnvelope[PageTableRecordsResponse],
    summary="读取镜像页的记录（列定义来自飞书实时 schema）",
)
async def list_page_table_records(
    page_key: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(page_table.DEFAULT_PAGE_SIZE, ge=1),
    keyword: str | None = Query(None),
    sort_field: str | None = Query(None),
    sort_direction: str = Query("asc"),
    filter_field: str | None = Query(None),
    filter_value: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[PageTableRecordsResponse]:
    _require_page_context(page_key)
    result = await page_table.list_page_table_records(
        db,
        page_key,
        page=page,
        page_size=page_size,
        keyword=keyword,
        sort_field=sort_field,
        sort_direction=sort_direction,
        filter_field=filter_field,
        filter_value=filter_value,
    )
    return ApiResponseEnvelope(data=result)


@page_table_router.get(
    "/page-tables/{page_key}/stats",
    response_model=ApiResponseEnvelope[PageTableStatsResponse],
    summary="页面仪表盘聚合（默认：日期按月 / 位置文本按车间号归一 / 单选按选项）",
)
async def get_page_table_stats(
    page_key: str,
    group_by: list[str] | None = Query(
        None, description="分组字段名，可重复；缺省时自动挑选日期/位置/单选字段"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[PageTableStatsResponse]:
    _require_page_context(page_key)
    result = await page_table.get_page_table_stats(db, page_key, group_by)
    return ApiResponseEnvelope(data=result)


@page_table_router.put(
    "/page-tables/{page_key}/records/{record_id}",
    response_model=ApiResponseEnvelope[PageTableRecord],
    summary="更新镜像页的记录（回写飞书多维表格）",
)
async def update_page_table_record(
    page_key: str,
    record_id: str,
    data: UpdatePageTableRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[PageTableRecord]:
    _require_page_context(page_key)
    result = await page_table.update_page_table_record(
        db,
        page_key,
        record_id,
        data.fields,
        user_id=current_user.id if current_user else None,
    )
    return ApiResponseEnvelope(data=result)


@page_table_router.post(
    "/page-tables/{page_key}/records/{record_id}/attachments/{field_name}",
    response_model=ApiResponseEnvelope[PageTableAttachmentUploadResponse],
    summary="上传附件到记录（追加到飞书附件字段）",
)
async def upload_page_table_attachment(
    page_key: str,
    record_id: str,
    field_name: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> ApiResponseEnvelope[PageTableAttachmentUploadResponse]:
    _require_page_context(page_key)
    result = await page_table.upload_page_table_attachment(
        db,
        page_key,
        record_id,
        field_name,
        file=file,
        user_id=current_user.id if current_user else None,
    )
    return ApiResponseEnvelope(data=result)


@page_table_router.get(
    "/page-tables/{page_key}/records/{record_id}/attachments/{field_name}/{file_token}/content",
    summary="代理下载镜像页记录附件",
)
async def download_page_table_attachment(
    page_key: str,
    record_id: str,
    field_name: str,
    file_token: str,
    inline: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    _require_page_context(page_key)
    content, content_type, filename = await page_table.fetch_page_table_attachment(
        db, page_key, record_id, field_name, file_token
    )
    inline_types = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
    }
    as_inline = inline and content_type in inline_types
    encoded_name = quote(filename)
    return StreamingResponse(
        iter([content]),
        media_type=content_type if as_inline else "application/octet-stream",
        headers={
            "Content-Disposition": (
                f"{'inline' if as_inline else 'attachment'}; "
                f"filename*=UTF-8''{encoded_name}"
            ),
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


@page_table_router.get(
    "/page-tables/{page_key}/records/{record_id}/attachments/{field_name}/{file_token}/thumbnail",
    summary="镜像页记录附件缩略图（PIL 缩放为小图，避免列表页拉取原图全量字节）",
)
async def thumbnail_page_table_attachment(
    page_key: str,
    record_id: str,
    field_name: str,
    file_token: str,
    max_width: int = Query(
        attachment_thumbnail.DEFAULT_MAX_WIDTH, ge=16, le=512
    ),
    max_height: int = Query(
        attachment_thumbnail.DEFAULT_MAX_HEIGHT, ge=16, le=512
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    _require_page_context(page_key)
    result = await attachment_thumbnail.get_page_table_attachment_thumbnail(
        db, page_key, record_id, field_name, file_token, max_width, max_height
    )
    if result is None:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            "该附件暂不支持生成缩略图，请下载后查看",
        )
    content, content_type, filename = result
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"inline; filename=thumbnail; filename*=UTF-8''{quote(filename)}"
            ),
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )
