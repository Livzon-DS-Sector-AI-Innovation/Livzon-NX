"""Energy request and response schemas live here."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

StrUUID = Annotated[str, BeforeValidator(str)]
EnergyType = Literal["electricity", "water", "gas"]
MonitorLevel = Literal["normal", "important", "urgent"]
CollectStatus = Literal["success", "partial", "failed"]
SheetSourceRole = Literal[
    "workshop_detail",
    "shared_detail",
    "energy_summary",
    "daily_summary",
]
SHEET_TITLE_DIMENSION = "$sheet_title"


class EnergyDeviceConfigCreate(BaseModel):
    platform_code: str = Field(..., min_length=1, max_length=50, description="平台标识")
    platform_device_code: str = Field(
        ..., min_length=1, max_length=100, description="三方平台设备编码"
    )
    device_name: str = Field(..., min_length=1, max_length=200, description="设备名称")
    energy_type: EnergyType = Field(..., description="能源类型")
    api_endpoint: str = Field(default="", max_length=500, description="API 路径")
    workshop: str = Field(..., min_length=1, max_length=100, description="所属车间")
    production_line: str | None = Field(
        default=None, max_length=100, description="所属产线"
    )
    monitor_level: MonitorLevel = Field(default="normal", description="监控等级")
    unit: str = Field(..., min_length=1, max_length=20, description="计量单位")
    collection_interval: int = Field(default=60, ge=1, description="采集间隔(分钟)")
    is_enabled: bool = Field(default=True, description="是否启用采集")
    remark: str | None = Field(default=None, max_length=500, description="备注")


class EnergyDeviceConfigUpdate(BaseModel):
    platform_code: str | None = Field(default=None, min_length=1, max_length=50)
    platform_device_code: str | None = Field(default=None, min_length=1, max_length=100)
    device_name: str | None = Field(default=None, min_length=1, max_length=200)
    energy_type: EnergyType | None = Field(default=None)
    api_endpoint: str = Field(default="", max_length=500)
    workshop: str | None = Field(default=None, min_length=1, max_length=100)
    production_line: str | None = Field(default=None, max_length=100)
    monitor_level: MonitorLevel | None = Field(default=None)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    collection_interval: int | None = Field(default=None, ge=1)
    is_enabled: bool | None = Field(default=None)
    remark: str | None = Field(default=None, max_length=500)


class EnergyDeviceConfigResponse(BaseModel):
    id: StrUUID
    platform_code: str
    platform_device_code: str
    device_name: str
    energy_type: str
    api_endpoint: str
    workshop: str
    production_line: str | None
    monitor_level: str
    unit: str
    collection_interval: int
    is_enabled: bool
    remark: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnergyDataResponse(BaseModel):
    id: StrUUID
    device_config_id: StrUUID
    timestamp: datetime
    value: float
    unit: str
    collected_at: datetime

    model_config = {"from_attributes": True}


class EnergyStatisticsResponse(BaseModel):
    group_key: str = Field(description="分组键(车间/产线/设备名)")
    total_value: float = Field(description="能耗合计")
    unit: str = Field(description="计量单位")
    data_count: int = Field(description="数据条数")


class CollectLogResponse(BaseModel):
    id: StrUUID
    platform_code: str
    collect_time: datetime
    status: str
    device_count: int
    success_count: int
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CollectLogDeviceDetail(BaseModel):
    """采集日志中单个设备的数据详情"""

    device_name: str = Field(description="设备名称")
    platform_device_code: str = Field(description="平台设备编码")
    energy_type: str = Field(description="能源类型")
    value: float = Field(description="采集值")
    unit: str = Field(description="计量单位")
    data_timestamp: datetime = Field(description="数据时间点")


class CollectLogDetailResponse(BaseModel):
    """采集日志详情响应"""

    id: StrUUID
    platform_code: str
    collect_time: datetime
    status: str
    device_count: int
    success_count: int
    error_message: str | None
    created_at: datetime
    devices: list[CollectLogDeviceDetail] = Field(
        default_factory=list, description="设备数据详情列表"
    )
    time_range_start: datetime | None = Field(
        default=None, description="数据覆盖起始时间"
    )
    time_range_end: datetime | None = Field(
        default=None, description="数据覆盖结束时间"
    )


class CollectTriggerRequest(BaseModel):
    platform_code: str | None = Field(
        default=None,
        description="指定平台，为空则采集所有平台",
    )


# ── 预警系统 ──

AlertLevel = Literal["info", "warning", "critical", "emergency"]
MonitorMetric = Literal["instant", "daily_total", "monthly_total"]
ThresholdType = Literal["greater_than", "less_than", "equal"]
NotifyFrequency = Literal["first", "every", "daily_summary"]
EffectiveTime = Literal["all_day", "custom"]
AlertRecordStatus = Literal["pending", "processed", "ignored"]


class EnergyAlertRuleCreate(BaseModel):
    rule_name: str = Field(..., min_length=1, max_length=200, description="规则名称")
    rule_description: str | None = Field(
        default=None, max_length=500, description="规则描述"
    )
    energy_type: EnergyType = Field(..., description="能源类型")
    monitor_metric: MonitorMetric = Field(..., description="监控指标")
    threshold_type: ThresholdType = Field(..., description="阈值类型")
    threshold_value: float = Field(..., gt=0, description="阈值")
    unit: str = Field(..., min_length=1, max_length=20, description="计量单位")
    alert_level: AlertLevel = Field(..., description="预警等级")
    notify_method: list[str] = Field(..., min_length=1, description="通知方式")
    notify_users: list[str] = Field(..., min_length=1, description="通知用户列表")
    notify_frequency: NotifyFrequency = Field(default="first", description="通知频率")
    effective_time: EffectiveTime = Field(default="all_day", description="生效时段类型")
    custom_time_start: str | None = Field(default=None, description="自定义开始时间")
    custom_time_end: str | None = Field(default=None, description="自定义结束时间")
    is_enabled: bool = Field(default=True, description="是否启用")


class EnergyAlertRuleUpdate(BaseModel):
    rule_name: str | None = Field(default=None, min_length=1, max_length=200)
    rule_description: str | None = Field(default=None, max_length=500)
    energy_type: EnergyType | None = Field(default=None)
    monitor_metric: MonitorMetric | None = Field(default=None)
    threshold_type: ThresholdType | None = Field(default=None)
    threshold_value: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    alert_level: AlertLevel | None = Field(default=None)
    notify_method: list[str] | None = Field(default=None, min_length=1)
    notify_users: list[str] | None = Field(default=None, min_length=1)
    notify_frequency: NotifyFrequency | None = Field(default=None)
    effective_time: EffectiveTime | None = Field(default=None)
    custom_time_start: str | None = Field(default=None)
    custom_time_end: str | None = Field(default=None)
    is_enabled: bool | None = Field(default=None)


class EnergyAlertRuleResponse(BaseModel):
    id: StrUUID
    rule_name: str
    rule_description: str | None
    energy_type: str
    monitor_metric: str
    threshold_type: str
    threshold_value: float
    unit: str
    alert_level: str
    notify_method: list[str]
    notify_users: list[str]
    notify_frequency: str
    effective_time: str
    custom_time_start: str | None
    custom_time_end: str | None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnergyAlertRecordResponse(BaseModel):
    id: StrUUID
    rule_id: StrUUID
    device_config_id: StrUUID | None
    energy_type: str
    alert_level: str
    trigger_value: float
    threshold_value: float
    unit: str
    alert_time: datetime
    status: str
    processed_by: str | None
    processed_at: datetime | None
    process_note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertRecordProcessRequest(BaseModel):
    status: Literal["processed", "ignored"] = Field(..., description="处理结果")
    process_note: str | None = Field(
        default=None, max_length=500, description="处理备注"
    )


# ── Wiki / Sheets ingestion contracts ─────────────────────────────


class EnergyFeishuConfigUpsert(BaseModel):
    config_name: str = Field(default="能源 Wiki 数据源", min_length=1, max_length=128)
    app_id: str = Field(..., min_length=1, max_length=128)
    app_secret: str | None = Field(default=None, min_length=1, max_length=500)
    root_wiki_url: str = Field(default="", max_length=2000)
    timezone: str = Field(default="Asia/Shanghai", max_length=64)
    daily_sync_time: str = Field(default="02:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    is_active: bool = True
    remark: str | None = Field(default=None, max_length=1000)


class EnergyFeishuConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: StrUUID | None = None
    config_name: str
    app_id: str
    app_secret_configured: bool
    app_secret_masked: str
    root_wiki_url: str
    root_wiki_token: str | None
    timezone: str
    daily_sync_time: str
    is_active: bool
    last_successful_sync_date: date | None
    sync_status: str
    sync_error: str | None
    remark: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EnergyFeishuSourceRootInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_type: Literal["wiki", "base"] = "wiki"
    source_url: str = Field(..., min_length=1, max_length=2000)
    is_active: bool = True


class EnergyFeishuSourceRootResponse(BaseModel):
    id: StrUUID
    config_id: StrUUID
    name: str
    source_type: str
    source_url: str
    root_token: str
    is_active: bool
    discovery_status: str
    last_discovered_at: datetime | None = None
    discovery_error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class EnergyFeishuConnectivityStep(BaseModel):
    name: str
    status: Literal["ok", "error", "warning"]
    message: str


class EnergyFeishuConnectivityResult(BaseModel):
    ok: bool
    steps: list[EnergyFeishuConnectivityStep]


class EnergySyncTriggerRequest(BaseModel):
    force: bool = Field(
        default=False, description="即使今日已成功同步也创建一次手动同步"
    )


class EnergySyncRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: StrUUID
    config_id: StrUUID
    trigger_type: str
    scheduled_for: datetime | None
    started_at: datetime
    completed_at: datetime | None
    status: str
    document_count: int
    sheet_count: int
    snapshot_count: int
    fact_count: int
    error_count: int
    error_message: str | None


class EnergySourceDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: StrUUID
    wiki_node_token: str
    parent_node_token: str | None
    object_type: str
    document_token: str | None
    title: str
    node_path: list[dict[str, str]]
    period_month: date | None
    classification_status: str
    last_synced_at: datetime | None


class EnergySourceSheetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: StrUUID
    document_id: StrUUID
    external_sheet_id: str
    title: str
    sheet_index: int
    header_row: int
    headers: list[str]
    schema_hash: str | None
    mapping_status: str
    source_role: SheetSourceRole | None = None
    latest_snapshot_id: StrUUID | None
    last_synced_at: datetime | None
    document_title: str | None = None
    period_month: date | None = None


class EnergySnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: StrUUID
    sheet_id: StrUUID
    sync_run_id: StrUUID
    snapshot_number: int
    source_revision: str | None
    content_hash: str
    header_values: list[str]
    row_count: int
    captured_at: datetime


class EnergySnapshotRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: StrUUID
    snapshot_id: StrUUID
    row_index: int
    values: list[object]
    row_hash: str


ValueSemantics = Literal["direct", "cumulative"]
OverviewScope = Literal["detail", "daily_summary", "energy_summary"]


class EnergyMappingMetricInput(BaseModel):
    metric_key: str = Field(..., min_length=1, max_length=256)
    value_column: str = Field(..., min_length=1, max_length=256)
    energy_type: str = Field(..., min_length=1, max_length=128)
    unit: str | None = Field(default=None, max_length=64)
    unit_column: str | None = Field(default=None, max_length=256)
    meter_key_column: str | None = Field(default=None, max_length=256)
    value_semantics: ValueSemantics = "direct"

    @model_validator(mode="after")
    def validate_metric(self) -> EnergyMappingMetricInput:
        if not self.unit and not self.unit_column:
            raise ValueError("每个指标必须配置固定单位或单位列")
        if self.value_semantics == "cumulative" and not self.meter_key_column:
            raise ValueError("累计表底指标必须配置计量点列")
        return self


class EnergySheetMappingUpsert(BaseModel):
    is_enabled: bool = False
    source_role: SheetSourceRole = "workshop_detail"
    header_row: int = Field(default=1, ge=1, le=100)
    date_column: str | None = Field(default=None, max_length=256)
    date_format: str | None = Field(default=None, max_length=128)
    dimensions: dict[str, str] = Field(default_factory=dict)
    metrics: list[EnergyMappingMetricInput] = Field(default_factory=list)

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not key.strip() or not column.strip() for key, column in value.items()):
            raise ValueError("维度名称和列名不能为空")
        return value

    @model_validator(mode="after")
    def validate_enabled_mapping(self) -> EnergySheetMappingUpsert:
        if self.is_enabled and (not self.date_column or not self.metrics):
            raise ValueError("启用分析时必须配置日期列和至少一个指标")
        return self


class EnergySheetMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: StrUUID
    sheet_id: StrUUID
    version: int
    is_current: bool
    is_enabled: bool
    source_role: SheetSourceRole
    schema_hash: str | None
    header_row: int
    date_column: str | None
    date_format: str | None
    dimensions: dict[str, str]
    metrics: list[dict[str, object]]
    validation_error: str | None
    created_at: datetime
    updated_at: datetime


class EnergyMappingPreviewRow(BaseModel):
    row_index: int
    values: dict[str, object]
    errors: list[str] = Field(default_factory=list)


class EnergyMappingPreviewResponse(BaseModel):
    valid_row_count: int
    invalid_row_count: int
    rows: list[EnergyMappingPreviewRow]


class EnergyOverviewMetric(BaseModel):
    metric_key: str | None = None
    energy_type: str
    unit: str
    total_value: float
    record_count: int


class EnergyOverviewTrendPoint(BaseModel):
    date: date
    metric_key: str | None = None
    energy_type: str
    unit: str
    value: float


class EnergyOverviewDistributionPoint(BaseModel):
    key: str
    metric_key: str | None = None
    energy_type: str
    unit: str
    value: float


class EnergyOverviewLatestMetric(BaseModel):
    metric_key: str
    energy_type: str
    unit: str
    value: float
    observed_at: datetime


class EnergyOverviewResponse(BaseModel):
    source_scope: OverviewScope
    metrics: list[EnergyOverviewMetric]
    trend: list[EnergyOverviewTrendPoint]
    distribution: list[EnergyOverviewDistributionPoint]
    latest_metrics: list[EnergyOverviewLatestMetric]
    last_observed_at: datetime | None = None
    invalid_count: int


class EnergyApiResponse[ResponseData](BaseModel):
    code: int = 200
    message: str = "success"
    data: ResponseData
    meta: dict[str, object] | None = None


class EnergySnapshotRowsData(BaseModel):
    snapshot: EnergySnapshotResponse
    rows: list[EnergySnapshotRowResponse]
