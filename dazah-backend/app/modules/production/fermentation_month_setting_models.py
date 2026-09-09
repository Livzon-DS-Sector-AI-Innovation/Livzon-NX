"""发酵看板扎帐月设置模型。

当前仅存本月计划产能（kg），按周期起始日唯一；由看板进度卡右侧入口编辑。
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class FermentationMonthSetting(BaseModel):
    """发酵看板扎帐月设置"""

    __tablename__ = "fermentation_month_settings"
    __table_args__ = (
        Index(
            "ux_fermentation_month_settings_period",
            "period_start",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "production"},
    )

    period_start: Mapped[date] = mapped_column(
        Date(), nullable=False, comment="扎帐月起始日"
    )
    period_end: Mapped[date] = mapped_column(
        Date(), nullable=False, comment="扎帐月结束日"
    )
    planned_capacity_kg: Mapped[float | None] = mapped_column(
        Float(), nullable=True, comment="本月计划产能(kg)"
    )
