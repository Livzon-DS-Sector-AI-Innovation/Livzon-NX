"""Statistics Pydantic schemas."""


from typing import Any

from pydantic import BaseModel


class StepBreakdownItem(BaseModel):
    step: str
    label: str
    roleLabel: str
    count: int


class DeviationStatistics(BaseModel):
    total: int
    pending: int
    closedCount: int
    departmentDistribution: list[dict[str, Any]]
    statusDistribution: list[dict[str, Any]]
    levelDistribution: list[dict[str, Any]]
    rootCauseDistribution: list[dict[str, Any]]
    stepBreakdown: list[StepBreakdownItem]


class CapaStatistics(BaseModel):
    total: int
    closedCount: int
    overdueCount: int
    statusDistribution: list[dict[str, Any]]
    sourceDistribution: list[dict[str, Any]]
    categoryDistribution: list[dict[str, Any]]
    departmentDistribution: list[dict[str, Any]]


class ChangeStatistics(BaseModel):
    total: int
    closedCount: int
    delayCount: int
    statusDistribution: list[dict[str, Any]]
    levelDistribution: list[dict[str, Any]]
    typeDistribution: list[dict[str, Any]]
    departmentDistribution: list[dict[str, Any]]
    actionPlanTotal: int
    actionPlanOverdue: int
    actionPlanConfirmed: int


class ValidationStatistics(BaseModel):
    total: int
    typeDistribution: list[dict[str, Any]]
    statusDistribution: list[dict[str, Any]]
    executionDistribution: list[dict[str, Any]]
    revalidationUpcoming: int
