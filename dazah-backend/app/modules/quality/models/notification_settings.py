"""Quality notification settings models."""

from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class QualityNotificationSetting(BaseModel):
    """质量模块通知设置（按通知类型一行）。

    recipients 的 JSON 形状按 notification_type 约定：
    - change_action_plan_due: {"fallback_recipients": [{"open_id", "name"}]}
    - inspection_trend_alert: {"lines": {"<entity_code>": {"enabled", "recipients",
      "qa_recipients"}}}
    - inspection_trend_alert_escalation: {"first_recipients": [{"open_id", "name"}],
      "escalation_hours": int}
    - items_stock_alert: {"recipients": [...], "header_template", "footer_template",
      "warning_source"}
    """

    __tablename__ = "quality_notification_settings"
    __table_args__ = (
        UniqueConstraint(
            "notification_type",
            name="uq_quality_notification_settings_notification_type",
        ),
        {"schema": "quality"},
    )

    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    notification_label: Mapped[str] = mapped_column(String(100), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    lead_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default="3",
    )
    repeat_interval_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    send_time: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="09:00",
        server_default="09:00",
    )
    recipients: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
