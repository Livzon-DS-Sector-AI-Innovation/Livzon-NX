from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.modules.agent.automation_schedule import (
    next_fire_at,
    normalize_schedule_config,
    preview_next_fires,
)
from app.modules.agent.automation_schema import (
    AutomationDefinitionV1,
    AutomationErrorCode,
    compile_automation_definition,
)


def test_v11_requires_explicit_acyclic_reachable_control_flow() -> None:
    valid = AutomationDefinitionV1.model_validate(
        {
            "schema_version": "1.1",
            "name": "异常分支",
            "steps": [
                {
                    "key": "check",
                    "type": "condition",
                    "expression": {
                        "field": "trigger.count",
                        "op": "gt",
                        "value": 0,
                    },
                    "if_true": "notify",
                    "if_false": "done",
                },
                {
                    "key": "notify",
                    "type": "transform",
                    "operations": [
                        {"op": "template", "template": "发现 {{trigger.count}} 条"}
                    ],
                    "next": "done",
                },
                {"key": "done", "type": "end", "status": "succeeded"},
            ],
        }
    )

    assert valid.schema_version == "1.1"

    with pytest.raises(ValidationError, match="cycle"):
        AutomationDefinitionV1.model_validate(
            {
                "schema_version": "1.1",
                "name": "循环流程",
                "steps": [
                    {
                        "key": "first",
                        "type": "transform",
                        "operations": [{"op": "limit", "limit": 1}],
                        "next": "second",
                    },
                    {
                        "key": "second",
                        "type": "transform",
                        "operations": [{"op": "limit", "limit": 1}],
                        "next": "first",
                    },
                ],
            }
        )


def test_legacy_v10_linear_definition_remains_compatible() -> None:
    definition = AutomationDefinitionV1.model_validate(
        {
            "name": "旧流程",
            "steps": [
                {
                    "key": "prepare",
                    "type": "transform",
                    "operations": [{"op": "limit", "limit": 3}],
                },
                {"key": "done", "type": "end", "status": "succeeded"},
            ],
        }
    )

    assert definition.schema_version == "1.0"


def test_schedule_contract_supports_cron_once_and_interval() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    cron = normalize_schedule_config(
        trigger_type="schedule",
        schedule={"cron": "0 9 * * 1-5"},
        timezone="Asia/Shanghai",
    )
    once_at = now + timedelta(hours=2)
    once = normalize_schedule_config(
        trigger_type="schedule",
        schedule={"kind": "once", "run_at": once_at.isoformat()},
        timezone="Asia/Shanghai",
    )
    interval = normalize_schedule_config(
        trigger_type="schedule",
        schedule={
            "kind": "interval",
            "every": 2,
            "unit": "hours",
            "anchor_at": now.isoformat(),
        },
        timezone="Asia/Shanghai",
    )

    assert cron == {"kind": "cron", "cron": "0 9 * * 1-5"}
    assert once["run_at"] == once_at.isoformat()
    assert next_fire_at(schedule=once, timezone="Asia/Shanghai", after=now) == once_at
    assert preview_next_fires(
        schedule=interval,
        timezone="Asia/Shanghai",
        count=3,
        after=now,
    ) == [
        now + timedelta(hours=2),
        now + timedelta(hours=4),
        now + timedelta(hours=6),
    ]


def test_high_risk_tool_is_rejected_even_when_marked_workflow_allowed() -> None:
    definition = AutomationDefinitionV1.model_validate(
        {
            "name": "危险流程",
            "steps": [
                {
                    "key": "danger",
                    "type": "tool",
                    "operation": "quality.approve_deviation",
                }
            ],
        }
    )

    report = compile_automation_definition(
        definition,
        capabilities={
            "quality.approve_deviation": {
                "workflow_allowed": True,
                "human_decision_required": False,
                "risk_level": "high",
                "module": "quality",
            }
        },
    )

    assert not report.valid
    assert report.issues[0].code == AutomationErrorCode.HIGH_RISK_UNATTENDED
