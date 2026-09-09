"""Department weekly confirmation ORM model（部门联系人相关表已下线）."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


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
