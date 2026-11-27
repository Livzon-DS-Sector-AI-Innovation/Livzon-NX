"""排产异常记录模型。

看板与排产表只呈现「当前正常状态」，计划外的变化（延后、减批、补种、
染菌等）会被静默吸收，系统里不留任何痕迹；减批的批次甚至不会出现在
看板上。本表由人工登记这类计划外异常，只负责存与查，不与排产 Excel
比对或上传流程耦合，也不做审批流转。
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ScheduleAnomalyRecord(BaseModel):
    """排产计划外异常的人工登记记录"""

    __tablename__ = "schedule_anomaly_records"
    __table_args__ = (
        Index(
            "ix_schedule_anomaly_records_product_date",
            "product_code",
            "event_date",
        ),
        Index("ix_schedule_anomaly_records_batch", "batch_no"),
        {"schema": "production"},
    )

    product_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="FA",
        comment="产品代码（如 FA/MC/DR），记录按产品隔离",
    )
    batch_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="批号（手填）"
    )
    tank_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="罐号（选填）"
    )
    anomaly_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        comment="异常类型：delayed/reduced/reseeded/contamination/other",
    )
    event_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="异常发生日期"
    )
    reason: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="原因（必填）"
    )
    remark: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="备注（选填）"
    )
