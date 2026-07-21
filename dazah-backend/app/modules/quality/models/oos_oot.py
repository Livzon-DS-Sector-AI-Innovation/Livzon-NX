"""ORM models for quality OOS/OOT records and OOT limits."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class QualityOosOotBaseModel(BaseModel):
    """Quality-owned records deliberately avoid database foreign keys."""

    __abstract__ = True

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class OosOotRecord(QualityOosOotBaseModel):
    """One out-of-specification or out-of-trend investigation ledger entry."""

    __tablename__ = "oos_oot_records"
    __table_args__ = (
        UniqueConstraint("record_code", name="uq_quality_oos_oot_records_record_code"),
        Index(
            "ix_quality_oos_oot_records_active_type_status_date",
            "is_deleted",
            "record_type",
            "status",
            "discovered_date",
        ),
        Index("ix_quality_oos_oot_records_product_batch", "product_name", "batch_no"),
        {"schema": "quality"},
    )

    record_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="记录编号"
    )
    record_type: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="OOS 或 OOT"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="事件标题")
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="责任部门"
    )
    product_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="产品名称"
    )
    batch_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="批号"
    )
    test_item: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="检验项目"
    )
    specification: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="标准规定"
    )
    test_result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="检验结果"
    )
    discovered_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="发现日期"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="事件描述"
    )
    investigation_result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="调查结论"
    )
    corrective_actions: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="纠正预防措施"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        server_default="open",
        comment="状态",
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="关闭时间"
    )


class OotLimitProduct(QualityOosOotBaseModel):
    """Product-level container for controlled OOT limit definitions."""

    __tablename__ = "oot_limit_products"
    __table_args__ = (
        UniqueConstraint(
            "product_code", name="uq_quality_oot_limit_products_product_code"
        ),
        Index(
            "ix_quality_oot_limit_products_active_code", "is_deleted", "product_code"
        ),
        Index(
            "ix_quality_oot_limit_products_active_name", "is_deleted", "product_name"
        ),
        {"schema": "quality"},
    )

    product_code: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="产品编码"
    )
    product_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="产品名称"
    )
    document_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="标准文件编号"
    )
    document_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="标准文件版本"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", comment="是否启用"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class OotLimitItem(QualityOosOotBaseModel):
    """Single OOT limit item. product_id is an application-enforced association."""

    __tablename__ = "oot_limit_items"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "display_order",
            name="uq_quality_oot_limit_items_product_order",
        ),
        Index("ix_quality_oot_limit_items_active_product", "is_deleted", "product_id"),
        Index("ix_quality_oot_limit_items_name", "item_name"),
        {"schema": "quality"},
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, comment="OOT限度产品ID（应用层关联）"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", comment="显示顺序"
    )
    item_group: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="项目分组"
    )
    item_name: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="项目名称"
    )
    specification: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="标准规定"
    )
    oot_limit: Mapped[str] = mapped_column(Text, nullable=False, comment="OOT限度")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
