"""Product business ORM models live here."""

from datetime import date

from sqlalchemy import Date, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class Product(BaseModel):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_name", "name"),
        Index("ix_products_major_category", "major_category"),
        Index("ix_products_product_type", "product_type"),
        Index("ix_products_feishu_record_id", "feishu_record_id"),
        {"schema": "product"},
    )

    # 产品名称
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="产品名称"
    )
    # 产品代码
    major_category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="产品代码: SM, FSM"
    )
    # 制剂代码
    formulation_code: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="制剂代码: AA, AB, AC..."
    )
    # 产品剂型
    product_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="产品剂型: API, 制品, 包装"
    )
    # 生产规格
    spec: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="生产规格"
    )
    # 生产批量（飞书多选字段，同步时转换为逗号分隔文本）
    capacity_range: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="生产批量（逗号分隔）"
    )
    # 单位
    unit: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="单位: 支, g, 批"
    )
    # 适应症
    indication: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="适应症"
    )

    # ─── Feishu sync metadata ───
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="飞书多维表格 record_id"
    )
    feishu_synced_at: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="上次飞书同步时间"
    )
