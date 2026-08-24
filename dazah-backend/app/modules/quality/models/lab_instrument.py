"""Lab instrument / 仪器管理 ORM model."""

from datetime import date

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class LabInstrument(BaseModel):
    """实验室仪器设备."""

    __tablename__ = "lab_instruments"
    __table_args__ = {"schema": "quality"}

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="仪器名称")
    model: Mapped[str | None] = mapped_column(String(100), comment="型号")
    serial_no: Mapped[str | None] = mapped_column(
        String(100), unique=True, comment="序列号"
    )
    manufacturer: Mapped[str | None] = mapped_column(String(200), comment="生产厂家")
    department: Mapped[str | None] = mapped_column(String(100), comment="所属部门")
    location: Mapped[str | None] = mapped_column(String(100), comment="放置位置")
    calibration_date: Mapped[date | None] = mapped_column(Date, comment="最近校准日期")
    next_calibration_date: Mapped[date | None] = mapped_column(
        Date, comment="下次校准日期"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="normal",
        comment="状态：normal/maintenance/calibration_due/scrapped",
    )
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")
