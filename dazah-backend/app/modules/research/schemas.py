"""Research request and response schemas."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ResearchProjectStage = Literal["立项", "研发中试", "验证", "注册", "商业化"]
ResearchProjectStatus = Literal["进行中", "已暂停", "已完成", "已终止"]


class ResearchProjectCreate(BaseModel):
    """创建研发项目请求"""

    project_no: str | None = Field(
        default=None, max_length=50, description="项目编号（可选，不填则自动生成）"
    )
    name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    project_type: str | None = Field(
        default=None, max_length=100, description="项目类型"
    )
    stage: ResearchProjectStage = Field(default="立项", description="项目阶段")
    status: ResearchProjectStatus = Field(default="进行中", description="项目状态")
    leader: str | None = Field(default=None, max_length=100, description="项目负责人")
    start_date: date | None = Field(default=None, description="开始日期")
    end_date: date | None = Field(default=None, description="结束日期")
    description: str | None = Field(default=None, description="项目描述")


class ResearchProjectUpdate(BaseModel):
    """更新研发项目请求"""

    project_no: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    project_type: str | None = Field(default=None, max_length=100)
    stage: ResearchProjectStage | None = None
    status: ResearchProjectStatus | None = None
    leader: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None


class ResearchProjectResponse(BaseModel):
    """研发项目响应"""

    id: uuid.UUID
    project_no: str
    name: str
    project_type: str | None
    stage: str
    status: str
    leader: str | None
    start_date: date | None
    end_date: date | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None

    model_config = {"from_attributes": True}


# ===== Pilot Workflow Schemas =====

PilotWorkflowStatus = Literal[
    "pending", "running", "waiting_approval", "completed", "failed"
]
PilotWorkflowStepStatus = Literal[
    "pending", "running", "waiting_approval", "completed", "failed", "skipped"
]


class PilotWorkflowCreate(BaseModel):
    """创建中试研究"""

    project_id: uuid.UUID | None = Field(default=None, description="关联研发项目ID")
    product_name: str = Field(..., min_length=1, max_length=200, description="产品名称")
    scale_up_ratio: float = Field(..., gt=0, description="放大倍数")
    equipment_type: str = Field(
        ..., min_length=1, max_length=100, description="设备类型"
    )
    equipment_volume: float = Field(..., gt=0, description="设备容积(L)")
    input_context: dict[str, Any] | None = Field(
        default=None, description="额外上下文信息"
    )


class PilotWorkflowStepResponse(BaseModel):
    """工作流步骤响应"""

    id: uuid.UUID
    workflow_id: uuid.UUID
    step_order: int
    step_code: str
    step_name: str
    status: str
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PilotWorkflowResponse(BaseModel):
    """工作流响应"""

    id: uuid.UUID
    project_id: uuid.UUID | None
    product_name: str
    scale_up_ratio: float
    equipment_type: str
    equipment_volume: float
    input_document_path: str | None
    input_context: dict[str, Any] | None
    status: str
    final_report: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    steps: list[PilotWorkflowStepResponse] = []

    model_config = {"from_attributes": True}


class PilotWorkflowListResponse(BaseModel):
    """工作流列表响应"""

    id: uuid.UUID
    product_name: str
    scale_up_ratio: float
    equipment_type: str
    equipment_volume: float
    status: str
    created_at: datetime
    step_count: int = 0
    completed_step_count: int = 0

    model_config = {"from_attributes": True}


# Alias for backward compatibility
PilotWorkflowListItem = PilotWorkflowListResponse
