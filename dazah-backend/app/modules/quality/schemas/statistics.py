"""Statistics Pydantic schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CamelAliasModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class StepBreakdownItem(CamelAliasModel):
    step: str
    label: str
    role_label: str = Field(alias="roleLabel")
    count: int


class DeviationStatistics(CamelAliasModel):
    total: int
    pending: int
    closed_count: int = Field(alias="closedCount")
    capa_total: int = Field(alias="capaTotal")
    department_distribution: list[dict[str, Any]] = Field(
        alias="departmentDistribution"
    )
    status_distribution: list[dict[str, Any]] = Field(alias="statusDistribution")
    level_distribution: list[dict[str, Any]] = Field(alias="levelDistribution")
    root_cause_distribution: list[dict[str, Any]] = Field(alias="rootCauseDistribution")
    step_breakdown: list[StepBreakdownItem] = Field(alias="stepBreakdown")
    monthly_trend: list[dict[str, Any]] = Field(alias="monthlyTrend")


class CapaStatistics(CamelAliasModel):
    total: int
    closed_count: int = Field(alias="closedCount")
    overdue_count: int = Field(alias="overdueCount")
    status_distribution: list[dict[str, Any]] = Field(alias="statusDistribution")
    source_distribution: list[dict[str, Any]] = Field(alias="sourceDistribution")
    category_distribution: list[dict[str, Any]] = Field(alias="categoryDistribution")
    department_distribution: list[dict[str, Any]] = Field(
        alias="departmentDistribution"
    )


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
