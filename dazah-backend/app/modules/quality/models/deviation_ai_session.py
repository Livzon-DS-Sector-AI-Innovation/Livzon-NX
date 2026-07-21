"""Deviation conversational AI session models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class DeviationAiSession(BaseModel):
    __tablename__ = "deviation_ai_sessions"
    __table_args__ = (
        UniqueConstraint(
            "deviation_id",
            name="uq_quality_deviation_ai_sessions_deviation_id",
        ),
        {"schema": "quality"},
    )

    deviation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    supplement_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    attachment_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    deviation_analysis_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    capa_suggestion_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="idle",
        server_default="idle",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class DeviationAiSessionAttachment(BaseModel):
    __tablename__ = "deviation_ai_session_attachments"
    __table_args__ = {"schema": "quality"}

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
