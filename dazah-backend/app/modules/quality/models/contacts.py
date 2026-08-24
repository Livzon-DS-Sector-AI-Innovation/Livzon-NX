"""Department contacts ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class DepartmentContact(BaseModel):
    __tablename__ = "department_contacts"
    __table_args__ = {"schema": "quality"}

    name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    department: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    enterprise_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    open_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    department_head_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department_head_enterprise_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    department_head_open_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )


class DepartmentWeeklyConfirmation(BaseModel):
    __tablename__ = "department_weekly_confirmations"
    __table_args__ = (
        UniqueConstraint("department", "week_key", name="uq_dept_weekly_confirmation"),
        {"schema": "quality"},
    )

    department: Mapped[str] = mapped_column(String(255), nullable=False)
    week_key: Mapped[str] = mapped_column(String(20), nullable=False)
    production_status: Mapped[str] = mapped_column(String(20), nullable=False)
    deviation_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unsubmitted", server_default="unsubmitted"
    )
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
