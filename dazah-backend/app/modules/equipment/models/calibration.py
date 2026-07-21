"""Calibration ORM models."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel

if TYPE_CHECKING:
    from app.modules.equipment.models.equipment import Equipment


class CalibrationPlan(BaseModel):
    """校准计划表"""

    __tablename__ = "calibration_plans"
    __table_args__ = (
        CheckConstraint(
            "calibration_type IN ('内部校准', '外部检定')",
            name="ck_calibration_plans_calibration_type",
        ),
        CheckConstraint(
            "status IN ('启用', '停用')",
            name="ck_calibration_plans_status",
        ),
        {"schema": "equipment"},
    )

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.equipments.id"),
        comment="设备ID",
    )
    calibration_type: Mapped[str] = mapped_column(
        String(20), comment="校准类型：内部校准/外部检定"
    )
    cycle_months: Mapped[int] = mapped_column(
        comment="校准周期（月）"
    )
    last_calibration_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="上次校准日期"
    )
    next_calibration_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="下次校准日期"
    )
    responsible_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="负责人ID",
    )
    status: Mapped[str] = mapped_column(
        String(10),
        default="启用",
        comment="状态：启用/停用",
    )
    remark: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注"
    )

    # 关系
    equipment: Mapped[Equipment] = relationship(
        "Equipment",
        foreign_keys=[equipment_id],
    )


class CalibrationRecord(BaseModel):
    """校准记录表"""

    __tablename__ = "calibration_records"
    __table_args__ = (
        CheckConstraint(
            "calibration_type IN ('内部校准', '外部检定')",
            name="ck_calibration_records_calibration_type",
        ),
        CheckConstraint(
            "result IN ('合格', '不合格')",
            name="ck_calibration_records_result",
        ),
        {"schema": "equipment"},
    )

    calibration_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.calibration_plans.id"),
        comment="校准计划ID",
    )
    equipment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.equipments.id"),
        comment="设备ID",
    )
    calibration_date: Mapped[date] = mapped_column(
        Date, comment="校准日期"
    )
    calibration_type: Mapped[str] = mapped_column(
        String(20), comment="校准类型：内部校准/外部检定"
    )
    result: Mapped[str] = mapped_column(
        String(10), comment="校准结果：合格/不合格"
    )
    certificate_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="证书编号"
    )
    calibrated_by: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="校准人/机构"
    )
    next_due_date: Mapped[date] = mapped_column(
        Date, comment="下次校准日期"
    )
    remark: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注"
    )

    # 关系
    calibration_plan: Mapped[CalibrationPlan] = relationship(
        "CalibrationPlan",
        foreign_keys=[calibration_plan_id],
    )
    equipment: Mapped[Equipment] = relationship(
        "Equipment",
        foreign_keys=[equipment_id],
    )
