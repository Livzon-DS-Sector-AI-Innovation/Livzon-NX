"""偏差工作台 Pydantic schemas。"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeviationWorkbenchAttachmentIn(BaseModel):
    """工作台附件描述（由上传接口返回后随 analyze 提交）。"""

    id: str
    file_name: str
    storage_key: str
    content_type: str | None = None
    file_size: int | None = None
    converted: bool = False
    converted_md_key: str | None = None
    asset_keys: list[str] = Field(default_factory=list)


class DeviationWorkbenchAttachmentOut(BaseModel):
    id: str
    file_name: str
    url: str = ""
    content_type: str | None = None
    file_size: int | None = None
    converted: bool = False
    uploaded_at: datetime | None = None


class DeviationWorkbenchSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_system_prompt: str
    updated_at: datetime | None = None


class UpdateDeviationWorkbenchSettingsRequest(BaseModel):
    report_system_prompt: str = Field(min_length=1)


class DeviationWorkbenchReportListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    source_type: str
    deviation_summary: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DeviationWorkbenchReportDetail(DeviationWorkbenchReportListItem):
    source_record_id: str | None = None
    manual_text: str | None = None
    attachments: list[DeviationWorkbenchAttachmentOut] = Field(default_factory=list)
    context_snapshot: dict[str, Any] | None = None
    report_payload: dict[str, Any] | None = None
    report_md: str | None = None
    model_name: str | None = None


class CreateDeviationWorkbenchRequest(BaseModel):
    source_type: str = Field(default="manual", pattern="^(report_record|manual)$")
    source_record_id: str | None = None
    manual_text: str | None = None
    affected_items: str | None = None
    supplement_text: str | None = None
    attachments: list[DeviationWorkbenchAttachmentIn] = Field(default_factory=list)
