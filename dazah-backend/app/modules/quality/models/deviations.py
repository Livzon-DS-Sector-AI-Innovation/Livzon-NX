"""Deviation ORM models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class Deviation(BaseModel):
    __tablename__ = "deviations"
    __table_args__ = {"schema": "quality"}

    deviation_code: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discovery_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    discovery_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovery_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", server_default="draft"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    immediate_actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    handler: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discoverer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    root_cause_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    investigation_records: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    review_opinions: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    attachments: Mapped[list[Any] | None] = mapped_column(ARRAY(Text), nullable=True)
    final_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    returned_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    needs_cross_dept_review: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=True, server_default="true"
    )
    cross_dept_reviewers: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    affected_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    batch_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_versions: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    has_occurred_before: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    previous_occurrence_code: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="曾发生偏差编号（偏差是否曾发生=是时填写）"
    )
    material_disposition: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    investigation_completed_at: Mapped[datetime | None] = mapped_column(
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
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="删除操作人"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="删除时间"
    )
