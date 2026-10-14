"""Private platform feedback and bounded screenshot attachments."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel


class UserFeedback(BaseModel):
    __tablename__ = "user_feedback"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'resolved')", name="ck_feedback_status"
        ),
        Index("ix_feedback_owner_created", "created_by", "created_at"),
        Index("ix_feedback_status_created", "status", "created_at"),
        {"schema": "core"},
    )

    reporter_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    page_path: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    reply: Mapped[str] = mapped_column(Text, default="", server_default="")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    screenshots: Mapped[list[FeedbackScreenshot]] = relationship(lazy="raise")


class FeedbackScreenshot(BaseModel):
    __tablename__ = "feedback_screenshots"
    __table_args__ = ({"schema": "core"},)

    feedback_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.user_feedback.id"), index=True
    )
    content_type: Mapped[str] = mapped_column(String(30))
    # Never load screenshot bytes while listing feedback.
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
