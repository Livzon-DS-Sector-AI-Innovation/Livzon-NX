"""合同管理模块 Schemas"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContractManagementCreate(BaseModel):
    employee_number: str = Field(..., max_length=32)
    name: str = Field(..., max_length=64)
    gender: str | None = Field(None, max_length=4)
    dept_level1: str | None = Field(None, max_length=64)
    dept_level2: str | None = Field(None, max_length=64)
    position: str | None = Field(None, max_length=64)
    job_level: str | None = Field(None, max_length=32)
    domain_account: str | None = Field(None, max_length=64)
    id_card: str | None = Field(None, max_length=32)
    id_card_expiry: str | None = Field(None, max_length=32)
    archive_number: str | None = Field(None, max_length=64)
    contract_sequence: str | None = Field(None, max_length=8)
    contract_start_1: date | None = None
    contract_end_1: date | None = None
    contract_start_2: date | None = None
    contract_end_2: str | None = Field(None, max_length=32)
    contract_start_3: date | None = None
    contract_end_3: str | None = Field(None, max_length=32)
    contract_start_4: date | None = None
    contract_end_4: str | None = Field(None, max_length=32)
    contract_start_5: date | None = None
    contract_end_5: str | None = Field(None, max_length=32)
    contract_start_6: str | None = Field(None, max_length=32)
    contract_end_6: str | None = Field(None, max_length=32)


class ContractManagementUpdate(ContractManagementCreate):
    employee_number: str | None = Field(  # type: ignore[assignment]  # update payload is partial
        None, max_length=32
    )
    name: str | None = Field(  # type: ignore[assignment]  # update payload is partial
        None, max_length=64
    )


class ContractManagementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    employee_number: str
    name: str
    gender: str | None = None
    dept_level1: str | None = None
    dept_level2: str | None = None
    position: str | None = None
    job_level: str | None = None
    domain_account: str | None = None
    id_card: str | None = None
    id_card_expiry: str | None = None
    archive_number: str | None = None
    contract_sequence: str | None = None
    contract_start_1: date | None = None
    contract_end_1: date | None = None
    contract_start_2: date | None = None
    contract_end_2: str | None = None
    contract_start_3: date | None = None
    contract_end_3: str | None = None
    contract_start_4: date | None = None
    contract_end_4: str | None = None
    contract_start_5: date | None = None
    contract_end_5: str | None = None
    contract_start_6: str | None = None
    contract_end_6: str | None = None
    dept_leader_name: str | None = None
    contract_opinion: str | None = None
    approval_status: str | None = None
    supervisor_name: str | None = None
    supervisor_open_id: str | None = None
    dept_approved_at: datetime | None = None
    supervisor_approved_at: datetime | None = None
    signed_status: str | None = None
    signed_at: datetime | None = None
    sign_reminded_at: datetime | None = None
    feishu_record_id: str | None = None
    feishu_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ContractApprovalCallback(BaseModel):
    """飞书卡片按钮回调"""

    employee_number: str
    employee_name: str
    action: str  # "approve" 或 "reject"
    leader_name: str | None = None
    stage: str = "dept"  # dept=部门负责人 / supervisor=分管领导
    token: str = ""


class ContractSignStatusRequest(BaseModel):
    """标记合同签署状态"""

    signed_status: str = Field(..., description="已签署/拒签")


class ContractApprovalResultItem(BaseModel):
    """审批结果列表项"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    employee_number: str
    name: str
    dept_level1: str | None = None
    dept_level2: str | None = None
    contract_sequence: str | None = None
    contract_end_date: str | None = None
    approval_status: str | None = None
    contract_opinion: str | None = None
    dept_leader_name: str | None = None
    supervisor_name: str | None = None
    dept_approved_at: datetime | None = None
    supervisor_approved_at: datetime | None = None
    signed_status: str | None = None
    signed_at: datetime | None = None
    created_at: datetime | None = None


class ContractRenewRequest(BaseModel):
    """续签合同日期填写请求"""

    start_date: str = Field(..., description="续签开始日期，格式 YYYY-MM-DD")
    end_date: str = Field(..., description="续签截止日期，格式 YYYY-MM-DD")
