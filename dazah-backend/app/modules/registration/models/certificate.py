"""Certificate management ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class RegistrationCertificateEntry(BaseModel):
    """注册证书台账记录表。"""

    __tablename__ = "certificate_entries"
    __table_args__ = (
        Index("ix_registration_certificate_entries_sheet_key", "sheet_key"),
        Index(
            "ix_registration_certificate_entries_certificate_name", "certificate_name"
        ),
        Index("ix_registration_certificate_entries_issue_date", "issue_date"),
        {"schema": "registration"},
    )

    sheet_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="子表键")
    sheet_name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="子表名称"
    )
    sheet_title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="子表标题"
    )
    source_sequence: Mapped[int | None] = mapped_column(
        nullable=True, comment="来源表格序号"
    )
    certificate_name: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="证照名称"
    )
    acceptance_number: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="受理号"
    )
    approval_number: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="批件号"
    )
    certificate_number: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="证书编号/编号"
    )
    issuing_authority: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="发证机关"
    )
    issue_date: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="发证日期"
    )
    validity_period: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="有效期/复验期"
    )
    expiry_date: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="到期日期"
    )
    product_scope: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="产品范围"
    )
    quality_standard: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="质量标准"
    )
    page_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="页数"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class RegistrationCertificateReminderSetting(BaseModel):
    """证书到期提醒配置。"""

    __tablename__ = "certificate_reminder_settings"
    __table_args__ = (
        Index(
            "ix_registration_certificate_reminder_settings_recipient_open_id",
            "recipient_open_id",
        ),
        {"schema": "registration"},
    )

    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否启用自动提醒",
    )
    reminder_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=90,
        server_default="90",
        comment="提前提醒天数",
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


class RegistrationCertificateReminderNotification(BaseModel):
    """证书到期提醒发送记录。"""

    __tablename__ = "certificate_reminder_notifications"
    __table_args__ = (
        UniqueConstraint(
            "entry_id",
            "recipient_open_id",
            "reminder_days",
            name="uq_registration_certificate_reminder_notification",
        ),
        Index(
            "ix_registration_certificate_reminder_notifications_entry_id",
            "entry_id",
        ),
        {"schema": "registration"},
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
        comment="证书记录ID",
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
    reminder_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="提醒提前天数",
    )
    expiry_date: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="证书到期日期快照",
    )
    notified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="发送时间",
    )
