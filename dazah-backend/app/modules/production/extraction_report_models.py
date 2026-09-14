"""提炼成品日报模型（提炼工段卡片右侧日报表）。

提炼工段按日记录成品产量，与批次台账（方案 B）相互独立：
同产品同一天仅一条进行中记录，重复录入即覆盖更新，删除采用软删。
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ExtractionDailyReport(BaseModel):
    """提炼成品日报"""

    __tablename__ = "extraction_daily_reports"
    __table_args__ = (
        Index(
            "ux_extraction_daily_reports_product_date",
            "product_code",
            "report_date",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "production"},
    )

    product_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="FA",
        comment="产品代码（如 FA/MC/DR），日报按产品隔离",
    )
    report_date: Mapped[date] = mapped_column(
        Date(), nullable=False, comment="成品日期"
    )
    quantity_kg: Mapped[float] = mapped_column(
        Float(), nullable=False, comment="成品量(kg)"
    )
