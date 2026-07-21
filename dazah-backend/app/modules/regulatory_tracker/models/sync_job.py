"""SyncJob ORM model."""

import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.shared.base_model import BaseModel


class SyncJob(BaseModel):
    """同步任务表"""

    __tablename__ = "sync_jobs"
    __table_args__ = {"schema": "regulatory_tracker"}

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
    job_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="backfill/daily_sync/manual_sync/test"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="pending/running/success/partial_failed/failed"
    )
    total_pages: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="总页数"
    )
    checked_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    new_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    updated_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    source = relationship("DataSource", back_populates="sync_jobs")
    channel = relationship("DataChannel", back_populates="sync_jobs")
    pages = relationship("SyncJobPage", back_populates="sync_job", cascade="all, delete-orphan")
