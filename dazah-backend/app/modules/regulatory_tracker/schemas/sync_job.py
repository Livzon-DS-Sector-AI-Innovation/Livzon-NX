"""SyncJob schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SyncJobCreate(BaseModel):
    source_id: uuid.UUID
    channel_id: uuid.UUID
    job_type: str


class SyncJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    channel_id: uuid.UUID
    job_type: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str
    total_pages: int | None = None
    checked_count: int
    new_count: int
    updated_count: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class SyncJobPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sync_job_id: uuid.UUID
    page_number: int
    page_size: int
    total_records_on_page: int
    new_records: int
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
