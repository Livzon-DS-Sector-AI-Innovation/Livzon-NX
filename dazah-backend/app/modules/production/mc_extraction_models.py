"""MC 霉酚酸 — 提取工段 ORM 模型（粗品→萃取→湿粉）"""

from datetime import date
from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel


class ExtractionRecord(BaseModel):
    """提取工段主表 — 多批粗品合并提取"""
    __tablename__ = "extraction_records"
    __table_args__ = (
        Index("ix_er_batch", "batch_no"),
        Index("ix_er_workshop", "workshop"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="提取批号（MC-260129）"
    )
    workshop: Mapped[str] = mapped_column(
        String(32), nullable=False, default="201-2", comment="车间"
    )
    extract_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="提取生产日期"
    )

    # ── 投入汇总（由明细表自动计算）──
    total_crude_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="粗品总投入量(kg)"
    )
    total_converted_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="折纯总量(kg)"
    )

    # ── 萃取滤液 ──
    filter_product_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="滤液产品量(kg)"
    )
    filter_potency: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="滤液效价(mg/L)"
    )
    filter_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="滤液体积(m³)"
    )
    carbon_usage: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="用碳量(kg)"
    )

    # ── 湿粉产出 ──
    wet_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="湿粉毛重(kg)"
    )
    wet_content: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="湿粉含量(%)"
    )
    dry_loss: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="干燥失重(%)"
    )
    dry_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="折干产量(kg) — 计算字段"
    )
    yield_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="单步收率(%) — 计算字段"
    )

    # ── 母液 ──
    mother_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液体积(kL)"
    )
    mother_content: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液含量(mg/L)"
    )
    mother_loss: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液损失量(kg) — 计算字段"
    )
    yield_to_filter: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="对滤液收率(%) — 计算字段"
    )

    # ── 状态 ──
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="状态（0草稿/1已提交/2已审核）"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class ExtractionInput(BaseModel):
    """提取投入明细表 — 多行粗品投入"""
    __tablename__ = "extraction_inputs"
    __table_args__ = (
        Index("ix_ei_extraction", "extraction_batch"),
        Index("ix_ei_crude", "crude_batch_no"),
        {"schema": "production"},
    )

    extraction_batch: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="提取批号（关联主表）"
    )
    seq_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="投入顺序号"
    )
    crude_batch_no: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="粗品批号（MC-260527-1）"
    )
    crude_weight: Mapped[float] = mapped_column(
        Float, nullable=False, comment="粗品重量(kg)"
    )
    crude_moisture: Mapped[float] = mapped_column(
        Float, nullable=False, comment="水分(%)"
    )
    crude_content: Mapped[float] = mapped_column(
        Float, nullable=False, comment="含量(%)"
    )
    converted_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="折合产品重量(kg) — 计算字段"
    )
