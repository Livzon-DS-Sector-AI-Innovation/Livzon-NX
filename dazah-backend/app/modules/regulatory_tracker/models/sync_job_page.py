"""SyncJobPage ORM model."""

import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.shared.base_model import BaseModel


class SyncJobPage(BaseModel):
    """同步任务分页记录表"""

    __tablename__ = "sync_job_pages"
    __table_args__ = {"schema": "regulatory_tracker"}

    sync_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulatory_tracker.sync_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="页码"
    )
    page_size: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="10", comment="每页条数"
    )
    total_records_on_page: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="本页记录数"
    )
    new_records: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="本页新增记录数"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="pending/synced/failed"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    sync_job = relationship("SyncJob", back_populates="pages")
