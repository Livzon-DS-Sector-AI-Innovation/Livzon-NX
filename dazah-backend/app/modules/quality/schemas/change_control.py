"""Change control Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ChangeListItem(BaseModel):
    id: uuid.UUID
    serial_number: str | None = None
    change_code: str
    applicant_department: str | None = None
    change_object: str | None = None
    change_content: str | None = None
    impact_assessment: str | None = None
    change_level: str | None = None
    application_date: date | None = None
    planned_approval_date: date | None = None
    execution_date: date | None = None
    closure_date: date | None = None
    created_at: datetime
    updated_at: datetime
    action_plan_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ChangeDetail(ChangeListItem):
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class CreateChangeRequest(BaseModel):
    serial_number: str | None = None
    change_code: str | None = None
    applicant_department: str | None = None
    change_object: str | None = None
    change_content: str | None = None
    impact_assessment: str | None = None
    change_level: str | None = None
    application_date: date | None = None
    planned_approval_date: date | None = None
    execution_date: date | None = None
    closure_date: date | None = None


class UpdateChangeRequest(BaseModel):
    serial_number: str | None = None
    change_code: str | None = None
    applicant_department: str | None = None
    change_object: str | None = None
    change_content: str | None = None
    impact_assessment: str | None = None
    change_level: str | None = None
    application_date: date | None = None
    planned_approval_date: date | None = None
    execution_date: date | None = None
    closure_date: date | None = None
