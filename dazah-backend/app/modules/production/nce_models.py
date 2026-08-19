"""非密事件与运行偏差 ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class NonConformingEvent(BaseModel):
    """非密事件与运行偏差表"""

    __tablename__ = "non_conforming_events"
    __table_args__ = (
        Index("ix_nce_event_time", "event_time"),
        Index("ix_nce_workshop", "workshop"),
        Index("ix_nce_event_type", "event_type"),
        {"schema": "production"},
    )

    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="发生时间"
    )
    restore_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="恢复正常时间"
    )
    impact_duration: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="影响时间（自动计算）"
    )
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="事件类型"
    )
    workshop: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="车间"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="事件描述"
    )
    impact_scope: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="影响范围"
    )
    action_taken: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="处理措施"
    )
    remarks: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注"
    )


class NCEBatchLink(BaseModel):
    """非密事件与发酵批次关联表"""

    __tablename__ = "nce_batch_links"
    __table_args__ = (
        Index("ix_nce_links_nce_id", "nce_id"),
        Index("ix_nce_links_batch_id", "batch_id"),
        {"schema": "production"},
    )

    nce_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production.non_conforming_events.id"), nullable=False, comment="非密事件ID"
    )
    batch_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production.fermentation_records.id"), nullable=False, comment="发酵批次ID"
    )
