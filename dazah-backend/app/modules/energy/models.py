"""Energy ORM models: device config, data collection, and collect logs."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as UUIDType  # noqa: N811

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class EnergyWikiBaseModel(BaseModel):
    """Energy integration entities keep audit UUIDs without database FKs.

    The project-wide BaseModel carries identity foreign keys for older tables.
    New energy ingestion tables deliberately override them because this module's
    integration records must remain deployable without cross-schema FK coupling.
    """

    __abstract__ = True

    created_by: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    updated_by: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class EnergyType(enum.StrEnum):
    ELECTRICITY = "electricity"
    WATER = "water"
    GAS = "gas"


class MonitorLevel(enum.StrEnum):
    NORMAL = "normal"
    IMPORTANT = "important"
    URGENT = "urgent"


class CollectStatus(enum.StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class EnergyDeviceConfig(BaseModel):
    """三方平台设备配置表"""

    __tablename__ = "energy_device_configs"
    __table_args__ = (
        UniqueConstraint(
            "platform_code",
            "platform_device_code",
            "is_deleted",
            name="uq_energy_device_config_platform_device",
        ),
        CheckConstraint(
            "energy_type IN ('electricity', 'water', 'gas')",
            name="ck_energy_device_config_energy_type",
        ),
        CheckConstraint(
            "monitor_level IN ('normal', 'important', 'urgent')",
            name="ck_energy_device_config_monitor_level",
        ),
        CheckConstraint(
            "collection_interval > 0",
            name="ck_energy_device_config_interval_positive",
        ),
        {"schema": "energy"},
    )

    platform_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="平台标识"
    )
    platform_device_code: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="三方平台设备/采集点编码"
    )
    device_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="设备名称"
    )
    energy_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="能源类型: electricity/water/gas"
    )
    api_endpoint: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="API 路径"
    )
    workshop: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="所属车间"
    )
    production_line: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="所属产线"
    )
    monitor_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="normal", comment="监控等级"
    )
    unit: Mapped[str] = mapped_column(String(20), nullable=False, comment="计量单位")
    collection_interval: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, comment="采集间隔(分钟)"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用采集"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class EnergyData(BaseModel):
    """能耗数据采集表"""

    __tablename__ = "energy_data"
    __table_args__ = (
        UniqueConstraint(
            "device_config_id",
            "timestamp",
            name="uq_energy_data_device_timestamp",
        ),
        {"schema": "energy"},
    )

    device_config_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="设备配置ID",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="数据时间点(小时粒度)",
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="能耗累计值"
    )
    unit: Mapped[str] = mapped_column(String(20), nullable=False, comment="计量单位")
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="实际采集时间",
    )
    platform_raw_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="原始返回数据"
    )


class EnergyCollectLog(BaseModel):
    """采集日志表"""

    __tablename__ = "energy_collect_logs"
    __table_args__ = ({"schema": "energy"},)

    platform_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="采集的平台"
    )
    collect_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="采集触发时间",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="状态: success/partial/failed"
    )
    device_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="应采集设备数"
    )
    success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="成功条数"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="错误信息"
    )


# ── 预警系统 ──


class AlertLevel(enum.StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class MonitorMetric(enum.StrEnum):
    INSTANT = "instant"
    DAILY_TOTAL = "daily_total"
    MONTHLY_TOTAL = "monthly_total"


class ThresholdType(enum.StrEnum):
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    EQUAL = "equal"


class NotifyFrequency(enum.StrEnum):
    FIRST = "first"
    EVERY = "every"
    DAILY_SUMMARY = "daily_summary"


class EffectiveTimeType(enum.StrEnum):
    ALL_DAY = "all_day"
    CUSTOM = "custom"


class AlertRecordStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    IGNORED = "ignored"


class EnergyAlertRule(BaseModel):
    """能耗预警规则表"""

    __tablename__ = "energy_alert_rules"
    __table_args__ = (
        CheckConstraint(
            "energy_type IN ('electricity', 'water', 'gas')",
            name="ck_energy_alert_rule_energy_type",
        ),
        CheckConstraint(
            "alert_level IN ('info', 'warning', 'critical', 'emergency')",
            name="ck_energy_alert_rule_alert_level",
        ),
        CheckConstraint(
            "monitor_metric IN ('instant', 'daily_total', 'monthly_total')",
            name="ck_energy_alert_rule_monitor_metric",
        ),
        CheckConstraint(
            "threshold_type IN ('greater_than', 'less_than', 'equal')",
            name="ck_energy_alert_rule_threshold_type",
        ),
        CheckConstraint(
            "notify_frequency IN ('first', 'every', 'daily_summary')",
            name="ck_energy_alert_rule_notify_frequency",
        ),
        CheckConstraint(
            "effective_time IN ('all_day', 'custom')",
            name="ck_energy_alert_rule_effective_time",
        ),
        {"schema": "energy"},
    )

    rule_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="规则名称"
    )
    rule_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="规则描述"
    )
    energy_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="能源类型"
    )
    monitor_metric: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="监控指标: instant/daily_total/monthly_total",
    )
    threshold_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="阈值类型"
    )
    threshold_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="阈值"
    )
    unit: Mapped[str] = mapped_column(String(20), nullable=False, comment="计量单位")
    alert_level: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="预警等级"
    )
    notify_method: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, comment="通知方式: email/sms/feishu"
    )
    notify_users: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, comment="通知用户列表"
    )
    notify_frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="first", comment="通知频率"
    )
    effective_time: Mapped[str] = mapped_column(
        String(20), nullable=False, default="all_day", comment="生效时段类型"
    )
    custom_time_start: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="自定义开始时间(HH:MM:SS)"
    )
    custom_time_end: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="自定义结束时间(HH:MM:SS)"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )


class EnergyAlertRecord(BaseModel):
    """预警记录表"""

    __tablename__ = "energy_alert_records"
    __table_args__ = (
        CheckConstraint(
            "alert_level IN ('info', 'warning', 'critical', 'emergency')",
            name="ck_energy_alert_record_alert_level",
        ),
        CheckConstraint(
            "status IN ('pending', 'processed', 'ignored')",
            name="ck_energy_alert_record_status",
        ),
        {"schema": "energy"},
    )

    rule_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("energy.energy_alert_rules.id", ondelete="CASCADE"),
        nullable=False,
        comment="预警规则ID",
    )
    device_config_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="关联设备配置ID",
    )
    energy_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="能源类型"
    )
    alert_level: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="预警等级"
    )
    trigger_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="触发值"
    )
    threshold_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, comment="阈值"
    )
    unit: Mapped[str] = mapped_column(String(20), nullable=False, comment="计量单位")
    alert_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="预警触发时间"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", comment="处理状态"
    )
    processed_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="处理人"
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="处理时间"
    )
    process_note: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="处理备注"
    )


# ── Wiki / Sheets read-only ingestion ─────────────────────────────


class EnergyFeishuConfig(EnergyWikiBaseModel):
    """The energy module's independent Feishu application settings."""

    __tablename__ = "feishu_configs"
    __table_args__ = (
        Index("ix_energy_feishu_configs_active", "is_active"),
        {"schema": "energy"},
    )

    config_name: Mapped[str] = mapped_column(
        String(128), nullable=False, default="能源 Wiki 数据源", comment="配置名称"
    )
    app_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书 App ID"
    )
    encrypted_app_secret: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="加密后的飞书 App Secret"
    )
    root_wiki_url: Mapped[str] = mapped_column(
        Text, nullable=False, comment="月度表父 Wiki 根链接"
    )
    root_wiki_token: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="解析后的 Wiki 根节点 token"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Shanghai", comment="同步时区"
    )
    daily_sync_time: Mapped[str] = mapped_column(
        String(5), nullable=False, default="02:00", comment="每日同步时间 HH:MM"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", comment="是否启用"
    )
    last_successful_sync_date: Mapped[date | None] = mapped_column(
        nullable=True, comment="最近成功同步的本地日期"
    )
    sync_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", comment="最近同步状态"
    )
    sync_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近同步错误"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class EnergyFeishuSourceRoot(EnergyWikiBaseModel):
    """One Wiki or Base entry owned by the energy module credentials."""

    __tablename__ = "feishu_source_roots"
    __table_args__ = (
        UniqueConstraint(
            "config_id",
            "source_type",
            "root_token",
            "is_deleted",
            name="uq_energy_feishu_source_root",
        ),
        Index("ix_energy_feishu_source_roots_config", "config_id", "is_active"),
        {"schema": "energy"},
    )

    config_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="wiki")
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    root_token: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    discovery_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    last_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovery_error: Mapped[str | None] = mapped_column(Text)


class EnergyWikiDocument(EnergyWikiBaseModel):
    """A Wiki node resolved to a source spreadsheet document."""

    __tablename__ = "wiki_documents"
    __table_args__ = (
        UniqueConstraint(
            "config_id",
            "wiki_node_token",
            "is_deleted",
            name="uq_energy_wiki_document_node",
        ),
        Index("ix_energy_wiki_documents_period", "config_id", "period_month"),
        {"schema": "energy"},
    )

    config_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    wiki_node_token: Mapped[str] = mapped_column(String(256), nullable=False)
    parent_node_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    space_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    object_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="sheet"
    )
    document_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    node_path: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    period_month: Mapped[date | None] = mapped_column(
        nullable=True, comment="所属月份首日"
    )
    classification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unclassified",
        comment="monthly/unclassified",
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EnergyWorkbookSheet(EnergyWikiBaseModel):
    """One physical worksheet within a discovered spreadsheet."""

    __tablename__ = "workbook_sheets"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "external_sheet_id",
            "is_deleted",
            name="uq_energy_workbook_sheet",
        ),
        Index("ix_energy_workbook_sheets_document", "document_id"),
        Index("ix_energy_workbook_sheets_schema", "schema_hash"),
        {"schema": "energy"},
    )

    document_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    external_sheet_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    grid_properties: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    header_row: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    headers: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mapping_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unmapped",
        comment="unmapped/mapped/needs_mapping",
    )
    latest_snapshot_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    latest_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EnergyFeishuPageBinding(EnergyWikiBaseModel):
    """Published binding between a menu page and a read-only Feishu sheet."""

    __tablename__ = "feishu_page_bindings"
    __table_args__ = (
        UniqueConstraint(
            "page_key", "sheet_id", "is_deleted", name="uq_energy_feishu_page_binding"
        ),
        Index("ix_energy_feishu_page_bindings_page", "page_key", "sort_order"),
        {"schema": "energy"},
    )

    page_key: Mapped[str] = mapped_column(String(255), nullable=False)
    sheet_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    tab_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    visible_field_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class EnergySyncRun(EnergyWikiBaseModel):
    """Auditable manual or scheduled ingestion execution."""

    __tablename__ = "sync_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_energy_sync_run_idempotency"),
        Index("ix_energy_sync_runs_config_started", "config_id", "started_at"),
        Index("ix_energy_sync_runs_status", "status"),
        {"schema": "energy"},
    )

    config_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    trigger_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual"
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sheet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    lock_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EnergySheetSnapshot(EnergyWikiBaseModel):
    """An immutable changed state of a worksheet."""

    __tablename__ = "sheet_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "sheet_id", "snapshot_number", name="uq_energy_sheet_snapshot_number"
        ),
        Index("ix_energy_sheet_snapshots_sheet_captured", "sheet_id", "captured_at"),
        {"schema": "energy"},
    )

    sheet_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    sync_run_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    snapshot_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    header_values: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EnergySnapshotRow(EnergyWikiBaseModel):
    """Raw cells for one row in an immutable sheet snapshot."""

    __tablename__ = "snapshot_rows"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "row_index", name="uq_energy_snapshot_row_index"
        ),
        Index("ix_energy_snapshot_rows_snapshot", "snapshot_id", "row_index"),
        {"schema": "energy"},
    )

    snapshot_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    values: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    display_values: Mapped[list[Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="飞书按单元格格式渲染后的显示值",
    )
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class EnergySheetMapping(EnergyWikiBaseModel):
    """Versioned conversion rule from raw rows to energy facts."""

    __tablename__ = "sheet_mappings"
    __table_args__ = (
        UniqueConstraint("sheet_id", "version", name="uq_energy_sheet_mapping_version"),
        Index("ix_energy_sheet_mappings_sheet_current", "sheet_id", "is_current"),
        {"schema": "energy"},
    )

    sheet_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="workshop_detail",
        server_default="workshop_detail",
        comment="workshop_detail/shared_detail/energy_summary/daily_summary",
    )
    schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    header_row: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    date_column: Mapped[str | None] = mapped_column(String(256), nullable=True)
    date_format: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dimensions: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    metrics: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EnergyMetricFact(EnergyWikiBaseModel):
    """Normalized numeric row produced by the current mapping version."""

    __tablename__ = "metric_facts"
    __table_args__ = (
        UniqueConstraint(
            "mapping_id",
            "snapshot_id",
            "metric_key",
            "source_row_index",
            name="uq_energy_metric_fact_source",
        ),
        Index("ix_energy_metric_facts_observed", "observed_at", "energy_type", "unit"),
        Index("ix_energy_metric_facts_sheet_snapshot", "sheet_id", "snapshot_id"),
        {"schema": "energy"},
    )

    mapping_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    snapshot_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(256), nullable=False)
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    energy_type: Mapped[str] = mapped_column(String(128), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    meter_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    value_semantics: Mapped[str] = mapped_column(
        String(32), nullable=False, default="direct"
    )
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    dimensions: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    quality_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="valid"
    )
