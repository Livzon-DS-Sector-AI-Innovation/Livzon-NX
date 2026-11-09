from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.modules.energy.ledger_basis import build_report_basis
from app.modules.energy.ledger_schemas import (
    MeterDefinition,
    RuleDefinition,
    RuleTerm,
    UsageRow,
)

DAY = date(2026, 7, 28)


def test_basis_explains_pending_review_without_losing_calculation() -> None:
    source = fact(
        "point:water",
        "10",
        status="pending_review",
        effective_value=None,
        provenance={"review": [{"reason": "原表值与差分冲突"}]},
    )
    basis = build_report_basis(
        DAY,
        ["point:water"],
        {"point:water": meter()},
        {"point:water": source},
    )
    assert basis.nodes[0].value is None
    assert basis.nodes[0].calculated_value == Decimal(10)
    assert "待确认：原表值与差分冲突" in basis.nodes[0].note


def test_reference_manual_value_does_not_replace_formula_or_hide_dependencies():
    basis = build_report_basis(
        DAY,
        ["rule:total"],
        {"rule:total": rule(), "point:water": meter()},
        {
            "rule:total": fact(
                "rule:total",
                "20",
                provenance={
                    "reference": {
                        "source_sheet": "日用量",
                        "source_column": 5,
                        "reported_value": "999",
                    },
                },
            ),
            "point:water": fact("point:water", "40"),
        },
    )
    assert basis.nodes[0].operation == "sum"
    assert basis.nodes[0].value == 20
    assert basis.nodes[0].source_column == "E"
    assert "999（仅留痕，不参与计算）" in basis.nodes[0].note
    assert basis.nodes[1].value == 40


def test_basis_uses_actual_source_formula_instead_of_old_normalized_terms() -> None:
    original = fact(
        "rule:total",
        "30",
        provenance={
            "source_sheet": "日用量",
            "source_cell": "B28",
            "formula": "=电量!B27*3",
            "sources": [{"sheet": "电量", "cell": "B27", "value": "10"}],
        },
    )
    basis = build_report_basis(
        DAY,
        ["rule:total"],
        {"rule:total": rule(), "point:water": meter()},
        {"rule:total": original},
    )
    assert len(basis.nodes) == 1
    assert basis.nodes[0].operation == "source"
    assert "原表公式：=电量!B27*3" in basis.nodes[0].note
    assert "引用：电量!B27 = 10" in basis.nodes[0].note


def meter() -> MeterDefinition:
    return MeterDefinition(
        code="water",
        name="原表·制水里",
        area="制水",
        department="能源",
        category="drinking_water",
        unit="m³",
        active_from=DAY,
        source_sheet="饮用水码",
        source_column=14,
    )


def rule() -> RuleDefinition:
    return RuleDefinition(
        code="total",
        name="日总量·饮用水",
        department="能源",
        category="drinking_water",
        unit="m³",
        active_from=DAY,
        terms=[RuleTerm(metric_key="point:water", coefficient=Decimal("0.5"))],
    )


def fact(key: str, value: str, **updates: object) -> UsageRow:
    return UsageRow.model_validate(
        {
            "id": uuid4(),
            "metric_key": key,
            "usage_date": DAY,
            "name": "用量",
            "category": "drinking_water",
            "unit": "m³",
            "department": "能源",
            "workshop": "",
            "report_scope": "source",
            "quantity_kind": "volume",
            "temperature": "",
            "status": "complete",
            "effective_value": value,
            "calculated_value": value,
            "provenance": {},
            **updates,
        }
    )


def test_basis_retains_original_field_readings_coefficients_and_adjustments() -> None:
    definitions = {"point:water": meter(), "rule:total": rule()}
    facts = {
        "point:water": fact(
            "point:water",
            "4576",
            provenance={
                "reading_dates": ["2026-07-28", "2026-07-29"],
                "reading_values": ["6540992", "6545568"],
            },
        ),
        "rule:total": fact(
            "rule:total",
            "2300",
            status="adjusted",
            calculated_value="2288",
            provenance={
                "adjustment": {
                    "mode": "override",
                    "value": "2300",
                    "reason": "核对修正",
                },
            },
        ),
    }
    basis = build_report_basis(DAY, ["rule:total"], definitions, facts)
    root, source = basis.nodes
    assert basis.usage_date == DAY
    assert root.value == Decimal(2300) and root.calculated_value == Decimal(2288)
    assert "核对修正" in root.note
    assert source.source_sheet == "饮用水码" and source.source_column == "N"
    assert source.name == "制水里" and source.value == Decimal(4576)
    assert source.reading_values == ["6540992", "6545568"]
    assert source.coefficient == Decimal("0.5") and source.parent_id == root.node_id


def test_basis_does_not_turn_missing_sources_into_zero_or_loop_on_cycles() -> None:
    missing = build_report_basis(DAY, ["rule:total"], {"rule:total": rule()}, {})
    assert missing.nodes[1].value is None and missing.nodes[1].name == "来源配置缺失"
    cycle = rule().model_copy(update={"terms": [RuleTerm(metric_key="rule:total")]})
    result = build_report_basis(DAY, ["rule:total"], {"rule:total": cycle}, {})
    assert len(result.nodes) == 2 and "循环" in result.nodes[1].note


def test_basis_explains_zero_direct_usage_without_fabricating_counter_readings() -> (
    None
):
    direct = meter().model_copy(update={"reading_type": "direct"})
    result = build_report_basis(
        DAY,
        ["point:water"],
        {"point:water": direct},
        {"point:water": fact("point:water", "0")},
    )
    assert result.nodes[0].value == 0 and result.nodes[0].reading_type == "direct"
    assert result.nodes[0].reading_dates == []
    missing = build_report_basis(DAY, ["point:water"], {"point:water": direct}, {})
    assert missing.nodes[0].value is None
    assert missing.nodes[0].status == "missing_reading"


def test_basis_bounds_expansion_of_shared_dependency_paths() -> None:
    total = rule().model_copy(
        update={
            "terms": [RuleTerm(metric_key="point:water")] * 5000,
        }
    )
    with pytest.raises(AppException, match="计算依据过多"):
        build_report_basis(
            DAY,
            ["rule:total"],
            {"rule:total": total, "point:water": meter()},
            {},
        )
