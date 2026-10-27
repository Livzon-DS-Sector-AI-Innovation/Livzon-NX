"""目标责任与绩效的请求 / 响应模型。"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SafetyTargetCreate(BaseModel):
    year: int = Field(ge=2000, le=2100, description="目标年度")
    title: str = Field(min_length=1, max_length=200, description="目标名称")
    category: str = Field(default="事故控制", max_length=40, description="目标类别")
    metric: str = Field(default="", max_length=200, description="考核指标说明")
    target_value: str = Field(default="", max_length=100, description="目标值")
    unit: str = Field(default="", max_length=30, description="计量单位")
    owner_department: str = Field(default="", max_length=100, description="责任部门")
    owner_name: str = Field(default="", max_length=60, description="责任人")
    deadline: date | None = Field(default=None, description="完成时限")
    status: str = Field(
        default="in_progress",
        max_length=20,
        description="状态: in_progress/achieved/not_achieved",
    )
    remark: str = Field(default="", max_length=8000, description="备注")


class SafetyTargetUpdate(BaseModel):
    year: int | None = Field(default=None, ge=2000, le=2100)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=40)
    metric: str | None = Field(default=None, max_length=200)
    target_value: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=30)
    owner_department: str | None = Field(default=None, max_length=100)
    owner_name: str | None = Field(default=None, max_length=60)
    deadline: date | None = None
    status: str | None = Field(default=None, max_length=20)
    remark: str | None = Field(default=None, max_length=8000)


class SafetyTargetRecordCreate(BaseModel):
    period: str = Field(
        min_length=1, max_length=20, description="考核期（如 2026-Q1、2026-03）"
    )
    actual_value: str = Field(default="", max_length=100, description="实际完成值")
    completion_pct: float | None = Field(
        default=None, ge=0, le=1000, description="完成率（%）"
    )
    note: str = Field(default="", max_length=8000, description="情况说明")


class SafetyTargetRecordUpdate(BaseModel):
    actual_value: str | None = Field(default=None, max_length=100)
    completion_pct: float | None = Field(default=None, ge=0, le=1000)
    note: str | None = Field(default=None, max_length=8000)


class SafetyTargetRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_id: UUID
    period: str
    actual_value: str
    completion_pct: float | None = None
    note: str
    created_at: datetime
    updated_at: datetime


class SafetyTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    year: int
    title: str
    category: str
    metric: str
    target_value: str
    unit: str
    owner_department: str
    owner_name: str
    deadline: date | None = None
    status: str
    remark: str
    records: list[SafetyTargetRecordResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SafetyTargetListResponse(BaseModel):
    items: list[SafetyTargetResponse]
    total: int
    page: int
    page_size: int


class SafetyTargetDepartmentStat(BaseModel):
    department: str
    total: int
    achieved: int
    not_achieved: int
    in_progress: int


class SafetyTargetStatsResponse(BaseModel):
    total: int
    achieved: int
    in_progress: int
    not_achieved: int
    categories: list[str] = Field(default_factory=list)
    departments: list[SafetyTargetDepartmentStat] = Field(default_factory=list)
