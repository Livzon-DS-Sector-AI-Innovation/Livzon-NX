from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FeedbackStatus = Literal["pending", "processing", "resolved"]


class FeedbackScreenshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    content_type: str


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    reporter_name: str
    description: str
    occurred_at: datetime
    page_path: str
    status: FeedbackStatus
    reply: str
    version: int
    created_at: datetime
    updated_at: datetime
    screenshots: list[FeedbackScreenshotResponse]


class FeedbackListResponse(BaseModel):
    items: list[FeedbackResponse]
    total: int
    pending_count: int
    page: int
    page_size: int


class FeedbackUpdate(BaseModel):
    status: FeedbackStatus
    reply: str = Field(default="", max_length=2000)
    version: int = Field(ge=1)
