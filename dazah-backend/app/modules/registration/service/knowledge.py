"""Registration knowledge service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.registration.models.knowledge import (
    KnowledgeArticle,
    KnowledgeAttachment,
    KnowledgeCategory,
    KnowledgeComment,
)
from app.modules.registration.repository.knowledge import (
    RegistrationKnowledgeRepository,
)
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

logger = logging.getLogger(__name__)


class RegistrationKnowledgeService:
    """注册知识库业务服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = RegistrationKnowledgeRepository(session)

    # ─ Category operations ──────────────────────────────────────────────

    async def list_categories(self) -> list[KnowledgeCategoryResponse]:
        categories = await self.repository.list_categories()
        return [await self._build_category_response(cat) for cat in categories]

    async def create_category(
        self, data: KnowledgeCategoryCreate
    ) -> KnowledgeCategoryResponse:
        category = KnowledgeCategory(
            name=data.name,
            description=data.description,
            sort_order=data.sort_order,
        )
        created = await self.repository.create_category(category)
        await self.session.commit()
        return await self._build_category_response(created)

    async def update_category(
        self, category_id: UUID, data: KnowledgeCategoryUpdate
    ) -> KnowledgeCategoryResponse:
        category = await self.repository.get_category_by_id(category_id)
        if category is None:
            raise NotFoundException("知识分类", str(category_id))

        payload = data.model_dump(exclude_unset=True)
        updated = await self.repository.update_category(category, payload)
        await self.session.commit()
        return await self._build_category_response(updated)

    async def delete_category(self, category_id: UUID) -> None:
        category = await self.repository.get_category_by_id(category_id)
        if category is None:
            raise NotFoundException("知识分类", str(category_id))
        await self.repository.soft_delete_category(category)
        await self.session.commit()

    # ── Article operations ───────────────────────────────────────────────

    async def get_overview(self) -> KnowledgeOverview:
        categories = await self.repository.list_categories()
        category_responses = [
            await self._build_category_response(cat) for cat in categories
        ]

        return KnowledgeOverview(
            total_categories=len(categories),
            total_articles=await self.repository.count_articles(),
            published_articles=await self.repository.count_published_articles(),
            draft_articles=await self.repository.count_draft_articles(),
            categories=category_responses,
        )

    async def list_articles(
        self,
        *,
        category_id: UUID | None = None,
        keyword: str | None = None,
        tags: str | None = None,
        country: str | None = None,
        is_published: bool | None = None,
    ) -> list[KnowledgeArticleListItem]:
        articles = await self.repository.list_articles(
            category_id=category_id,
            keyword=keyword,
            tags=tags,
            country=country,
            is_published=is_published,
        )
        # 批量加载分类名称映射，避免逐篇文章查询（N+1）
        categories = await self.repository.list_categories()
        category_names = {category.id: category.name for category in categories}
        return [
            self._build_article_list_item(article, category_names)
            for article in articles
        ]

    async def _increment_view_count_and_refresh(
        self, article: KnowledgeArticle
    ) -> None:
        await self.repository.increment_view_count(article.id)
        await self.session.commit()
        # 视图计数用 bulk UPDATE 绕过 ORM 同步，updated_at 等列会被标记过期；
        # 不 refresh 直接读属性会在 async 上下文触发 MissingGreenlet。
        await self.session.refresh(article)

    async def get_article(self, article_id: UUID) -> KnowledgeArticleResponse:
        article = await self.repository.get_article_by_id(article_id)
        if article is None:
            raise NotFoundException("知识文章", str(article_id))

        await self._increment_view_count_and_refresh(article)

        return await self._build_article_response(article)

    async def create_article(
        self, data: KnowledgeArticleCreate
    ) -> KnowledgeArticleResponse:
        category = await self.repository.get_category_by_id(data.category_id)
        if category is None:
            raise NotFoundException("知识分类", str(data.category_id))

        now = datetime.now(UTC)
        article = KnowledgeArticle(
            title=data.title,
            category_id=data.category_id,
            content=data.content,
            tags=data.tags,
            country=data.country,
            product=data.product,
            is_published=data.is_published,
            published_at=now if data.is_published else None,
            author=data.author,
            source_url=data.source_url,
        )
        created = await self.repository.create_article(article)
        await self.session.commit()
        return await self._build_article_response(created)

    async def update_article(
        self, article_id: UUID, data: KnowledgeArticleUpdate
    ) -> KnowledgeArticleResponse:
        article = await self.repository.get_article_by_id(article_id)
        if article is None:
            raise NotFoundException("知识文章", str(article_id))

        payload = data.model_dump(exclude_unset=True)

        if (
            "is_published" in payload
            and payload["is_published"]
            and not article.is_published
        ):
            article.published_at = datetime.now(UTC)

        if "category_id" in payload:
            category = await self.repository.get_category_by_id(payload["category_id"])
            if category is None:
                raise NotFoundException("知识分类", str(payload["category_id"]))

        updated = await self.repository.update_article(article, payload)
        await self.session.commit()
        return await self._build_article_response(updated)

    async def delete_article(self, article_id: UUID) -> None:
        article = await self.repository.get_article_by_id(article_id)
        if article is None:
            raise NotFoundException("知识文章", str(article_id))
        await self.repository.soft_delete_article(article)
        await self.session.commit()

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _build_category_response(
        self, category: KnowledgeCategory
    ) -> KnowledgeCategoryResponse:
        article_count = await self.repository.count_articles_by_category(category.id)
        return KnowledgeCategoryResponse(
            id=category.id,
            name=category.name,
            description=category.description,
            sort_order=category.sort_order,
            article_count=article_count,
            created_at=category.created_at,
            updated_at=category.updated_at,
        )

    def _build_article_list_item(
        self, article: KnowledgeArticle, category_names: dict[UUID, str]
    ) -> KnowledgeArticleListItem:
        return KnowledgeArticleListItem(
            id=article.id,
            title=article.title,
            category_id=article.category_id,
            category_name=category_names.get(article.category_id),
            tags=article.tags,
            country=article.country,
            product=article.product,
            is_published=article.is_published,
            published_at=article.published_at,
            author=article.author,
            view_count=article.view_count,
            source_url=article.source_url,
            created_at=article.created_at,
            updated_at=article.updated_at,
        )

    async def _build_article_response(
        self, article: KnowledgeArticle
    ) -> KnowledgeArticleResponse:
        category = await self.repository.get_category_by_id(article.category_id)
        return KnowledgeArticleResponse(
            id=article.id,
            title=article.title,
            category_id=article.category_id,
            category_name=category.name if category else None,
            content=article.content,
            tags=article.tags,
            country=article.country,
            product=article.product,
            is_published=article.is_published,
            published_at=article.published_at,
            author=article.author,
            view_count=article.view_count,
            source_url=article.source_url,
            created_at=article.created_at,
            updated_at=article.updated_at,
        )

    # ── Article detail with attachments and comments ─────────────────────

    async def get_article_detail(self, article_id: UUID) -> KnowledgeArticleDetail:
        article = await self.repository.get_article_by_id(article_id)
        if article is None:
            raise NotFoundException("知识文章", str(article_id))

        await self._increment_view_count_and_refresh(article)

        category = await self.repository.get_category_by_id(article.category_id)
        attachments = await self.repository.list_attachments_by_article(article_id)
        comments = await self.repository.list_comments_by_article(article_id)

        return KnowledgeArticleDetail(
            id=article.id,
            title=article.title,
            category_id=article.category_id,
            category_name=category.name if category else None,
            content=article.content,
            tags=article.tags,
            country=article.country,
            product=article.product,
            is_published=article.is_published,
            published_at=article.published_at,
            author=article.author,
            view_count=article.view_count,
            source_url=article.source_url,
            created_at=article.created_at,
            updated_at=article.updated_at,
            attachments=[
                KnowledgeAttachmentResponse(
                    id=a.id,
                    article_id=a.article_id,
                    file_name=a.file_name,
                    file_size=a.file_size,
                    content_type=a.content_type,
                    ai_summary=a.ai_summary,
                    created_at=a.created_at,
                )
                for a in attachments
            ],
            comments=[
                KnowledgeCommentResponse(
                    id=c.id,
                    article_id=c.article_id,
                    content=c.content,
                    author=c.created_by,
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                )
                for c in comments
            ],
        )

    # ── Attachment operations ────────────────────────────────────────────

    async def list_attachments(
        self, article_id: UUID
    ) -> list[KnowledgeAttachmentResponse]:
        attachments = await self.repository.list_attachments_by_article(article_id)
        return [
            KnowledgeAttachmentResponse(
                id=a.id,
                article_id=a.article_id,
                file_name=a.file_name,
                file_size=a.file_size,
                content_type=a.content_type,
                ai_summary=a.ai_summary,
                created_at=a.created_at,
            )
            for a in attachments
        ]

    async def create_attachment(
        self,
        article_id: UUID,
        file_name: str,
        file_path: str,
        file_size: int,
        content_type: str,
    ) -> KnowledgeAttachmentResponse:
        article = await self.repository.get_article_by_id(article_id)
        if article is None:
            raise NotFoundException("知识文章", str(article_id))

        attachment = KnowledgeAttachment(
            article_id=article_id,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            content_type=content_type,
        )
        created = await self.repository.create_attachment(attachment)
        await self.session.commit()
        return KnowledgeAttachmentResponse(
            id=created.id,
            article_id=created.article_id,
            file_name=created.file_name,
            file_size=created.file_size,
            content_type=created.content_type,
            ai_summary=created.ai_summary,
            created_at=created.created_at,
        )

    async def get_attachment_model(self, attachment_id: UUID) -> KnowledgeAttachment:
        """返回附件 ORM 模型（供服务端内部定位存储对象，路径不下发前端）。"""
        attachment = await self.repository.get_attachment_by_id(attachment_id)
        if attachment is None:
            raise NotFoundException("附件", str(attachment_id))
        return attachment

    async def get_attachment(self, attachment_id: UUID) -> KnowledgeAttachmentResponse:
        attachment = await self.repository.get_attachment_by_id(attachment_id)
        if attachment is None:
            raise NotFoundException("附件", str(attachment_id))
        return KnowledgeAttachmentResponse(
            id=attachment.id,
            article_id=attachment.article_id,
            file_name=attachment.file_name,
            file_size=attachment.file_size,
            content_type=attachment.content_type,
            ai_summary=attachment.ai_summary,
            created_at=attachment.created_at,
        )

    async def delete_attachment(self, attachment_id: UUID) -> None:
        attachment = await self.repository.get_attachment_by_id(attachment_id)
        if attachment is None:
            raise NotFoundException("附件", str(attachment_id))
        await self.repository.soft_delete_attachment(attachment)
        await self.session.commit()

    # ─ Comment operations ───────────────────────────────────────────────

    async def list_comments(self, article_id: UUID) -> list[KnowledgeCommentResponse]:
        comments = await self.repository.list_comments_by_article(article_id)
        return [
            KnowledgeCommentResponse(
                id=c.id,
                article_id=c.article_id,
                content=c.content,
                author=c.created_by,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in comments
        ]

    async def create_comment(
        self, article_id: UUID, data: KnowledgeCommentCreate
    ) -> KnowledgeCommentResponse:
        article = await self.repository.get_article_by_id(article_id)
        if article is None:
            raise NotFoundException("知识文章", str(article_id))

        comment = KnowledgeComment(
            article_id=article_id,
            content=data.content,
        )
        created = await self.repository.create_comment(comment)
        await self.session.commit()
        return KnowledgeCommentResponse(
            id=created.id,
            article_id=created.article_id,
            content=created.content,
            author=created.created_by,
            created_at=created.created_at,
            updated_at=created.updated_at,
        )

    async def update_comment(
        self, comment_id: UUID, data: KnowledgeCommentUpdate
    ) -> KnowledgeCommentResponse:
        comment = await self.repository.get_comment_by_id(comment_id)
        if comment is None:
            raise NotFoundException("评论", str(comment_id))

        payload = data.model_dump(exclude_unset=True)
        updated = await self.repository.update_comment(comment, payload)
        await self.session.commit()
        return KnowledgeCommentResponse(
            id=updated.id,
            article_id=updated.article_id,
            content=updated.content,
            author=updated.created_by,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )

    async def delete_comment(self, comment_id: UUID) -> None:
        comment = await self.repository.get_comment_by_id(comment_id)
        if comment is None:
            raise NotFoundException("评论", str(comment_id))
        await self.repository.soft_delete_comment(comment)
        await self.session.commit()
