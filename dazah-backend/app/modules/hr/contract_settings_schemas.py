"""HR通用提醒配置 + 审批流程配置 schemas"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _empty_list(v: Any) -> Any:
    """兼容数据库历史 NULL 值"""
    return v if v is not None else []


class ReminderConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_code: str
    entity_label: str
    module_group: str
    reminder_type: str
    reminder_label: str
    reminder_days: list[int] = Field(default=[90, 60, 30])
    recipient_open_ids: list[str] = Field(default=[])
    dept_notify_enabled: bool = False
    trigger_frequency: str = "monthly"
    trigger_day: int = 1
    trigger_hour: int = 9
    notify_hours: int = Field(
        default=24, ge=1, le=72, description="离职记录创建后多少小时提醒(最大72)"
    )
    message_template: str = Field(default="", description="提醒消息模板")
    sign_clerk_open_ids: list[str] = Field(
        default=[],
        description="签署办事员open_id列表（合同续签实体，为空回退recipient_open_ids）",
    )
    sign_clerk_names: list[str] = Field(default=[], description="签署办事员姓名列表")
    sign_reminder_days: int = Field(
        default=7, ge=1, le=365, description="合同签署催签间隔天数（默认7天）"
    )
    is_enabled: bool = True
    sort_order: int = 0

    _norm_clerk_ids = field_validator("sign_clerk_open_ids", mode="before")(_empty_list)
    _norm_clerk_names = field_validator("sign_clerk_names", mode="before")(_empty_list)
    _norm_recipient_ids = field_validator("recipient_open_ids", mode="before")(
        _empty_list
    )
    _norm_reminder_days = field_validator("reminder_days", mode="before")(_empty_list)


class ReminderConfigUpdate(BaseModel):
    reminder_days: list[int] = Field(default=[90, 60, 30])
    recipient_open_ids: list[str] = Field(default=[])
    dept_notify_enabled: bool = False
    trigger_frequency: str = "monthly"
    trigger_day: int = 1
    trigger_hour: int = 9
    notify_hours: int = Field(
        default=24, ge=1, le=72, description="离职记录创建后多少小时提醒(最大72)"
    )
    sign_clerk_open_ids: list[str] = Field(
        default=[], description="签署办事员open_id列表"
    )
    sign_clerk_names: list[str] = Field(default=[], description="签署办事员姓名列表")
    sign_reminder_days: int = Field(
        default=7, ge=1, le=365, description="合同签署催签间隔天数"
    )
    is_enabled: bool = True


class ApprovalConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_code: str
    entity_label: str
    module_group: str
    role: str
    role_label: str
    approver_open_ids: list[str] = Field(default=[])
    approver_names: list[str] = Field(default=[])
    deadline_days: int | None = None
    sort_order: int = 0


class ApprovalConfigUpdate(BaseModel):
    approver_open_ids: list[str] = Field(default=[])
    approver_names: list[str] = Field(default=[])
    deadline_days: int | None = None


class DeptRecipientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reminder_config_id: UUID
    department: str
    recipient_open_ids: list[str] = Field(default=[])
    recipient_names: list[str] = Field(default=[])
    use_dept_leader: bool = True


class DeptRecipientUpdate(BaseModel):
    recipient_open_ids: list[str] = Field(default=[])
    recipient_names: list[str] = Field(default=[])
    use_dept_leader: bool = True


class DeptRecipientCreate(BaseModel):
    reminder_config_id: str
    department: str
    recipient_open_ids: list[str] = Field(default=[])
    recipient_names: list[str] = Field(default=[])
    use_dept_leader: bool = True
