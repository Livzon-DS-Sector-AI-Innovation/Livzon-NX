"""Safety API — knowledge endpoints."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.response import ApiResponse
from app.modules.safety.schemas import (
    SafetyKnowledgeArticleCreate,
    SafetyKnowledgeArticleResponse,
    SafetyKnowledgeArticleUpdate,
)
from app.modules.safety.service import (
    KnowledgeService,
    knowledge_feishu,
)

knowledge_router = APIRouter()


@knowledge_router.get(
    "/knowledge-articles", response_model=ApiResponse, summary="获取安全知识库文章列表"
)
async def get_knowledge_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = None,
    regulation_status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取安全知识库文章列表"""
    service = KnowledgeService(db)
    skip = (page - 1) * page_size
    items, total = await service.get_articles(
        skip, page_size, keyword, regulation_status
    )
    return ApiResponse(
        data=[SafetyKnowledgeArticleResponse.model_validate(a) for a in items],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@knowledge_router.post(
    "/knowledge-articles", response_model=ApiResponse, summary="创建安全知识库文章"
)
async def create_knowledge_article(
    data: SafetyKnowledgeArticleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """创建安全知识库文章"""
    service = KnowledgeService(db)
    item = await service.create_article(data)
    await db.commit()
    return ApiResponse(data=SafetyKnowledgeArticleResponse.model_validate(item))


@knowledge_router.get(
    "/knowledge-articles/{article_id}",
    response_model=ApiResponse,
    summary="获取安全知识库文章详情",
)
async def get_knowledge_article(
    article_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """获取安全知识库文章详情"""
    service = KnowledgeService(db)
    item = await service.get_article(article_id)
    if not item:
        return ApiResponse(code=404, message="文章不存在")
    return ApiResponse(data=SafetyKnowledgeArticleResponse.model_validate(item))


@knowledge_router.put(
    "/knowledge-articles/{article_id}",
    response_model=ApiResponse,
    summary="更新安全知识库文章",
)
async def update_knowledge_article(
    article_id: uuid.UUID,
    data: SafetyKnowledgeArticleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """更新安全知识库文章"""
    service = KnowledgeService(db)
    item = await service.update_article(article_id, data)
    if not item:
        return ApiResponse(code=404, message="文章不存在")
    await db.commit()
    return ApiResponse(data=SafetyKnowledgeArticleResponse.model_validate(item))


@knowledge_router.delete(
    "/knowledge-articles/{article_id}",
    response_model=ApiResponse,
    summary="删除安全知识库文章",
)
async def delete_knowledge_article(
    article_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除安全知识库文章"""
    service = KnowledgeService(db)
    result = await service.delete_article(article_id)
    if not result:
        return ApiResponse(code=404, message="文章不存在")
    await db.commit()
    return ApiResponse(message="删除成功")


# ── EHS 法规库（飞书多维表格）同步与附件 ──


@knowledge_router.post(
    "/knowledge-articles/feishu/sync",
    response_model=ApiResponse,
    summary="从 EHS 法规库多维表格同步知识库",
)
async def sync_knowledge_from_feishu(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """全量拉取 EHS 法规库并按 feishu_record_id upsert 本地镜像。"""
    result = await knowledge_feishu.sync_knowledge_from_feishu(db)
    return ApiResponse(data=result)


def _attachment_response(
    content: bytes,
    content_type: str,
    filename: str,
    *,
    inline: bool,
) -> StreamingResponse:
    from urllib.parse import quote

    disposition = "inline" if inline else "attachment"
    encoded_name = quote(filename)
    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{encoded_name}"
            ),
            "Cache-Control": "private, max-age=86400",
        },
    )


@knowledge_router.get(
    "/knowledge-articles/feishu/records/{record_id}/attachments/{file_token}/content",
    summary="下载知识库飞书附件",
)
async def download_knowledge_attachment(
    record_id: str,
    file_token: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    """按附件快照校验后经安全应用凭证代理下载（平台缓存加速）。"""
    result = await knowledge_feishu.get_knowledge_attachment(
        db, record_id, file_token
    )
    return _attachment_response(*result, inline=False)


@knowledge_router.get(
    "/knowledge-articles/feishu/records/{record_id}/attachments/{file_token}/preview",
    summary="在线预览知识库飞书附件",
)
async def preview_knowledge_attachment(
    record_id: str,
    file_token: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    """浏览器内联预览（PDF/图片直接打开，其余类型回退为下载）。"""
    content, content_type, filename = await knowledge_feishu.get_knowledge_attachment(
        db, record_id, file_token
    )
    inline_types = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
    }
    inline = content_type in inline_types
    return _attachment_response(
        content,
        content_type if inline else "application/octet-stream",
        filename,
        inline=inline,
    )


# ── 本地文档附件管理 ──


@knowledge_router.post(
    "/knowledge-articles/{article_id}/attachments",
    response_model=ApiResponse,
    summary="为本地文档上传附件（支持多文件）",
)
async def upload_knowledge_attachments(
    article_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """镜像文档附件请在飞书多维表格维护；本端点仅服务本地创建的文档。"""
    service = KnowledgeService(db)
    item = await service.add_local_attachments(article_id, files)
    return ApiResponse(data=SafetyKnowledgeArticleResponse.model_validate(item))


@knowledge_router.delete(
    "/knowledge-articles/{article_id}/attachments/{token}",
    response_model=ApiResponse,
    summary="删除本地文档附件",
)
async def delete_knowledge_attachment(
    article_id: uuid.UUID,
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """删除附件快照与磁盘文件。"""
    service = KnowledgeService(db)
    item = await service.remove_local_attachment(article_id, token)
    return ApiResponse(data=SafetyKnowledgeArticleResponse.model_validate(item))


def _guess_content_type(filename: str) -> str:
    import mimetypes

    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _local_attachment_response(
    path,
    filename: str,
    *,
    inline: bool,
    content_type: str | None = None,
) -> Response:
    from pathlib import Path as _Path
    from urllib.parse import quote

    from fastapi.responses import FileResponse

    media_type = content_type or _guess_content_type(_Path(path).name)
    disposition = "inline" if inline else "attachment"
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{quote(filename)}"
            ),
            "Cache-Control": "private, max-age=86400",
        },
    )


@knowledge_router.get(
    "/knowledge-articles/{article_id}/attachments/{token}/content",
    summary="下载本地文档附件",
)
async def download_knowledge_local_attachment(
    article_id: uuid.UUID,
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    """校验属主后返回文件流（attachment）。"""
    service = KnowledgeService(db)
    meta = await service.get_local_attachment_meta(article_id, token)
    path, _ = service.resolve_local_attachment(article_id, token)
    return _local_attachment_response(
        path, str(meta.get("name") or token), inline=False
    )


@knowledge_router.get(
    "/knowledge-articles/{article_id}/attachments/{token}/preview",
    summary="在线预览本地文档附件",
)
async def preview_knowledge_local_attachment(
    article_id: uuid.UUID,
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Response:
    """PDF/图片浏览器内联预览，其余类型回退为下载。"""
    service = KnowledgeService(db)
    meta = await service.get_local_attachment_meta(article_id, token)
    path, _ = service.resolve_local_attachment(article_id, token)
    content_type = _guess_content_type(path.name)
    inline = content_type in {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
    }
    return _local_attachment_response(
        path,
        str(meta.get("name") or token),
        inline=inline,
        content_type=content_type if inline else "application/octet-stream",
    )
