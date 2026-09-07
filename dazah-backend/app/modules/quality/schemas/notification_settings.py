"""Schemas for quality notification settings."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class QualityNotificationRecipientItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    open_id: str | None = None
    name: str = ""


class InspectionLineNotificationPayload(BaseModel):
    entity_code: str
    entity_label: str = ""
    enabled: bool = True
    recipients: list[QualityNotificationRecipientItem] = Field(default_factory=list)


class QualityNotificationSettingItem(BaseModel):
    notification_type: str
    notification_label: str
    is_enabled: bool
    lead_days: int
    repeat_interval_days: int
    send_time: str
    fallback_recipients: list[QualityNotificationRecipientItem] = Field(
        default_factory=list
    )
    inspection_lines: list[InspectionLineNotificationPayload] = Field(
        default_factory=list
    )


class UpdateQualityNotificationSettingRequest(BaseModel):
    is_enabled: bool = True
    lead_days: int | None = Field(default=None, ge=0, le=365)
    repeat_interval_days: int | None = Field(default=None, ge=1, le=30)
    send_time: str | None = Field(
        default=None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="每天发送时间 HH:MM（Asia/Shanghai）",
    )
    fallback_recipients: list[QualityNotificationRecipientItem] | None = None
    inspection_lines: list[InspectionLineNotificationPayload] | None = None
