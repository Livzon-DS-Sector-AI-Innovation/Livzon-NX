"""CAPA ORM models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class CAPA(BaseModel):
    __tablename__ = "capas"
    __table_args__ = {"schema": "quality"}

    capa_code: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", server_default="draft"
    )
    deviation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    root_cause_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    non_conformity_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    capa_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    capa_items: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    executors: Mapped[list[Any] | None] = mapped_column(ARRAY(Text), nullable=True)
    expected_completion_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    qa_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    qa_review_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    qa_review_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    q_head_approver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    q_head_approval_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    q_head_approval_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_tracks: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    dept_head_confirmations: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    evaluation_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_target: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evaluation_confirmer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    evaluation_confirm_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closure_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closure_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    report_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_versions: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    returned_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reporter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qa_confirmer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qa_confirm_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    root_cause_attachments: Mapped[list[Any] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    reason_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    affected_product: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
