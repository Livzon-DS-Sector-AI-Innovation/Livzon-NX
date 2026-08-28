"""RegulatoryDocument schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class RegulatoryDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    channel_id: uuid.UUID
    document_id: str
    title: str
    publish_date: date | None = None
    status_text: str | None = None
    classification: str | None = None
    original_url: str | None = None
    is_new: bool
    is_read: bool
    ai_summary: str | None = None
    ai_key_points: list[str] | None = None
    ai_relevance_score: float | None = None
    ai_analyzed_at: datetime | None = None
    ai_analysis_status: str | None = None
    first_found_at: datetime
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
