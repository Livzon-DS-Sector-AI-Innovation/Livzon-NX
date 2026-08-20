"""生产日志与交接班 ORM model."""

from datetime import date
from enum import StrEnum

from sqlalchemy import Date, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ShiftType(StrEnum):
    MORNING = "morning"  # 早班
    AFTERNOON = "afternoon"  # 中班
    NIGHT = "night"  # 晚班


class ShiftLog(BaseModel):
    """生产日志与交接班记录表"""

    __tablename__ = "shift_logs"
    __table_args__ = (
        Index("ix_shift_logs_date", "log_date"),
        Index("ix_shift_logs_workshop", "workshop"),
        {"schema": "production"},
    )

    log_date: Mapped[date] = mapped_column(Date, nullable=False, comment="日期")
    shift: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="班次（morning/afternoon/night）"
    )
    workshop: Mapped[str] = mapped_column(String(64), nullable=False, comment="车间")
    handover_from: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="交班人"
    )
    handover_to: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="接班人"
    )
    production_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="本班生产情况"
    )
    equipment_status: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="设备运行状况"
    )
    abnormal_events: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="异常情况"
    )
    pending_tasks: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="待办事项交接"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
