"""Registration knowledge API routes."""

import logging
import uuid
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs, storage
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import AppException, NotFoundException
from app.core.response import success_response
from app.core.upload_security import read_upload_secure, sniff_upload_mime
from app.modules.registration.api._common import require_user as _require_user
from app.modules.registration.schemas.knowledge import (
    KnowledgeArticleCreate,
    KnowledgeArticleDetail,
    KnowledgeArticleListItem,
    KnowledgeArticleResponse,
    KnowledgeArticleUpdate,
    KnowledgeAttachmentResponse,
    KnowledgeCategoryCreate,
    KnowledgeCategoryResponse,
    KnowledgeCategoryUpdate,
    KnowledgeCommentCreate,
    KnowledgeCommentResponse,
    KnowledgeCommentUpdate,
    KnowledgeOverview,
)
from app.modules.registration.service.knowledge import RegistrationKnowledgeService
from app.shared.schemas import ApiResponseEnvelope

logger = logging.getLogger(__name__)

router = APIRouter()
KNOWLEDGE_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".md",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
}
KNOWLEDGE_UPLOAD_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/markdown",
    "text/plain",
    "image/png",
    "image/jpeg",
}

# ── 异步任务（基于 app/core/jobs.py，Redis 存储状态） ─────────────────


async def _extract_article_task(
    file_name: str, content_type: str, file_content: bytes
) -> Any:
    """AI 提取附件内容，返回结果存入任务状态。"""
    from app.modules.registration.service.knowledge_ai import (
        extract_article_from_content,
    )

    return await extract_article_from_content(
        file_name=file_name,
        content_type=content_type,
        file_content=file_content,
    )


async def _summarize_attachment_task(attachment_id: uuid.UUID) -> Any:
    """AI 生成附件摘要，返回结果存入任务状态。"""
    from app.core.database import async_session_factory
    from app.modules.registration.service.knowledge_ai import (
        generate_attachment_summary,
    )

    async with async_session_factory() as db:
        summary = await generate_attachment_summary(db, attachment_id)
    return {"ai_summary": summary}


# ── Category routes ─────────────────────────────────────────────────────


@router.get(
    "/categories",
    summary="获取知识分类列表",
    response_model=ApiResponseEnvelope[list[KnowledgeCategoryResponse]],
)
async def list_categories(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    categories = await RegistrationKnowledgeService(db).list_categories()
    return success_response(data=categories)


@router.post(
    "/categories",
    summary="新增知识分类",
    response_model=ApiResponseEnvelope[KnowledgeCategoryResponse],
)
async def create_category(
    data: KnowledgeCategoryCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    category = await RegistrationKnowledgeService(db).create_category(data)
    return success_response(message="新增成功", data=category)


@router.put(
    "/categories/{category_id}",
    summary="编辑知识分类",
    response_model=ApiResponseEnvelope[KnowledgeCategoryResponse],
)
async def update_category(
    category_id: uuid.UUID,
    data: KnowledgeCategoryUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    category = await RegistrationKnowledgeService(db).update_category(category_id, data)
    return success_response(message="更新成功", data=category)


@router.delete("/categories/{category_id}", summary="删除知识分类")
async def delete_category(
    category_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await RegistrationKnowledgeService(db).delete_category(category_id)
    return success_response(message="删除成功")


# ── Article routes ──────────────────────────────────────────────────────


@router.get(
    "/overview",
    summary="获取知识库概览",
    response_model=ApiResponseEnvelope[KnowledgeOverview],
)
async def get_knowledge_overview(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    overview = await RegistrationKnowledgeService(db).get_overview()
    return success_response(data=overview)


@router.get(
    "/articles",
    summary="获取知识文章列表",
    response_model=ApiResponseEnvelope[list[KnowledgeArticleListItem]],
)
async def list_articles(
    current_user: CurrentUser,
    category_id: uuid.UUID | None = Query(None, description="分类ID"),
    keyword: str | None = Query(None, description="关键词"),
    tags: str | None = Query(None, description="标签（逗号分隔）"),
    country: str | None = Query(None, description="适用国家"),
    is_published: bool | None = Query(None, description="是否发布"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    articles = await RegistrationKnowledgeService(db).list_articles(
        category_id=category_id,
        keyword=keyword,
        tags=tags,
        country=country,
        is_published=is_published,
    )
    return success_response(data=articles)


@router.get(
    "/articles/{article_id}",
    summary="获取知识文章详情",
    response_model=ApiResponseEnvelope[KnowledgeArticleDetail],
)
async def get_article(
    article_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    article = await RegistrationKnowledgeService(db).get_article_detail(article_id)
    return success_response(data=article)


@router.post(
    "/articles",
    summary="新增知识文章",
    response_model=ApiResponseEnvelope[KnowledgeArticleResponse],
)
async def create_article(
    data: KnowledgeArticleCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    article = await RegistrationKnowledgeService(db).create_article(data)
    return success_response(message="新增成功", data=article)


@router.put(
    "/articles/{article_id}",
    summary="编辑知识文章",
    response_model=ApiResponseEnvelope[KnowledgeArticleResponse],
)
async def update_article(
    article_id: uuid.UUID,
    data: KnowledgeArticleUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    article = await RegistrationKnowledgeService(db).update_article(article_id, data)
    return success_response(message="更新成功", data=article)


@router.delete("/articles/{article_id}", summary="删除知识文章")
async def delete_article(
    article_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await RegistrationKnowledgeService(db).delete_article(article_id)
    return success_response(message="删除成功")


# ── Attachment routes ───────────────────────────────────────────────────


@router.get(
    "/articles/{article_id}/attachments",
    summary="获取文章附件列表",
    response_model=ApiResponseEnvelope[list[KnowledgeAttachmentResponse]],
)
async def list_attachments(
    article_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    attachments = await RegistrationKnowledgeService(db).list_attachments(article_id)
    return success_response(data=attachments)


@router.post(
    "/articles/{article_id}/attachments",
    summary="上传文章附件",
    response_model=ApiResponseEnvelope[KnowledgeAttachmentResponse],
)
async def upload_attachment(
    article_id: uuid.UUID,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    if not storage.is_enabled():
        raise AppException(
            status_code=503, message="文件存储未启用，请联系管理员配置 MinIO"
        )

    safe_name, file_content = await read_upload_secure(
        file,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions=KNOWLEDGE_UPLOAD_EXTENSIONS,
        allowed_mimes=KNOWLEDGE_UPLOAD_MIMES,
        what="知识库附件",
    )
    content_type = sniff_upload_mime(safe_name, file_content)
    object_key = f"knowledge/{article_id}/{uuid4().hex}_{safe_name}"
    try:
        storage.upload_object(
            "registration", object_key, file_content, len(file_content), content_type
        )
    except Exception:
        logger.exception(
            "附件上传到存储失败: article_id=%s object_key=%s", article_id, object_key
        )
        raise AppException(status_code=500, message="附件上传失败，请稍后重试")

    try:
        attachment = await RegistrationKnowledgeService(db).create_attachment(
            article_id=article_id,
            file_name=safe_name,
            file_path=object_key,
            file_size=len(file_content),
            content_type=content_type,
        )
    except Exception as exc:
        try:
            storage.delete_object("registration", object_key)
        except Exception:  # noqa: BLE001
            logger.exception(
                "知识库附件数据库写入失败且清理对象失败: object_key=%s", object_key
            )
        if isinstance(exc, AppException):
            raise
        logger.exception(
            "知识库附件元数据写入失败: article_id=%s object_key=%s",
            article_id,
            object_key,
        )
        raise AppException(
            status_code=500, message="附件记录保存失败，请稍后重试"
        ) from exc
    return success_response(message="上传成功", data=attachment)


@router.get(
    "/attachments/{attachment_id}",
    summary="获取附件详情",
    response_model=ApiResponseEnvelope[KnowledgeAttachmentResponse],
)
async def get_attachment(
    attachment_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    attachment = await RegistrationKnowledgeService(db).get_attachment(attachment_id)
    return success_response(data=attachment)


@router.get("/attachments/{attachment_id}/preview", summary="在线预览/下载附件")
async def preview_attachment(
    attachment_id: uuid.UUID,
    current_user: CurrentUser,
    download: bool = Query(False, description="是否强制下载（否则浏览器内联预览）"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """从对象存储读取附件内容并返回文件流。"""
    _require_user(current_user)
    from fastapi import Response

    attachment = await RegistrationKnowledgeService(db).get_attachment(attachment_id)
    obj = storage.get_object("registration", attachment.file_path)
    if obj is None:
        raise NotFoundException("附件文件")
    data, content_type = obj
    disposition = "attachment" if download else "inline"
    return Response(
        content=data,
        media_type=content_type,
        headers={
            (
                "Content-Disposition"
            ): f"{disposition}; filename*=UTF-8''{quote(attachment.file_name)}"
        },
    )


@router.delete("/attachments/{attachment_id}", summary="删除附件")
async def delete_attachment(
    attachment_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    attachment = await RegistrationKnowledgeService(db).get_attachment(attachment_id)
    stored_object: tuple[bytes, str] | None = None
    if storage.is_enabled():
        try:
            stored_object = storage.get_object("registration", attachment.file_path)
            # 先删除对象；数据库失败时下面用原内容恢复，避免留下已删除记录或断链。
            storage.delete_object("registration", attachment.file_path)
        except Exception as exc:
            logger.exception(
                "删除附件存储对象失败: object_key=%s", attachment.file_path
            )
            raise AppException(
                status_code=502, message="附件删除失败，请稍后重试"
            ) from exc

    try:
        await RegistrationKnowledgeService(db).delete_attachment(attachment_id)
    except Exception as exc:
        if storage.is_enabled() and stored_object is not None:
            try:
                data, content_type = stored_object
                storage.upload_object(
                    "registration",
                    attachment.file_path,
                    data,
                    len(data),
                    content_type,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "附件数据库删除失败且对象恢复失败: object_key=%s",
                    attachment.file_path,
                )
        if isinstance(exc, AppException):
            raise
        logger.exception("附件元数据删除失败: attachment_id=%s", attachment_id)
        raise AppException(status_code=500, message="附件删除失败，请稍后重试") from exc
    return success_response(message="删除成功")


@router.post("/articles/extract", summary="AI提取附件内容生成文章结构（异步任务）")
async def extract_article_from_file(
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> Any:
    _require_user(current_user)

    safe_name, file_content = await read_upload_secure(
        file,
        max_bytes=get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        allowed_extensions=KNOWLEDGE_UPLOAD_EXTENSIONS,
        allowed_mimes=KNOWLEDGE_UPLOAD_MIMES,
        what="知识库提取文件",
    )
    task_id = await jobs.submit_job(
        _extract_article_task,
        ttl=600,
        file_name=safe_name,
        content_type=sniff_upload_mime(safe_name, file_content),
        file_content=file_content,
    )
    return success_response(
        message="任务已提交", data={"task_id": task_id, "status": "pending"}
    )


@router.post(
    "/attachments/{attachment_id}/summarize", summary="AI生成附件摘要（异步任务）"
)
async def summarize_attachment(
    attachment_id: uuid.UUID,
    current_user: CurrentUser,
) -> Any:
    _require_user(current_user)

    task_id = await jobs.submit_job(
        _summarize_attachment_task,
        ttl=600,
        attachment_id=attachment_id,
    )
    return success_response(
        message="任务已提交", data={"task_id": task_id, "status": "pending"}
    )


@router.get("/tasks/{task_id}", summary="查询异步任务状态")
async def get_task_status(
    task_id: str,
    current_user: CurrentUser,
) -> Any:
    _require_user(current_user)
    job = await jobs.get_job_status(task_id)
    if job is None:
        raise AppException(message="任务不存在或已过期", status_code=404)
    # 适配前端轮询契约：{task_id, status:
    # pending/running/completed/failed,
    # result?, error?}
    state = job.get("state")
    if state == "completed":
        payload: dict[str, Any] = {
            "task_id": task_id,
            "status": "completed",
            "result": job.get("result"),
        }
    elif state == "failed":
        payload = {
            "task_id": task_id,
            "status": "failed",
            "error": str(job.get("progress") or "任务执行失败"),
        }
    else:
        payload = {"task_id": task_id, "status": "running"}
    return success_response(data=payload)


# ─ Comment routes ──────────────────────────────────────────────────────


@router.get(
    "/articles/{article_id}/comments",
    summary="获取文章评论列表",
    response_model=ApiResponseEnvelope[list[KnowledgeCommentResponse]],
)
async def list_comments(
    article_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    comments = await RegistrationKnowledgeService(db).list_comments(article_id)
    return success_response(data=comments)


@router.post(
    "/articles/{article_id}/comments",
    summary="新增评论",
    response_model=ApiResponseEnvelope[KnowledgeCommentResponse],
)
async def create_comment(
    article_id: uuid.UUID,
    data: KnowledgeCommentCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    comment = await RegistrationKnowledgeService(db).create_comment(article_id, data)
    return success_response(message="评论成功", data=comment)


@router.put(
    "/comments/{comment_id}",
    summary="编辑评论",
    response_model=ApiResponseEnvelope[KnowledgeCommentResponse],
)
async def update_comment(
    comment_id: uuid.UUID,
    data: KnowledgeCommentUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    comment = await RegistrationKnowledgeService(db).update_comment(comment_id, data)
    return success_response(message="更新成功", data=comment)


@router.delete("/comments/{comment_id}", summary="删除评论")
async def delete_comment(
    comment_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    _require_user(current_user)
    await RegistrationKnowledgeService(db).delete_comment(comment_id)
    return success_response(message="删除成功")
