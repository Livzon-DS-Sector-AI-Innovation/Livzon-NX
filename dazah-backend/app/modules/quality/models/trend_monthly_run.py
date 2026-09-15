"""趋势 AI 月度定时分析运行状态模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class QualityTrendMonthlyRun(BaseModel):
    """一个月度周期（YYYY-MM）只允许一条记录，防止同月重复触发。"""

    __tablename__ = "quality_trend_monthly_runs"
    __table_args__ = (
        # 软删除语义：仅未删除行唯一（"重跑本月"=软删旧标记再插入新标记）
        Index(
            "uq_quality_trend_monthly_run_period",
            "period",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "quality"},
    )

    period: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
