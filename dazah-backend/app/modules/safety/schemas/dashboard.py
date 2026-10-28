"""总览驾驶舱聚合（地图落点/超储/近7日统计）的响应模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CampusBuildingItem(BaseModel):
    id: UUID
    code: str
    name: str
    category: str
    x_pct: float
    y_pct: float


class MapRiskItem(BaseModel):
    """一条落点风险信息（按来源表快照）。"""

    source: str = Field(description="来源: special_op / daily_risk / accident / hazard")
    title: str = Field(default="", description="摘要（作业内容/事故类型/隐患描述截断）")
    location_text: str = Field(default="", description="原始地点/部门文本")
    building_id: UUID | None = Field(
        default=None, description="归一到的建筑，未映射为 None"
    )
    matched_by: str = Field(
        default="location",
        description="落点依据: location=地点文本匹配 / department=部门兜底匹配",
    )
    department: str = ""
    risk_level: str = ""
    operation_type: str = ""
    happened_at: datetime | None = None
    detail_url: str = Field(default="", description="前端跳转路径")


class MapBuildingMarkers(BaseModel):
    building_id: UUID
    name: str
    x_pct: float
    y_pct: float
    total: int
    levels: dict[str, int] = Field(default_factory=dict, description="风险等级计数")
    items: list[MapRiskItem] = Field(default_factory=list)


class UnmappedRiskGroup(BaseModel):
    location_text: str
    total: int
    items: list[MapRiskItem] = Field(default_factory=list)


class WeeklyOperationTypeCount(BaseModel):
    operation_type: str
    total: int


class OverLimitChemicalItem(BaseModel):
    inventory_id: UUID
    chemical_name: str
    workshop: str
    quantity: float
    upper_limit: float | None = None
    over_pct: float | None = None
    unit: str = ""


class SafetyOverviewResponse(BaseModel):
    buildings: list[CampusBuildingItem] = Field(default_factory=list)
    markers: list[MapBuildingMarkers] = Field(default_factory=list)
    unmapped: list[UnmappedRiskGroup] = Field(default_factory=list)
    source_totals: dict[str, int] = Field(
        default_factory=dict,
        description="当日各来源总数（special_op/daily_risk/accident/hazard），"
        "与 markers+unmapped 总数核对一致性",
    )
    over_limit_chemicals: list[OverLimitChemicalItem] = Field(default_factory=list)
    weekly_operation_types: list[WeeklyOperationTypeCount] = Field(default_factory=list)
    open_hazard_count: int = 0
    generated_at: datetime | None = None
