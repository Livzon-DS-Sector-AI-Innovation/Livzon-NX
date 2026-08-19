"""MC 霉酚酸 — 粗提工段 ORM 模型（发酵液→提炼→分罐→钠化/酸化→粗品）"""

from datetime import date, datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel


# ═══════════════════════ 发酵液 ═══════════════════════

class FermentationLiquid(BaseModel):
    """发酵液源头表"""
    __tablename__ = "fermentation_liquids"
    __table_args__ = (
        Index("ix_fl_batch", "batch_no"),
        UniqueConstraint("batch_no"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="发酵液批号（MC-103-25017）")
    workshop: Mapped[str] = mapped_column(String(10), nullable=False, comment="发酵车间号（101/103）")
    year: Mapped[int] = mapped_column(Integer, nullable=False, comment="年份")
    annual_seq: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="年度流水号")
    input_volume: Mapped[float | None] = mapped_column(Float, nullable=True, comment="投入体积(KL)")
    potency: Mapped[float | None] = mapped_column(Float, nullable=True, comment="效价(mg/L)")
    product_qty: Mapped[float | None] = mapped_column(Float, nullable=True, comment="核对产品量(kg)")
    create_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="生产日期")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


# ═══════════════════════ 提炼批次 ═══════════════════════

class RefiningBatch(BaseModel):
    """提炼批次主表 — 1对1关联发酵液"""
    __tablename__ = "refining_batches"
    __table_args__ = (
        Index("ix_rb_batch", "batch_no"),
        Index("ix_rb_fermentation", "fermentation_no"),
        UniqueConstraint("batch_no"),
        UniqueConstraint("fermentation_no"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="提炼批号（MC-251224）")
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default="201-2")
    fermentation_no: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="关联发酵液批号（一对一）")
    year: Mapped[int] = mapped_column(Integer, nullable=False, comment="年份")
    month: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="月份")
    monthly_seq: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="当月流水号")
    produce_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="生产日期")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


# ═══════════════════════ 分罐记录 ═══════════════════════

class SubTankRecord(BaseModel):
    """分罐记录 — 每个提炼批固定有 -1 和 -2 两条"""
    __tablename__ = "sub_tank_records"
    __table_args__ = (
        Index("ix_str_parent", "parent_batch"),
        Index("ix_str_batch", "batch_no"),
        UniqueConstraint("parent_batch", "tank_no"),
        {"schema": "production"},
    )

    parent_batch: Mapped[str] = mapped_column(String(128), nullable=False, comment="父提炼批号（MC-251224）")
    tank_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="分罐号（1 或 2）")
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="完整分罐批号（MC-251224-1）")

    # ── 发酵液放罐 ──
    fl_volume: Mapped[float | None] = mapped_column(Float, nullable=True, comment="体积(KL)")
    fl_potency: Mapped[float | None] = mapped_column(Float, nullable=True, comment="效价(mg/L)")
    fl_product_qty: Mapped[float | None] = mapped_column(Float, nullable=True, comment="核对产品量(kg)")
    total_input: Mapped[float | None] = mapped_column(Float, nullable=True, comment="总产量(kg)")
    cumulative_qty: Mapped[float | None] = mapped_column(Float, nullable=True, comment="累计放罐产品量")

    # ── 粗品产出 ──
    crude_weight: Mapped[float | None] = mapped_column(Float, nullable=True, comment="粗品重量(kg)")
    bag_weight: Mapped[float | None] = mapped_column(Float, nullable=True, comment="袋种(KG)")
    crude_content: Mapped[float | None] = mapped_column(Float, nullable=True, comment="含量(%)")
    crude_moisture: Mapped[float | None] = mapped_column(Float, nullable=True, comment="水分(%)")
    crude_product_qty: Mapped[float | None] = mapped_column(Float, nullable=True, comment="产品量(kg)")
    yield_rate: Mapped[float | None] = mapped_column(Float, nullable=True, comment="收率≥92%")
    cumulative_crude_qty: Mapped[float | None] = mapped_column(Float, nullable=True, comment="累积粗品产品量(kg)")
    cumulative_crude_yield: Mapped[float | None] = mapped_column(Float, nullable=True, comment="粗品累计收率(%)")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


# ═══════════════════════ 钠化步骤 ═══════════════════════

class SubTankSodiumStep(BaseModel):
    """分罐钠化步骤明细 — 支持多行"""
    __tablename__ = "sub_tank_sodium_steps"
    __table_args__ = (
        Index("ix_stss_sub_tank", "sub_tank_id"),
        {"schema": "production"},
    )

    sub_tank_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="关联分罐批号")
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="步骤序号")
    na_before_volume: Mapped[float | None] = mapped_column(Float, nullable=True, comment="钠化前体积")
    na_after_volume: Mapped[float | None] = mapped_column(Float, nullable=True, comment="钠化后体积")
    na_potency: Mapped[float | None] = mapped_column(Float, nullable=True, comment="效价(mg/L)")
    na_product_qty: Mapped[float | None] = mapped_column(Float, nullable=True, comment="产品量(kg)")
    sodium_total: Mapped[float | None] = mapped_column(Float, nullable=True, comment="钠化总产品量")
    ph_value: Mapped[float | None] = mapped_column(Float, nullable=True, comment="pH值")
    alkali_usage: Mapped[float | None] = mapped_column(Float, nullable=True, comment="液碱用量(L)")


# ═══════════════════════ 酸化步骤 ═══════════════════════

class SubTankAcidStep(BaseModel):
    """分罐酸化步骤明细 — 支持多行"""
    __tablename__ = "sub_tank_acid_steps"
    __table_args__ = (
        Index("ix_stas_sub_tank", "sub_tank_id"),
        {"schema": "production"},
    )

    sub_tank_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="关联分罐批号")
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="步骤序号")
    acid_filter_volume: Mapped[float | None] = mapped_column(Float, nullable=True, comment="钠化滤液体积")
    acid_potency: Mapped[float | None] = mapped_column(Float, nullable=True, comment="效价")
    acid_product_qty: Mapped[float | None] = mapped_column(Float, nullable=True, comment="产品量(kg)")
    filter_subtotal: Mapped[float | None] = mapped_column(Float, nullable=True, comment="滤液小计")
    ph_value: Mapped[float | None] = mapped_column(Float, nullable=True, comment="pH")
    acid_usage: Mapped[float | None] = mapped_column(Float, nullable=True, comment="硫酸用量(L)")
    acid_filter_content: Mapped[float | None] = mapped_column(Float, nullable=True, comment="酸化滤液含量")
    filter_total: Mapped[float | None] = mapped_column(Float, nullable=True, comment="滤液合计")
    na_to_fermentation_yield: Mapped[float | None] = mapped_column(Float, nullable=True, comment="钠化滤液对发酵液收率")
    monthly_cumulative_yield: Mapped[float | None] = mapped_column(Float, nullable=True, comment="当月累计收率")
