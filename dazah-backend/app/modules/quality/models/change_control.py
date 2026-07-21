"""Change control ORM model."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ChangeControl(BaseModel):
    __tablename__ = "quality_change_controls"
    __table_args__ = {"schema": "quality"}

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
