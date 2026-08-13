import pytest
from fastapi import HTTPException

from app.modules.agent.interaction_service import (
    _has_complete_record,
    _has_sheet_values,
    _validate_values,
)

SCHEMA = [
    {"key": "name", "label": "姓名", "type": "text", "required": True},
    {"key": "amount", "label": "数量", "type": "number", "required": False},
    {
        "key": "tags",
        "label": "标签",
        "type": "multi_select",
        "required": False,
        "options": ["复核", "通过"],
    },
    {"key": "confirmed", "label": "确认", "type": "boolean", "required": False},
    {"key": "due_date", "label": "日期", "type": "date", "required": False},
]


def test_interaction_values_are_checked_against_schema_and_write_scope() -> None:
    assert _validate_values(
        {"name": "张三", "amount": 2, "tags": ["复核"]},
        SCHEMA,
        writable_fields={"name", "amount", "tags"},
    ) == {"name": "张三", "amount": 2, "tags": ["复核"]}


def test_feishu_form_strings_are_safely_coerced_by_declared_field_type() -> None:
    result = _validate_values(
        {
            "name": "张三",
            "amount": "2.5",
            "confirmed": "是",
            "due_date": "2026-08-11",
        },
        SCHEMA,
        writable_fields={"name", "amount", "confirmed", "due_date"},
    )

    assert result["name"] == "张三"
    assert result["amount"] == 2.5
    assert result["confirmed"] is True
    assert isinstance(result["due_date"], int)


@pytest.mark.parametrize(
    ("values", "writable_fields"),
    [
        ({"amount": 2}, {"name", "amount"}),
        ({"name": "张三", "unknown": "x"}, {"name"}),
        ({"name": "张三", "amount": "two"}, {"name", "amount"}),
        ({"name": "张三", "amount": 2}, {"name"}),
    ],
)
def test_interaction_values_fail_closed(
    values: dict[str, object], writable_fields: set[str]
) -> None:
    with pytest.raises(HTTPException):
        _validate_values(values, SCHEMA, writable_fields=writable_fields)


def test_table_link_readback_requires_complete_key_fields() -> None:
    assert _has_complete_record(
        {"items": [{"fields": {"name": "张三", "amount": 2}}]},
        ["name", "amount"],
    )
    assert not _has_complete_record(
        {"items": [{"fields": {"name": "张三", "amount": ""}}]},
        ["name", "amount"],
    )


def test_sheet_link_readback_requires_at_least_one_non_empty_cell() -> None:
    assert _has_sheet_values({"values": [["姓名", "张三"], ["数量", 2]]})
    assert not _has_sheet_values({"values": [["", None], []]})
