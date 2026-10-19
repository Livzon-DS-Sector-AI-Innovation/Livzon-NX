"""Validated contracts for native metering, entry, reporting and notifications."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.modules.energy.ledger_source_policy import manual_input_allowed

EnergyCategory = Literal[
    "drinking_water",
    "chilled_water",
    "steam",
    "circulating_water",
    "air",
    "electricity",
]
ReportScope = Literal["source", "detail", "plant", "check"]
Amount = Annotated[Decimal, Field(max_digits=28, decimal_places=8, allow_inf_nan=False)]
PositiveAmount = Annotated[Amount, Field(ge=0)]
Clock = Annotated[str, Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]


class LedgerSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MeterDefinition(LedgerSchema):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    category: EnergyCategory
    area: str = Field(min_length=1, max_length=100)
    workshop: str = Field(default="", max_length=100)
    department: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=24)
    reading_type: Literal["counter", "direct"] = "counter"
    frequency: Literal["daily", "monthly"] = "daily"
    multiplier: Amount = Field(default=Decimal(1), gt=0)
    precision: int = Field(default=3, ge=0, le=8)
    report_scope: ReportScope = "source"
    active_from: date
    active_to: date | None = None
    enabled: bool = False
    temperature: str = Field(default="", max_length=40)
    quantity_kind: Literal["volume", "heat", "mass", "electricity"] = "volume"
    warning_limit: PositiveAmount | None = None
    source_sheet: str = Field(default="", max_length=100)
    source_column: int | None = Field(default=None, ge=2, le=16384)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_period(self) -> "MeterDefinition":
        if self.enabled and (self.unit == "待确认" or self.department == "待确认"):
            raise ValueError("启用前须确认计量单位和归属部门")
        if self.active_to is not None and self.active_to < self.active_from:
            raise ValueError("结束日期不能早于启用日期")
        if self.category == "electricity" and self.reading_type != "direct":
            raise ValueError("电量按每日直接用量录入")
        if self.reading_type == "direct" and self.frequency != "daily":
            raise ValueError("直接用量按日填写；月底抄表请配置累计表码")
        return self


class MeterWrite(LedgerSchema):
    definition: MeterDefinition
    version: int = Field(default=0, ge=0)
    reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_input_boundary(self) -> "MeterWrite":
        if self.definition.enabled and not manual_input_allowed(
            self.definition.source_sheet,
            self.definition.name,
            self.definition.reading_type,
            self.definition.category,
        ):
            raise ValueError(
                "人工计量点只接受五类累计表码和当日电量；汇总及差额须自动计算"
            )
        return self


class MeterResponse(LedgerSchema):
    id: UUID
    version: int
    definition: MeterDefinition


class RuleTerm(LedgerSchema):
    metric_key: str = Field(
        min_length=1, max_length=100, pattern=r"^(point|rule):[a-zA-Z0-9_-]+$"
    )
    coefficient: Amount = Decimal(1)


class RuleDefinition(LedgerSchema):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    category: EnergyCategory
    unit: str = Field(min_length=1, max_length=24)
    workshop: str = Field(default="", max_length=100)
    department: str = Field(min_length=1, max_length=100)
    report_scope: ReportScope = "detail"
    quantity_kind: Literal["volume", "heat", "mass", "electricity", "ratio"] = "volume"
    temperature: str = Field(default="", max_length=40)
    operation: Literal["sum", "ratio"] = "sum"
    frequency: Literal["daily", "monthly"] = "daily"
    terms: list[RuleTerm] = Field(min_length=1, max_length=100)
    active_from: date
    active_to: date | None = None
    enabled: bool = False
    notes: str = Field(default="", max_length=2000)
    source_sheet: str = Field(default="", max_length=100)
    source_column: int | None = Field(default=None, ge=2, le=16384)

    @model_validator(mode="after")
    def validate_operation(self) -> "RuleDefinition":
        if self.source_sheet == "电量" and self.name.split("·")[-1].strip() in {
            "其他",
            "差额",
            "差值",
        }:
            self.report_scope = "check"
        if self.enabled and (self.unit == "待确认" or self.department == "待确认"):
            raise ValueError("启用前须确认计量单位和归属部门")
        if self.operation == "ratio" and (
            len(self.terms) != 2 or self.quantity_kind != "ratio"
        ):
            raise ValueError("占比必须配置分子、分母两个来源，指标类型选择占比")
        if self.operation == "sum" and self.quantity_kind == "ratio":
            raise ValueError("占比指标须使用占比计算")
        if self.active_to is not None and self.active_to < self.active_from:
            raise ValueError("结束日期不能早于启用日期")
        return self


class RuleWrite(LedgerSchema):
    definition: RuleDefinition
    version: int = Field(default=0, ge=0)
    reason: str = Field(default="", max_length=1000)


class RuleResponse(LedgerSchema):
    id: UUID
    version: int
    definition: RuleDefinition


class EntryPlanDefinition(LedgerSchema):
    name: str = Field(min_length=1, max_length=120)
    point_ids: list[UUID] = Field(min_length=1, max_length=200)
    owner_ids: list[UUID] = Field(min_length=1, max_length=30)
    publish_time: Clock = "08:00"
    deadline_time: Clock = "10:00"
    reminder_time: Clock = "10:30"
    group_chat_id: str = Field(default="", max_length=160)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_times(self) -> "EntryPlanDefinition":
        if not self.publish_time <= self.deadline_time <= self.reminder_time:
            raise ValueError("发布时间、截止时间、提醒时间须依次递增")
        if len(set(self.point_ids)) != len(self.point_ids) or len(
            set(self.owner_ids)
        ) != len(self.owner_ids):
            raise ValueError("计量点和责任人不能重复")
        return self


class PlanWrite(LedgerSchema):
    definition: EntryPlanDefinition
    version: int = Field(default=0, ge=0)
    reason: str = Field(default="", max_length=1000)


class PlanResponse(LedgerSchema):
    id: UUID
    version: int
    definition: EntryPlanDefinition


class GenerateTasks(LedgerSchema):
    task_date: date


class ReadingException(LedgerSchema):
    kind: Literal["replacement", "reset", "rollover"]
    previous_final: PositiveAmount
    new_initial: PositiveAmount
    reason: str = Field(min_length=1, max_length=1000)


class EntryValue(LedgerSchema):
    reading_id: UUID
    version: int = Field(ge=0)
    value: PositiveAmount
    exception: ReadingException | None = None


class EntrySubmission(LedgerSchema):
    values: list[EntryValue] = Field(min_length=1, max_length=200)
    draft: bool = False
    reason: str = Field(default="", max_length=1000)
    source: Literal["platform", "feishu"] = "platform"

    @model_validator(mode="after")
    def unique_values(self) -> "EntrySubmission":
        if len({item.reading_id for item in self.values}) != len(self.values):
            raise ValueError("同一计量点不能重复提交")
        return self


class EntryItemResponse(LedgerSchema):
    id: UUID
    point_id: UUID
    name: str
    category: EnergyCategory
    unit: str
    precision: int
    multiplier: Decimal = Decimal(1)
    reading_type: str
    frequency: str = "daily"
    reading_date: date
    value: Decimal | None
    draft_value: Decimal | None
    previous_value: Decimal | None
    previous_date: date | None
    version: int
    submitted_at: datetime | None
    estimated_usage: Decimal | None = None
    exception: ReadingException | None = None


class TaskResponse(LedgerSchema):
    id: UUID
    task_date: date
    name: str
    owner_ids: list[UUID]
    deadline_time: str
    total_count: int
    completed_count: int
    items: list[EntryItemResponse]


class UsageRow(LedgerSchema):
    id: UUID
    metric_key: str
    usage_date: date
    name: str
    category: EnergyCategory
    unit: str
    workshop: str
    department: str
    report_scope: ReportScope
    quantity_kind: str
    temperature: str
    calculated_value: Decimal | None
    effective_value: Decimal | None
    status: str
    provenance: dict[str, JsonValue]


class ReportTotal(LedgerSchema):
    category: EnergyCategory
    unit: str
    quantity_kind: str
    temperature: str
    value: Decimal | None
    expected_count: int
    available_count: int


class ReportTrend(ReportTotal):
    usage_date: date


class ReportDistribution(ReportTotal):
    workshop: str


class PeriodMetric(LedgerSchema):
    metric_key: str
    name: str
    unit: str
    value: Decimal | None
    status: str
    quantity_kind: str = "volume"


class ReportResponse(LedgerSchema):
    start_date: date
    end_date: date
    status: Literal["complete", "partial", "pending"]
    rows: list[UsageRow]
    totals: list[ReportTotal]
    trend: list[ReportTrend] = Field(default_factory=list)
    distribution: list[ReportDistribution] = Field(default_factory=list)
    period_metrics: list[PeriodMetric] = Field(default_factory=list)
    total_count: int
    latest_complete_date: date | None = None
    entry_total: int = 0
    entry_completed: int = 0
    quality_counts: dict[str, int] = Field(default_factory=dict)


class WorkbookDataset(LedgerSchema):
    name: str
    kind: Literal["reading", "usage", "mixed"]


class EnergyMetricOption(LedgerSchema):
    metric_key: str
    name: str
    category: EnergyCategory
    unit: str


class WorkbookColumn(LedgerSchema):
    key: str
    label: str
    unit: str
    value_kind: Literal["reading", "usage"]
    quantity_kind: str


class WorkbookCell(LedgerSchema):
    value: Decimal | None = None
    calculated_value: Decimal | None = None
    status: str
    trace_id: UUID | None = None
    reading_id: UUID | None = None
    provenance: dict[str, JsonValue] = Field(default_factory=dict)


class WorkbookDay(LedgerSchema):
    date: date
    cells: dict[str, WorkbookCell]


class WorkbookReport(LedgerSchema):
    year: int
    month: int
    dataset: str
    columns: list[WorkbookColumn]
    rows: list[WorkbookDay]
    available_count: int
    expected_count: int


class AdjustmentWrite(LedgerSchema):
    metric_key: str = Field(min_length=1, max_length=100)
    usage_date: date
    mode: Literal["override", "delta"]
    value: Amount
    reason: str = Field(min_length=1, max_length=1000)


class LockWrite(LedgerSchema):
    locked: bool
    version: int = Field(default=0, ge=0)
    reason: str = Field(min_length=1, max_length=1000)


class LockResponse(LedgerSchema):
    month: str
    locked: bool
    version: int


class RevisionResponse(LedgerSchema):
    id: UUID
    entity_kind: str
    entity_id: UUID
    version: int
    payload: dict[str, JsonValue]
    reason: str
    created_by: UUID | None
    created_at: datetime


class BotDefinition(LedgerSchema):
    app_id: str = Field(default="", max_length=128)
    base_url: str = Field(default="", max_length=500)
    enabled: bool = False

    @model_validator(mode="after")
    def validate_url(self) -> "BotDefinition":
        from urllib.parse import urlsplit

        parsed = urlsplit(self.base_url)
        if self.base_url and (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("填写无账号、查询参数的 HTTPS 平台访问地址")
        if self.enabled and (not self.app_id or not self.base_url):
            raise ValueError("启用机器人前须配置应用和 HTTPS 地址")
        return self


class BotWrite(LedgerSchema):
    definition: BotDefinition
    app_secret: str | None = Field(default=None, max_length=1024)
    version: int = Field(default=0, ge=0)


class BotResponse(LedgerSchema):
    definition: BotDefinition
    secret_configured: bool
    version: int = 0


class NotificationResponse(LedgerSchema):
    id: UUID
    task_id: UUID
    status: str
    attempts: int
    message_id: str | None
    error: str | None
    next_attempt_at: datetime | None


class ImportMapping(LedgerSchema):
    sheet: str = Field(min_length=1, max_length=100)
    column: int = Field(ge=2, le=16384)
    point_id: UUID


class ImportConfirm(LedgerSchema):
    mappings: list[ImportMapping] = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)
    adjustments: list[AdjustmentWrite] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def unique_adjustments(self) -> "ImportConfirm":
        if len(
            {(item.metric_key, item.usage_date) for item in self.adjustments}
        ) != len(self.adjustments):
            raise ValueError("同一日期同一指标不能重复导入人工修正")
        return self


class ImportResponse(LedgerSchema):
    id: UUID
    status: str
    payload: dict[str, JsonValue]


class SnapshotImportRequest(LedgerSchema):
    snapshot_ids: list[UUID] = Field(min_length=1, max_length=6)
    year: int = Field(ge=2000, le=2100)
    start_date: date | None = None
    end_date: date | None = None


class SnapshotImportOption(LedgerSchema):
    id: UUID
    sheet_title: str
    captured_at: datetime
    snapshot_number: int


class TrialRequest(LedgerSchema):
    usage_date: date


class LedgerOptions(LedgerSchema):
    is_manager: bool
    people: list[dict[str, str]]
