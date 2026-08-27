"""HR推送设置 schemas - 推送模板、接收人配置、推送记录、发送通知"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PushTemplateResponse(BaseModel):
    """推送模板响应"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_code: str
    scene_code: str
    scene_label: str
    channel: str
    title_template: str
    body_template: str
    available_variables: list[str] = []
    is_enabled: bool = True


class PushTemplateUpdate(BaseModel):
    """推送模板更新"""

    title_template: str | None = None
    body_template: str | None = None
    is_enabled: bool | None = None


class PushRecipientResponse(BaseModel):
    """推送接收人配置响应"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_code: str
    scene_code: str
    channel: str
    department: str | None = None
    recipient_open_ids: list[str] = []
    recipient_names: list[str] = []
    use_dept_leader: bool = True
    is_enabled: bool = True


class PushRecipientUpdate(BaseModel):
    """推送接收人配置更新"""

    recipient_open_ids: list[str] = Field(default=[])
    recipient_names: list[str] = Field(default=[])
    use_dept_leader: bool | None = None
    is_enabled: bool | None = None


class PushTestRequest(BaseModel):
    """手动测试推送"""

    template_id: UUID
    recipient: str
    test_variables: dict[str, Any] = Field(default_factory=dict)


class PushLogResponse(BaseModel):
    """推送记录响应"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_code: str
    scene_code: str
    channel: str
    recipient: str
    recipient_name: str | None = None
    title: str
    content_snippet: str | None = None
    status: str
    error_message: str | None = None
    sent_at: datetime | None = None
    candidate_id: str | None = None
    candidate_name: str | None = None
    triggered_by: str | None = None
    created_at: datetime | None = None


class SendNoticeRequest(BaseModel):
    """发送面试通知/Offer通知请求"""

    scene_code: str  # interview_notice / offer_notice


class SendNoticeResult(BaseModel):
    """发送通知结果"""

    scene_code: str
    scene_label: str
    email_sent: bool = False
    email_recipient: str | None = None
    email_error: str | None = None
    feishu_sent: bool = False
    feishu_recipients: list[str] = []
    feishu_errors: list[str] = []
