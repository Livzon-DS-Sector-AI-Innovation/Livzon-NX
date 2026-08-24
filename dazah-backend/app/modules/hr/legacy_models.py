"""Compatibility ORM models for the former HR turnover tables.

The migrated HR implementation keeps employee/offboarding workflows in the
current tables, while the turnover analysis still reads the historical
onboarding/departure snapshots.  These narrow models retain those table names
and the fields used by the analysis without making the legacy tables part of
new HR writes.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Date, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class DepartureRecord(BaseModel):
    __tablename__ = "departure_records"
    __table_args__ = (
        Index("ix_departure_department", "department"),
        Index("ix_departure_offboarding_date", "offboarding_date"),
        Index("ix_departure_feishu_record_id", "feishu_record_id"),
        {"schema": "hr"},
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[str] = mapped_column(String(64), nullable=False)
    team: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[str] = mapped_column(String(64), nullable=False)
    job_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    livo_entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    factory_entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    work_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    offboarding_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    company_tenure_at_leave: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    education: Mapped[str | None] = mapped_column(String(16), nullable=True)
    school: Mapped[str | None] = mapped_column(String(128), nullable=True)
    major: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(16), nullable=True)
    id_card: Mapped[str | None] = mapped_column(String(18), nullable=True)
    native_place: Mapped[str | None] = mapped_column(String(64), nullable=True)
    household_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    political_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    emergency_contact_relation: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    bank_account: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transfer_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    offboarding_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="辞职", server_default="辞职"
    )
    offboarding_reason: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    offboarding_reason_2: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    offboarding_remarks: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    feishu_record_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    feishu_synced_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class OnboardingRecord(BaseModel):
    __tablename__ = "onboarding_records"
    __table_args__ = (
        Index("ix_onboarding_employee_number", "employee_number"),
        Index("ix_onboarding_department", "department"),
        Index("ix_onboarding_hire_date", "hire_date"),
        Index("ix_onboarding_feishu_record_id", "feishu_record_id"),
        {"schema": "hr"},
    )

    seq_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_number: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department: Mapped[str] = mapped_column(String(64), nullable=False)
    team: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[str] = mapped_column(String(64), nullable=False)
    job_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_employed: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    factory_entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    livo_entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    work_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    birth_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    birth_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contract_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_start_2: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end_2: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_start_3: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end_3: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_start_4: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end_4: Mapped[date | None] = mapped_column(Date, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    factory_tenure: Mapped[str | None] = mapped_column(String(32), nullable=True)
    company_tenure: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hire_month: Mapped[str | None] = mapped_column(String(16), nullable=True)
    school: Mapped[str | None] = mapped_column(String(128), nullable=True)
    education: Mapped[str | None] = mapped_column(String(16), nullable=True)
    major: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(16), nullable=True)
    id_card: Mapped[str | None] = mapped_column(String(18), nullable=True)
    id_card_expiry: Mapped[str | None] = mapped_column(String(32), nullable=True)
    id_card_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    household_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    political_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    emergency_contact_relation: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    bank_account: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bank_account_location: Mapped[str | None] = mapped_column(String(32), nullable=True)
    training_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transfer_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    feishu_record_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    feishu_synced_at: Mapped[date | None] = mapped_column(Date, nullable=True)
