"""Validation record ORM model."""

from __future__ import annotations

from datetime import date

from sqlalchemy import ARRAY, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ValidationRecord(BaseModel):
    __tablename__ = "validation_records"
    __table_args__ = {"schema": "quality"}

    record_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    equipment_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_codes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 设备确认/工艺验证/清洁验证/其他验证 专属字段
    group_chat: Mapped[str | None] = mapped_column(String(255), nullable=True)
    participants: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plan_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    drafted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    report_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    drafted_at_1: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_at_1: Mapped[date | None] = mapped_column(Date, nullable=True)
    revalidation_cycle_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
