"""Change action plan ORM model."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String, Text, Uuid, true
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ChangeActionPlan(BaseModel):
    __tablename__ = "quality_change_action_plans"
    __table_args__ = {"schema": "quality"}

    change_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    change_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    related_work: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    director_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    director_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delay_flag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delayed_deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
    )
    sync_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reminder_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    reminder_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    last_reminded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reminder_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reminder_confirmed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reminder_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
