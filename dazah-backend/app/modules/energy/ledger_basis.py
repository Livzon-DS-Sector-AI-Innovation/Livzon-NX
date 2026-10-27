"""Explain a dated reporting group using its historical definitions and facts."""

from datetime import date
from decimal import Decimal

from openpyxl.utils.cell import get_column_letter

from app.core.exceptions import AppException
from app.modules.energy.ledger_schemas import (
    MeterDefinition,
    ReportBasis,
    ReportBasisNode,
    RuleDefinition,
    UsageRow,
)


def build_report_basis(
    day: date,
    root_keys: list[str],
    definitions: dict[str, MeterDefinition | RuleDefinition],
    facts: dict[str, UsageRow],
) -> ReportBasis:
    """Retain intermediate sums/adjustments; never invent leaf contributions."""
    nodes: list[ReportBasisNode] = []

    def visit(
        key: str,
        node_id: str,
        parent_id: str | None,
        coefficient: Decimal,
        ancestors: frozenset[str],
    ) -> None:
        if len(nodes) >= 5000:
            raise AppException(422, "计算依据过多，请缩小统计范围或简化计算关系")
        definition = definitions.get(key)
        if definition is None:
            nodes.append(
                ReportBasisNode(
                    node_id=node_id,
                    parent_id=parent_id,
                    name="来源配置缺失",
                    coefficient=coefficient,
                    status="missing_dependency",
                )
            )
            return
        fact = facts.get(key)
        evidence = fact.provenance if fact else {}
        raw_dates = evidence.get("reading_dates")
        raw_values = evidence.get("reading_values")
        adjustment = evidence.get("adjustment")
        adjustment_mode = (
            "替换为"
            if isinstance(adjustment, dict) and adjustment.get("mode") == "override"
            else "增减"
        )
        node = ReportBasisNode(
            node_id=node_id,
            parent_id=parent_id,
            name=definition.name.rsplit("·", 1)[-1].strip(),
            source_sheet=definition.source_sheet,
            source_column=get_column_letter(definition.source_column)
            if definition.source_column
            else "",
            coefficient=coefficient,
            value=fact.effective_value if fact else None,
            calculated_value=fact.calculated_value if fact else None,
            status=fact.status
            if fact
            else "missing_reading"
            if isinstance(definition, MeterDefinition)
            else "missing_dependency",
            reading_dates=[str(value) for value in raw_dates]
            if isinstance(raw_dates, list)
            else [],
            reading_values=[
                None if value is None else str(value) for value in raw_values
            ]
            if isinstance(raw_values, list)
            else [],
            note=f"人工修正：{adjustment_mode} {adjustment.get('value')}；"
            f"{adjustment.get('reason', '')}"
            if isinstance(adjustment, dict)
            else "",
        )
        if isinstance(definition, MeterDefinition):
            node.reading_type = definition.reading_type
            node.multiplier = str(definition.multiplier)
        else:
            node.operation = definition.operation
        reviews = evidence.get("review")
        if isinstance(reviews, list):
            reasons = [
                str(review["reason"])
                for review in reviews
                if isinstance(review, dict) and review.get("reason")
            ]
            if reasons:
                node.note = "；".join(
                    filter(None, [node.note, "待确认：" + "；".join(reasons)])
                )
        nodes.append(node)
        if isinstance(definition, RuleDefinition):
            if key in ancestors or len(ancestors) >= 32:
                node.note = "计算关系存在循环或超过展示深度，请核对配置"
                return
            for index, term in enumerate(definition.terms):
                visit(
                    term.metric_key,
                    f"{node_id}.{index}",
                    node_id,
                    term.coefficient,
                    ancestors | {key},
                )

    for index, key in enumerate(root_keys):
        visit(key, str(index), None, Decimal(1), frozenset())
    return ReportBasis(usage_date=day, nodes=nodes)
