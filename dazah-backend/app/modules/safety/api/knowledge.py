"""Safety API — knowledge endpoints."""

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.response import ApiResponse
from app.modules.safety.schemas import (
    RegulationRadarRunDetail,
    RegulationRadarRunSummary,
    SafetyKnowledgeArticleCreate,
    SafetyKnowledgeArticleResponse,
    SafetyKnowledgeArticleUpdate,
)
from app.modules.safety.service import (
    KnowledgeService,
    knowledge_feishu,
    regulation_radar,
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
    path: Path,
    filename: str,
    *,
    inline: bool,
    content_type: str | None = None,
) -> Response:
    from urllib.parse import quote

    from fastapi.responses import FileResponse

    media_type = content_type or _guess_content_type(Path(path).name)
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


# ── EHS 法规雷达 ──


def _run_summary(model: Any) -> RegulationRadarRunSummary:
    return RegulationRadarRunSummary.model_validate(model)


@knowledge_router.post(
    "/knowledge-articles/radar/run",
    response_model=ApiResponse,
    summary="手动执行法规雷达扫描",
)
async def run_regulation_radar(
    dry_run: bool = Query(False, description="干跑：只比对不写入飞书表"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """扫描官方栏目页，发现新法规与已修订法规。dry_run 只出报告不写入。"""
    result = await regulation_radar.run_radar(
        db, dry_run=dry_run, trigger="manual"
    )
    return ApiResponse(data=result)


@knowledge_router.get(
    "/knowledge-articles/radar/runs",
    response_model=ApiResponse,
    summary="查询法规雷达扫描批次",
)
async def list_regulation_radar_runs(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """返回最近的扫描批次（新的在前）。"""
    from sqlalchemy import select

    from app.modules.safety.models import RegulationRadarRun

    rows = (
        await db.execute(
            select(RegulationRadarRun)
            .where(RegulationRadarRun.is_deleted.is_(False))
            .order_by(RegulationRadarRun.started_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return ApiResponse(
        data=[_run_summary(r).model_dump(mode="json") for r in rows],
        meta={"total": len(rows)},
    )


@knowledge_router.get(
    "/knowledge-articles/radar/runs/{run_id}",
    response_model=ApiResponse,
    summary="查询法规雷达扫描批次详情",
)
async def get_regulation_radar_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    from sqlalchemy import select

    from app.modules.safety.models import RegulationRadarRun

    row = (
        await db.execute(
            select(RegulationRadarRun).where(
                RegulationRadarRun.id == run_id,
                RegulationRadarRun.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return ApiResponse(code=404, message="扫描批次不存在")
    detail = RegulationRadarRunDetail.model_validate(row)
    return ApiResponse(data=detail.model_dump(mode="json"))



@knowledge_router.post(
    "/knowledge-articles/radar/notify/test",
    response_model=ApiResponse,
    summary="测试法规雷达通知发送",
)
async def test_regulation_radar_notify(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> Any:
    """向已配置的群/个人发送一条测试卡片，验证通知目标配置。"""
    result = await regulation_radar.send_test_notification(db)
    return ApiResponse(data=result)
