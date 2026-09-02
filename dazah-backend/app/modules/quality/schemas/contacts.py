"""Department contacts Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DepartmentContactOut(BaseModel):
    id: uuid.UUID
    name: str | None = None
    department: str
    enterprise_email: str | None = None
    open_id: str | None = None
    department_head_name: str | None = None
    department_head_enterprise_email: str | None = None
    department_head_open_id: str | None = None
    feishu_record_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeishuDepartmentContactOut(BaseModel):
    """飞书多维表直读的部门联系人输出 schema"""

    id: str
    name: str | None = None
    avatar_url: str | None = None
    bitable_user_id: str | None = None
    department: str = ""
    enterprise_email: str | None = None
    open_id: str | None = None
    department_head_name: str | None = None
    department_head_avatar_url: str | None = None
    department_head_bitable_user_id: str | None = None
    department_head_enterprise_email: str | None = None
    department_head_open_id: str | None = None
    feishu_record_id: str | None = None
    created_at: str = ""
    updated_at: str = ""


class UpdateFeishuDepartmentContactRequest(BaseModel):
    """更新飞书多维表部门联系人整条记录的请求

    人员身份来自人事管理下同步的飞书联系人（open_id）；后端负责把 open_id
    解析为该多维表人员字段可用的 id 后写回。
    """

    open_id: str | None = None
    department_head_open_id: str | None = None
    department: str | None = None
    enterprise_email: str | None = None


class CreateDepartmentContactRequest(BaseModel):
    name: str
    department: str
    enterprise_email: str | None = None
    open_id: str | None = None
    department_head_name: str | None = None
    department_head_enterprise_email: str | None = None
    department_head_open_id: str | None = None
    feishu_record_id: str | None = None


class UpdateDepartmentContactRequest(BaseModel):
    name: str | None = None
    department: str | None = None
    enterprise_email: str | None = None
    open_id: str | None = None
    department_head_name: str | None = None
    department_head_enterprise_email: str | None = None
    department_head_open_id: str | None = None
    feishu_record_id: str | None = None


class DepartmentWeeklyConfirmationOut(BaseModel):
    id: uuid.UUID
    department: str
    week_key: str
    production_status: str
    deviation_status: str
    confirmed_by_id: uuid.UUID | None = None
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConfirmProductionStatusRequest(BaseModel):
    department: str
    week_key: str
    production_status: str
    deviation_status: str = "unsubmitted"
