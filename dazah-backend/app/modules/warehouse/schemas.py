"""Warehouse request and response schemas live here."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _strip_text(value: str | None) -> str | None:
    if isinstance(value, str):
        return value.strip()
    return value


class RawMaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: str | None = None
    code: str
    name: str
    spec: str | None = None
    unit: str | None = None
    available: float
    safety: float
    last_month: float
    two_months_ago: float
    today_balance: float
    front_stock: float
    this_month_use: float
    warning: str | None = None
    product_line: str | None = None
    erp_no: str | None = None
    delivery: str | None = None
    remark: str | None = None
    source: str | None = None
    import_key: str
    last_synced_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PackagingMaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: str | None = None
    code: str
    name: str
    spec: str | None = None
    batch: str | None = None
    available: float
    safety: float
    last_month: float
    two_months_ago: float
    today_balance: float
    front_stock: float
    this_month_use: float
    warning: str | None = None
    product_line: str | None = None
    erp_no: str | None = None
    delivery: str | None = None
    remark: str | None = None
    source: str | None = None
    import_key: str
    last_synced_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProductInventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: str | None = None
    name: str
    spec: str | None = None
    order_quantity: float
    pending_quantity: float
    qualified_quantity: float
    subtotal_quantity: float
    remaining_quantity: float
    unit: str | None = None
    remark: str | None = None
    source: str | None = None
    import_key: str
    last_synced_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RawMaterialListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[RawMaterialResponse]
    meta: dict[str, int] | None = None


class PackagingMaterialListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[PackagingMaterialResponse]
    meta: dict[str, int] | None = None


class ProductInventoryListResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[ProductInventoryResponse]
    meta: dict[str, int] | None = None


class WarehouseFeishuConfigBase(BaseModel):
    config_name: str = Field(default="仓储飞书配置", max_length=128)
    app_id: str = Field(..., max_length=128)
    is_active: bool = True
    timezone: str = Field(default="Asia/Shanghai", max_length=64)
    daily_sync_time: str = Field(default="02:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    remark: str | None = None

    @field_validator("config_name", "app_id", mode="before")
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

class WarehouseFeishuConfigUpsert(WarehouseFeishuConfigBase):
    app_secret: str | None = Field(default=None, max_length=500)

    @field_validator("app_secret", mode="before")
    @classmethod
    def normalize_app_secret(cls, value: str | None) -> str | None:
        return _clean_text(value)


class WarehouseFeishuConfigResponse(WarehouseFeishuConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    app_secret_configured: bool = False
    app_secret_masked: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WarehouseFeishuConfigApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseFeishuConfigResponse
    meta: dict[str, int] | None = None


class WarehouseFeishuTableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    app_token: str
    table_id: str
    name: str
    revision: int | None = None
    last_discovered_at: datetime | None = None
    last_event_at: datetime | None = None
    field_count: int = 0
    record_count: int = 0
    last_synced_at: datetime | None = None
    sync_status: str | None = None
    sync_error: str | None = None
    source_root_id: UUID | None = None
    source_path: list[dict[str, str]] = Field(default_factory=list)
    schema_hash: str | None = None
    active_mirror_version: str | None = None


class WarehouseFeishuTableListApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[WarehouseFeishuTableResponse]
    meta: dict[str, int] | None = None


class WarehouseFeishuFieldResponse(BaseModel):
    field_id: str
    field_name: str
    type: int | None = None
    property: dict[str, Any] | None = None
    display_order: int = 0


class WarehouseFeishuRawRecordResponse(BaseModel):
    record_id: str
    fields: dict[str, Any]
    created_time: int | None = None
    last_modified_time: int | None = None
    normalized_fields: dict[str, Any] = Field(default_factory=dict)


class WarehouseFeishuSourceRootInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_type: Literal["base", "wiki"]
    source_url: str = Field(..., min_length=1, max_length=2000)
    is_active: bool = True


class WarehouseFeishuSourceRootResponse(WarehouseFeishuSourceRootInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    root_token: str
    discovery_status: str
    discovery_error: str | None = None
    last_discovered_at: datetime | None = None


class WarehouseFeishuSourceRootListApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[WarehouseFeishuSourceRootResponse]


class WarehouseFeishuSourceRootApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseFeishuSourceRootResponse


class WarehouseFeishuPageBindingInput(BaseModel):
    table_pk: UUID
    tab_label: str = Field(..., min_length=1, max_length=255)
    display_order: int = Field(default=0, ge=0)
    is_default: bool = False
    visible_field_ids: list[str] = Field(default_factory=list)
    default_sort: list[dict[str, str]] = Field(default_factory=list)
    history_mode: Literal["current_mirror", "daily_snapshot"] = "current_mirror"
    is_enabled: bool = True


class WarehouseFeishuPageBindingReplace(BaseModel):
    bindings: list[WarehouseFeishuPageBindingInput] = Field(max_length=50)


class WarehouseFeishuPageBindingResponse(WarehouseFeishuPageBindingInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    page_key: str
    status: str
    table: WarehouseFeishuTableResponse


class WarehouseFeishuPageDataResponse(BaseModel):
    page_key: str
    bindings: list[WarehouseFeishuPageBindingResponse]


class WarehouseFeishuPageDataApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseFeishuPageDataResponse


class WarehouseDatasetPagination(BaseModel):
    page: int
    page_size: int
    total: int


class WarehouseDatasetRecordResponse(BaseModel):
    record_id: str
    fields: dict[str, Any]
    normalized_fields: dict[str, Any] = Field(default_factory=dict)
    created_time: int | None = None
    last_modified_time: int | None = None


class WarehouseDatasetResponse(BaseModel):
    dataset: WarehouseFeishuPageBindingResponse
    fields: list[WarehouseFeishuFieldResponse]
    records: list[WarehouseDatasetRecordResponse]
    pagination: WarehouseDatasetPagination


class WarehouseDatasetApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseDatasetResponse


class WarehouseDatasetRecordApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseDatasetRecordResponse


class WarehouseFieldValueItem(BaseModel):
    value: str
    count: int


class WarehouseFieldValuesResponse(BaseModel):
    field_id: str
    values: list[WarehouseFieldValueItem]


class WarehouseFieldValuesApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseFieldValuesResponse


WarehouseAnalyticsMetric = Literal["count", "count_distinct", "sum", "avg", "min", "max"]
WarehouseAnalyticsPeriod = Literal["none", "day", "week", "month"]


class WarehouseAnalyticsQuery(BaseModel):
    binding_id: UUID
    metric: WarehouseAnalyticsMetric = "count"
    metric_field_id: str | None = None
    group_field_id: str | None = None
    time_field_id: str | None = None
    period: WarehouseAnalyticsPeriod = "none"
    limit: int = Field(default=20, ge=1, le=200)


class WarehouseAnalyticsResponse(BaseModel):
    rows: list[dict[str, Any]]
    meta: dict[str, Any]


class WarehouseAnalyticsApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseAnalyticsResponse


class WarehouseAnalysisProfileInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    resource_ids: list[UUID] = Field(min_length=1)
    analysis_goal: str = Field(..., min_length=1, max_length=4000)
    input_field_ids: list[str] = Field(default_factory=list)
    time_field_id: str | None = None
    metric_field_ids: list[str] = Field(default_factory=list)
    dimension_field_ids: list[str] = Field(default_factory=list)
    quality_rules: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    max_raw_rows: int = Field(default=100, ge=20, le=200)
    auto_run: bool = False
    allow_sensitive_fields: bool = False
    system_prompt: str = Field(..., min_length=1, max_length=20000)
    business_context: str | None = Field(default=None, max_length=10000)
    focus_points: list[str] = Field(default_factory=list, max_length=30)


class WarehouseAnalysisProfileResponse(BaseModel):
    id: UUID
    name: str
    resource_ids: list[str]
    analysis_goal: str
    input_field_ids: list[str]
    time_field_id: str | None = None
    metric_field_ids: list[str]
    dimension_field_ids: list[str]
    max_raw_rows: int
    auto_run: bool
    allow_sensitive_fields: bool
    prompt_version: int


class WarehousePromptVersionInput(BaseModel):
    system_prompt: str = Field(..., min_length=1, max_length=20000)
    business_context: str | None = Field(default=None, max_length=10000)
    focus_points: list[str] = Field(default_factory=list, max_length=30)


class WarehousePromptVersionResponse(BaseModel):
    id: UUID
    profile_id: UUID
    version: int
    system_prompt: str
    business_context: str | None = None
    focus_points: list[str]
    status: str
    published_at: datetime | None = None


class WarehousePromptVersionApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehousePromptVersionResponse


class WarehousePromptVersionListApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[WarehousePromptVersionResponse]


class WarehouseAnalysisRunResponse(BaseModel):
    id: UUID
    profile_id: UUID
    trigger_type: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None


class WarehouseAnalysisProfileApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseAnalysisProfileResponse


class WarehouseAnalysisRunApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseAnalysisRunResponse


class WarehouseFeishuRawRecordData(BaseModel):
    table: WarehouseFeishuTableResponse | None = None
    fields: list[WarehouseFeishuFieldResponse]
    records: list[WarehouseFeishuRawRecordResponse]
    page: int = 1
    page_size: int = 50
    total: int | None = None


class WarehouseFeishuRawRecordApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseFeishuRawRecordData
    meta: dict[str, int] | None = None


class WarehouseFeishuWsStatus(BaseModel):
    enabled: bool
    connected: bool
    app_id: str | None = None
    app_tokens: dict[str, str] = Field(default_factory=dict)
    last_started_at: datetime | None = None
    last_error: str | None = None


class WarehouseFeishuTableSyncResult(BaseModel):
    table: WarehouseFeishuTableResponse
    field_count: int
    record_count: int


class WarehouseFeishuTableSyncApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseFeishuTableSyncResult
    meta: dict[str, int] | None = None


class WarehouseFeishuWsStatusApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseFeishuWsStatus
    meta: dict[str, int] | None = None


class WarehouseFeishuConnectivityStep(BaseModel):
    name: str
    status: str
    message: str


class WarehouseFeishuConnectivityResult(BaseModel):
    ok: bool
    steps: list[WarehouseFeishuConnectivityStep]


class WarehouseFeishuConnectivityApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: WarehouseFeishuConnectivityResult
    meta: dict[str, int] | None = None
