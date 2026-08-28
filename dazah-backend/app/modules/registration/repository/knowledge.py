"""Registration knowledge repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import asc, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registration.models.knowledge import (
    KnowledgeArticle,
    KnowledgeAttachment,
    KnowledgeCategory,
    KnowledgeComment,
)


class RegistrationKnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Category operations ──────────────────────────────────────────────

    async def count_categories(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(KnowledgeCategory)
            .where(KnowledgeCategory.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def get_category_by_id(self, category_id: UUID) -> KnowledgeCategory | None:
        result = await self.session.execute(
            select(KnowledgeCategory).where(
                KnowledgeCategory.id == category_id,
                KnowledgeCategory.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_categories(self) -> list[KnowledgeCategory]:
        result = await self.session.execute(
            select(KnowledgeCategory)
            .where(KnowledgeCategory.is_deleted.is_(False))
            .order_by(
                asc(KnowledgeCategory.sort_order), asc(KnowledgeCategory.created_at)
            )
        )
        return list(result.scalars().all())

    async def create_category(self, category: KnowledgeCategory) -> KnowledgeCategory:
        self.session.add(category)
        await self.session.flush()
        return category

    async def update_category(
        self,
        category: KnowledgeCategory,
        data: dict[str, object | None],
    ) -> KnowledgeCategory:
        for key, value in data.items():
            if hasattr(category, key):
                setattr(category, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(KnowledgeCategory).where(KnowledgeCategory.id == category.id)
        )
        return result.scalar_one()

    async def soft_delete_category(self, category: KnowledgeCategory) -> None:
        category.is_deleted = True
        await self.session.flush()

    async def count_articles_by_category(self, category_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(KnowledgeArticle)
            .where(
                KnowledgeArticle.is_deleted.is_(False),
                KnowledgeArticle.category_id == category_id,
            )
        )
        return result.scalar() or 0

    # ── Article operations ───────────────────────────────────────────────

    async def count_articles(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(KnowledgeArticle)
            .where(KnowledgeArticle.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def count_published_articles(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(KnowledgeArticle)
            .where(
                KnowledgeArticle.is_deleted.is_(False),
                KnowledgeArticle.is_published.is_(True),
            )
        )
        return result.scalar() or 0

    async def count_draft_articles(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(KnowledgeArticle)
            .where(
                KnowledgeArticle.is_deleted.is_(False),
                KnowledgeArticle.is_published.is_(False),
            )
        )
        return result.scalar() or 0

    async def get_article_by_id(self, article_id: UUID) -> KnowledgeArticle | None:
        result = await self.session.execute(
            select(KnowledgeArticle).where(
                KnowledgeArticle.id == article_id,
                KnowledgeArticle.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_articles(
        self,
        *,
        category_id: UUID | None = None,
        keyword: str | None = None,
        tags: str | None = None,
        country: str | None = None,
        is_published: bool | None = None,
    ) -> list[KnowledgeArticle]:
        stmt = select(KnowledgeArticle).where(KnowledgeArticle.is_deleted.is_(False))

        if category_id:
            stmt = stmt.where(KnowledgeArticle.category_id == category_id)
        if country:
            stmt = stmt.where(KnowledgeArticle.country == country)
        if is_published is not None:
            stmt = stmt.where(KnowledgeArticle.is_published.is_(is_published))
        if keyword:
            like_keyword = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    KnowledgeArticle.title.ilike(like_keyword),
                    KnowledgeArticle.content.ilike(like_keyword),
                    KnowledgeArticle.tags.ilike(like_keyword),
                )
            )
        if tags:
            for tag in tags.split(","):
                tag = tag.strip()
                if tag:
                    stmt = stmt.where(KnowledgeArticle.tags.ilike(f"%{tag}%"))

        stmt = stmt.order_by(desc(KnowledgeArticle.created_at))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_article(self, article: KnowledgeArticle) -> KnowledgeArticle:
        self.session.add(article)
        await self.session.flush()
        return article

    async def update_article(
        self,
        article: KnowledgeArticle,
        data: dict[str, object | None],
    ) -> KnowledgeArticle:
        for key, value in data.items():
            if hasattr(article, key):
                setattr(article, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(KnowledgeArticle).where(KnowledgeArticle.id == article.id)
        )
        return result.scalar_one()

    async def soft_delete_article(self, article: KnowledgeArticle) -> None:
        article.is_deleted = True
        await self.session.flush()

    async def increment_view_count(self, article_id: UUID) -> None:
        await self.session.execute(
            update(KnowledgeArticle)
            .where(KnowledgeArticle.id == article_id)
            .values(view_count=KnowledgeArticle.view_count + 1)
        )
        await self.session.flush()

    async def publish_article(self, article: KnowledgeArticle) -> KnowledgeArticle:
        article.is_published = True
        article.published_at = datetime.now(tz=None)
        await self.session.flush()
        result = await self.session.execute(
            select(KnowledgeArticle).where(KnowledgeArticle.id == article.id)
        )
        return result.scalar_one()

    # ── Attachment operations ────────────────────────────────────────────

    async def list_attachments_by_article(
        self, article_id: UUID
    ) -> list[KnowledgeAttachment]:
        result = await self.session.execute(
            select(KnowledgeAttachment)
            .where(
                KnowledgeAttachment.article_id == article_id,
                KnowledgeAttachment.is_deleted.is_(False),
            )
            .order_by(asc(KnowledgeAttachment.created_at))
        )
        return list(result.scalars().all())

    async def create_attachment(
        self, attachment: KnowledgeAttachment
    ) -> KnowledgeAttachment:
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def get_attachment_by_id(
        self, attachment_id: UUID
    ) -> KnowledgeAttachment | None:
        result = await self.session.execute(
            select(KnowledgeAttachment).where(
                KnowledgeAttachment.id == attachment_id,
                KnowledgeAttachment.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def soft_delete_attachment(self, attachment: KnowledgeAttachment) -> None:
        attachment.is_deleted = True
        await self.session.flush()

    async def update_attachment(
        self, attachment: KnowledgeAttachment, data: dict[str, object | None]
    ) -> KnowledgeAttachment:
        for key, value in data.items():
            if hasattr(attachment, key):
                setattr(attachment, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(KnowledgeAttachment).where(KnowledgeAttachment.id == attachment.id)
        )
        return result.scalar_one()

    # ── Comment operations ───────────────────────────────────────────────

    async def list_comments_by_article(
        self, article_id: UUID
    ) -> list[KnowledgeComment]:
        result = await self.session.execute(
            select(KnowledgeComment)
            .where(
                KnowledgeComment.article_id == article_id,
                KnowledgeComment.is_deleted.is_(False),
            )
            .order_by(asc(KnowledgeComment.created_at))
        )
        return list(result.scalars().all())

    async def create_comment(self, comment: KnowledgeComment) -> KnowledgeComment:
        self.session.add(comment)
        await self.session.flush()
        return comment

    async def get_comment_by_id(self, comment_id: UUID) -> KnowledgeComment | None:
        result = await self.session.execute(
            select(KnowledgeComment).where(
                KnowledgeComment.id == comment_id,
                KnowledgeComment.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def update_comment(
        self, comment: KnowledgeComment, data: dict[str, object | None]
    ) -> KnowledgeComment:
        for key, value in data.items():
            if hasattr(comment, key):
                setattr(comment, key, value)
        await self.session.flush()
        result = await self.session.execute(
            select(KnowledgeComment).where(KnowledgeComment.id == comment.id)
        )
        return result.scalar_one()

    async def soft_delete_comment(self, comment: KnowledgeComment) -> None:
        comment.is_deleted = True
        await self.session.flush()
