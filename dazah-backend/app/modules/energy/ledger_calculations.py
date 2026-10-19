"""Deterministic Decimal calculations; no spreadsheet formula execution."""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, localcontext

from pydantic import JsonValue

from app.modules.energy.ledger_schemas import MeterDefinition, RuleDefinition
from app.modules.energy.ledger_source_policy import manual_input_allowed


@dataclass(frozen=True)
class Observation:
    value: Decimal
    version: int
    exception: dict[str, JsonValue] = field(default_factory=dict)
    late: bool = False


@dataclass(frozen=True)
class Calculation:
    value: Decimal | None
    status: str
    provenance: dict[str, JsonValue]


def bounded_result(
    value: Decimal | None,
    status: str,
    provenance: dict[str, JsonValue],
    precision: int = 8,
) -> Calculation:
    if value is None:
        return Calculation(None, status, provenance)
    if not value.is_finite() or abs(value) >= Decimal("1e20"):
        return Calculation(None, "out_of_range", provenance)
    with localcontext() as context:
        context.prec = 60
        return Calculation(
            value.quantize(Decimal(1).scaleb(-precision)), status, provenance
        )


def active_on(definition: MeterDefinition | RuleDefinition, day: date) -> bool:
    return (
        definition.enabled
        and definition.active_from <= day
        and (definition.active_to is None or day <= definition.active_to)
    )


def next_month(day: date) -> date:
    return (day.replace(day=1) + timedelta(days=32)).replace(day=1)


def counter_dates(point: MeterDefinition, day: date) -> tuple[date, date] | None:
    if point.frequency == "monthly":
        if day.day != monthrange(day.year, day.month)[1]:
            return None
        return day.replace(day=1), next_month(day)
    return day, day + timedelta(days=1)


def calculate_point(
    point: MeterDefinition,
    day: date,
    observations: dict[date, Observation],
) -> Calculation | None:
    if not active_on(point, day):
        return None
    if not manual_input_allowed(
        point.source_sheet, point.name, point.reading_type, point.category
    ):
        return Calculation(
            None,
            "configuration_conflict",
            {"reason": "原始来源或计量口径配置冲突，请核对人工录入与计算边界"},
        )
    if point.reading_type == "direct":
        observation = observations.get(day)
        return bounded_result(
            observation.value * point.multiplier if observation else None,
            "complete" if observation else "missing_reading",
            {
                "reading_dates": [day.isoformat()],
                "reading_values": [str(observation.value)] if observation else [None],
                "versions": [observation.version] if observation else [],
                "late": observation.late if observation else False,
            },
            point.precision,
        )
    dates = counter_dates(point, day)
    if dates is None:
        return None
    start, end = dates
    before, after = observations.get(start), observations.get(end)
    provenance: dict[str, JsonValue] = {
        "reading_dates": [start.isoformat(), end.isoformat()],
        "versions": [o.version if o else None for o in (before, after)],
        "reading_values": [str(o.value) if o else None for o in (before, after)],
        "multiplier": str(point.multiplier),
        "interval_start": start.isoformat(),
        "interval_end": end.isoformat(),
        "late": any(
            observation and observation.late for observation in (before, after)
        ),
    }
    if before is None or after is None:
        return Calculation(None, "missing_reading", provenance)
    if after.exception:
        event = after.exception
        previous_final = Decimal(str(event["previous_final"]))
        new_initial = Decimal(str(event["new_initial"]))
        if previous_final < before.value or after.value < new_initial:
            return Calculation(None, "invalid_meter_event", provenance)
        delta = previous_final - before.value + after.value - new_initial
        provenance["meter_event"] = event
    else:
        delta = after.value - before.value
    if delta < 0:
        return Calculation(None, "reading_rollback", provenance)
    value = delta * point.multiplier
    status = (
        "abnormal_usage"
        if point.warning_limit is not None and value > point.warning_limit
        else "complete"
    )
    return bounded_result(value, status, provenance, point.precision)


def calculate_rule(rule: RuleDefinition, inputs: dict[str, Calculation]) -> Calculation:
    values = [inputs.get(term.metric_key) for term in rule.terms]
    provenance: dict[str, JsonValue] = {
        "terms": [term.model_dump(mode="json") for term in rule.terms],
        "operation": rule.operation,
    }
    if any(item is None or item.value is None for item in values):
        return Calculation(None, "missing_dependency", provenance)
    numbers = [inputs[term.metric_key].value for term in rule.terms]
    with localcontext() as context:
        context.prec = 60
        weighted = [
            value * term.coefficient
            for value, term in zip(numbers, rule.terms, strict=True)
            if value is not None
        ]
        if rule.operation == "ratio":
            if weighted[1] == 0:
                return Calculation(None, "zero_denominator", provenance)
            value = weighted[0] / weighted[1]
            if rule.unit == "%":
                value *= 100
        else:
            value = sum(weighted, Decimal(0))
    if value < 0 and rule.report_scope != "check":
        return Calculation(None, "negative_usage", provenance)
    return bounded_result(
        value,
        "complete"
        if all(item and item.status in {"complete", "adjusted"} for item in values)
        else "abnormal_dependency",
        provenance,
    )


def validate_graph(
    points: dict[str, MeterDefinition],
    rules: dict[str, RuleDefinition],
    *,
    allow_missing: bool = False,
) -> list[str]:
    """Validate DAG and unit/type/aggregation ownership, returning evaluation order."""
    ordered: list[str] = []
    visiting: set[str] = set()
    definitions: dict[str, MeterDefinition | RuleDefinition] = {**points, **rules}

    def visit(key: str) -> None:
        if len(visiting) >= 32:
            raise ValueError("计算关系超过 32 层，请简化计算层级")
        if key in visiting:
            raise ValueError("计算关系存在循环引用")
        if key in ordered:
            return
        rule = rules[key]
        visiting.add(key)
        for term in rule.terms:
            source = definitions.get(term.metric_key)
            if source is None:
                if allow_missing:
                    continue
                raise ValueError(f"来源不存在：{term.metric_key}")
            if rule.enabled and not source.enabled:
                raise ValueError("启用的计算规则不能引用未启用来源")
            if rule.enabled and source.frequency != rule.frequency:
                raise ValueError("计算来源与结果的日／月计量周期必须一致")
            if (
                rule.enabled
                and rule.operation == "sum"
                and (
                    source.category,
                    source.unit,
                    source.quantity_kind,
                    source.temperature,
                )
                != (rule.category, rule.unit, rule.quantity_kind, rule.temperature)
            ):
                raise ValueError("加减计算的能源、单位、指标类型和温度必须一致")
            if rule.operation == "ratio" and source.quantity_kind == "ratio":
                raise ValueError("占比的来源必须是数量指标")
            if (
                rule.enabled
                and rule.operation == "sum"
                and source.enabled
                and source.report_scope == rule.report_scope
                and rule.report_scope in {"detail", "plant"}
                and max(source.active_from, rule.active_from)
                <= min(source.active_to or date.max, rule.active_to or date.max)
            ):
                raise ValueError(
                    "来源与计算结果不能同时进入同一汇总范围，请将来源设为原始来源"
                )
            if term.metric_key in rules:
                visit(term.metric_key)
        visiting.remove(key)
        ordered.append(key)

    for key in rules:
        visit(key)

    # Verify additive ownership at every effective-date boundary, preserving residuals.
    def leaves(key: str, day: date) -> dict[str, Decimal]:
        definition = definitions[key]
        if not active_on(definition, day):
            return {}
        if key in points:
            return {key: Decimal(1)}
        rule = rules[key]
        if rule.operation == "ratio":
            return {}
        result: dict[str, Decimal] = {}
        for term in rule.terms:
            for leaf, coefficient in leaves(term.metric_key, day).items():
                result[leaf] = (
                    result.get(leaf, Decimal(0)) + coefficient * term.coefficient
                )
        return {
            leaf: coefficient for leaf, coefficient in result.items() if coefficient
        }

    for day in {definition.active_from for definition in definitions.values()}:
        contributions: dict[tuple[str, str], list[Decimal]] = {}
        for key, definition in definitions.items():
            if active_on(definition, day) and definition.report_scope in {
                "detail",
                "plant",
            }:
                for leaf, coefficient in leaves(key, day).items():
                    contributions.setdefault(
                        (definition.report_scope, leaf), []
                    ).append(coefficient)
        for values in contributions.values():
            if len(values) > 1 and abs(sum(values, Decimal(0))) > 1:
                raise ValueError(
                    "共享计量点在多个汇总指标中重复统计，请配置分摊或差量关系"
                )
    return ordered
