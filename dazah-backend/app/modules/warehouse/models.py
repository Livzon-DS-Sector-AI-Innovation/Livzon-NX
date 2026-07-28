"""Warehouse ORM models live here."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class RawMaterialInventory(BaseModel):
    __tablename__ = "raw_material_inventories"
    __table_args__ = (
        Index("ix_warehouse_raw_materials_code", "code"),
        Index("ix_warehouse_raw_materials_product_line", "product_line"),
        Index("ix_warehouse_raw_materials_import_key", "import_key", unique=True),
        {"schema": "warehouse"},
    )

    source_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="来源记录 ID"
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="物料编码")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="物料名称")
    spec: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="规格")
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="单位")
    available: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="可用库存"
    )
    safety: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="安全库存"
    )
    last_month: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="上月库存/用量"
    )
    two_months_ago: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="前月库存/用量"
    )
    today_balance: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="今日结存"
    )
    front_stock: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="前台库存"
    )
    this_month_use: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="本月用量"
    )
    warning: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="预警"
    )
    product_line: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="使用产品/类别"
    )
    erp_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="ERP 编号"
    )
    delivery: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="到货时间"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    import_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="导入唯一键"
    )
    source: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="数据来源"
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        comment="最近同步时间",
    )


class PackagingMaterialInventory(BaseModel):
    __tablename__ = "packaging_material_inventories"
    __table_args__ = (
        Index("ix_warehouse_packaging_materials_code", "code"),
        Index("ix_warehouse_packaging_materials_product_line", "product_line"),
        Index(
            "ix_warehouse_packaging_materials_import_key",
            "import_key",
            unique=True,
        ),
        {"schema": "warehouse"},
    )

    source_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="来源记录 ID"
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="包材编码")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="名称")
    spec: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="规格")
    batch: Mapped[str | None] = mapped_column(Text, nullable=True, comment="批次")
    available: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="可用库存"
    )
    safety: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="安全库存"
    )
    last_month: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="上月库存/用量"
    )
    two_months_ago: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="前月库存/用量"
    )
    today_balance: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="今日结存"
    )
    front_stock: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="前台库存"
    )
    this_month_use: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="本月用量"
    )
    warning: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="预警"
    )
    product_line: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="使用产品"
    )
    erp_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="ERP 编号"
    )
    delivery: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="到货时间"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    import_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="导入唯一键"
    )
    source: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="数据来源"
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        comment="最近同步时间",
    )


class ProductInventory(BaseModel):
    __tablename__ = "product_inventories"
    __table_args__ = (
        Index("ix_warehouse_products_name", "name"),
        Index("ix_warehouse_products_import_key", "import_key", unique=True),
        {"schema": "warehouse"},
    )

    source_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="来源记录 ID"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="产品名称")
    spec: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="包装规格"
    )
    order_quantity: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="订单量"
    )
    pending_quantity: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="待检数量"
    )
    qualified_quantity: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="合格数量"
    )
    subtotal_quantity: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="小计"
    )
    remaining_quantity: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="剩余量"
    )
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="单位")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    import_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="导入唯一键"
    )
    source: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="数据来源"
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        comment="最近同步时间",
    )


class WarehouseFeishuConfig(BaseModel):
    __tablename__ = "feishu_configs"
    __table_args__ = (
        Index("ix_warehouse_feishu_configs_is_active", "is_active"),
        {"schema": "warehouse"},
    )

    config_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="仓储飞书配置",
        comment="配置名称",
    )
    app_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书应用 App ID"
    )
    encrypted_app_secret: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="加密后的飞书应用 App Secret"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="是否启用",
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Shanghai",
        server_default="Asia/Shanghai",
    )
    daily_sync_time: Mapped[str] = mapped_column(
        String(5), nullable=False, default="02:00", server_default="02:00"
    )


class WarehouseFeishuSourceRoot(BaseModel):
    """A Wiki or Base entry owned by the warehouse module."""

    __tablename__ = "feishu_source_roots"
    __table_args__ = (
        UniqueConstraint(
            "config_id", "root_token", "is_deleted", name="uq_warehouse_feishu_root"
        ),
        Index("ix_warehouse_feishu_roots_active", "config_id", "is_active"),
        {"schema": "warehouse"},
    )

    config_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="base/wiki"
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    root_token: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    discovery_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    discovery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_discovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WarehouseFeishuTable(BaseModel):
    __tablename__ = "feishu_tables"
    __table_args__ = (
        Index(
            "uq_warehouse_feishu_tables_root_app_token_table_id",
            "source_root_id",
            "app_token",
            "table_id",
            unique=True,
        ),
        Index("ix_warehouse_feishu_tables_root", "source_root_id"),
        Index("ix_warehouse_feishu_tables_app_token", "app_token"),
        {"schema": "warehouse"},
    )

    business_domain: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="飞书资源命名空间"
    )
    app_token: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书多维表格 app_token"
    )
    table_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书多维表格 table_id"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="数据表名称")
    revision: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="飞书表 revision"
    )
    last_discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        comment="最近发现时间",
    )
    last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近事件时间"
    )
    field_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="字段数量"
    )
    record_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="记录数量"
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近同步时间"
    )
    sync_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="同步状态"
    )
    sync_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近同步错误"
    )
    source_root_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    source_path: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_mirror_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


class WarehouseFeishuField(BaseModel):
    __tablename__ = "feishu_fields"
    __table_args__ = (
        Index(
            "uq_warehouse_feishu_fields_domain_table_field",
            "business_domain",
            "app_token",
            "table_id",
            "field_id",
            unique=True,
        ),
        Index(
            "ix_warehouse_feishu_fields_table",
            "business_domain",
            "app_token",
            "table_id",
        ),
        {"schema": "warehouse"},
    )

    business_domain: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="飞书资源命名空间"
    )
    app_token: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书多维表格 app_token"
    )
    table_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书多维表格 table_id"
    )
    field_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书字段 ID"
    )
    field_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="飞书字段名称"
    )
    field_type: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="飞书字段类型"
    )
    property: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="飞书字段属性"
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        comment="最近同步时间",
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class WarehouseFeishuRecord(BaseModel):
    __tablename__ = "feishu_records"
    __table_args__ = (
        Index(
            "uq_warehouse_feishu_records_domain_table_record",
            "business_domain",
            "app_token",
            "table_id",
            "record_id",
            unique=True,
        ),
        Index(
            "ix_warehouse_feishu_records_table",
            "business_domain",
            "app_token",
            "table_id",
        ),
        {"schema": "warehouse"},
    )

    business_domain: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="飞书资源命名空间"
    )
    app_token: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书多维表格 app_token"
    )
    table_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书多维表格 table_id"
    )
    record_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="飞书记录 ID"
    )
    fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, comment="飞书原始字段 JSON"
    )
    normalized_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="检索文本"
    )
    feishu_created_time: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="飞书创建时间"
    )
    feishu_last_modified_time: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="飞书最近修改时间"
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        comment="最近同步时间",
    )
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mirror_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_source_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class WarehouseFeishuRecordSnapshot(BaseModel):
    __tablename__ = "feishu_record_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "table_pk",
            "mirror_version",
            "record_id",
            name="uq_warehouse_record_snapshot",
        ),
        Index("ix_warehouse_record_snapshots_table", "table_pk", "captured_at"),
        {"schema": "warehouse"},
    )

    table_pk: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    mirror_version: Mapped[str] = mapped_column(String(64), nullable=False)
    record_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WarehouseFeishuPageBinding(BaseModel):
    __tablename__ = "feishu_page_bindings"
    __table_args__ = (
        UniqueConstraint(
            "page_key", "table_pk", "is_deleted", name="uq_warehouse_page_table_binding"
        ),
        Index("ix_warehouse_page_bindings_page", "page_key", "is_enabled"),
        {"schema": "warehouse"},
    )

    page_key: Mapped[str] = mapped_column(String(128), nullable=False)
    table_pk: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    tab_label: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visible_field_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    default_sort: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    history_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="current_mirror",
        server_default="current_mirror",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="published", server_default="published"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class WarehouseFeishuSyncRun(BaseModel):
    __tablename__ = "feishu_data_sync_runs"
    __table_args__ = (
        Index("ix_warehouse_data_sync_runs_table", "table_pk", "started_at"),
        {"schema": "warehouse"},
    )

    table_pk: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    mirror_version: Mapped[str] = mapped_column(String(64), nullable=False)
    start_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class WarehouseFeishuAnalysisProfile(BaseModel):
    __tablename__ = "feishu_analysis_profiles"
    __table_args__ = (
        Index("ix_warehouse_analysis_profiles_active", "is_active", "auto_run"),
        {"schema": "warehouse"},
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    analysis_goal: Mapped[str] = mapped_column(Text, nullable=False)
    input_field_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    time_field_id: Mapped[str | None] = mapped_column(String(128))
    metric_field_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    dimension_field_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    quality_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    output_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    max_raw_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    auto_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_sensitive_fields: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    published_prompt_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class WarehouseFeishuPromptVersion(BaseModel):
    __tablename__ = "feishu_prompt_versions"
    __table_args__ = (
        UniqueConstraint("profile_id", "version", name="uq_warehouse_prompt_version"),
        {"schema": "warehouse"},
    )

    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    business_context: Mapped[str | None] = mapped_column(Text)
    focus_points: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WarehouseFeishuAnalysisRun(BaseModel):
    __tablename__ = "feishu_analysis_runs"
    __table_args__ = (
        Index("ix_warehouse_analysis_runs_profile", "profile_id", "started_at"),
        {"schema": "warehouse"},
    )

    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    prompt_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_versions: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    algorithm_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="1"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class WarehouseFeishuAnalysisResult(BaseModel):
    __tablename__ = "feishu_analysis_results"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_warehouse_analysis_result_run"),
        {"schema": "warehouse"},
    )

    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    trends: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    feasibility: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    recommendations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    llm_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
