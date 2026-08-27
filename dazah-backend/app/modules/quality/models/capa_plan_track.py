"""CAPA plan track ORM model."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class CapaPlanTrack(BaseModel):
    __tablename__ = "capa_plan_tracks"
    __table_args__ = {"schema": "quality"}

    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    capa_code: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_content: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    department_head: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department_head_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    progress: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reminder_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", server_default="pending"
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
