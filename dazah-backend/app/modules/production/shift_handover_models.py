"""班组交接确认 ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ShiftHandover(BaseModel):
    """班组交接确认表"""

    __tablename__ = "shift_handovers"
    __table_args__ = (
        Index("ix_shift_handovers_handover_time", "handover_time"),
        Index("ix_shift_handovers_position", "position"),
        Index("ix_shift_handovers_workshop", "workshop"),
        {"schema": "production"},
    )

    position: Mapped[str] = mapped_column(String(64), nullable=False, comment="岗位")
    workshop: Mapped[str] = mapped_column(String(64), nullable=False, comment="车间")
    shift: Mapped[str] = mapped_column(String(16), nullable=False, comment="班次")
    handover_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="交接时间"
    )
    handover_from: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="交班人"
    )
    handover_to: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="接班人"
    )
    production_status: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="生产工艺运行情况"
    )
    equipment_status: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="设备运行情况"
    )
    equipment_inspection: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="设备巡检情况"
    )
    tools_handover: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="工、器具移交"
    )
    fire_emergency: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="消防、应急器材情况"
    )
    ppe_status: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="人员劳动防护用品穿戴"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", comment="状态: pending/confirmed"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="确认时间"
    )
