"""Regulatory tracker ledger page schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class TrackerLedgerItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    capture_date: date | None = None
    title: str
    version_text: str | None = None
    publish_date: date | None = None
    effective_date: date | None = None
    summary_text: str | None = None
    source_url: str | None = None
    source_site_name: str | None = None
    is_new: bool
    ai_summary: str | None = None
    ai_analysis_status: str | None = None
    ai_analyzed_at: datetime | None = None


class TrackerLedgerDetailRead(TrackerLedgerItemRead):
    """Regulatory tracker ledger detail payload."""

    ai_summary: str | None = None
    ai_key_points: list[str] | None = None
    ai_relevance_score: float | None = None
    ai_analysis_status: str | None = None
    ai_analyzed_at: datetime | None = None


class TrackerLedgerPageRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[TrackerLedgerItemRead]
    total: int
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total_pages: int = Field(serialization_alias="totalPages")


class TrackerLedgerListResponse(BaseModel):
    code: int
    message: str
    data: TrackerLedgerPageRead


class TrackerLedgerDetailResponse(BaseModel):
    code: int
    message: str
    data: TrackerLedgerDetailRead | None
