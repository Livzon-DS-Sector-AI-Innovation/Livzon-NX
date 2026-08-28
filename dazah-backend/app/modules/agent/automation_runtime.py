from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from app.modules.agent.automation_schema import (
    ConditionExpression,
    ConditionGroup,
    ConditionPredicate,
    TransformOperation,
    ValueReference,
)


def lookup_path(context: Mapping[str, Any], path: str) -> Any:
    cursor: Any = context
    for part in path.split("."):
        if isinstance(cursor, Mapping) and part in cursor:
            cursor = cursor[part]
            continue
        if isinstance(cursor, list) and part.isdigit() and int(part) < len(cursor):
            cursor = cursor[int(part)]
            continue
        return None
    return cursor


def evaluate_condition(
    expression: ConditionExpression, context: Mapping[str, Any]
) -> bool:
    if isinstance(expression, ConditionGroup):
        if expression.all is not None:
            return all(evaluate_condition(item, context) for item in expression.all)
        if expression.any is not None:
            return any(evaluate_condition(item, context) for item in expression.any)
        if expression.not_ is not None:
            return not evaluate_condition(expression.not_, context)
        return False
    return _evaluate_predicate(expression, context)


def _evaluate_predicate(
    predicate: ConditionPredicate, context: Mapping[str, Any]
) -> bool:
    actual = lookup_path(context, predicate.field)
    expected = predicate.value
    if isinstance(expected, ValueReference):
        expected = lookup_path(context, expected.ref)
    if isinstance(expected, list):
        expected = [
            lookup_path(context, item.ref) if isinstance(item, ValueReference) else item
            for item in expected
        ]
    match predicate.op:
        case "eq":
            return bool(actual == expected)
        case "ne":
            return bool(actual != expected)
        case "gt":
            return _ordered(actual, expected, lambda left, right: left > right)
        case "gte":
            return _ordered(actual, expected, lambda left, right: left >= right)
        case "lt":
            return _ordered(actual, expected, lambda left, right: left < right)
        case "lte":
            return _ordered(actual, expected, lambda left, right: left <= right)
        case "in":
            return isinstance(expected, list) and actual in expected
        case "not_in":
            return isinstance(expected, list) and actual not in expected
        case "contains":
            return actual is not None and expected in actual
        case "exists":
            return actual is not None
    return False


def _ordered(left: Any, right: Any, compare: Any) -> bool:
    try:
        return bool(compare(left, right))
    except TypeError:
        return False


def apply_transforms(
    operations: list[TransformOperation], context: Mapping[str, Any]
) -> Any:
    value: Any = dict(context)
    for operation in operations:
        source = lookup_path(context, operation.source) if operation.source else value
        if operation.op == "select":
            value = _select(source, operation.fields)
        elif operation.op == "rename":
            value = _rename(source, operation.fields)
        elif operation.op == "filter":
            value = _filter(source, operation)
        elif operation.op == "sort":
            value = _sort(source, operation)
        elif operation.op == "limit":
            value = (
                list(source or [])[: operation.limit]
                if isinstance(source, list)
                else source
            )
        elif operation.op == "aggregate":
            value = _aggregate(source, operation.fields)
        elif operation.op == "group_by":
            value = _group_by(source, operation.group_by)
        elif operation.op == "template":
            value = _render_template(operation.template or "", context)
        if operation.target:
            value = {operation.target: value}
    return value


def _select(source: Any, fields: list[str]) -> Any:
    if isinstance(source, list):
        return [_select(item, fields) for item in source]
    if isinstance(source, Mapping):
        return {field: lookup_path(source, field) for field in fields}
    return source


def _rename(source: Any, fields: list[str]) -> Any:
    mapping = {}
    for item in fields:
        if ":" not in item:
            raise ValueError("rename fields must use source:target")
        old, new = item.split(":", maxsplit=1)
        mapping[old] = new
    if isinstance(source, list):
        return [_rename(item, fields) for item in source]
    if isinstance(source, Mapping):
        return {mapping.get(str(key), str(key)): value for key, value in source.items()}
    return source


def _filter(source: Any, operation: TransformOperation) -> list[Any]:
    if not isinstance(source, list):
        return []
    return [item for item in source if _filter_matches(item, operation)]


def _filter_matches(item: Any, operation: TransformOperation) -> bool:
    actual = lookup_path(item, operation.field or "")
    expected = operation.value
    match operation.operator:
        case "eq":
            return bool(actual == expected)
        case "ne":
            return bool(actual != expected)
        case "gt":
            return _ordered(actual, expected, lambda left, right: left > right)
        case "gte":
            return _ordered(actual, expected, lambda left, right: left >= right)
        case "lt":
            return _ordered(actual, expected, lambda left, right: left < right)
        case "lte":
            return _ordered(actual, expected, lambda left, right: left <= right)
        case "contains":
            return actual is not None and expected in actual
        case "exists":
            return actual is not None
    return False


def _sort(source: Any, operation: TransformOperation) -> Any:
    if not isinstance(source, list):
        return source
    return sorted(
        source,
        key=lambda item: (
            lookup_path(item, operation.field or "") is None,
            lookup_path(item, operation.field or ""),
        ),
        reverse=operation.descending,
    )


def _aggregate(source: Any, fields: list[str]) -> dict[str, Any]:
    items = source if isinstance(source, list) else []
    result: dict[str, Any] = {"count": len(items)}
    for field in fields:
        values = [lookup_path(item, field) for item in items]
        numbers = [
            item
            for item in values
            if isinstance(item, int | float) and not isinstance(item, bool)
        ]
        result[field] = {
            "count": len(values),
            "sum": sum(numbers) if numbers else None,
            "min": min(numbers) if numbers else None,
            "max": max(numbers) if numbers else None,
        }
    return result


def _group_by(source: Any, fields: list[str]) -> list[dict[str, Any]]:
    if not isinstance(source, list):
        return []
    groups: dict[tuple[Any, ...], list[Any]] = {}
    for item in source:
        key = tuple(lookup_path(item, field) for field in fields)
        groups.setdefault(key, []).append(item)
    return [
        {
            "group": dict(zip(fields, key, strict=True)),
            "count": len(items),
            "items": items,
        }
        for key, items in groups.items()
    ]


_TEMPLATE_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")


def _render_template(template: str, context: Mapping[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = lookup_path(context, match.group(1))
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    return _TEMPLATE_PATTERN.sub(replace, template)
