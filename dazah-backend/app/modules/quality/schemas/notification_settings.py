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
    # 产品QA（每条产品线可单独设置；人员来自人事-飞书联系人目录）。
    # None = 调用方未携带，保存时保留库中已有值（兼容旧调用方）
    qa_recipients: list[QualityNotificationRecipientItem] | None = None


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
    # 成品/纯化水异常升级推送（仅该类型有值）
    first_recipients: list[QualityNotificationRecipientItem] = Field(
        default_factory=list
    )
    escalation_hours: int | None = None
    # 物品库存不足预警推送（仅该类型有值）
    stock_recipients: list[QualityNotificationRecipientItem] = Field(
        default_factory=list
    )
    stock_header_template: str | None = None
    stock_footer_template: str | None = None
    # 预警判定口径：feishu=用飞书"库存报警"字段，local_threshold=当前库存≤警戒库存
    stock_warning_source: str = "feishu"
    # 趋势 AI 月度分析（仅 inspection_trend_alert 有值）
    monthly_day: int | None = None
    manual_rerun_send: bool | None = None


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
    first_recipients: list[QualityNotificationRecipientItem] | None = None
    escalation_hours: int | None = Field(default=None, ge=1, le=72)
    monthly_day: int | None = Field(default=None, ge=1, le=31)
    manual_rerun_send: bool | None = None
    # 物品库存不足预警推送
    stock_recipients: list[QualityNotificationRecipientItem] | None = None
    stock_header_template: str | None = Field(default=None, max_length=500)
    stock_footer_template: str | None = Field(default=None, max_length=500)
    stock_warning_source: str | None = Field(
        default=None, pattern=r"^(feishu|local_threshold)$"
    )
