"""MC 霉酚酸 — QC检验 + 乙酸丁酯盘点 ORM 模型"""

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class QcInspection(BaseModel):
    """QC检验主表 — 实测值 vs 理论值比对"""

    __tablename__ = "qc_inspections"
    __table_args__ = (
        Index("ix_qci_qc_id", "qc_id"),
        Index("ix_qci_batch", "batch_no"),
        {"schema": "production"},
    )

    qc_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="QC单号（QC-260101）"
    )
    batch_no: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="后台批号（关联混粉批次）"
    )
    inspection_std: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="请检标准"
    )
    front_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="前台批号"
    )
    pack_spec: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="规格"
    )
    warehouse_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="入库重量(kg)"
    )
    barrel_count: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="桶数（如：98桶）"
    )
    blend_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="混粉日期"
    )
    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="状态（0待检/1检验中/2合格/3复测中/4返工）",
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 混粉入库台账专属字段 ──
    input_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="入库日期"
    )
    cumulative_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="累计入库重量(kg)"
    )


class QcInspectionItem(BaseModel):
    """QC检验明细表 — 各RRT点位的实测值"""

    __tablename__ = "qc_inspection_items"
    __table_args__ = (
        Index("ix_qcii_inspection", "inspection_id"),
        {"schema": "production"},
    )

    inspection_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="QC单号（关联主表）"
    )
    item_code: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="项目编码（rrt_053等）"
    )
    theory_value: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="理论值（来自混粉方案A）"
    )
    actual_value: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="实测值"
    )
    deviation: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="偏差（actual - theory）"
    )
    is_blocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否触发阻止提交"
    )
    verify_mode: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="验证模式（0未验证/1方案A/2方案B）"
    )


# ═══════════════════════ 丁酯台账（飞书同步） ═══════════════════════


class ButylAcetateRecord(BaseModel):
    """丁酯消耗/入库台账 — 飞书交叉表镜像"""

    __tablename__ = "butyl_acetate_records"
    __table_args__ = (
        UniqueConstraint("check_date", "equipment"),
        {"schema": "production"},
    )

    check_date: Mapped[date] = mapped_column(Date, nullable=False, comment="抽查日期")
    equipment: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="设备名称（入库行='入库'）"
    )
    consumption: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="消耗量/入库量(kg)"
    )
    is_inbound: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="是否入库行"
    )
    is_check: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="是否盘点行"
    )


# ═══════════════════════ QC检验投入明细 — 混粉入库台账子表 ═══════════════════════


class QcInspectionInput(BaseModel):
    """QC检验单 — 投入明细（每批干粉来源）"""

    __tablename__ = "qc_inspection_inputs"
    __table_args__ = (
        Index("ix_qcii_qc", "qc_batch"),
        Index("ix_qcii_input", "input_batch"),
        {"schema": "production"},
    )

    qc_batch: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="关联QC批号（成品后台批号）"
    )
    input_batch: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="单批批号（MC-F2-xxxxx）"
    )
    dry_weight: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="干粉重量(kg)"
    )
