"""Validation execution child record ORM models."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import ARRAY, Date, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ValidationExecutionRecordBase(BaseModel):
    __abstract__ = True

    master_validation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    product_codes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
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


class EquipmentQualificationRecord(ValidationExecutionRecordBase):
    __tablename__ = "equipment_qualification_records"
    __table_args__ = (
        UniqueConstraint(
            "master_validation_id",
            name="uq_equipment_qualification_master_validation_id",
        ),
        {"schema": "quality"},
    )


class ProcessValidationRecord(ValidationExecutionRecordBase):
    __tablename__ = "process_validation_records"
    __table_args__ = (
        UniqueConstraint(
            "master_validation_id", name="uq_process_validation_master_validation_id"
        ),
        {"schema": "quality"},
    )


class CleaningValidationRecord(ValidationExecutionRecordBase):
    __tablename__ = "cleaning_validation_records"
    __table_args__ = (
        UniqueConstraint(
            "master_validation_id", name="uq_cleaning_validation_master_validation_id"
        ),
        {"schema": "quality"},
    )


class OtherValidationRecord(ValidationExecutionRecordBase):
    __tablename__ = "other_validation_records"
    __table_args__ = (
        UniqueConstraint(
            "master_validation_id", name="uq_other_validation_master_validation_id"
        ),
        {"schema": "quality"},
    )
