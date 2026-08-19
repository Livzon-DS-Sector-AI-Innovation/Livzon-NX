"""MC 霉酚酸 — 混粉工段 ORM 模型（多批原料混合 + 5RRT点位杂质加权计算）"""

from sqlalchemy import Boolean, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel


class BlendingRecord(BaseModel):
    """混粉批次主表"""
    __tablename__ = "blending_records"
    __table_args__ = (
        Index("ix_blr_batch", "batch_no"),
        Index("ix_blr_workshop", "workshop"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="混合批号（MC-260118）"
    )
    workshop: Mapped[str] = mapped_column(
        String(32), nullable=False, default="201-2", comment="车间"
    )
    blend_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="混粉级别（1或2）"
    )
    total_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="入库总重量(kg)"
    )
    front_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="前台批号（对外）"
    )
    pack_spec: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="包装规格（20/40/50kg）"
    )
    barrel_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="桶数 — 计算字段"
    )

    # ── 杂质计算结果（加权平均）──
    rrt_053: Mapped[float | None] = mapped_column(Float, nullable=True, comment="RRT=0.53")
    rrt_0755: Mapped[float | None] = mapped_column(Float, nullable=True, comment="RRT=0.755")
    rrt_094_096: Mapped[float | None] = mapped_column(Float, nullable=True, comment="RRT=0.94-0.96")
    rrt_103_106: Mapped[float | None] = mapped_column(Float, nullable=True, comment="RRT=1.03-1.06")
    rrt_201: Mapped[float | None] = mapped_column(Float, nullable=True, comment="RRT=2.01")
    total_impurity: Mapped[float | None] = mapped_column(Float, nullable=True, comment="总杂")
    content: Mapped[float | None] = mapped_column(Float, nullable=True, comment="含量(%)")

    # ── 状态 ──
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="状态（0草稿/1待补数据/2计算完成/3已送检/4已完工）"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class BlendingInput(BaseModel):
    """混粉投入明细表 — 记录每批投入原料"""
    __tablename__ = "blending_inputs"
    __table_args__ = (
        Index("ix_bli_blend", "blend_batch"),
        Index("ix_bli_source", "input_batch_no"),
        {"schema": "production"},
    )

    blend_batch: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="混合批号"
    )
    input_batch_no: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="投入批号（MC-F2/退货粉/进口粉/余粉/上级混粉）"
    )
    source_type: Mapped[str] = mapped_column(
        String(128), nullable=False, default="mc_f2",
        comment="来源类型（mc_f2/returned/imported/surplus/blending）"
    )
    batch_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="投入批次级别（0=原料/1=一级混粉）"
    )
    seq_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="飞书表格行序号，保持原始顺序"
    )
    input_weight: Mapped[float] = mapped_column(
        Float, nullable=False, comment="投入重量(kg)"
    )

    # 各杂质检测值
    rrt_053: Mapped[float | None] = mapped_column(Float, nullable=True)
    rrt_0755: Mapped[float | None] = mapped_column(Float, nullable=True)
    rrt_094_096: Mapped[float | None] = mapped_column(Float, nullable=True)
    rrt_103_106: Mapped[float | None] = mapped_column(Float, nullable=True)
    rrt_201: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_impurity: Mapped[float | None] = mapped_column(Float, nullable=True)
    content: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="数据状态（0待录入/1已录入/2已复核）"
    )
