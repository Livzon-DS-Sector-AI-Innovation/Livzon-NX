"""Equipment health ORM models（健康快照、维修病历、月度报告）."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel

if TYPE_CHECKING:
    from app.modules.equipment.models.equipment import Equipment


class EquipmentHealthSnapshot(BaseModel):
    """设备健康度每日快照（评分 + 分项指标）"""

    __tablename__ = "equipment_health_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "equipment_id",
            "snapshot_date",
            "is_deleted",
            name="uq_equipment_health_snapshot_date",
        ),
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_equipment_health_snapshots_score",
        ),
        CheckConstraint(
            "grade IN ('G', 'Y', 'R')",
            name="ck_equipment_health_snapshots_grade",
        ),
        {"schema": "equipment"},
    )

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.equipments.id"),
        comment="设备ID",
    )
    snapshot_date: Mapped[dt.date] = mapped_column(Date, comment="快照日期")
    score: Mapped[float] = mapped_column(Numeric(5, 2), comment="健康度评分 0-100")
    grade: Mapped[str] = mapped_column(String(1), comment="分档：G绿/Y黄/R红")
    metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "分项指标：fault_count_90d/mttr_min_90d/overdue_maintenance_count/"
            "overdue_calibration_count/max_repeat_fault_90d 及各分项罚分"
        ),
    )

    equipment: Mapped[Equipment] = relationship(
        "Equipment", foreign_keys=[equipment_id]
    )


class RepairProfile(BaseModel):
    """设备维修病历（冗余聚合表，工单闭环后触发更新）"""

    __tablename__ = "repair_profiles"
    __table_args__ = ({"schema": "equipment"},)

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.equipments.id"),
        unique=True,
        comment="设备ID（一台设备一行）",
    )
    total_orders: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计工单数"
    )
    total_faults: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计故障维修数"
    )
    total_downtime_min: Mapped[int] = mapped_column(
        Integer, default=0, comment="累计维修用时（分钟）"
    )
    total_spare_cost: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0, comment="累计备件费用"
    )
    mtbf_days: Mapped[float | None] = mapped_column(
        Numeric(10, 1), nullable=True, comment="平均故障间隔（天）"
    )
    last_3_faults: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="最近 3 次故障摘要（工单号/日期/现象/原因）",
    )

    equipment: Mapped[Equipment] = relationship(
        "Equipment", foreign_keys=[equipment_id]
    )


class EquipmentMonthlyReport(BaseModel):
    """设备模块月度健康报告（SQL 聚合数字 + LLM 叙述）"""

    __tablename__ = "equipment_monthly_reports"
    __table_args__ = (
        UniqueConstraint(
            "report_month",
            "is_deleted",
            name="uq_equipment_monthly_reports_month",
        ),
        CheckConstraint(
            "report_month ~ '^[0-9]{4}-[0-9]{2}$'",
            name="ck_equipment_monthly_reports_month",
        ),
        {"schema": "equipment"},
    )

    report_month: Mapped[str] = mapped_column(
        String(7), comment="报告月份 YYYY-MM（全厂汇总一份）"
    )
    metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="SQL 聚合指标（LLM 不参与计算）"
    )
    content_md: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="报告正文（Markdown）"
    )
    generated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="生成时间",
    )
