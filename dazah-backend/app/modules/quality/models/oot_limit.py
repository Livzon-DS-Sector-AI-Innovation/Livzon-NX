"""OOT limit management ORM models."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class OotLimitProduct(BaseModel):
    """OOT limit product master record."""

    __tablename__ = "oot_limit_products"
    __table_args__ = (
        UniqueConstraint("product_code", name="uq_oot_limit_products_product_code"),
        Index("ix_oot_limit_products_product_name", "product_name"),
        {"schema": "quality"},
    )

    product_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="产品编码"
    )
    product_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="产品名称"
    )
    # Preserve the legacy table columns while exposing the migrated names.
    document_no: Mapped[str | None] = mapped_column(
        String(200), comment="旧版通知单编号"
    )
    document_version: Mapped[str | None] = mapped_column(
        String(100), comment="旧版通知单版本"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="旧版启用状态"
    )
    document_title: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="通知单标题"
    )
    document_year: Mapped[int | None] = mapped_column(Integer, comment="年份")
    version_label: Mapped[str | None] = mapped_column(String(50), comment="版本标签")
    source_file_name: Mapped[str | None] = mapped_column(
        String(255), comment="源文件名"
    )
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")


class OotLimitItem(BaseModel):
    """OOT limit detail record."""

    __tablename__ = "oot_limit_items"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "display_order", name="uq_oot_limit_items_product_order"
        ),
        Index("ix_oot_limit_items_product_id", "product_id"),
        {"schema": "quality"},
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        comment="产品ID",
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="显示顺序"
    )
    item_group: Mapped[str | None] = mapped_column(String(200), comment="一级项目")
    item_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="项目名称"
    )
    # The old table keeps `oot_limit` NOT NULL; write it together with the
    # canonical migrated field so old reads and new writes remain compatible.
    specification: Mapped[str | None] = mapped_column(String(300), comment="旧版标准值")
    oot_limit: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="旧版OOT限度"
    )
    standard_value: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="标准值"
    )
    oot_limit_value: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="OOT限度"
    )
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")
