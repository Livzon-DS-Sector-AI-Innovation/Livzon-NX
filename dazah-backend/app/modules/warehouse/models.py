"""Warehouse ORM models live here."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
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
        Index(
            "ix_warehouse_packaging_materials_product_line",
            "product_line",
        ),
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


class MaterialPageSnapshot(BaseModel):
    __tablename__ = "material_page_snapshots"
    __table_args__ = (
        Index("ix_warehouse_material_page_snapshots_page_key", "page_key", unique=True),
        Index("ix_warehouse_material_page_snapshots_table_id", "table_id"),
        {"schema": "warehouse"},
    )

    page_key: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="页面唯一键"
    )
    page_title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="页面标题"
    )
    table_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="来源表名"
    )
    table_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="飞书 table_id"
    )
    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="feishu_bitable",
        server_default="feishu_bitable",
        comment="快照来源",
    )
    columns: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="列结构快照",
    )
    total_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="同步行数",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近一次同步错误"
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        comment="最近同步时间",
    )


class MaterialPageRow(BaseModel):
    __tablename__ = "material_page_rows"
    __table_args__ = (
        Index("ix_warehouse_material_page_rows_page_id", "page_snapshot_id"),
        Index(
            "ix_warehouse_material_page_rows_source_record_id",
            "source_record_id",
        ),
        Index(
            "ix_warehouse_material_page_rows_page_record",
            "page_snapshot_id",
            "source_record_id",
            unique=True,
        ),
        {"schema": "warehouse"},
    )

    page_snapshot_id: Mapped[Any] = mapped_column(
        ForeignKey("warehouse.material_page_snapshots.id"),
        nullable=False,
        comment="所属页面快照 ID",
    )
    source_record_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="飞书记录 ID"
    )
    row_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="行序号",
    )
    cells: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="行内容快照",
    )
    search_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="关键字检索串",
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        comment="最近同步时间",
    )


class WarehousePageFeishuConfig(BaseModel):
    """页面飞书多维表格配置（支持动态切换数据源）"""

    __tablename__ = "warehouse_page_feishu_configs"
    __table_args__ = {
        "schema": "warehouse",
    }

    page_key: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="页面唯一键"
    )
    app_token: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="飞书多维表格 app_token"
    )
    table_id: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="飞书多维表格 table_id"
    )
    table_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="飞书多维表格名称"
    )
    view_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="飞书多维表格视图 ID（可选）"
    )


# The migrated page mirror is the active implementation; these imports keep
# the former Feishu ORM names and tables available for old Agent integrations.
from app.modules.warehouse.legacy_models import (  # noqa: E402,F401
    WarehouseFeishuAnalysisProfile,
    WarehouseFeishuAnalysisResult,
    WarehouseFeishuAnalysisRun,
    WarehouseFeishuConfig,
    WarehouseFeishuField,
    WarehouseFeishuPageBinding,
    WarehouseFeishuPromptVersion,
    WarehouseFeishuRecord,
    WarehouseFeishuRecordSnapshot,
    WarehouseFeishuSourceRoot,
    WarehouseFeishuSyncRun,
    WarehouseFeishuTable,
)
