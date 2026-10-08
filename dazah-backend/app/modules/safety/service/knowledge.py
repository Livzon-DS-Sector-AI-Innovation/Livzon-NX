"""Safety business workflows."""

import logging
import os
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.models import (
    SafetyKnowledgeArticle,
)
from app.modules.safety.repository import SafetyRepository
from app.modules.safety.schemas import (
    SafetyKnowledgeArticleCreate,
    SafetyKnowledgeArticleUpdate,
)

logger = logging.getLogger(__name__)

# 本地附件约束：扩展名白名单、单文件上限、单篇数量上限
LOCAL_ATTACHMENT_ALLOWED_EXTS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".png", ".jpg", ".jpeg", ".webp", ".txt", ".md",
}
LOCAL_ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024
LOCAL_ATTACHMENT_MAX_COUNT = 10
KNOWLEDGE_UPLOAD_DIR = os.path.join("uploads", "safety", "knowledge")


class KnowledgeService:
    """安全知识库业务服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SafetyRepository(session)

    async def get_articles(
        self,
        skip: int = 0,
        limit: int = 20,
        keyword: str | None = None,
        regulation_status: str | None = None,
    ) -> tuple[list[SafetyKnowledgeArticle], int]:
        """获取知识库文章列表"""
        return await self.repo.get_knowledge_articles(
            skip, limit, keyword, regulation_status
        )

    async def get_article(self, article_id: uuid.UUID) -> SafetyKnowledgeArticle | None:
        """获取文章详情"""
        return await self.repo.get_knowledge_article_by_id(article_id)

    async def create_article(
        self, data: SafetyKnowledgeArticleCreate
    ) -> SafetyKnowledgeArticle:
        """创建知识库文章（本地文档直接可见，无草稿生命周期）"""
        article_data = data.model_dump()
        article_data["status"] = "published"
        return await self.repo.create_knowledge_article(article_data)

    async def update_article(
        self, article_id: uuid.UUID, data: SafetyKnowledgeArticleUpdate
    ) -> SafetyKnowledgeArticle | None:
        """更新知识库文章"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        return await self.repo.update_knowledge_article(article_id, update_data)

    async def delete_article(self, article_id: uuid.UUID) -> bool:
        """删除知识库文章"""
        return await self.repo.delete_knowledge_article(article_id)

    async def add_local_attachments(
        self, article_id: uuid.UUID, files: list[UploadFile]
    ) -> SafetyKnowledgeArticle:
        """为本地文档追加附件（镜像行附件在飞书多维表格维护）。

        存储路径 uploads/safety/knowledge/{article_id}/{token}{ext}，
        记录快照 [{token, name, size}]，不落原始文件名到磁盘。
        """
        article = await self.repo.get_knowledge_article_by_id(article_id)
        if article is None:
            raise AppException(status_code=404, message="知识库文档不存在")
        if article.feishu_record_id:
            raise AppException(
                message="该文档来自飞书法规库镜像，附件请在多维表格中维护"
            )
        if not files:
            raise AppException(message="未收到附件文件")

        attachments = list(article.local_attachments or [])
        if len(attachments) + len(files) > LOCAL_ATTACHMENT_MAX_COUNT:
            raise AppException(
                message=f"每篇文档最多 {LOCAL_ATTACHMENT_MAX_COUNT} 个附件"
            )

        article_dir = Path(KNOWLEDGE_UPLOAD_DIR) / str(article_id)
        article_dir.mkdir(parents=True, exist_ok=True)
        saved: list[dict] = []
        for file in files:
            original_name = (file.filename or "attachment").strip() or "attachment"
            ext = os.path.splitext(original_name)[1].lower()
            if ext not in LOCAL_ATTACHMENT_ALLOWED_EXTS:
                raise AppException(
                    message=f"不支持的附件类型：{original_name}（仅支持 "
                    "PDF/Office/图片/文本）"
                )
            content = await file.read()
            if len(content) > LOCAL_ATTACHMENT_MAX_BYTES:
                raise AppException(message=f"附件超过 20MB 上限：{original_name}")
            if not content:
                raise AppException(message=f"附件内容为空：{original_name}")
            token = uuid.uuid4().hex
            (article_dir / f"{token}{ext}").write_bytes(content)
            saved.append(
                {"token": token, "name": original_name, "size": len(content)}
            )
            logger.info(
                "知识库附件已上传: article=%s name=%s bytes=%s",
                article_id,
                original_name,
                len(content),
            )

        attachments.extend(saved)
        item = await self.repo.update_knowledge_article(
            article_id, {"local_attachments": attachments}
        )
        await self.session.commit()
        return item  # type: ignore[return-value]

    async def remove_local_attachment(
        self, article_id: uuid.UUID, token: str
    ) -> SafetyKnowledgeArticle:
        """删除本地文档附件（快照与磁盘文件一并清理）。"""
        article = await self.repo.get_knowledge_article_by_id(article_id)
        if article is None:
            raise AppException(status_code=404, message="知识库文档不存在")
        attachments = list(article.local_attachments or [])
        match = next((a for a in attachments if a.get("token") == token), None)
        if match is None:
            raise AppException(status_code=404, message="附件不存在")

        article_dir = Path(KNOWLEDGE_UPLOAD_DIR) / str(article_id)
        # 只按自身目录 + 已知扩展名定位文件，杜绝路径注入
        for ext in LOCAL_ATTACHMENT_ALLOWED_EXTS:
            target = article_dir / f"{token}{ext}"
            if target.is_file():
                target.unlink(missing_ok=True)
                break
        remaining = [a for a in attachments if a.get("token") != token]
        item = await self.repo.update_knowledge_article(
            article_id, {"local_attachments": remaining}
        )
        await self.session.commit()
        return item  # type: ignore[return-value]

    def resolve_local_attachment(
        self, article_id: uuid.UUID, token: str
    ) -> tuple[Path, str]:
        """校验 token 并返回 (磁盘路径, 展示文件名)，供下载/预览端点使用。"""
        if not token or not all(c in "0123456789abcdef" for c in token):
            raise AppException(status_code=404, message="附件不存在")
        article_dir = Path(KNOWLEDGE_UPLOAD_DIR) / str(article_id)
        for ext in LOCAL_ATTACHMENT_ALLOWED_EXTS:
            target = (article_dir / f"{token}{ext}").resolve()
            if target.is_file() and target.parent == article_dir.resolve():
                return target, f"{token}{ext}"
        raise AppException(status_code=404, message="附件不存在")

    async def get_local_attachment_meta(
        self, article_id: uuid.UUID, token: str
    ) -> dict:
        """读取附件快照元信息（展示名/大小），并完成属主校验。"""
        article = await self.repo.get_knowledge_article_by_id(article_id)
        if article is None:
            raise AppException(status_code=404, message="知识库文档不存在")
        match = next(
            (a for a in (article.local_attachments or []) if a.get("token") == token),
            None,
        )
        if match is None:
            raise AppException(status_code=404, message="附件不存在")
        return match



# ==================== 风险作业报备 Services ====================
