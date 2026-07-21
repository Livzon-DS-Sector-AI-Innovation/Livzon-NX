"""Deviation investigation push record ORM model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class DeviationInvestigationPushRecord(BaseModel):
    __tablename__ = "deviation_investigation_push_records"
    __table_args__ = {"schema": "quality"}

    deviation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    deviation_code: Mapped[str] = mapped_column(String(255), nullable=False)
    push_round: Mapped[str] = mapped_column(String(50), nullable=False)
    investigation_report_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department_head: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department_head_result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department_head_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    qa_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qa_result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    qa_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    qa_head_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qa_head_result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    qa_head_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    feishu_base_table_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feishu_base_record_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )
    feishu_sync_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    feishu_last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    feishu_last_sync_direction: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    feishu_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    feishu_source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
