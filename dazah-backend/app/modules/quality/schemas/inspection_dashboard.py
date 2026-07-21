"""API contracts for quality inspection overview and trend analysis."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class InspectionDashboardResourceSummary(BaseModel):
    resource_code: str
    resource_name: str
    total: int = 0
    qualified: int = 0
    attention_required: int = 0


class InspectionDashboardLatestRecord(BaseModel):
    id: UUID
    resource_code: str
    resource_name: str
    inspection_no: str | None = None
    subject: str | None = None
    batch_no: str | None = None
    inspection_item: str | None = None
    test_result: str | None = None
    specification: str | None = None
    conclusion: str | None = None
    inspection_date: date | None = None
    created_at: datetime


class InspectionDashboardResponse(BaseModel):
    resource_summaries: list[InspectionDashboardResourceSummary]
    latest_records: list[InspectionDashboardLatestRecord]


class InspectionTrendPoint(BaseModel):
    record_id: UUID
    label: str
    subject: str | None = None
    inspection_date: date | None = None
    value: float
    specification: str | None = None
    lower_specification_limit: float | None = None
    upper_specification_limit: float | None = None
    is_alert: bool = False


class InspectionTrendAlert(BaseModel):
    record_id: UUID
    label: str
    subject: str | None = None
    actual_value: float
    alert_type: str
    message: str


class InspectionTrendSummary(BaseModel):
    sample_count: int = 0
    mean: float | None = None
    standard_deviation: float | None = None
    lower_control_limit: float | None = None
    upper_control_limit: float | None = None
    alert_count: int = 0


class InspectionTrendResponse(BaseModel):
    resource_code: str
    resource_name: str
    subject: str | None = None
    inspection_item: str | None = None
    points: list[InspectionTrendPoint]
    alerts: list[InspectionTrendAlert]
    summary: InspectionTrendSummary


class InspectionFeishuSyncResponse(BaseModel):
    resource_code: str
    entity_code: str
    record_id: str
    table_id: str
    synced_at: datetime = Field(description="平台向飞书完成单条推送的时间")
