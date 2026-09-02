"""历史偏差 Pydantic schemas。"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HistoricalDeviationAttachmentOut(BaseModel):
    id: str
    file_name: str
    url: str = ""
    content_type: str | None = None
    file_size: int | None = None
    converted: bool = False
    uploaded_at: datetime | None = None
    uploaded_by: str | None = None


class HistoricalDeviationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    deviation_event: str | None = None
    deviation_content: str | None = None
    direct_cause: str | None = None
    root_cause: str | None = None
    investigation_conclusion: str | None = None
    attachment_count: int = 0
    created_at: datetime
    updated_at: datetime


class HistoricalDeviationDetail(HistoricalDeviationListItem):
    attachments: list[HistoricalDeviationAttachmentOut] = Field(default_factory=list)
    ai_extract_payload: dict[str, Any] | None = None
    remark: str | None = None


class CreateHistoricalDeviationRequest(BaseModel):
    deviation_event: str | None = None
    deviation_content: str | None = None
    direct_cause: str | None = None
    root_cause: str | None = None
    investigation_conclusion: str | None = None
    remark: str | None = None


class UpdateHistoricalDeviationRequest(CreateHistoricalDeviationRequest):
    pass


class HistoricalDeviationAiExtractResult(BaseModel):
    deviation_event: str | None = None
    deviation_content: str | None = None
    direct_cause: str | None = None
    root_cause: str | None = None
