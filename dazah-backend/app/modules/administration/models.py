"""Administration module ORM models.

行政管理模块当前承载「烟酒礼品管理」的飞书只读镜像：

- ``administration.feishu_configs``：行政模块飞书应用凭证（secret 加密存储）。
- ``administration.feishu_read_*``：通用只读镜像六表（入口/数据表/字段/记录/
  页面绑定/同步运行），由平台层 ``ModuleFeishuReadMirrorService`` 读写。
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class AdministrationFeishuConfig(BaseModel):
    """行政模块飞书应用配置（允许多行，运行时取最近更新的激活行）。"""

    __tablename__ = "feishu_configs"
    __table_args__ = (
        Index("ix_administration_feishu_configs_is_active", "is_active"),
        {"schema": "administration"},
    )

    config_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="行政管理飞书配置",
        server_default="行政管理飞书配置",
    )
    app_id: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default=""
    )
    encrypted_app_secret: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Shanghai",
        server_default="Asia/Shanghai",
    )
    daily_sync_time: Mapped[str] = mapped_column(
        String(16), nullable=False, default="02:00", server_default="02:00"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class AdministrationFeishuReadSourceRoot(BaseModel):
    """飞书数据入口（Wiki 树节点或多维表格 Base）。"""

    __tablename__ = "feishu_read_source_roots"
    __table_args__ = (
        # 软删除唯一用部分唯一索引；is_deleted 不得进 UniqueConstraint（规范）
        Index(
            "uq_administration_feishu_read_source_root",
            "config_id",
            "source_type",
            "root_token",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_administration_feishu_read_roots_config", "config_id", "is_active"),
        {"schema": "administration"},
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


class AdministrationFeishuReadResource(BaseModel):
    """已发现的数据表（Base 内一张子表为一行）。"""

    __tablename__ = "feishu_read_resources"
    __table_args__ = (
        Index(
            "uq_administration_feishu_read_resource",
            "app_token",
            "table_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_administration_feishu_read_resources_root", "source_root_id"),
        {"schema": "administration"},
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


class AdministrationFeishuReadField(BaseModel):
    """数据表字段结构快照（每次同步刷新）。"""

    __tablename__ = "feishu_read_fields"
    __table_args__ = (
        Index(
            "uq_administration_feishu_read_field",
            "resource_id",
            "field_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_administration_feishu_read_fields_resource",
            "resource_id",
            "sort_order",
        ),
        {"schema": "administration"},
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


class AdministrationFeishuReadRecord(BaseModel):
    """数据表记录镜像（按 mirror_version 全量版本化）。"""

    __tablename__ = "feishu_read_records"
    __table_args__ = (
        # 记录按 mirror_version 版本化；同样用部分唯一索引，保持全库同一约定
        Index(
            "uq_administration_feishu_read_record_version",
            "resource_id",
            "record_id",
            "mirror_version",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_administration_feishu_read_records_page",
            "resource_id",
            "mirror_version",
            "record_id",
        ),
        {"schema": "administration"},
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


class AdministrationFeishuReadPageBinding(BaseModel):
    """页面 ↔ 数据表绑定（一个页面可绑多张表形成页签）。"""

    __tablename__ = "feishu_read_page_bindings"
    __table_args__ = (
        Index(
            "uq_administration_feishu_read_page_binding",
            "page_key",
            "resource_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_administration_feishu_read_bindings_page",
            "page_key",
            "sort_order",
        ),
        {"schema": "administration"},
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


class AdministrationFeishuReadSyncRun(BaseModel):
    """同步运行记录（含完整性校验结果）。"""

    __tablename__ = "feishu_read_sync_runs"
    __table_args__ = (
        Index(
            "ix_administration_feishu_read_runs_resource",
            "resource_id",
            "started_at",
        ),
        {"schema": "administration"},
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
