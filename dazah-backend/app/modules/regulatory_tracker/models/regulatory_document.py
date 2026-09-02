"""RegulatoryDocument ORM model."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel


class RegulatoryDocument(BaseModel):
    """法规文档主表"""

    __tablename__ = "regulatory_documents"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "channel_id", "document_id", name="uq_reg_docs_src_ch_doc"
        ),
        Index("ix_regulatory_documents_source_site_code", "source_site_code"),
        Index("ix_regulatory_documents_capture_date", "capture_date"),
        Index("ix_regulatory_documents_filter_status", "filter_status"),
        Index("ix_regulatory_documents_content_hash", "content_hash"),
        {"schema": "regulatory_tracker"},
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulatory_tracker.data_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulatory_tracker.data_channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="文档唯一标识，如 zdyzIdCODE"
    )
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    publish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status_text: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="状态，如 颁布"
    )
    classification: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="分类，如 生物制品、化学药品"
    )
    source_site_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="来源网站编码"
    )
    source_site_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="来源网站名称"
    )
    source_url: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="来源页面原始链接"
    )
    version_text: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="版本号文本"
    )
    effective_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="生效日期"
    )
    summary_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="法规内容总结"
    )
    capture_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="抓取日期"
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="正文内容哈希"
    )
    filter_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="过滤状态"
    )
    filter_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="过滤原因"
    )
    original_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    first_found_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # AI analysis fields
    ai_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="AI 生成的文档摘要"
    )
    ai_key_points: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="AI 提取的关键要点"
    )
    ai_relevance_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="AI 评估的相关性评分 (0-1)"
    )
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="AI 分析完成时间"
    )
    ai_analysis_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="AI 分析状态: pending/completed/failed"
    )
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    source = relationship("DataSource", back_populates="documents")
    channel = relationship("DataChannel", back_populates="documents")
