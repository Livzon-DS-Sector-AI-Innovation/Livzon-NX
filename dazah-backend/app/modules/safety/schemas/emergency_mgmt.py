"""应急管理（预案 / 演练 / 物资）的请求 / 响应模型。"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------- 应急预案 ----------


class EmergencyPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="预案名称")
    plan_type: str = Field(
        default="onsite",
        max_length=30,
        description="类型: comprehensive/special/onsite",
    )
    version: str = Field(default="V1.0", max_length=60, description="版本号")
    issued_at: date | None = Field(default=None, description="发布日期")
    review_due_date: date | None = Field(default=None, description="下次评审到期日")
    status: str = Field(
        default="active", max_length=20, description="状态: active/revising/obsolete"
    )
    department: str = Field(default="", max_length=100, description="编制/归口部门")
    remark: str = Field(default="", max_length=8000, description="备注")


class EmergencyPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    plan_type: str | None = Field(default=None, max_length=30)
    version: str | None = Field(default=None, max_length=60)
    issued_at: date | None = None
    review_due_date: date | None = None
    status: str | None = Field(default=None, max_length=20)
    department: str | None = Field(default=None, max_length=100)
    remark: str | None = Field(default=None, max_length=8000)


class EmergencyPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    plan_type: str
    version: str
    issued_at: date | None = None
    review_due_date: date | None = None
    status: str
    department: str
    file_path: str
    file_name: str
    remark: str
    created_at: datetime
    updated_at: datetime


class EmergencyPlanListResponse(BaseModel):
    items: list[EmergencyPlanResponse]
    total: int
    page: int
    page_size: int


# ---------- 应急演练 ----------


class EmergencyDrillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="演练名称")
    drill_type: str = Field(
        default="practical",
        max_length=30,
        description="类型: tabletop/practical/comprehensive",
    )
    scenario: str = Field(default="", max_length=255, description="演练情景")
    plan_name: str = Field(default="", max_length=255, description="对应预案名称")
    planned_date: date | None = Field(default=None, description="计划日期")
    actual_date: date | None = Field(default=None, description="实际执行日期")
    location: str = Field(default="", max_length=255, description="演练地点")
    departments: str = Field(default="", max_length=500, description="参演部门")
    participants_count: int | None = Field(default=None, ge=0, description="参演人数")
    summary: str = Field(default="", max_length=8000, description="演练总结")
    issues: str = Field(default="", max_length=8000, description="问题与改进")
    status: str = Field(
        default="planned", max_length=20, description="状态: planned/done/cancelled"
    )


class EmergencyDrillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    drill_type: str | None = Field(default=None, max_length=30)
    scenario: str | None = Field(default=None, max_length=255)
    plan_name: str | None = Field(default=None, max_length=255)
    planned_date: date | None = None
    actual_date: date | None = None
    location: str | None = Field(default=None, max_length=255)
    departments: str | None = Field(default=None, max_length=500)
    participants_count: int | None = Field(default=None, ge=0)
    summary: str | None = Field(default=None, max_length=8000)
    issues: str | None = Field(default=None, max_length=8000)
    status: str | None = Field(default=None, max_length=20)


class EmergencyDrillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    drill_type: str
    scenario: str
    plan_name: str
    planned_date: date | None = None
    actual_date: date | None = None
    location: str
    departments: str
    participants_count: int | None = None
    summary: str
    issues: str
    status: str
    created_at: datetime
    updated_at: datetime


class EmergencyDrillListResponse(BaseModel):
    items: list[EmergencyDrillResponse]
    total: int
    page: int
    page_size: int


# ---------- 应急物资 ----------


class EmergencySupplyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="物资名称")
    category: str = Field(
        default="other",
        max_length=30,
        description="类别: firefighting/protective/medical/communication/"
        "leak_sealing/other",
    )
    spec: str = Field(default="", max_length=200, description="规格型号")
    location: str = Field(default="", max_length=255, description="存放位置")
    department: str = Field(default="", max_length=100, description="管理部门")
    quantity: float = Field(default=0, ge=0, description="数量")
    unit: str = Field(default="件", max_length=30, description="单位")
    status: str = Field(
        default="good", max_length=20, description="状态: good/repair/scrapped"
    )
    expiry_date: date | None = Field(default=None, description="有效期至")
    last_checked_at: date | None = Field(default=None, description="最近检查日期")
    last_check_result: str = Field(
        default="", max_length=255, description="最近检查结论"
    )
    remark: str = Field(default="", max_length=8000, description="备注")


class EmergencySupplyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=30)
    spec: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=100)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=30)
    status: str | None = Field(default=None, max_length=20)
    expiry_date: date | None = None
    last_checked_at: date | None = None
    last_check_result: str | None = Field(default=None, max_length=255)
    remark: str | None = Field(default=None, max_length=8000)


class EmergencySupplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    category: str
    spec: str
    location: str
    department: str
    quantity: float
    unit: str
    status: str
    expiry_date: date | None = None
    last_checked_at: date | None = None
    last_check_result: str
    remark: str
    created_at: datetime
    updated_at: datetime


class EmergencySupplyListResponse(BaseModel):
    items: list[EmergencySupplyResponse]
    total: int
    page: int
    page_size: int


# ---------- 汇总统计 ----------


class EmergencyMgmtStatsResponse(BaseModel):
    plans_total: int
    plans_active: int
    plans_review_due_30d: int
    drills_total: int
    drills_planned: int
    drills_done: int
    drills_due_30d: int
    supplies_total: int
    supplies_abnormal: int
    supplies_by_category: dict[str, int] = Field(default_factory=dict)
