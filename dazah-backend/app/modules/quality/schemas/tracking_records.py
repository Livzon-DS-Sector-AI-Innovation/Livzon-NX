"""Tracking record schemas for deviation investigations and CAPA plans."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator


class DeviationInvestigationPushRecordListItem(BaseModel):
    id: str | uuid.UUID
    local_record_id: uuid.UUID | None = None
    deviation_id: uuid.UUID | None = None
    deviation_code: str
    push_round: str
    investigation_report_url: str | None = None
    submitted_at: datetime | None = None
    submitter: str | None = None
    department_head: str | None = None
    department_head_result: str | None = None
    department_head_reviewed_at: datetime | None = None
    qa_name: str | None = None
    qa_result: str | None = None
    qa_reviewed_at: datetime | None = None
    qa_head_name: str | None = None
    qa_head_result: str | None = None
    qa_head_reviewed_at: datetime | None = None
    feishu_base_table_id: str | None = None
    feishu_base_record_id: str | None = None
    feishu_sync_status: str | None = "pending"
    feishu_last_sync_error: str | None = None
    feishu_last_sync_direction: str | None = None
    feishu_synced_at: datetime | None = None
    feishu_source_updated_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DeviationInvestigationPushRecordDetail(DeviationInvestigationPushRecordListItem):
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class CreateDeviationInvestigationPushRecordRequest(BaseModel):
    deviation_id: uuid.UUID | None = None
    deviation_code: str | None = None
    push_round: str
    investigation_report_url: str | None = None
    submitted_at: datetime | None = None
    submitter_open_id: str | None = None
    submitter: str | None = None
    department_head: str | None = None
    department_head_result: str | None = None
    department_head_reviewed_at: datetime | None = None
    qa_name: str | None = None
    qa_result: str | None = None
    qa_reviewed_at: datetime | None = None
    qa_head_name: str | None = None
    qa_head_result: str | None = None
    qa_head_reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_deviation_reference(self) -> "CreateDeviationInvestigationPushRecordRequest":
        if not self.deviation_id and not (self.deviation_code or "").strip():
            raise ValueError("deviation_id 和 deviation_code 至少提供一个")
        return self


class UpdateDeviationInvestigationPushRecordRequest(BaseModel):
    push_round: str | None = None
    investigation_report_url: str | None = None
    submitted_at: datetime | None = None
    submitter: str | None = None
    department_head: str | None = None
    department_head_result: str | None = None
    department_head_reviewed_at: datetime | None = None
    qa_name: str | None = None
    qa_result: str | None = None
    qa_reviewed_at: datetime | None = None
    qa_head_name: str | None = None
    qa_head_result: str | None = None
    qa_head_reviewed_at: datetime | None = None


class CapaPlanTrackListItem(BaseModel):
    id: uuid.UUID
    capa_id: uuid.UUID
    capa_code: str
    plan_content: str
    due_date: date | None = None
    owner_name: str | None = None
    owner_confirmed: bool
    department_head: str | None = None
    department_head_confirmed: bool
    progress: str | None = None
    reminder_status: str
    linked_capa_code: str | None = None
    feishu_base_table_id: str | None = None
    feishu_base_record_id: str | None = None
    feishu_sync_status: str | None = "pending"
    feishu_last_sync_error: str | None = None
    feishu_last_sync_direction: str | None = None
    feishu_synced_at: datetime | None = None
    feishu_source_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CapaPlanTrackDetail(CapaPlanTrackListItem):
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class CreateCapaPlanTrackRequest(BaseModel):
    capa_id: uuid.UUID
    plan_content: str
    due_date: date | None = None
    owner_name: str | None = None
    owner_confirmed: bool = False
    department_head: str | None = None
    department_head_confirmed: bool = False
    progress: str | None = None
    reminder_status: str = "pending"


class UpdateCapaPlanTrackRequest(BaseModel):
    plan_content: str | None = None
    due_date: date | None = None
    owner_name: str | None = None
    owner_confirmed: bool | None = None
    department_head: str | None = None
    department_head_confirmed: bool | None = None
    progress: str | None = None
    reminder_status: str | None = None
