import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .automation_schema import (
    AutomationDefinitionV1,
    AutomationRunStatus,
    TriggerType,
)

AgentRole = Literal["system", "user", "assistant", "tool"]
AgentBackendEventType = Literal[
    "accepted",
    "thinking",
    "capability_search",
    "tool_call",
    "tool_result",
    "text_delta",
    "confirmation",
    "delivery",
    "error",
    "finished",
    "ping",
]
AGENT_BACKEND_PROTOCOL_VERSION: Literal["2.0"] = "2.0"


class AgentTrustedSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: uuid.UUID
    display_name: str | None = Field(default=None, max_length=200)
    source: Literal["web", "feishu", "automation", "internal"]
    external_binding_id: uuid.UUID | None = None


class AgentBackendSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Literal["web", "feishu"]
    sender_user_id: str | None = Field(default=None, max_length=128)
    sender_open_id: str | None = Field(default=None, max_length=128)
    sender_union_id: str | None = Field(default=None, max_length=128)
    chat_id: str | None = Field(default=None, max_length=255)
    chat_type: str | None = Field(default=None, max_length=32)
    thread_id: str | None = Field(default=None, max_length=255)
    reply_to: str | None = Field(default=None, max_length=255)
    message_id: str | None = Field(default=None, max_length=255)


class AgentBackendAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attachment_id: uuid.UUID | None = None
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size: int = Field(gt=0, le=10 * 1024 * 1024)
    kind: Literal["image", "document"]
    data_base64: str | None = Field(default=None, max_length=14 * 1024 * 1024)
    text: str | None = Field(default=None, max_length=50_000)
    truncated: bool = False


class AgentBackendV2Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal["2.0"] = AGENT_BACKEND_PROTOCOL_VERSION
    run_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    trace_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    session_id: str = Field(min_length=1, max_length=512)
    subject: AgentTrustedSubject
    source: AgentBackendSource
    message: str = Field(min_length=1, max_length=8000)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[AgentBackendAttachment] = Field(
        default_factory=list, max_length=5
    )
    attachment_catalog: list[dict[str, Any]] = Field(
        default_factory=list, max_length=100
    )
    client_capabilities: list[str] = Field(default_factory=list)


class AgentBackendV2Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal["2.0"] = AGENT_BACKEND_PROTOCOL_VERSION
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    trace_id: uuid.UUID
    run_id: uuid.UUID
    sequence: int = Field(ge=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    type: AgentBackendEventType
    data: dict[str, Any] = Field(default_factory=dict)


class AgentAttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size: int = Field(gt=0, le=10 * 1024 * 1024)
    data_base64: str = Field(min_length=1, max_length=14 * 1024 * 1024)


class AgentChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=8000)
    context: dict[str, Any] = Field(default_factory=dict)
    attachments: list[AgentAttachmentIn] = Field(default_factory=list, max_length=5)


class FeishuConversationAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    kind: Literal["image", "audio", "video", "document"]
    size: int | None = Field(default=None, gt=0, le=10 * 1024 * 1024)
    data_base64: str | None = Field(
        default=None, min_length=1, max_length=14 * 1024 * 1024
    )


class FeishuConversationPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: AgentTrustedSubject
    peer_id: str = Field(min_length=1, max_length=512)
    external_message_id: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=8000)
    trace_id: uuid.UUID
    run_id: uuid.UUID
    source: AgentBackendSource
    attachments: list[FeishuConversationAttachment] = Field(
        default_factory=list, max_length=5
    )


class FeishuConversationPrepareResponse(BaseModel):
    session_id: uuid.UUID
    messages: list[dict[str, str]] = Field(default_factory=list)
    attachment_catalog: list[dict[str, Any]] = Field(default_factory=list)
    duplicate: bool = False
    response_text: str | None = None


class FeishuConversationCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: AgentTrustedSubject
    external_message_id: str = Field(min_length=1, max_length=255)
    trace_id: uuid.UUID
    run_id: uuid.UUID
    assistant_message: str = Field(min_length=1, max_length=100_000)
    tool_trace: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


class FeishuConversationCompleteResponse(BaseModel):
    session_id: uuid.UUID
    message_id: uuid.UUID
    duplicate: bool = False


class AgentMessageOut(BaseModel):
    id: uuid.UUID | None = None
    role: AgentRole
    content: str
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentAuditSessionItem(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    username: str | None = None
    department: str | None = None
    title: str | None = None
    status: str
    channel: str | None = None
    message_count: int = 0
    tool_call_count: int = 0
    failed_operation_count: int = 0
    created_at: datetime
    updated_at: datetime


class AgentAuditSessionPage(BaseModel):
    items: list[AgentAuditSessionItem] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class AgentAuditMessageItem(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AgentAuditOperationItem(BaseModel):
    id: uuid.UUID
    operation: str
    status: str
    request_payload: dict[str, Any] = Field(default_factory=dict)
    response_payload: dict[str, Any] | None = None
    error_message: str | None = None
    correlation_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AgentAuditConfirmationItem(BaseModel):
    id: uuid.UUID
    operation: str
    summary: str
    risk_level: str
    status: str
    request_payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] | None = None
    expires_at: datetime
    executed_at: datetime | None = None
    created_at: datetime


class AgentAuditSessionDetail(BaseModel):
    session: AgentAuditSessionItem
    context: dict[str, Any] = Field(default_factory=dict)
    messages: list[AgentAuditMessageItem] = Field(default_factory=list)
    operations: list[AgentAuditOperationItem] = Field(default_factory=list)
    confirmations: list[AgentAuditConfirmationItem] = Field(default_factory=list)


class AgentConfirmationOut(BaseModel):
    id: uuid.UUID
    operation: str
    summary: str
    risk_level: str
    status: str
    expires_at: datetime
    request_payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] | None = None
    executed_at: datetime | None = None
    updated_at: datetime | None = None


class AgentSessionItem(BaseModel):
    id: uuid.UUID
    title: str | None = None
    status: str
    channel: str = "web"
    message_count: int = 0
    last_message_preview: str | None = None
    pending_confirmation_count: int = 0
    created_at: datetime
    updated_at: datetime


class AgentSessionPage(BaseModel):
    items: list[AgentSessionItem] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class AgentSessionDetail(BaseModel):
    session: AgentSessionItem
    messages: list[AgentMessageOut] = Field(default_factory=list)
    confirmations: list[AgentConfirmationOut] = Field(default_factory=list)


class AgentAutomationAuditItem(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    version: int
    actor_id: uuid.UUID | None = None
    change_summary: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class AgentChatResponse(BaseModel):
    session_id: uuid.UUID
    message: AgentMessageOut
    pending_confirmations: list[AgentConfirmationOut] = Field(default_factory=list)
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


class AgentToolExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(min_length=1, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] | None = None
    subject: AgentTrustedSubject
    session_id: uuid.UUID | None = None
    trace_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    execution_context: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=500)


class AgentToolControlRequest(BaseModel):
    """Authenticated web control-plane request without caller-owned identity."""

    model_config = ConfigDict(extra="forbid")

    operation: str = Field(min_length=1, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] | None = None
    reason: str | None = Field(default=None, max_length=500)
    session_id: uuid.UUID | None = None
    trace_id: uuid.UUID = Field(default_factory=uuid.uuid4)


class AgentToolSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=500)
    module: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=12, ge=1, le=50)
    subject: AgentTrustedSubject
    trace_id: uuid.UUID = Field(default_factory=uuid.uuid4)


class AgentToolCatalogEntry(BaseModel):
    operation: str
    module: str | None = None
    version: str
    summary: str
    status: Literal["active", "disabled"]
    risk_level: Literal["low", "medium", "high"]
    write: bool
    confirmation_required: bool
    permission_key: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int
    idempotent: bool


class AgentToolCatalogPage(BaseModel):
    items: list[AgentToolCatalogEntry] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class AgentToolEnabledUpdate(BaseModel):
    enabled: bool


class PolicyDecisionV1(BaseModel):
    decision: Literal["allow", "deny", "confirm"]
    reason_code: str
    resource_domain: Literal["dazah_business", "feishu_native"]
    risk_level: Literal["low", "medium", "high"]
    confirmation_required: bool = False
    audit_tags: list[str] = Field(default_factory=list)


class AgentToolExecuteResponse(BaseModel):
    ok: bool
    operation: str
    data: Any = None
    meta: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation: AgentConfirmationOut | None = None


class AgentConfirmationExecuteResponse(BaseModel):
    confirmation: AgentConfirmationOut
    result: AgentToolExecuteResponse


class AgentConfirmationResolveRequest(BaseModel):
    subject: AgentTrustedSubject
    choice: Literal["allow", "reject"]


class AgentModuleScopeOut(BaseModel):
    module_code: str
    module_name: str
    permissions: list[str] = Field(default_factory=list)
    data_scope: dict[str, Any] = Field(default_factory=dict)


class AgentAccessScopeOut(BaseModel):
    user_id: uuid.UUID
    source_grant_version: int
    agent_scope_version: int
    registry_version: str
    sync_status: str
    synced_at: datetime | None = None
    last_error: str | None = None
    modules: list[AgentModuleScopeOut] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    workflow_tool_names: list[str] = Field(default_factory=list)


class AgentSkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    trigger_keywords: list[str] = Field(default_factory=list)
    content: str = Field(min_length=1)
    status: Literal["active", "disabled"] = "active"
    is_builtin: bool = False


class AgentSkillUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    trigger_keywords: list[str] | None = None
    content: str | None = Field(default=None, min_length=1)
    status: Literal["active", "disabled"] | None = None


class AgentSkillOut(BaseModel):
    id: uuid.UUID
    name: str
    title: str
    description: str
    trigger_keywords: list[str] = Field(default_factory=list)
    content: str
    status: str
    is_builtin: bool
    version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentSkillResolveRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    enabled_toolsets: list[str] = Field(default_factory=list)
    business_scope: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    limit: int = Field(default=3, ge=1, le=10)


class AgentSkillResolvedOut(BaseModel):
    name: str
    title: str
    description: str
    trigger_keywords: list[str] = Field(default_factory=list)
    content: str
    score: int


class AgentSkillResolveResponse(BaseModel):
    skills: list[AgentSkillResolvedOut] = Field(default_factory=list)


class AgentWorkflowStep(BaseModel):
    order: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    operation: str = Field(min_length=1, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] | None = None
    description: str | None = Field(default=None, max_length=1000)


class AgentWorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    trigger_phrases: list[str] = Field(default_factory=list)
    steps: list[AgentWorkflowStep] = Field(min_length=1)
    source_skill: str | None = Field(default=None, max_length=120)
    source_request: str | None = Field(default=None, max_length=8000)


class AgentWorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    trigger_phrases: list[str] | None = None
    steps: list[AgentWorkflowStep] | None = Field(default=None, min_length=1)


class AgentWorkflowOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    status: str
    trigger_phrases: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    source_skill: str | None = None
    source_request: str | None = None
    last_run_id: uuid.UUID | None = None
    last_run_status: str | None = None
    last_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentWorkflowRunOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    user_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    status: str
    current_step: int
    steps_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    step_results: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


AutomationScope = Literal["mine", "shared", "platform"]


class AgentAutomationTriggerCreate(BaseModel):
    trigger_type: TriggerType
    schedule: dict[str, Any] = Field(default_factory=dict)
    event_type: str | None = Field(default=None, max_length=160)
    event_filter: dict[str, Any] = Field(default_factory=dict)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)


class AgentAutomationDraftCreate(BaseModel):
    definition: AutomationDefinitionV1
    scope_type: Literal["mine", "shared"] = "mine"
    scope_ref: dict[str, Any] = Field(default_factory=dict)
    source_session_id: uuid.UUID | None = None
    triggers: list[AgentAutomationTriggerCreate] = Field(
        default_factory=list, max_length=20
    )
    change_summary: str | None = Field(default=None, max_length=1000)


class AgentAutomationUpdate(BaseModel):
    definition: AutomationDefinitionV1 | None = None
    scope_type: Literal["mine", "shared"] | None = None
    scope_ref: dict[str, Any] | None = None
    triggers: list[AgentAutomationTriggerCreate] | None = Field(
        default=None, max_length=20
    )
    change_summary: str | None = Field(default=None, max_length=1000)


class AgentAutomationStatusUpdate(BaseModel):
    enabled: bool


class AgentAutomationSimulationRequest(BaseModel):
    automation_id: uuid.UUID
    count: int = Field(default=5, ge=1, le=20)


class AgentAutomationVersionOut(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    version: int
    schema_version: str
    definition: dict[str, Any] = Field(default_factory=dict)
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    capability_versions: dict[str, str] = Field(default_factory=dict)
    change_summary: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None


class AgentAutomationTriggerOut(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    trigger_type: str
    status: str
    schedule: dict[str, Any] = Field(default_factory=dict)
    event_type: str | None = None
    event_filter: dict[str, Any] = Field(default_factory=dict)
    timezone: str
    next_fire_at: datetime | None = None
    last_fired_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentAutomationOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    source_session_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    scope_type: str
    scope_ref: dict[str, Any] = Field(default_factory=dict)
    status: str
    active_version_id: uuid.UUID | None = None
    active_version: int | None = None
    triggers: list[AgentAutomationTriggerOut] = Field(default_factory=list)
    last_run_id: uuid.UUID | None = None
    last_run_status: str | None = None
    last_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    payload_redacted: bool = False
    legacy_source_workflow_id: uuid.UUID | None = None


class AgentAutomationRunOut(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    owner_user_id: uuid.UUID
    trigger_id: uuid.UUID | None = None
    version_id: uuid.UUID
    status: AutomationRunStatus | str
    correlation_id: uuid.UUID
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    payload_redacted: bool = False


class AgentStepRunOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    step_key: str
    operation: str | None = None
    attempt: int
    status: str
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    payload_redacted: bool = False


class AgentRunEventOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    event_type: str
    actor_type: str
    actor_id: uuid.UUID | None = None
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    payload_redacted: bool = False


class AgentAutomationPage(BaseModel):
    items: list[AgentAutomationOut] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class AgentAutomationRunPage(BaseModel):
    items: list[AgentAutomationRunOut] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
