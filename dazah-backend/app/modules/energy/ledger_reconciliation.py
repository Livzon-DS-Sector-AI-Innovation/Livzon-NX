"""Keep reported results as review evidence, separate from accepted native usage."""

from datetime import date
from decimal import Decimal, localcontext

from pydantic import JsonValue

from app.modules.energy.ledger_calculations import Calculation
from app.modules.energy.ledger_schemas import (
    RuleDefinition,
    UsageReview,
    UsageReviewPeriod,
    WorkbookCell,
)


def source_comparison(
    result: Calculation, source: WorkbookCell
) -> dict[str, JsonValue] | None:
    if source.value is None or source.value < 0 or source.status != "complete":
        return None
    with localcontext() as context:
        context.prec = 60
        difference = source.value - result.value if result.value is not None else None
    return {
        "reported_value": str(source.value),
        "calculation_status": result.status,
        "difference": str(difference) if difference is not None else None,
        "source": f"{source.provenance.get('source_sheet')}!"
        f"{source.provenance.get('source_cell')}",
    }


def source_result_review(
    day: date, rule: RuleDefinition, result: Calculation, source: WorkbookCell
) -> UsageReview | None:
    """Review failed calculations or differing hand-entered historical results.

    Formula date offsets alone do not authorize replacing business-date results.
    Missing inputs and invalid source results retain their original quality state.
    """
    comparison = source_comparison(result, source)
    if comparison is None or rule.source_column is None or source.value is None:
        return None
    failed = result.status in {"abnormal_dependency", "negative_usage"}
    differs = (
        result.status == "complete"
        and result.value is not None
        and abs(Decimal(str(comparison["difference"]))) > Decimal(".00000001")
        and source.provenance.get("source_kind") == "literal"
    )
    if not failed and not differs:
        return None
    reason = (
        "表码回退或来源计算异常，系统无法重算；原表已有结果，需核对清零、回卷或人工修正依据"
        if failed
        else "原表手填结果与系统重算不一致，需核对人工修正依据"
    )
    return UsageReview(
        dataset=rule.source_sheet,
        column=rule.source_column,
        periods=[
            UsageReviewPeriod(
                start_date=day,
                end_date=day,
                reason=reason,
                source=str(comparison["source"]),
                reported_values={day: source.value},
            )
        ],
    )
