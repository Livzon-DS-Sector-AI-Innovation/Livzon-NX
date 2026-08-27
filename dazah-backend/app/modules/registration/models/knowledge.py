"""Registration knowledge ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class KnowledgeCategory(BaseModel):
    """知识分类表。"""

    __tablename__ = "knowledge_categories"
    __table_args__ = (
        Index("ix_registration_knowledge_categories_name", "name"),
        {"schema": "registration"},
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="分类名称")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="分类描述"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="排序序号"
    )


class KnowledgeArticle(BaseModel):
    """知识文章表。"""

    __tablename__ = "knowledge_articles"
    __table_args__ = (
        Index("ix_registration_knowledge_articles_category_id", "category_id"),
        Index("ix_registration_knowledge_articles_title", "title"),
        Index("ix_registration_knowledge_articles_is_published", "is_published"),
        {"schema": "registration"},
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="文章标题")
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, comment="分类ID"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="文章内容")
    tags: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="标签（逗号分隔）"
    )
    country: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="适用国家"
    )
    product: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="关联产品"
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", comment="是否发布"
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="发布时间"
    )
    author: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="作者"
    )
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="浏览次数"
    )
    source_url: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, comment="信息来源链接"
    )


class KnowledgeAttachment(BaseModel):
    """文章附件表。"""

    __tablename__ = "knowledge_attachments"
    __table_args__ = (
        Index("ix_registration_knowledge_attachments_article_id", "article_id"),
        {"schema": "registration"},
    )

    article_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, comment="关联文章ID"
    )
    file_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="原始文件名"
    )
    file_path: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="MinIO存储路径"
    )
    file_size: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="文件大小（字节）"
    )
    content_type: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="MIME类型"
    )
    ai_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="AI生成的结构化摘要"
    )


class KnowledgeComment(BaseModel):
    """文章评论表。"""

    __tablename__ = "knowledge_comments"
    __table_args__ = (
        Index("ix_registration_knowledge_comments_article_id", "article_id"),
        {"schema": "registration"},
    )

    article_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, comment="关联文章ID"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="评论内容")
