from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AutomationErrorCode(StrEnum):
    INVALID_SCHEMA = "automation.invalid_schema"
    UNSUPPORTED_SCHEMA_VERSION = "automation.unsupported_schema_version"
    UNSUPPORTED_NODE_TYPE = "automation.unsupported_node_type"
    DUPLICATE_STEP_KEY = "automation.duplicate_step_key"
    UNSAFE_EXPRESSION = "automation.unsafe_expression"
    UNKNOWN_OPERATION = "automation.unknown_operation"
    OPERATION_NOT_WORKFLOW_ALLOWED = "automation.operation_not_workflow_allowed"
    HUMAN_DECISION_REQUIRED = "automation.human_decision_required"
    HIGH_RISK_UNATTENDED = "automation.high_risk_unattended"
    PERMISSION_DENIED = "automation.permission_denied"
    STALE_ACCESS_SCOPE = "automation.stale_access_scope"


class AutomationStatus(StrEnum):
    DRAFT = "draft"
    ENABLED = "enabled"
    PAUSED = "paused"
    SUSPENDED_POLICY = "suspended_policy"
    QUARANTINED = "quarantined"
    ARCHIVED = "archived"


class AutomationRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED_POLICY = "skipped_policy"
    EXPIRED = "expired"


class PushDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    INTERACTED = "interacted"
    FAILED = "failed"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"


class TriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    DATA_EVENT = "data_event"
    PLATFORM_EVENT = "platform_event"


class ConcurrencyPolicy(StrEnum):
    FORBID = "forbid"
    QUEUE_ONE = "queue_one"
    ALLOW = "allow"


class MissedTriggerPolicy(StrEnum):
    SKIP = "skip"
    RUN_ONCE = "run_once"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueReference(StrictModel):
    ref: str = Field(pattern=r"^(trigger|steps)\.[A-Za-z0-9_.-]+$")


ScalarValue = str | int | float | bool | None
ComparableValue = ScalarValue | ValueReference


class ConditionPredicate(StrictModel):
    field: str = Field(pattern=r"^(trigger|steps)\.[A-Za-z0-9_.-]+$")
    op: Literal[
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "not_in",
        "contains",
        "exists",
    ]
    value: ComparableValue | list[ComparableValue] = None

    @model_validator(mode="after")
    def validate_operator_value(self) -> ConditionPredicate:
        if self.op == "exists" and self.value is not None:
            raise ValueError("exists condition cannot define a value")
        if self.op in {"in", "not_in"} and not isinstance(self.value, list):
            raise ValueError(f"{self.op} condition requires a list value")
        return self


class ConditionGroup(StrictModel):
    all: list[ConditionExpression] | None = None
    any: list[ConditionExpression] | None = None
    not_: ConditionExpression | None = Field(default=None, alias="not")

    @model_validator(mode="after")
    def exactly_one_branch(self) -> ConditionGroup:
        branches = [self.all is not None, self.any is not None, self.not_ is not None]
        if sum(branches) != 1:
            raise ValueError("condition group must define exactly one of all, any, not")
        if self.all is not None and not self.all:
            raise ValueError("all condition group cannot be empty")
        if self.any is not None and not self.any:
            raise ValueError("any condition group cannot be empty")
        return self


ConditionExpression = ConditionPredicate | ConditionGroup


class RecipientRule(StrictModel):
    type: Literal["user", "owner_field", "department_leader", "role_in_scope"]
    user_id: str | None = None
    source: str | None = None
    department_ref: str | None = None
    role: str | None = None
    scope: dict[str, ScalarValue | list[ScalarValue]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_recipient_source(self) -> RecipientRule:
        required = {
            "user": self.user_id,
            "owner_field": self.source,
            "department_leader": self.department_ref,
            "role_in_scope": self.role,
        }[self.type]
        if not required:
            raise ValueError(f"recipient type {self.type} is missing its identifier")
        return self


class StepBase(StrictModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str | None = Field(default=None, max_length=200)
    next: str | None = Field(default=None, max_length=80)


class ToolStep(StepBase):
    type: Literal["tool"]
    operation: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    input: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)


class ConditionStep(StepBase):
    type: Literal["condition"]
    expression: ConditionExpression
    if_true: str | None = Field(default=None, max_length=80)
    if_false: str | None = Field(default=None, max_length=80)


class TransformOperation(StrictModel):
    op: Literal[
        "select",
        "rename",
        "filter",
        "sort",
        "limit",
        "aggregate",
        "group_by",
        "template",
    ]
    source: str | None = None
    target: str | None = None
    fields: list[str] = Field(default_factory=list)
    template: str | None = Field(default=None, max_length=4000)
    field: str | None = None
    operator: (
        Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains", "exists"] | None
    ) = None
    value: ScalarValue | list[ScalarValue] = None
    descending: bool = False
    limit: int | None = Field(default=None, ge=1, le=1000)
    group_by: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_operation(self) -> TransformOperation:
        if self.op in {"filter", "sort"} and not self.field:
            raise ValueError(f"{self.op} transform requires field")
        if self.op == "filter" and not self.operator:
            raise ValueError("filter transform requires operator")
        if self.op == "limit" and self.limit is None:
            raise ValueError("limit transform requires limit")
        if self.op == "template" and self.template is None:
            raise ValueError("template transform requires template")
        if self.op == "group_by" and not self.group_by:
            raise ValueError("group_by transform requires group_by")
        return self


class TransformStep(StepBase):
    type: Literal["transform"]
    operations: list[TransformOperation] = Field(min_length=1, max_length=50)


class NotifyStep(StepBase):
    type: Literal["notify"]
    channel: Literal["feishu"] = "feishu"
    template: str = Field(min_length=1, max_length=120)
    recipients: list[RecipientRule] = Field(min_length=1, max_length=200)
    variables: dict[str, ScalarValue | ValueReference] = Field(default_factory=dict)
    aggregation_key: str | ValueReference | None = Field(default=None, max_length=200)
    aggregation_window_seconds: int = Field(default=900, ge=60, le=86_400)
    incident_key: str | ValueReference | None = Field(default=None, max_length=200)
    silence_until: str | None = Field(default=None, max_length=64)

    @field_validator("silence_until")
    @classmethod
    def validate_silence_until(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("silence_until must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            raise ValueError("silence_until must include a timezone")
        return value


class EventWaitStep(StepBase):
    type: Literal["event_wait"]
    event_type: str = Field(
        min_length=3,
        max_length=160,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[0-9]+$",
    )
    timeout_seconds: int | None = Field(default=None, ge=1, le=2_592_000)
    on_timeout: str | None = Field(default=None, max_length=80)


class ManualTaskStep(StepBase):
    type: Literal["manual_task"]
    title: str = Field(min_length=1, max_length=300)
    detail: str | None = Field(default=None, max_length=2000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=2_592_000)
    on_timeout: str | None = Field(default=None, max_length=80)


class WaitStep(StepBase):
    type: Literal["wait"]
    duration_seconds: int | None = Field(default=None, ge=1, le=2_592_000)
    until: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def exactly_one_wait_target(self) -> WaitStep:
        if (self.duration_seconds is None) == (self.until is None):
            raise ValueError(
                "wait step must define exactly one of duration_seconds or until"
            )
        return self


class AnalysisStep(StepBase):
    type: Literal["analysis"]
    instruction: str = Field(min_length=1, max_length=8000)
    inputs: dict[str, ValueReference] = Field(default_factory=dict, max_length=50)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    max_output_chars: int = Field(default=8000, ge=100, le=32_000)
    failure_policy: Literal["fail", "continue_empty"] = "fail"


class CollectField(StrictModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=120)
    type: Literal["text", "number", "date", "single_select", "multi_select", "boolean"]
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=100)


class CollectStep(StepBase):
    type: Literal["collect"]
    mode: Literal["card_form", "table_link"]
    template_id: str = Field(min_length=1, max_length=80)
    recipients: list[RecipientRule] = Field(min_length=1, max_length=200)
    fields: list[CollectField] = Field(default_factory=list, max_length=50)
    prefill: dict[str, ScalarValue | ValueReference] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=86_400, ge=60, le=2_592_000)
    on_timeout: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_collection_mode(self) -> CollectStep:
        if self.mode == "card_form" and not self.fields:
            raise ValueError("card_form collection requires fields")
        if self.mode == "table_link" and not any(
            field.required for field in self.fields
        ):
            raise ValueError(
                "table_link collection requires at least one required field"
            )
        return self


class EndStep(StepBase):
    type: Literal["end"]
    status: Literal["succeeded", "partially_succeeded", "skipped_policy"]
    message: str | None = Field(default=None, max_length=1000)


AutomationStep = Annotated[
    ToolStep
    | ConditionStep
    | TransformStep
    | NotifyStep
    | EventWaitStep
    | ManualTaskStep
    | WaitStep
    | AnalysisStep
    | CollectStep
    | EndStep,
    Field(discriminator="type"),
]


class AutomationDefinitionV1(StrictModel):
    schema_version: Literal["1.0", "1.1"] = "1.0"
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    timezone: str = Field(default="Asia/Shanghai", pattern=r"^[A-Za-z_]+/[A-Za-z_]+$")
    concurrency_policy: ConcurrencyPolicy = ConcurrencyPolicy.FORBID
    missed_trigger_policy: MissedTriggerPolicy = MissedTriggerPolicy.RUN_ONCE
    steps: list[AutomationStep] = Field(min_length=1, max_length=200)

    @field_validator("steps")
    @classmethod
    def validate_unique_step_keys(
        cls, value: list[AutomationStep]
    ) -> list[AutomationStep]:
        keys = [step.key for step in value]
        if len(keys) != len(set(keys)):
            raise ValueError(AutomationErrorCode.DUPLICATE_STEP_KEY.value)
        return value

    @model_validator(mode="after")
    def validate_step_references(self) -> AutomationDefinitionV1:
        step_keys = {step.key for step in self.steps}
        for step in self.steps:
            if isinstance(step, ConditionStep):
                for target in (step.if_true, step.if_false):
                    if target is not None and target not in step_keys:
                        raise ValueError(f"condition target does not exist: {target}")
            for target in (
                step.next,
                getattr(step, "on_timeout", None),
            ):
                if target is not None and target not in step_keys:
                    raise ValueError(f"step target does not exist: {target}")
        if self.schema_version == "1.1":
            self._validate_v11_graph()
        _reject_unsafe_values(self.model_dump(mode="json", by_alias=True))
        return self

    def _validate_v11_graph(self) -> None:
        by_key = {step.key: step for step in self.steps}
        for step in self.steps:
            if isinstance(step, EndStep):
                if step.next is not None:
                    raise ValueError("end step cannot define next")
                continue
            if isinstance(step, ConditionStep):
                if step.if_true is None or step.if_false is None:
                    raise ValueError("v1.1 condition requires if_true and if_false")
                continue
            if step.next is None:
                raise ValueError(f"v1.1 step {step.key} requires next")

        visiting: set[str] = set()
        visited: set[str] = set()

        def targets(step: AutomationStep) -> list[str]:
            result: list[str] = []
            if isinstance(step, ConditionStep):
                result.extend([step.if_true or "", step.if_false or ""])
            elif step.next:
                result.append(step.next)
            timeout_target = getattr(step, "on_timeout", None)
            if timeout_target:
                result.append(timeout_target)
            return [item for item in result if item]

        def visit(key: str) -> None:
            if key in visiting:
                raise ValueError(f"automation graph contains cycle at {key}")
            if key in visited:
                return
            visiting.add(key)
            for target in targets(by_key[key]):
                visit(target)
            visiting.remove(key)
            visited.add(key)

        visit(self.steps[0].key)
        unreachable = sorted(set(by_key) - visited)
        if unreachable:
            raise ValueError(
                f"automation graph contains unreachable steps: {', '.join(unreachable)}"
            )


class AutomationCompileIssue(StrictModel):
    code: AutomationErrorCode
    message: str
    step_key: str | None = None
    operation: str | None = None


class AutomationCompileReport(StrictModel):
    valid: bool
    definition: AutomationDefinitionV1
    required_operations: list[str]
    required_modules: list[str]
    issues: list[AutomationCompileIssue] = Field(default_factory=list)


def compile_automation_definition(
    definition: AutomationDefinitionV1 | dict[str, Any],
    *,
    capabilities: dict[str, dict[str, Any]],
    allowed_tool_names: set[str] | None = None,
) -> AutomationCompileReport:
    parsed = (
        definition
        if isinstance(definition, AutomationDefinitionV1)
        else AutomationDefinitionV1.model_validate(definition)
    )
    issues: list[AutomationCompileIssue] = []
    operations = [step.operation for step in parsed.steps if isinstance(step, ToolStep)]
    for step in parsed.steps:
        if not isinstance(step, ToolStep):
            continue
        capability = capabilities.get(step.operation)
        if capability is None:
            issues.append(
                AutomationCompileIssue(
                    code=AutomationErrorCode.UNKNOWN_OPERATION,
                    message="能力未注册",
                    step_key=step.key,
                    operation=step.operation,
                )
            )
            continue
        if capability.get("human_decision_required"):
            issues.append(
                AutomationCompileIssue(
                    code=AutomationErrorCode.HUMAN_DECISION_REQUIRED,
                    message="需要人工责任判断的能力不能进入无人值守流程",
                    step_key=step.key,
                    operation=step.operation,
                )
            )
        elif capability.get("risk_level") == "high":
            issues.append(
                AutomationCompileIssue(
                    code=AutomationErrorCode.HIGH_RISK_UNATTENDED,
                    message=f"高风险操作不能进入无人值守自动化: {step.operation}",
                    step_key=step.key,
                    operation=step.operation,
                )
            )
        elif not capability.get("workflow_allowed", False):
            issues.append(
                AutomationCompileIssue(
                    code=AutomationErrorCode.OPERATION_NOT_WORKFLOW_ALLOWED,
                    message="能力未开放工作流编排",
                    step_key=step.key,
                    operation=step.operation,
                )
            )
        if allowed_tool_names is not None and step.operation not in allowed_tool_names:
            issues.append(
                AutomationCompileIssue(
                    code=AutomationErrorCode.PERMISSION_DENIED,
                    message="当前 Livzon 有效范围不包含该能力",
                    step_key=step.key,
                    operation=step.operation,
                )
            )
    modules = sorted(
        {
            str(capabilities[operation].get("module"))
            for operation in operations
            if operation in capabilities and capabilities[operation].get("module")
        }
    )
    return AutomationCompileReport(
        valid=not issues,
        definition=parsed,
        required_operations=list(dict.fromkeys(operations)),
        required_modules=modules,
        issues=issues,
    )


_UNSAFE_KEY_PATTERN = re.compile(
    r"(^|_)(sql|script|shell|python|javascript|command|file_path|url)($|_)",
    re.IGNORECASE,
)
_UNSAFE_VALUE_PATTERN = re.compile(
    r"(?:https?://|file://|\b(?:select|insert|update|delete|drop)\s+.+\b(?:from|into|table)\b|"
    r"(?:python|javascript|bash|powershell|cmd)\s*:)",
    re.IGNORECASE,
)


def _reject_unsafe_values(value: Any, path: str = "definition") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _UNSAFE_KEY_PATTERN.search(str(key)):
                raise ValueError(
                    f"{AutomationErrorCode.UNSAFE_EXPRESSION.value}: {path}.{key}"
                )
            _reject_unsafe_values(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_unsafe_values(item, f"{path}[{index}]")
        return
    if isinstance(value, str) and _UNSAFE_VALUE_PATTERN.search(value):
        raise ValueError(f"{AutomationErrorCode.UNSAFE_EXPRESSION.value}: {path}")


ConditionGroup.model_rebuild()
