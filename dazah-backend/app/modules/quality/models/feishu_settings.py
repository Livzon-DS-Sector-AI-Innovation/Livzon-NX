"""Quality Feishu settings models."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class QualityFeishuAppSettings(BaseModel):
    __tablename__ = "quality_feishu_app_settings"
    __table_args__ = {"schema": "quality"}

    app_id: Mapped[str] = mapped_column(String(100), nullable=False)
    app_secret: Mapped[str] = mapped_column(Text, nullable=False)
    app_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deviation_report_form_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deviation_investigation_push_form_url: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    oos_oot_report_form_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    oos_oot_investigation_push_form_url: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    last_test_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class QualityFeishuEntitySetting(BaseModel):
    __tablename__ = "quality_feishu_entity_settings"
    __table_args__ = {"schema": "quality"}

    entity_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    entity_name: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_group: Mapped[str] = mapped_column(String(100), nullable=False)
    app_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_table_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_table_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    enable_push_to_feishu: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    enable_pull_from_feishu: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    field_mappings: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
