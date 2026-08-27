"""Quality-owned read-only Feishu mirror models.

These tables are intentionally separate from the existing bidirectional
quality_feishu_* settings and business synchronization tables.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class QualityFeishuReadSourceRoot(BaseModel):
    __tablename__ = "feishu_read_source_roots"
    __table_args__ = (
        UniqueConstraint(
            "config_id",
            "source_type",
            "root_token",
            "is_deleted",
            name="uq_quality_feishu_read_source_root",
        ),
        Index("ix_quality_feishu_read_roots_config", "config_id", "is_active"),
        {"schema": "quality"},
    )

    config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    root_token: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    discovery_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    last_discovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    discovery_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class QualityFeishuReadResource(BaseModel):
    __tablename__ = "feishu_read_resources"
    __table_args__ = (
        UniqueConstraint(
            "app_token",
            "table_id",
            "is_deleted",
            name="uq_quality_feishu_read_resource",
        ),
        Index("ix_quality_feishu_read_resources_root", "source_root_id"),
        {"schema": "quality"},
    )

    source_root_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    app_token: Mapped[str] = mapped_column(String(256), nullable=False)
    table_id: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_mirror_version: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    last_complete_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class QualityFeishuReadField(BaseModel):
    __tablename__ = "feishu_read_fields"
    __table_args__ = (
        UniqueConstraint(
            "resource_id", "field_id", "is_deleted", name="uq_quality_feishu_read_field"
        ),
        Index("ix_quality_feishu_read_fields_resource", "resource_id", "sort_order"),
        {"schema": "quality"},
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_id: Mapped[str] = mapped_column(String(256), nullable=False)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[str] = mapped_column(String(64), nullable=False)
    property: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class QualityFeishuReadRecord(BaseModel):
    __tablename__ = "feishu_read_records"
    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "record_id",
            "mirror_version",
            name="uq_quality_feishu_read_record_version",
        ),
        Index(
            "ix_quality_feishu_read_records_page",
            "resource_id",
            "mirror_version",
            "record_id",
        ),
        {"schema": "quality"},
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_id: Mapped[str] = mapped_column(String(256), nullable=False)
    mirror_version: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    raw_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    normalized_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    source_created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_modified_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )


class QualityFeishuReadPageBinding(BaseModel):
    __tablename__ = "feishu_read_page_bindings"
    __table_args__ = (
        UniqueConstraint(
            "page_key",
            "resource_id",
            "is_deleted",
            name="uq_quality_feishu_read_page_binding",
        ),
        Index("ix_quality_feishu_read_bindings_page", "page_key", "sort_order"),
        {"schema": "quality"},
    )

    page_key: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tab_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    visible_field_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )


class QualityFeishuReadSyncRun(BaseModel):
    __tablename__ = "feishu_read_sync_runs"
    __table_args__ = (
        Index("ix_quality_feishu_read_runs_resource", "resource_id", "started_at"),
        {"schema": "quality"},
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mirror_version: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running", server_default="running"
    )
    expected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
