"""安全设施台账的请求 / 响应模型。"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SafetyFacilityItemInput(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=120)
    result: str = Field(pattern="^(ok|fail)$")
    remark: str = Field(default="", max_length=500)


class SafetyFacilityCreate(BaseModel):
    category: str = Field(
        default="other",
        max_length=30,
        description="类别: eyewash/gas_detector/protective/other",
    )
    facility_no: str = Field(default="", max_length=100, description="设施编号")
    name: str = Field(min_length=1, max_length=200, description="设施名称")
    model_spec: str = Field(default="", max_length=200, description="型号规格")
    department: str = Field(default="", max_length=100, description="所属部门/车间")
    location: str = Field(default="", max_length=255, description="安装位置")
    installed_at: date | None = Field(default=None, description="投用日期")
    expiry_date: date | None = Field(default=None, description="校准/检定/报废到期日")
    status: str = Field(
        default="normal", max_length=20, description="状态: normal/damaged/scrapped"
    )
    remark: str = Field(default="", max_length=8000, description="备注")


class SafetyFacilityUpdate(BaseModel):
    category: str | None = Field(default=None, max_length=30)
    facility_no: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    model_spec: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=255)
    installed_at: date | None = None
    expiry_date: date | None = None
    status: str | None = Field(default=None, max_length=20)
    remark: str | None = Field(default=None, max_length=8000)


class SafetyFacilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: str
    facility_no: str
    name: str
    model_spec: str
    department: str
    location: str
    installed_at: date | None = None
    expiry_date: date | None = None
    status: str
    last_inspected_at: datetime | None = None
    last_inspection_result: str | None = None
    remark: str
    created_at: datetime
    updated_at: datetime


class SafetyFacilityListResponse(BaseModel):
    items: list[SafetyFacilityResponse]
    total: int
    page: int
    page_size: int


class SafetyFacilityChecklistItem(BaseModel):
    key: str
    label: str


class SafetyFacilityChecklistResponse(BaseModel):
    category: str
    items: list[SafetyFacilityChecklistItem] = Field(default_factory=list)


class CreateSafetyFacilityInspectionRequest(BaseModel):
    items: list[SafetyFacilityItemInput] = Field(min_length=1)
    abnormal_action: str = Field(default="", max_length=8000)
    inspected_at: datetime | None = Field(
        default=None, description="点检时间，缺省取当前"
    )
    inspector_name: str = Field(default="", max_length=100)


class SafetyFacilityInspectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    facility_category: str
    facility_no: str
    facility_name: str
    items: list[SafetyFacilityItemInput] = Field(default_factory=list)
    result: str
    abnormal_action: str
    inspector_name: str
    inspected_at: datetime
    source: str
    created_at: datetime


class SafetyFacilityInspectionListResponse(BaseModel):
    items: list[SafetyFacilityInspectionResponse]
    total: int
    page: int
    page_size: int


class SafetyFacilityStatsResponse(BaseModel):
    total: int
    by_category: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    expiring_in_90d: int
    failed_recent: int
