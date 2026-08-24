from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as _SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.agent import agent_tools
from app.modules.agent import api as agent_api
from app.modules.agent import automation_runtime as automation_runtime_module
from app.modules.agent.automation_runner import AutomationNodeError
from app.modules.agent.automation_runtime import (
    apply_transforms,
    evaluate_condition,
    lookup_path,
)
from app.modules.agent.automation_schedule import (
    next_fire_at,
    normalize_schedule_config,
    preview_next_fires,
)
from app.modules.agent.automation_schema import (
    AutomationDefinitionV1,
    ConditionGroup,
    ConditionPredicate,
    RecipientRule,
    TransformOperation,
    ValueReference,
)
from app.modules.agent.automation_service import AgentAutomationService
from app.modules.agent.interaction_schemas import (
    FeishuResourceTemplateCreate,
    InteractionFormField,
    InteractionRequestCreate,
)
from app.modules.agent.push_delivery_service import (
    _card_action_elements,
    _card_form_field,
)
from app.modules.agent.schemas import AgentAutomationTriggerCreate
from app.modules.agent.tools import EmptyToolInput, ToolContext

SimpleNamespace: Any = _SimpleNamespace


def _context() -> dict[str, object]:
    return {
        "trigger": {"number": 3, "label": "urgent"},
        "steps": {
            "reference": 3,
            "rows": [
                {"name": "A", "score": 1, "tags": ["normal"], "group": "x"},
                {"name": "B", "score": 3, "tags": ["urgent"], "group": "x"},
                {"name": "C", "score": 2, "tags": [], "group": "y"},
            ],
        },
    }


def test_automation_runtime_covers_predicates_and_transform_operations() -> None:
    context = _context()
    assert lookup_path(context, "steps.rows.0.score") == 1
    assert lookup_path(context, "steps.rows.99") is None
    assert lookup_path(context, "steps.missing") is None

    predicates = [
        ("eq", 3, True),
        ("ne", 2, True),
        ("gt", 2, True),
        ("gte", 3, True),
        ("lt", 4, True),
        ("lte", 3, True),
        ("in", [2, 3], True),
        ("not_in", [1, 2], True),
        ("contains", "gen", True),
        ("exists", None, True),
    ]
    for operator, value, expected in predicates:
        assert (
            evaluate_condition(
                ConditionPredicate(
                    field="trigger.number"
                    if operator != "contains"
                    else "trigger.label",
                    op=operator,
                    value=value,
                ),
                context,
            )
            is expected
        )

    assert evaluate_condition(
        ConditionPredicate(
            field="trigger.number",
            op="eq",
            value=ValueReference(ref="steps.reference"),
        ),
        context,
    )
    assert evaluate_condition(
        ConditionPredicate(
            field="trigger.number",
            op="in",
            value=[ValueReference(ref="steps.reference"), 4],
        ),
        context,
    )
    assert not evaluate_condition(
        ConditionPredicate(field="trigger.label", op="gt", value=2), context
    )
    assert evaluate_condition(
        ConditionGroup(
            any=[
                ConditionPredicate(field="trigger.number", op="eq", value=99),
                ConditionPredicate(field="trigger.number", op="eq", value=3),
            ]
        ),
        context,
    )
    assert evaluate_condition(
        ConditionGroup.model_validate(
            {
                "not": {
                    "field": "trigger.number",
                    "op": "eq",
                    "value": 99,
                }
            }
        ),
        context,
    )

    rows = context["steps"]["rows"]  # type: ignore[index]
    assert apply_transforms(
        [
            TransformOperation(
                op="select",
                source="steps.rows",
                fields=["name", "score"],
            )
        ],
        context,
    ) == [
        {"name": "A", "score": 1},
        {"name": "B", "score": 3},
        {"name": "C", "score": 2},
    ]
    assert (
        apply_transforms(
            [
                TransformOperation(
                    op="rename",
                    source="steps.rows",
                    fields=["name:label"],
                )
            ],
            context,
        )[1]["label"]
        == "B"
    )
    assert (
        apply_transforms(
            [
                TransformOperation(
                    op="rename", source="steps.missing", fields=["old:new"]
                )
            ],
            context,
        )
        is None
    )

    filter_cases = [
        ("eq", 1, ["A"]),
        ("ne", 1, ["B", "C"]),
        ("gt", 1, ["B", "C"]),
        ("gte", 2, ["B", "C"]),
        ("lt", 2, ["A"]),
        ("lte", 2, ["A", "C"]),
        ("contains", "urgent", ["B"]),
        ("exists", None, ["A", "B", "C"]),
    ]
    for operator, value, names in filter_cases:
        filtered = apply_transforms(
            [
                TransformOperation(
                    op="filter",
                    source="steps.rows",
                    field="tags"
                    if operator == "contains"
                    else "name"
                    if operator == "exists"
                    else "score",
                    operator=operator,
                    value=value,
                )
            ],
            context,
        )
        assert [item["name"] for item in filtered] == names

    assert (
        apply_transforms(
            [
                TransformOperation(
                    op="sort", source="steps.rows", field="score", descending=True
                )
            ],
            context,
        )[0]["name"]
        == "B"
    )
    assert (
        apply_transforms(
            [TransformOperation(op="limit", source="steps.rows", limit=2)], context
        )
        == rows[:2]
    )
    aggregate = apply_transforms(
        [
            TransformOperation(
                op="aggregate", source="steps.rows", fields=["score", "missing"]
            )
        ],
        context,
    )
    assert aggregate["score"] == {"count": 3, "sum": 6, "min": 1, "max": 3}
    assert aggregate["missing"]["sum"] is None
    groups = apply_transforms(
        [TransformOperation(op="group_by", source="steps.rows", group_by=["group"])],
        context,
    )
    assert [item["count"] for item in groups] == [2, 1]
    templated = apply_transforms(
        [
            TransformOperation(
                op="template",
                template="{{trigger.label}}/{{trigger.number}}/{{missing}}",
                target="message",
            )
        ],
        context,
    )
    assert templated == {"message": "urgent/3/"}

    with pytest.raises(ValueError, match="source:target"):
        apply_transforms([TransformOperation(op="rename", fields=["invalid"])], context)

    empty_group = ConditionGroup.model_construct(all=None, any=None, not_=None)
    assert not evaluate_condition(empty_group, context)
    unknown_predicate = ConditionPredicate.model_construct(
        field="trigger.number",
        op="unknown",  # type: ignore[arg-type]
        value=None,
    )
    assert not evaluate_condition(unknown_predicate, context)
    assert automation_runtime_module._select(1, ["value"]) == 1
    assert (
        automation_runtime_module._filter(
            1, TransformOperation.model_construct(op="filter")
        )
        == []
    )
    assert not automation_runtime_module._filter_matches(
        {},
        TransformOperation.model_construct(operator="unknown", field="value"),  # type: ignore[arg-type, call-arg]
    )
    assert (
        automation_runtime_module._sort(
            1, TransformOperation.model_construct(op="sort")
        )
        == 1
    )
    assert automation_runtime_module._group_by(1, ["value"]) == []


def test_automation_node_error_keeps_machine_readable_code() -> None:
    error = AutomationNodeError("automation.test", "test failure")
    assert error.code == "automation.test"
    assert str(error) == "test failure"


def test_automation_schema_validates_edges_and_v11_graph_rules() -> None:
    with pytest.raises(ValidationError):
        ConditionPredicate(field="trigger.value", op="exists", value=1)
    with pytest.raises(ValidationError):
        ConditionPredicate(field="trigger.value", op="in", value=1)
    with pytest.raises(ValidationError):
        ConditionGroup(all=[])
    with pytest.raises(ValidationError):
        ConditionGroup(any=[])

    for rule in (
        RecipientRule(type="user", user_id="u-1"),
        RecipientRule(type="owner_field", source="trigger.owner"),
        RecipientRule(type="department_leader", department_ref="trigger.department"),
        RecipientRule(type="role_in_scope", role="buyer"),
    ):
        assert rule.type
    with pytest.raises(ValidationError):
        RecipientRule(type="user")

    invalid_operations = [
        {"op": "filter", "field": "score"},
        {"op": "sort"},
        {"op": "limit"},
        {"op": "template"},
        {"op": "group_by"},
    ]
    for operation in invalid_operations:
        with pytest.raises(ValidationError):
            TransformOperation.model_validate(operation)

    recipient = {"type": "user", "user_id": "u-1"}
    with pytest.raises(ValidationError):
        AutomationDefinitionV1.model_validate(
            {
                "name": "missing-target",
                "steps": [
                    {
                        "key": "check",
                        "type": "condition",
                        "expression": {
                            "field": "trigger.value",
                            "op": "exists",
                        },
                        "if_true": "missing",
                    },
                    {"key": "done", "type": "end", "status": "succeeded"},
                ],
            }
        )
    with pytest.raises(ValidationError):
        AutomationDefinitionV1.model_validate(
            {
                "schema_version": "1.1",
                "name": "end-next",
                "steps": [
                    {
                        "key": "done",
                        "type": "end",
                        "status": "succeeded",
                        "next": "done",
                    }
                ],
            }
        )
    with pytest.raises(ValidationError):
        AutomationDefinitionV1.model_validate(
            {
                "schema_version": "1.1",
                "name": "condition-branch",
                "steps": [
                    {
                        "key": "check",
                        "type": "condition",
                        "expression": {
                            "field": "trigger.value",
                            "op": "exists",
                        },
                        "if_true": "done",
                    },
                    {"key": "done", "type": "end", "status": "succeeded"},
                ],
            }
        )
    with pytest.raises(ValidationError):
        AutomationDefinitionV1.model_validate(
            {
                "schema_version": "1.1",
                "name": "missing-next",
                "steps": [
                    {
                        "key": "transform",
                        "type": "transform",
                        "operations": [{"op": "limit", "limit": 1}],
                    }
                ],
            }
        )
    with pytest.raises(ValidationError, match="unreachable"):
        AutomationDefinitionV1.model_validate(
            {
                "schema_version": "1.1",
                "name": "unreachable",
                "steps": [
                    {"key": "first", "type": "end", "status": "succeeded"},
                    {"key": "orphan", "type": "end", "status": "succeeded"},
                ],
            }
        )

    valid = AutomationDefinitionV1.model_validate(
        {
            "schema_version": "1.1",
            "name": "wait-timeout-target",
            "steps": [
                {
                    "key": "pause",
                    "type": "event_wait",
                    "event_type": "procurement.approved.v1",
                    "timeout_seconds": 1,
                    "next": "done",
                    "on_timeout": "done",
                },
                {"key": "done", "type": "end", "status": "succeeded"},
            ],
        }
    )
    assert valid.schema_version == "1.1"
    assert recipient["type"] == "user"


def test_schedule_validation_and_fire_time_edges() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    assert (
        normalize_schedule_config(
            trigger_type="manual", schedule={}, timezone="Asia/Shanghai"
        )
        == {}
    )
    with pytest.raises(HTTPException):
        normalize_schedule_config(
            trigger_type="manual", schedule={}, timezone="Invalid/Zone"
        )
    with pytest.raises(HTTPException):
        normalize_schedule_config(
            trigger_type="schedule",
            schedule={"kind": "once", "run_at": (now - timedelta(hours=1)).isoformat()},
            timezone="Asia/Shanghai",
        )
    for schedule in (
        {"kind": "interval", "every": True, "unit": "hours"},
        {"kind": "interval", "every": 1, "unit": "weeks"},
        {"kind": "interval", "every": 32, "unit": "days"},
        {"kind": "unsupported"},
        {"kind": "cron", "cron": "not a cron"},
        {"kind": "cron", "cron": "* * * * * *"},
    ):
        with pytest.raises(HTTPException):
            normalize_schedule_config(
                trigger_type="schedule", schedule=schedule, timezone="UTC"
            )
    for value in (None, "not-a-time", "2026-08-12T10:00:00"):
        with pytest.raises(HTTPException):
            normalize_schedule_config(
                trigger_type="schedule",
                schedule={"kind": "once", "run_at": value},
                timezone="UTC",
            )

    assert (
        next_fire_at(
            schedule={
                "kind": "once",
                "run_at": (now - timedelta(seconds=1)).isoformat(),
            },
            timezone="UTC",
            after=now,
        )
        is None
    )
    with pytest.raises(ValueError):
        next_fire_at(
            schedule={
                "kind": "interval",
                "every": 0,
                "unit": "hours",
                "anchor_at": now.isoformat(),
            },
            timezone="UTC",
            after=datetime.now(),
        )
    with pytest.raises(ValueError):
        next_fire_at(schedule={}, timezone="UTC", after=now)
    with pytest.raises(HTTPException):
        preview_next_fires(schedule={}, timezone="UTC", count=0, after=now)
    assert preview_next_fires(
        schedule={"kind": "once", "run_at": (now + timedelta(minutes=1)).isoformat()},
        timezone="UTC",
        count=2,
        after=now,
    )


def test_interaction_schema_rejects_unsafe_or_incomplete_inputs() -> None:
    with pytest.raises(ValidationError):
        InteractionFormField(key="choice", label="Choice", type="single_select")
    base = {
        "name": "Template",
        "resource_type": "bitable",
        "resource_url": "https://example.feishu.cn/base/abc",
        "base_token": "base",
        "table_id": "table",
    }
    with pytest.raises(ValidationError):
        FeishuResourceTemplateCreate(**{**base, "resource_url": "http://evil.test"})
    with pytest.raises(ValidationError):
        FeishuResourceTemplateCreate(**{**base, "writable_fields": ["unknown"]})
    with pytest.raises(ValidationError):
        FeishuResourceTemplateCreate(**{**base, "resource_type": "sheet"})
    with pytest.raises(ValidationError):
        FeishuResourceTemplateCreate(
            **{
                **base,
                "resource_type": "sheet",
                "sheet_range": "A1:B2",
                "field_schema": [{"key": "name", "label": "Name", "type": "text"}],
                "writable_fields": ["name"],
            }
        )

    request_base = {
        "template_id": uuid4(),
        "recipient_user_id": uuid4(),
        "title": "Fill in",
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
        "idempotency_key": "key-1",
    }
    with pytest.raises(ValidationError):
        InteractionRequestCreate(**{**request_base, "mode": "card_form"})
    with pytest.raises(ValidationError):
        InteractionRequestCreate(
            **{
                **request_base,
                "mode": "table_link",
                "form_schema": [{"key": "name", "label": "Name", "type": "text"}],
            }
        )
    with pytest.raises(ValidationError):
        InteractionRequestCreate(
            **{
                **request_base,
                "mode": "card_form",
                "form_schema": [{"key": "name", "label": "Name", "type": "text"}],
                "expires_at": datetime.now(),
            }
        )

    for collect_step in (
        {
            "key": "collect",
            "type": "collect",
            "mode": "card_form",
            "template_id": "template",
            "recipients": [{"type": "user", "user_id": "u-1"}],
        },
        {
            "key": "collect",
            "type": "collect",
            "mode": "table_link",
            "template_id": "template",
            "recipients": [{"type": "user", "user_id": "u-1"}],
            "fields": [{"key": "name", "label": "Name", "type": "text"}],
        },
    ):
        with pytest.raises(ValidationError):
            AutomationDefinitionV1.model_validate(
                {"name": "collect", "steps": [collect_step]}
            )


def test_push_card_helpers_render_interaction_and_action_variants() -> None:
    run_id = uuid4()
    elements = _card_action_elements(
        [
            {
                "type": "interaction_form",
                "label": "Submit",
                "interaction_request_id": "request",
                "interaction_version": 2,
                "fields": [
                    {"key": "when", "label": "When", "type": "date"},
                    {"key": "amount", "label": "Amount", "type": "number"},
                ],
            },
            {"type": "open_url", "label": "Open", "url": "https://feishu.cn/x"},
        ],
        run_id=run_id,
    )
    assert elements[0]["tag"] == "form"
    assert elements[1]["actions"][0]["behaviors"][0]["type"] == "open_url"
    assert _card_form_field({"key": "state", "type": "boolean"})["tag"] == (
        "select_static"
    )
    assert (
        _card_form_field({"key": "tags", "type": "multi_select", "options": ["a"]})[
            "tag"
        ]
        == "multi_select_static"
    )


@pytest.mark.anyio
async def test_agent_tool_wrappers_delegate_to_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = ToolContext(
        db=SimpleNamespace(),
        session_id=None,
        user_id=uuid4(),
        user=SimpleNamespace(id=uuid4()),
        reason=None,
        raw_request=None,  # type: ignore[arg-type]
    )

    class Dumpable:
        def __init__(self: Any, value: dict[str, object]) -> None:
            self.value = value

        def model_dump(self: Any, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return self.value  # type: ignore[no-any-return]

    class FakeInteractionService:
        async def list_templates(self: Any, _db: Any, *, user: Any) -> Any:
            assert user is context.user
            return [Dumpable({"id": "template"})]

        async def validate_template(
            self: Any, _db: Any, *, user: Any, template_id: Any
        ) -> Any:
            assert user is context.user
            assert template_id
            return Dumpable({"valid": True})

        async def list_requests(
            self: Any, _db: Any, *, user: Any, page: Any, page_size: Any
        ) -> Any:
            assert user is context.user
            return Dumpable({"page": page, "page_size": page_size})

        async def get_request(
            self: Any, _db: Any, *, user: Any, request_id: Any
        ) -> Any:
            assert user is context.user
            assert request_id
            return Dumpable({"id": str(request_id)})

    monkeypatch.setattr(
        agent_tools, "AgentInteractionService", lambda: FakeInteractionService()
    )
    assert await agent_tools.list_feishu_resource_templates(
        context, EmptyToolInput()
    ) == [{"id": "template"}]
    assert await agent_tools.validate_feishu_resource_template(
        context, agent_tools.FeishuResourceTemplateIdInput(template_id=uuid4())
    ) == {"valid": True}
    assert await agent_tools.list_interaction_requests(
        context, agent_tools.InteractionRequestListInput(page=2, page_size=3)
    ) == {"page": 2, "page_size": 3}
    request_id = uuid4()
    assert await agent_tools.get_interaction_request(
        context, agent_tools.InteractionRequestIdInput(request_id=request_id)
    ) == {"id": str(request_id)}

    automation_id = uuid4()

    class FakeAutomation:
        id = automation_id

        def model_dump(self: Any, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {"id": str(self.id)}

    class FakeAutomationService:
        async def update_automation(self: Any, _db: Any, **kwargs: Any) -> Any:
            assert kwargs["automation_id"] == automation_id
            return FakeAutomation()

        async def confirm_automation(self: Any, _db: Any, **kwargs: Any) -> Any:
            assert kwargs["automation_id"] == automation_id
            return FakeAutomation()

    monkeypatch.setattr(
        agent_tools,
        "_automation_service",
        lambda _context: FakeAutomationService(),
    )
    assert await agent_tools.update_automation(
        context,
        agent_tools.AutomationUpdateInput(
            automation_id=automation_id, change_summary="test"
        ),
    ) == {"automation": {"id": str(automation_id)}}

    with pytest.raises(ValidationError):
        agent_tools.DirectScheduledTaskCreateInput(
            name="missing schedule",
            requirement="run it",
            actions=[{"operation": "quality.list_deviations"}],
        )
    with pytest.raises(ValidationError):
        agent_tools.DirectScheduledTaskCreateInput(
            name="two schedules",
            requirement="run it",
            cron="0 9 * * 1-5",
            schedule={"kind": "cron", "cron": "0 9 * * 1-5"},
            actions=[{"operation": "quality.list_deviations"}],
        )


@pytest.mark.anyio
async def test_automation_preview_checks_schedules_and_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user: Any = SimpleNamespace(id=uuid4(), role="user")
    template_id = uuid4()
    definition = AutomationDefinitionV1.model_validate(
        {
            "name": "preview",
            "steps": [
                {
                    "key": "collect",
                    "type": "collect",
                    "mode": "card_form",
                    "template_id": str(template_id),
                    "recipients": [{"type": "user", "user_id": str(user.id)}],
                    "fields": [{"key": "name", "label": "Name", "type": "text"}],
                }
            ],
        }
    )
    report: Any = SimpleNamespace(
        definition=definition,
        valid=True,
        required_operations=[],
        required_modules=[],
        issues=[],
    )

    class PreviewDb:
        async def get(self: Any, _model: Any, requested_id: Any) -> Any:
            assert requested_id == template_id
            return SimpleNamespace(
                is_deleted=False,
                status="active",
                owner_user_id=None,
            )

    service = AgentAutomationService()

    async def compile_for_user(_db: Any, *, user: Any, definition: Any) -> Any:
        assert user is not None
        assert definition is not None
        return report, {"scope": "snapshot"}, {"agent.list": "1.0"}

    monkeypatch.setattr(service, "_compile_for_user", compile_for_user)
    result = await service.preview(
        PreviewDb(),  # type: ignore[arg-type]
        user=user,
        definition=definition,
        triggers=[
            AgentAutomationTriggerCreate(trigger_type="manual"),
            AgentAutomationTriggerCreate(
                trigger_type="schedule",
                schedule={"cron": "0 9 * * 1-5"},
                timezone="Asia/Shanghai",
            ),
        ],
    )

    assert result["valid"] is True
    assert len(result["schedule_previews"]) == 1
    assert result["feishu_template_checks"] == [
        {"template_id": str(template_id), "valid": True, "status": "active"}
    ]


@pytest.mark.anyio
async def test_interaction_api_wrappers_delegate_and_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user: Any = SimpleNamespace(id=uuid4())
    request_id = uuid4()
    template_id = uuid4()

    class FakeDb:
        def __init__(self: Any) -> None:
            self.commits = 0

        async def commit(self: Any) -> None:  # type: ignore[return]
            self.commits += 1

    class Dumpable:
        def __init__(self: Any, value: dict[str, object]) -> None:
            self.value = value

        def model_dump(self: Any, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return self.value

    class FakeInteractionService:
        async def create_template(
            self: Any, _db: Any, *, user: Any, request: Any
        ) -> Any:
            assert user is user_ref
            assert request is template_payload
            return Dumpable({"id": "template"})  # type: ignore[return-value]

        async def list_templates(self: Any, _db: Any, *, user: Any) -> Any:
            assert user is user_ref
            return [Dumpable({"id": "template"})]  # type: ignore[return-value]

        async def validate_template(
            self: Any, _db: Any, *, user: Any, template_id: Any
        ) -> Any:
            assert user is user_ref
            assert template_id == template_ref
            return Dumpable({"valid": True})  # type: ignore[return-value]

        async def create_request(
            self: Any, _db: Any, *, user: Any, request: Any
        ) -> Any:
            assert user is user_ref
            assert request is request_payload
            return Dumpable({"id": "request"})  # type: ignore[return-value]

        async def list_requests(
            self: Any, _db: Any, *, user: Any, page: Any, page_size: Any
        ) -> Any:
            assert user is user_ref
            assert (page, page_size) == (2, 100)
            return Dumpable({"page": page, "page_size": page_size})  # type: ignore[return-value]

        async def get_request(
            self: Any, _db: Any, *, user: Any, request_id: Any
        ) -> Any:
            assert user is user_ref
            assert request_id == request_ref
            return Dumpable({"id": str(request_id)})  # type: ignore[return-value]

        async def submit(
            self: Any, _db: Any, *, user: Any, request_id: Any, request: Any
        ) -> Any:
            assert user is user_ref
            assert request_id == request_ref
            assert request is submission_payload
            return Dumpable({"status": "submitted"})  # type: ignore[return-value]

    user_ref = user
    template_ref = template_id
    request_ref = request_id
    template_payload: Any = object()
    request_payload: Any = object()
    submission_payload: Any = object()
    monkeypatch.setattr(
        agent_api, "AgentInteractionService", lambda: FakeInteractionService()
    )
    db: Any = cast(Any, FakeDb)()

    await agent_api.create_feishu_resource_template(
        template_payload, db=db, current_user=user
    )
    await agent_api.list_feishu_resource_templates(db=db, current_user=user)
    await agent_api.validate_feishu_resource_template(
        template_id, db=db, current_user=user
    )
    await agent_api.create_interaction_request(
        request_payload, db=db, current_user=user
    )
    await agent_api.list_interaction_requests(
        page=2, page_size=1000, db=db, current_user=user
    )
    await agent_api.get_interaction_request(request_id, db=db, current_user=user)
    await agent_api.submit_interaction_request(
        request_id, submission_payload, db=db, current_user=user
    )

    assert db.commits == 4


@pytest.mark.anyio
async def test_internal_interaction_api_validates_subject_and_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    user: Any = SimpleNamespace(id=uuid4())
    db: Any = SimpleNamespace(commits=0)

    async def commit() -> None:
        db.commits += 1

    db.commit = commit
    payload: Any = SimpleNamespace(subject=object(), submission=object())
    settings: Any = SimpleNamespace(HERMES_INTERNAL_TOKEN="internal-token")

    def check_token(expected: str, authorization: str | None) -> None:
        assert expected == "internal-token"
        assert authorization == "Bearer internal-token"

    async def resolve_user(_db: Any, *, subject: Any) -> Any:
        assert subject is payload.subject
        return user

    class FakeService:
        async def submit(
            self: Any, _db: Any, *, user: Any, request_id: Any, request: Any
        ) -> Any:
            assert user is not None
            assert request_id == request_ref
            assert request is payload.submission
            return Dumpable({"status": "submitted"})  # type: ignore[return-value]

    class Dumpable:
        def __init__(self: Any, value: dict[str, object]) -> None:
            self.value = value

        def model_dump(self: Any, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return self.value

    request_ref = request_id
    monkeypatch.setattr(agent_api, "require_service_token", check_token)
    monkeypatch.setattr(agent_api, "_require_feishu_subject_user", resolve_user)
    monkeypatch.setattr(agent_api, "AgentInteractionService", lambda: FakeService())

    await agent_api.submit_internal_feishu_interaction_request(
        request_id,
        payload,
        db=db,
        authorization="Bearer internal-token",
        settings=settings,
    )
    assert db.commits == 1
