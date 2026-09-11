"""成品/纯化水异常升级推送队列模型。

首波异常推送给产品线收件人 + 升级首推人后入队；到点由
quality.scheduled.TrendAlertEscalationGenerator 复检，仍异常则升级推送
各部门负责人（提炼部门负责人 + 该产品QA），已恢复则取消。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class QualityTrendAlertEscalation(BaseModel):
    """一条待复检升级的趋势异常告警。"""

    __tablename__ = "quality_trend_alert_escalations"
    __table_args__ = (
        Index(
            "ix_quality_trend_alert_escalation_status_escalate_at",
            "status",
            "escalate_at",
        ),
        {"schema": "quality"},
    )

    entity_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(256), nullable=False)
    metric_label: Mapped[str] = mapped_column(String(256), nullable=False)
    # 首报时的判定快照：spec_lines/控制限/触发值等，复检仍异常时随卡片重述
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    first_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    escalate_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escalated_message_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
