"""Attachment review ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class AttachmentReview(BaseModel):
    __tablename__ = "attachment_reviews"
    __table_args__ = {"schema": "quality"}

    deviation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    capa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    attachment_url: Mapped[str] = mapped_column(String(500), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    review_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
