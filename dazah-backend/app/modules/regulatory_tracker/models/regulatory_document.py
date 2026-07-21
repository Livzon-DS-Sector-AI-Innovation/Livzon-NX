"""RegulatoryDocument ORM model."""

import uuid
from datetime import date, datetime
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, UniqueConstraint, Text, Float, text
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.shared.base_model import BaseModel


class RegulatoryDocument(BaseModel):
    """法规文档主表"""

    __tablename__ = "regulatory_documents"
    __table_args__ = (
        UniqueConstraint("source_id", "channel_id", "document_id", name="uq_reg_docs_src_ch_doc"),
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
    original_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_new: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
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
    ai_key_points: Mapped[dict | None] = mapped_column(
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
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    source = relationship("DataSource", back_populates="documents")
    channel = relationship("DataChannel", back_populates="documents")
