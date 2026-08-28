"""Inspection dashboard schemas."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class InspectionDashboardResourceSummary(BaseModel):
    """Legacy local-resource summary retained for the compatibility API."""

    resource_code: str
    resource_name: str
    total: int = 0
    qualified: int = 0
    attention_required: int = 0


class InspectionDashboardLatestRecord(BaseModel):
    """Legacy latest-record projection retained for the compatibility API."""

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


class LegacyInspectionDashboardResponse(BaseModel):
    """Response shape used by the pre-migration local dashboard endpoint."""

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


class InspectionDashboardSpecLine(BaseModel):
    label: str
    value: float


class InspectionDashboardPoint(BaseModel):
    batch_no: str
    value: float


class InspectionDashboardChartSummary(BaseModel):
    sample_count: int
    mean: float | None = None
    std_dev: float | None = None
    upper_control_limit: float | None = None
    lower_control_limit: float | None = None


class InspectionDashboardChart(BaseModel):
    metric_key: str
    metric_label: str
    categories: list[str]
    actual_series: list[float | None]
    mean_series: list[float | None]
    upper_sigma_series: list[float | None]
    lower_sigma_series: list[float | None]
    spec_lines: list[InspectionDashboardSpecLine]
    points: list[InspectionDashboardPoint]
    summary: InspectionDashboardChartSummary


class InspectionDashboardAlert(BaseModel):
    entity_code: str
    batch_no: str
    metric_key: str
    metric_label: str
    actual_value: float
    mean: float | None = None
    std_dev: float | None = None
    upper_control_limit: float | None = None
    lower_control_limit: float | None = None
    spec_lines: list[InspectionDashboardSpecLine]
    recipient_name: str | None = None
    recipient_open_id: str | None = None
    notification_status: str
    notification_sent: bool
    notification_deduplicated: bool
    notification_error: str | None = None
    feishu_message_id: str | None = None
    notified_at: str | None = None


class InspectionDashboardSummary(BaseModel):
    source_entity_code: str
    source_label: str
    total_records: int
    valid_record_count: int
    skipped_value_count: int
    alert_batch_count: int
    alert_metric_count: int
    first_notification_sent_count: int
    deduplicated_notification_count: int
    failed_notification_count: int
    unmapped_notification_count: int


class InspectionDashboardData(BaseModel):
    source_entity_code: str
    source_label: str
    charts: list[InspectionDashboardChart]
    alerts: list[InspectionDashboardAlert]
    summary: InspectionDashboardSummary
    configured: bool = True


class InspectionDashboardMeta(BaseModel):
    configured: bool


class InspectionDashboardResponse(BaseModel):
    data: InspectionDashboardData
    meta: InspectionDashboardMeta
