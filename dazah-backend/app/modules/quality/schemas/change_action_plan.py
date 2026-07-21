"""Change action plan Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ChangeActionPlanListItem(BaseModel):
    id: uuid.UUID
    change_id: uuid.UUID | None = None
    change_code: str
    project_name: str
    related_work: str | None = None
    owner_name: str | None = None
    owner_user_id: str | None = None
    director_name: str | None = None
    director_user_id: str | None = None
    deadline_date: date | None = None
    status: str | None = None
    delay_flag: str | None = None
    delayed_deadline_date: date | None = None
    feishu_record_id: str | None = None
    sync_status: str
    sync_error: str | None = None
    last_synced_at: datetime | None = None
    reminder_enabled: bool = True
    reminder_status: str
    last_reminded_at: datetime | None = None
    reminder_confirmed_at: datetime | None = None
    reminder_confirmed_by: str | None = None
    reminder_message_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChangeActionPlanDetail(ChangeActionPlanListItem):
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class ChangeActionPlanPersonOption(BaseModel):
    open_id: str
    name: str
    user_id: str | None = None
    mobile: str | None = None
    email: str | None = None
    job_title: str | None = None


class CreateChangeActionPlanRequest(BaseModel):
    change_id: uuid.UUID | None = None
    change_code: str
    project_name: str
    related_work: str | None = None
    owner_name: str | None = None
    owner_user_id: str | None = None
    director_name: str | None = None
    director_user_id: str | None = None
    deadline_date: date | None = None
    status: str | None = None
    delay_flag: str | None = None
    delayed_deadline_date: date | None = None
    reminder_enabled: bool = True


class UpdateChangeActionPlanRequest(BaseModel):
    change_id: uuid.UUID | None = None
    change_code: str | None = None
    project_name: str | None = None
    related_work: str | None = None
    owner_name: str | None = None
    owner_user_id: str | None = None
    director_name: str | None = None
    director_user_id: str | None = None
    deadline_date: date | None = None
    status: str | None = None
    delay_flag: str | None = None
    delayed_deadline_date: date | None = None
    reminder_enabled: bool | None = None


class ChangeActionPlanSyncResult(BaseModel):
    synced: int
    failed: int


class ChangeActionPlanReminderRunResult(BaseModel):
    scanned: int
    reminded: int
    failed: int


class ChangeActionPlanReminderConfirmResult(BaseModel):
    success: bool
    reminder_status: str
    reminder_confirmed_at: datetime | None = None
    reminder_confirmed_by: str | None = None
