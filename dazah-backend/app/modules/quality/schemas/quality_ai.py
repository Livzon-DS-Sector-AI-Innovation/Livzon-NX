"""Quality AI schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QualityAiApplicableField(BaseModel):
    field_key: str
    label: str
    description: str | None = None


class QualityAiApplyRequest(BaseModel):
    field_keys: list[str] = Field(default_factory=list)


class QualityAiAnalysisLogOut(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    analysis_type: str
    input_snapshot: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    model_name: str
    status: str
    error_message: str | None = None
    is_applied: bool
    created_at: datetime
    created_by: uuid.UUID | None = None
    applied_at: datetime | None = None
    applied_by: uuid.UUID | None = None
    applicable_fields: list[QualityAiApplicableField] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
