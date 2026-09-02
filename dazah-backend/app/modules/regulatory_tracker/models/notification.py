"""Notification models for regulatory tracker updates."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class RegulatoryTrackerNotificationSetting(BaseModel):
    """法规跟踪更新推送配置。"""

    __tablename__ = "notification_settings"
    __table_args__ = (
        Index(
            "ix_regulatory_tracker_notification_settings_recipient_open_id",
            "recipient_open_id",
        ),
        {"schema": "regulatory_tracker"},
    )

    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否启用每日自动抓取推送",
    )
    recent_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=7,
        server_default="7",
        comment="自动抓取最近天数窗口",
    )
    recipient_open_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="接收人飞书 open_id",
    )
    recipient_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="接收人姓名快照",
    )
    recipient_department: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="接收人部门快照",
    )
    schedule_time: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="10:00",
        server_default="10:00",
        comment="固定执行时间",
    )


class RegulatoryTrackerNotificationRecord(BaseModel):
    """法规更新推送发送记录。"""

    __tablename__ = "notification_records"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "recipient_open_id",
            "content_hash",
            name="uq_regulatory_tracker_notification_record",
        ),
        Index(
            "ix_regulatory_tracker_notification_records_document_id",
            "document_id",
        ),
        Index(
            "ix_regulatory_tracker_notification_records_notified_at",
            "notified_at",
        ),
        {"schema": "regulatory_tracker"},
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="法规文档ID快照",
    )
    recipient_open_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="接收人飞书 open_id",
    )
    recipient_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="接收人姓名快照",
    )
    content_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="推送时文档内容哈希",
    )
    document_title: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="法规标题快照",
    )
    source_site_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="来源网站快照",
    )
    publish_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="发布日期快照",
    )
    source_url: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="来源网址快照",
    )
    summary_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="推送摘要快照",
    )
    trigger_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="daily_auto_sync",
        server_default="daily_auto_sync",
        comment="触发类型",
    )
    notified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="发送时间",
    )
