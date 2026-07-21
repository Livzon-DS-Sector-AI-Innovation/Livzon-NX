"""Schemas for deviation conversational AI session."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.quality.schemas.quality_ai import QualityAiApplicableField


class DeviationAiSessionAttachmentOut(BaseModel):
    id: uuid.UUID
    file_name: str
    file_type: str
    file_size: int
    parse_status: str
    parse_error: str | None = None
    parsed_summary: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DeviationAiSessionResultPayload(BaseModel):
    summary: str = ""
    risk_level: str = ""
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    structured_fields: dict[str, str] = Field(default_factory=dict)
    disclaimer: str | None = None
    applicable_fields: list[QualityAiApplicableField] = Field(default_factory=list)


class DeviationAiSessionOut(BaseModel):
    id: uuid.UUID
    deviation_id: uuid.UUID
    supplement_text: str
    status: str
    error_message: str | None = None
    attachments: list[DeviationAiSessionAttachmentOut] = Field(default_factory=list)
    deviation_analysis_payload: DeviationAiSessionResultPayload | None = None
    capa_suggestion_payload: DeviationAiSessionResultPayload | None = None
    last_generated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateDeviationAiSessionRequest(BaseModel):
    supplement_text: str = ""


class ApplyDeviationAiSessionRequest(BaseModel):
    section: str
    field_keys: list[str] = Field(default_factory=list)
