"""Change control ORM model."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ChangeControl(BaseModel):
    __tablename__ = "quality_change_controls"
    __table_args__ = {"schema": "quality"}

    change_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="technical",
        server_default="technical",
        comment="台账类型: technical=技术变更, file=文件变更",
    )
    serial_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    change_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    applicant_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    change_object: Mapped[str | None] = mapped_column(String(255), nullable=True)
    change_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    application_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    execution_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closure_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="删除操作人"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="删除时间"
    )
