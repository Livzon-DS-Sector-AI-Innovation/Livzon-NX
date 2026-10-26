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
    # Retained as descriptive metadata for historical rows. Energy no longer
    # applies department data scopes; new imports leave this blank.
    department: str = Field(default="", max_length=100)
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
    department: str = Field(default="", max_length=100)
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










class ReadingException(LedgerSchema):
    kind: Literal["replacement", "reset", "rollover"]
    previous_final: PositiveAmount
    new_initial: PositiveAmount
    reason: str = Field(min_length=1, max_length=1000)










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


class UsageReviewPeriod(LedgerSchema):
    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=2000)
    source: str = Field(min_length=1, max_length=2000)
    reported_values: dict[date, Decimal] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_period(self) -> "UsageReviewPeriod":
        if (
            self.end_date < self.start_date
            or (self.end_date - self.start_date).days > 365
        ):
            raise ValueError("待确认区间须按先后顺序且最多覆盖一年")
        if any(
            not self.start_date <= day <= self.end_date for day in self.reported_values
        ):
            raise ValueError("原表结果日期必须在待确认区间内")
        if any(
            not value.is_finite() or abs(value) >= Decimal("1e20")
            for value in self.reported_values.values()
        ):
            raise ValueError("原表结果超出计量范围")
        return self


class UsageReview(LedgerSchema):
    dataset: str = Field(min_length=1, max_length=100)
    column: int = Field(ge=2, le=16384)
    periods: list[UsageReviewPeriod] = Field(default_factory=list, max_length=100)

    def evidence_on(self, day: date) -> list[dict[str, JsonValue]]:
        return [
            {
                "reason": period.reason,
                "source": period.source,
                "dataset": self.dataset,
                "column": self.column,
                "reported_value": str(period.reported_values[day])
                if day in period.reported_values
                else None,
            }
            for period in self.periods
            if period.start_date <= day <= period.end_date
        ]


class UsageReviewUpdate(LedgerSchema):
    reviews: list[UsageReview] = Field(min_length=1, max_length=100)
    reason: str = Field(default="Web 复核", max_length=1000)


class UsageReviewResponse(UsageReview):
    updated_at: datetime | None = None
    updated_by: UUID | None = None


class ReportBasisNode(LedgerSchema):
    node_id: str
    parent_id: str | None = None
    name: str
    source_sheet: str = ""
    source_column: str = ""
    reading_type: str = ""
    operation: str = ""
    coefficient: Decimal = Decimal(1)
    value: Decimal | None = None
    calculated_value: Decimal | None = None
    status: str
    reading_dates: list[str] = Field(default_factory=list)
    reading_values: list[str | None] = Field(default_factory=list)
    multiplier: str = "1"
    note: str = ""


class ReportBasis(LedgerSchema):
    usage_date: date
    nodes: list[ReportBasisNode]


class ReportTotal(LedgerSchema):
    category: EnergyCategory
    unit: str
    quantity_kind: str
    temperature: str
    value: Decimal | None
    expected_count: int
    available_count: int
    basis: ReportBasis | None = None


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


class DirectReadingItem(LedgerSchema):
    point_id: UUID
    reading_id: UUID | None = None
    name: str
    unit: str
    precision: int
    value: Decimal | None = None
    draft_value: Decimal | None = None
    version: int = 0


class DirectReadingResponse(LedgerSchema):
    reading_date: date
    dataset: str
    items: list[DirectReadingItem]


class DirectReadingValue(LedgerSchema):
    point_id: UUID
    value: PositiveAmount
    version: int = Field(ge=0)


class DirectReadingWrite(LedgerSchema):
    reading_date: date
    dataset: str = Field(min_length=1, max_length=100)
    values: list[DirectReadingValue] = Field(min_length=1, max_length=200)
    draft: bool = False
    reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def unique_fields(self) -> "DirectReadingWrite":
        if len({item.point_id for item in self.values}) != len(self.values):
            raise ValueError("同一原始字段不能重复提交")
        return self


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


class ImportResponse(LedgerSchema):
    id: UUID
    status: str
    payload: dict[str, JsonValue]


class LedgerOptions(LedgerSchema):
    is_manager: bool
    people: list[dict[str, str]]
