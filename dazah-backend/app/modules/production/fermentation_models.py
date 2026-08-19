"""Fermentation record ORM model."""

from datetime import date
from enum import Enum

from sqlalchemy import Date, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class FermentationStatus(str, Enum):
    IN_PROGRESS = "in_progress"       # 发酵中
    COMPLETED = "completed"           # 已完成
    ABNORMAL = "abnormal"             # 异常


class FermentationRecord(BaseModel):
    """发酵记录表"""

    __tablename__ = "fermentation_records"
    __table_args__ = (
        Index("ix_fermentation_records_batch_no", "batch_no"),
        Index("ix_fermentation_records_product_name", "product_name"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="批号"
    )
    product_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="L-苯丙氨酸", comment="产品名称"
    )
    fermenter: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="发酵罐"
    )
    entry_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="进罐日期"
    )
    discharge_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="放罐日期"
    )
    cycle_1: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="周期1"
    )
    cycle_2: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="周期2"
    )
    cycle_3: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="周期3"
    )
    cycle_4: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="周期4"
    )
    cycle_5: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="周期5"
    )
    cycle_6: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="周期6"
    )
    tank_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="罐产"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="in_progress", comment="状态"
    )
    remarks: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注"
    )
    attachment: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="附件"
    )
