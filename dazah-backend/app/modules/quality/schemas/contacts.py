"""Department contacts Pydantic schemas."""


import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DepartmentContactOut(BaseModel):
    id: uuid.UUID
    name: str | None = None
    department: str
    enterprise_email: str | None = None
    open_id: str | None = None
    department_head_name: str | None = None
    department_head_enterprise_email: str | None = None
    department_head_open_id: str | None = None
    feishu_record_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateDepartmentContactRequest(BaseModel):
    name: str
    department: str
    enterprise_email: str | None = None
    open_id: str | None = None
    department_head_name: str | None = None
    department_head_enterprise_email: str | None = None
    department_head_open_id: str | None = None
    feishu_record_id: str | None = None


class UpdateDepartmentContactRequest(BaseModel):
    name: str | None = None
    department: str | None = None
    enterprise_email: str | None = None
    open_id: str | None = None
    department_head_name: str | None = None
    department_head_enterprise_email: str | None = None
    department_head_open_id: str | None = None
    feishu_record_id: str | None = None


class DepartmentWeeklyConfirmationOut(BaseModel):
    id: uuid.UUID
    department: str
    week_key: str
    production_status: str
    deviation_status: str
    confirmed_by_id: uuid.UUID | None = None
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConfirmProductionStatusRequest(BaseModel):
    department: str
    week_key: str
    production_status: str
    deviation_status: str = "unsubmitted"
