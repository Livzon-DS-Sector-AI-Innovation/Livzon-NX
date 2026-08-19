"""MC 霉酚酸 — MC 二次精制工段 ORM 模型（湿粉→二次结晶→干粉 MC-F2）"""

from datetime import date
from sqlalchemy import Date, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel


class McRefinementRecord(BaseModel):
    """MC 二次精制主表 — 多批湿粉合并二次结晶"""
    __tablename__ = "mc_refinement_records"
    __table_args__ = (
        Index("ix_mcr_batch", "batch_no"),
        Index("ix_mcr_workshop", "workshop"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="二次结晶批号（MC-F2-260101）"
    )
    workshop: Mapped[str] = mapped_column(
        String(32), nullable=False, default="201-2", comment="车间"
    )
    input_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="投料日期"
    )

    # ── 投入汇总 ──
    total_input_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="总重(kg)"
    )
    total_pure_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="折纯量(kg)"
    )
    dry_product_total: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="折干产品总量(kg)"
    )

    # ── 溶解结晶 ──
    dissolution_tank: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="溶解用罐（1#结晶罐/8#浓缩罐/1#溶解罐）"
    )
    butyl_acetate_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="加入丁酯量(m³)"
    )
    crystallization_tank: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="结晶用罐（3#结晶罐）"
    )
    wet_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="湿粉重量(kg)"
    )
    dry_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="干粉重量(kg)"
    )

    # ── 收率 ──
    single_step_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="单步收率(%) — 计算字段"
    )

    # ── 累计字段 ──
    cumulative_dry_product: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="累计折干产品量(kg)"
    )
    cumulative_dry_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="累计干粉重量(kg)"
    )
    cumulative_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="二次结晶累计收率(%)"
    )

    # ── 母液 ──
    mother_liquid_content: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="二次母液含量(mg/L)"
    )
    mother_liquid_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="二次母液体积(m³)"
    )
    mother_liquid_loss: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液损失量(kg) — 计算字段"
    )

    # ── 状态 ──
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="状态（0草稿/1已提交/2已审核）"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class McRefinementInput(BaseModel):
    """MC 二次精制投入明细表 — 多行湿粉投入"""
    __tablename__ = "mc_refinement_inputs"
    __table_args__ = (
        Index("ix_mcri_refinement", "refinement_batch"),
        Index("ix_mcri_wet", "wet_batch_no"),
        {"schema": "production"},
    )

    refinement_batch: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="二次结晶批号（关联主表）"
    )
    wet_batch_no: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="上游湿粉批号"
    )
    input_weight: Mapped[float] = mapped_column(
        Float, nullable=False, comment="重量(kg)"
    )
    moisture: Mapped[float] = mapped_column(
        Float, nullable=False, comment="水分(%)"
    )
    content: Mapped[float] = mapped_column(
        Float, nullable=False, comment="含量(%)"
    )
    pure_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="折纯量(kg) — 计算字段"
    )
