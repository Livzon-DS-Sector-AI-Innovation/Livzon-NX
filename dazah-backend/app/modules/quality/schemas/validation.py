"""Validation Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class ValidationListItem(BaseModel):
    id: uuid.UUID
    validation_type: str
    record_code: str
    title: str
    status: str | None = None
    department: str | None = None
    equipment_code: str | None = None
    product_codes: list[str] | None = None
    planned_end_date: date | None = None
    # 设备确认/工艺验证/清洁验证/其他验证 专属字段
    group_chat: str | None = None
    participants: str | None = None
    owner_name: str | None = None
    plan_name: str | None = None
    plan_code: str | None = None
    drafted_at: date | None = None
    approved_at: date | None = None
    report_no: str | None = None
    drafted_at_1: date | None = None
    approved_at_1: date | None = None
    revalidation_cycle_years: int | None = None
    created_at: datetime
    updated_at: datetime

class ValidationDetail(ValidationListItem):
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class ValidationExecutionListItem(BaseModel):
    id: uuid.UUID
    master_validation_id: uuid.UUID
    title: str
    status: str | None = None
    department: str | None = None
    product_codes: list[str] | None = None
    group_chat: str | None = None
    participants: str | None = None
    owner_name: str | None = None
    plan_name: str | None = None
    plan_code: str | None = None
    drafted_at: date | None = None
    approved_at: date | None = None
    report_no: str | None = None
    drafted_at_1: date | None = None
    approved_at_1: date | None = None
    revalidation_cycle_years: int | None = None
    created_at: datetime
    updated_at: datetime


class UpdateValidationExecutionRequest(BaseModel):
    group_chat: str | None = None
    participants: str | None = None
    owner_name: str | None = None
    plan_name: str | None = None
    plan_code: str | None = None
    drafted_at: date | None = None
    approved_at: date | None = None
    report_no: str | None = None
    drafted_at_1: date | None = None
    approved_at_1: date | None = None
    revalidation_cycle_years: int | None = None


class CreateValidationRequest(BaseModel):
    validation_type: str
    record_code: str
    title: str
    status: str | None = None
    department: str | None = None
    equipment_code: str | None = None
    product_codes: list[str] | None = None
    planned_end_date: date | None = None
    # 设备确认/工艺验证/清洁验证/其他验证 专属字段
    group_chat: str | None = None
    participants: str | None = None
    owner_name: str | None = None
    plan_name: str | None = None
    plan_code: str | None = None
    drafted_at: date | None = None
    approved_at: date | None = None
    report_no: str | None = None
    drafted_at_1: date | None = None
    approved_at_1: date | None = None
    revalidation_cycle_years: int | None = None


class UpdateValidationRequest(BaseModel):
    validation_type: str | None = None
    record_code: str | None = None
    title: str | None = None
    status: str | None = None
    department: str | None = None
    equipment_code: str | None = None
    product_codes: list[str] | None = None
    planned_end_date: date | None = None
    # 设备确认/工艺验证/清洁验证/其他验证 专属字段
    group_chat: str | None = None
    participants: str | None = None
    owner_name: str | None = None
    plan_name: str | None = None
    plan_code: str | None = None
    drafted_at: date | None = None
    approved_at: date | None = None
    report_no: str | None = None
    drafted_at_1: date | None = None
    approved_at_1: date | None = None
    revalidation_cycle_years: int | None = None
