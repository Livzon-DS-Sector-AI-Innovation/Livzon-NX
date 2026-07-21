from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, NoReturn, cast

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.modules.agent.tools import ToolContext, agent_tool
from app.modules.procurement.models import Supplier

MetricType = Literal["count", "count_distinct", "sum", "avg", "min", "max"]
FilterOp = Literal["eq", "ne", "contains", "not_empty", "is_empty", "gte", "lte"]
SortDirection = Literal["asc", "desc"]


@dataclass(frozen=True)
class AnalyticsField:
    column: InstrumentedAttribute[Any]
    label: str
    type: Literal["string", "number", "date", "datetime", "boolean"]
    filterable: bool = True
    groupable: bool = True
    aggregatable: bool = True


@dataclass(frozen=True)
class AnalyticsDataset:
    name: str
    label: str
    model: type[Any]
    fields: dict[str, AnalyticsField]
    default_filters: tuple[ColumnElement[bool], ...] = ()


DATASETS: dict[str, AnalyticsDataset] = {
    "procurement.suppliers": AnalyticsDataset(
        name="procurement.suppliers",
        label="采购供应商清单",
        model=Supplier,
        fields={
            "supplier_code": AnalyticsField(
                Supplier.supplier_code, "供应商代码", "string"
            ),
            "supplier_name": AnalyticsField(
                Supplier.supplier_name, "供应商名称", "string"
            ),
            "material_code": AnalyticsField(
                Supplier.material_code, "物料编码", "string"
            ),
            "material_name": AnalyticsField(
                Supplier.material_name, "物料名称", "string"
            ),
            "manufacturer_code": AnalyticsField(
                Supplier.manufacturer_code, "生产厂家编码", "string"
            ),
            "manufacturer_name": AnalyticsField(
                Supplier.manufacturer_name, "生产厂家名称", "string"
            ),
            "purchase_category": AnalyticsField(
                Supplier.purchase_category, "采购品类", "string"
            ),
            "last_updated_by": AnalyticsField(
                Supplier.last_updated_by, "最后更新人", "string"
            ),
            "last_updated_date": AnalyticsField(
                Supplier.last_updated_date, "最后更新日期", "date"
            ),
        },
        default_filters=(Supplier.is_deleted.is_(False),),
    )
}


class AnalyticsMetricInput(BaseModel):
    type: MetricType = "count"
    field: str | None = None
    alias: str | None = Field(default=None, max_length=80)


class AnalyticsFilterInput(BaseModel):
    field: str
    op: FilterOp
    value: Any = None


class AnalyticsOrderInput(BaseModel):
    field: str | None = None
    metric: str | None = None
    direction: SortDirection = "desc"

    @model_validator(mode="after")
    def require_field_or_metric(self) -> "AnalyticsOrderInput":
        if not self.field and not self.metric:
            raise ValueError("order_by requires field or metric")
        return self


class AnalyticsAggregateInput(BaseModel):
    dataset: str
    metrics: list[AnalyticsMetricInput] = Field(
        default_factory=lambda: [AnalyticsMetricInput()]
    )
    group_by: list[str] = Field(default_factory=list, max_length=3)
    filters: list[AnalyticsFilterInput] = Field(default_factory=list, max_length=20)
    order_by: list[AnalyticsOrderInput] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=20, ge=1, le=200)


def _dataset(name: str) -> AnalyticsDataset:
    try:
        return DATASETS[name]
    except KeyError as exc:
        allowed = ", ".join(sorted(DATASETS))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported analytics dataset: {name}. Allowed: {allowed}",
        ) from exc


def _field(dataset: AnalyticsDataset, name: str) -> AnalyticsField:
    try:
        return dataset.fields[name]
    except KeyError as exc:
        allowed = ", ".join(sorted(dataset.fields))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported field for {dataset.name}: {name}. Allowed: {allowed}",
        ) from exc


def _bad_request(message: str) -> NoReturn:
    raise HTTPException(status.HTTP_400_BAD_REQUEST, message)


def _metric_expr(
    dataset: AnalyticsDataset, metric: AnalyticsMetricInput
) -> tuple[str, Any]:
    field = _field(dataset, metric.field) if metric.field else None
    if field and not field.aggregatable:
        _bad_request(f"Field is not aggregatable: {metric.field}")

    expr: ColumnElement[Any]
    if metric.type == "count":
        expr = func.count(field.column if field else dataset.model.id)
    elif metric.type == "count_distinct":
        if field is None:
            _bad_request("count_distinct requires field")
        expr = func.count(func.distinct(field.column))
    elif metric.type == "sum":
        if field is None or field.type != "number":
            _bad_request("sum requires a numeric field")
        expr = func.sum(field.column)
    elif metric.type == "avg":
        if field is None or field.type != "number":
            _bad_request("avg requires a numeric field")
        expr = func.avg(field.column)
    elif metric.type == "min":
        if field is None:
            _bad_request("min requires field")
        expr = func.min(field.column)
    elif metric.type == "max":
        if field is None:
            _bad_request("max requires field")
        expr = func.max(field.column)
    else:
        _bad_request(f"Unsupported metric type: {metric.type}")

    default_alias = (
        metric.type if metric.field is None else f"{metric.type}_{metric.field}"
    )
    alias = metric.alias or default_alias
    return alias, expr.label(alias)


def _filter_expr(
    dataset: AnalyticsDataset, filter_input: AnalyticsFilterInput
) -> ColumnElement[bool]:
    field = _field(dataset, filter_input.field)
    if not field.filterable:
        _bad_request(f"Field is not filterable: {filter_input.field}")
    column = field.column
    value = filter_input.value

    if filter_input.op == "eq":
        return cast(ColumnElement[bool], column == value)
    if filter_input.op == "ne":
        return cast(ColumnElement[bool], column != value)
    if filter_input.op == "contains":
        if value is None:
            _bad_request("contains requires value")
        return column.ilike(f"%{value}%")
    if filter_input.op == "not_empty":
        return column.is_not(None) & (func.trim(column) != "")
    if filter_input.op == "is_empty":
        return column.is_(None) | (func.trim(column) == "")
    if filter_input.op == "gte":
        return cast(ColumnElement[bool], column >= value)
    if filter_input.op == "lte":
        return cast(ColumnElement[bool], column <= value)
    _bad_request(f"Unsupported filter op: {filter_input.op}")


def _apply_ordering(
    query: Select[tuple[Any, ...]],
    *,
    dataset: AnalyticsDataset,
    order_by: Sequence[AnalyticsOrderInput],
    metric_columns: dict[str, Any],
    group_columns: dict[str, Any],
) -> Select[tuple[Any, ...]]:
    if not order_by:
        if metric_columns:
            first_metric = next(iter(metric_columns.values()))
            return query.order_by(desc(first_metric))
        return query

    for order in order_by:
        if order.metric:
            if order.metric not in metric_columns:
                _bad_request(f"Unknown order metric: {order.metric}")
            expression = metric_columns[order.metric]
        else:
            assert order.field is not None
            _field(dataset, order.field)
            if order.field not in group_columns:
                _bad_request("Ordering by field requires the field in group_by")
            expression = group_columns[order.field]
        query = query.order_by(
            desc(expression) if order.direction == "desc" else asc(expression)
        )
    return query


async def aggregate_analytics(
    context: ToolContext, data: AnalyticsAggregateInput
) -> dict[str, Any]:
    dataset = _dataset(data.dataset)
    group_columns: dict[str, Any] = {}
    select_columns: list[Any] = []

    for field_name in data.group_by:
        field = _field(dataset, field_name)
        if not field.groupable:
            _bad_request(f"Field is not groupable: {field_name}")
        column = field.column.label(field_name)
        group_columns[field_name] = column
        select_columns.append(column)

    metric_columns: dict[str, Any] = {}
    for metric in data.metrics:
        alias, expression = _metric_expr(dataset, metric)
        if alias in metric_columns or alias in group_columns:
            _bad_request(f"Duplicate metric alias: {alias}")
        metric_columns[alias] = expression
        select_columns.append(expression)

    query = select(*select_columns).select_from(dataset.model)
    for default_filter in dataset.default_filters:
        query = query.where(default_filter)
    for filter_input in data.filters:
        query = query.where(_filter_expr(dataset, filter_input))
    if group_columns:
        query = query.group_by(*group_columns.values())
    query = _apply_ordering(
        query,
        dataset=dataset,
        order_by=data.order_by,
        metric_columns=metric_columns,
        group_columns=group_columns,
    ).limit(data.limit)

    result = await context.db.execute(query)
    rows = [dict(row._mapping) for row in result.all()]
    return {
        "dataset": {"name": dataset.name, "label": dataset.label},
        "rows": rows,
        "meta": {
            "row_count": len(rows),
            "limit": data.limit,
            "group_by": data.group_by,
            "metrics": list(metric_columns),
        },
    }


@agent_tool(
    name="analytics.aggregate",
    summary="通用业务数据聚合统计",
    input_model=AnalyticsAggregateInput,
    method="TOOL",
    path="/agent/analytics/aggregate",
    input_schema={
        "body": {
            "dataset": "数据集名称；当前支持 procurement.suppliers",
            "metrics": "聚合指标列表，支持 count/count_distinct/sum/avg/min/max",
            "group_by": "分组字段列表，最多 3 个；例如 manufacturer_name",
            "filters": "过滤条件列表，支持 eq/ne/contains/not_empty/is_empty/gte/lte",
            "order_by": "按 metric 或 group_by 字段排序",
            "limit": "返回分组数量，默认 20，最大 200",
        },
        "examples": [
            {
                "dataset": "procurement.suppliers",
                "metrics": [
                    {
                        "type": "count",
                        "field": "manufacturer_name",
                        "alias": "record_count",
                    }
                ],
                "group_by": ["manufacturer_name"],
                "filters": [{"field": "manufacturer_name", "op": "not_empty"}],
                "order_by": [{"metric": "record_count", "direction": "desc"}],
                "limit": 10,
            }
        ],
    },
    output_hint=(
        "用于全量计数、去重计数、TopN、分布统计等场景；返回数据库聚合后的 rows，"
        "避免逐页读取全量明细。"
    ),
)
async def aggregate_analytics_tool(
    context: ToolContext, data: AnalyticsAggregateInput
) -> dict[str, Any]:
    return await aggregate_analytics(context, data)
