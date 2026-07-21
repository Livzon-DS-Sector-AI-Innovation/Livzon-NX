"""Review node calculation and stats schemas."""

from typing import Literal

from pydantic import BaseModel


class ReviewNodeConfig(BaseModel):
    index: int
    name: str
    days: int


class NodeCalculation(BaseModel):
    node_index: int
    node_name: str
    days: int
    estimated_date: str | None = None
    estimated_date_with_inspection: str | None = None
    dynamic_estimate: str | None = None
    actual_date: str | None = None
    status: Literal["completed", "in-progress", "pending"]


class StatsResponse(BaseModel):
    total: int
    first_submission: int
    completed_supplement: int
    approved: int
    in_progress: int
