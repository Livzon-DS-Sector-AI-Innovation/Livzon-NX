"""Finished product trend alert notification persistence model."""

from datetime import datetime

from sqlalchemy import DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class FinishedTrendAlertNotification(BaseModel):
    """Deduplicated notification record for finished product trend alerts."""

    __tablename__ = "quality_finished_trend_alert_notifications"
    __table_args__ = (
        UniqueConstraint(
            "entity_code",
            "batch_no",
            "metric_key",
            name="uq_quality_finished_trend_alert_notification_key",
        ),
        {"schema": "quality"},
    )

    entity_code: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(256), nullable=False)
    metric_label: Mapped[str] = mapped_column(String(256), nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)
    upper_control_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    lower_control_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recipient_open_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    feishu_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
