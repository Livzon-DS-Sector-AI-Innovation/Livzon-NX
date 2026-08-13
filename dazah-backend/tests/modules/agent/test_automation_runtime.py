from app.modules.agent.automation_runtime import apply_transforms, evaluate_condition
from app.modules.agent.automation_schema import (
    ConditionGroup,
    ConditionPredicate,
    TransformOperation,
)


def test_condition_groups_and_references_are_deterministic() -> None:
    expression = ConditionGroup(
        all=[
            ConditionPredicate(field="steps.query.count", op="gt", value=0),
            ConditionPredicate(field="trigger.factory", op="eq", value="F-1"),
        ]
    )

    assert evaluate_condition(
        expression,
        {"trigger": {"factory": "F-1"}, "steps": {"query": {"count": 2}}},
    )


def test_transform_pipeline_filters_sorts_limits_and_templates() -> None:
    context = {
        "steps": {
            "query": {
                "items": [
                    {"name": "A", "count": 1},
                    {"name": "B", "count": 3},
                    {"name": "C", "count": 2},
                ]
            }
        }
    }
    result = apply_transforms(
        [
            TransformOperation(
                op="filter",
                source="steps.query.items",
                field="count",
                operator="gt",
                value=1,
            ),
            TransformOperation(op="sort", field="count", descending=True),
            TransformOperation(op="limit", limit=1),
        ],
        context,
    )
    rendered = apply_transforms(
        [TransformOperation(op="template", template="共 {{steps.query.items}}")],
        context,
    )

    assert result == [{"name": "B", "count": 3}]
    assert rendered.startswith("共 [")
