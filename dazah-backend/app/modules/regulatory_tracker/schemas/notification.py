"""Notification schemas for regulatory tracker."""

from pydantic import BaseModel, Field


class RegulatoryTrackerNotificationRecipientOption(BaseModel):
    """法规跟踪推送接收人选项。"""

    open_id: str = Field(..., description="飞书 open_id")
    name: str = Field(..., description="联系人姓名")
    department: str | None = Field(None, description="所属部门")
    enterprise_email: str | None = Field(None, description="企业邮箱")


class RegulatoryTrackerNotificationSettingUpdate(BaseModel):
    """法规跟踪推送配置更新入参。"""

    is_enabled: bool = Field(..., description="是否启用每日自动抓取推送")
    recent_days: int = Field(..., ge=1, le=30, description="自动抓取最近天数窗口")
    recipient_open_id: str | None = Field(None, description="接收人飞书 open_id")


class RegulatoryTrackerNotificationSettingRead(BaseModel):
    """法规跟踪推送配置响应。"""

    is_enabled: bool = Field(..., description="是否启用每日自动抓取推送")
    recent_days: int = Field(..., description="自动抓取最近天数窗口")
    recipient_open_id: str | None = Field(None, description="接收人飞书 open_id")
    recipient_name: str | None = Field(None, description="接收人姓名")
    recipient_department: str | None = Field(None, description="接收人部门")
    schedule_time: str = Field(..., description="每日固定执行时间")
    pending_count: int = Field(..., description="当前配置下待推送的更新数")
