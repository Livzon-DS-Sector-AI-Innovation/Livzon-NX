"""Statistics Pydantic schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CamelAliasModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class StatDistributionItem(CamelAliasModel):
    name: str
    count: int


class MonthlyTrendPoint(CamelAliasModel):
    month: str
    count: int


class DeviationStatistics(CamelAliasModel):
    total: int
    closed_count: int = Field(alias="closedCount")
    major_count: int = Field(alias="majorCount")
    level_distribution: list[StatDistributionItem] = Field(alias="levelDistribution")
    department_distribution: list[StatDistributionItem] = Field(
        alias="departmentDistribution"
    )
    root_cause_distribution: list[StatDistributionItem] = Field(
        alias="rootCauseDistribution"
    )
    monthly_trend: list[MonthlyTrendPoint] = Field(alias="monthlyTrend")


class CapaStatistics(CamelAliasModel):
    """CAPA 台账统计：按台账列口径（本地台账数据源）。"""

    total: int
    closed_count: int = Field(alias="closedCount")
    in_progress_count: int = Field(alias="inProgressCount")
    result_distribution: list[dict[str, Any]] = Field(alias="resultDistribution")
    department_distribution: list[dict[str, Any]] = Field(
        alias="departmentDistribution"
    )
    monthly_trend: list[dict[str, Any]] = Field(alias="monthlyTrend")


class ChangeStatistics(CamelAliasModel):
    total: int
    closed_count: int = Field(alias="closedCount")
    delay_count: int = Field(alias="delayCount")
    status_distribution: list[dict[str, Any]] = Field(alias="statusDistribution")
    level_distribution: list[dict[str, Any]] = Field(alias="levelDistribution")
    type_distribution: list[dict[str, Any]] = Field(alias="typeDistribution")
    department_distribution: list[dict[str, Any]] = Field(
        alias="departmentDistribution"
    )
    action_plan_total: int = Field(alias="actionPlanTotal")
    action_plan_overdue: int = Field(alias="actionPlanOverdue")
    action_plan_confirmed: int = Field(alias="actionPlanConfirmed")


class ValidationStatistics(CamelAliasModel):
    total: int
    type_distribution: list[dict[str, Any]] = Field(alias="typeDistribution")
    status_distribution: list[dict[str, Any]] = Field(alias="statusDistribution")
    execution_distribution: list[dict[str, Any]] = Field(alias="executionDistribution")
    revalidation_upcoming: int = Field(alias="revalidationUpcoming")
