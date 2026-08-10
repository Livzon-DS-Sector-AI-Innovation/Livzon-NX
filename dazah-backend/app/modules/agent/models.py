import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class AgentSession(BaseModel):
    __tablename__ = "agent_sessions"
    __table_args__ = {"schema": "core", "comment": "Agent conversation sessions"}

    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="active", server_default="active"
    )
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )


class AgentMemoryTenantPolicy(BaseModel):
    __tablename__ = "agent_memory_tenant_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_core_agent_memory_tenant_policy"),
        CheckConstraint(
            "mode IN ('auto', 'explicit_only', 'disabled')",
            name="ck_core_agent_memory_tenant_policy_mode",
        ),
        {"schema": "core", "comment": "租户级 Agent 个人记忆上限策略"},
    )

    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="auto", server_default="auto"
    )
    policy_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )


class AgentMemoryUserPreference(BaseModel):
    __tablename__ = "agent_memory_user_preferences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", name="uq_core_agent_memory_user_preference"
        ),
        CheckConstraint(
            "mode IN ('auto', 'explicit_only', 'paused')",
            name="ck_core_agent_memory_user_preference_mode",
        ),
        CheckConstraint(
            "mode_before_pause IS NULL OR "
            "mode_before_pause IN ('auto', 'explicit_only')",
            name="ck_core_agent_memory_user_preference_prior_mode",
        ),
        {"schema": "core", "comment": "用户个人记忆模式与删除标记"},
    )

    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="auto", server_default="auto"
    )
    mode_before_pause: Mapped[str | None] = mapped_column(String(32), nullable=True)
    preference_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    notice_sent_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentMemoryClearConfirmation(BaseModel):
    __tablename__ = "agent_memory_clear_confirmations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", name="uq_core_agent_memory_clear_confirmation"
        ),
        {"schema": "core", "comment": "用户清空长期记忆的短期确认"},
    )

    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AgentMessage(BaseModel):
    __tablename__ = "agent_messages"
    __table_args__ = {"schema": "core", "comment": "Agent conversation messages"}

    session_id: Mapped[uuid.UUID] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )


class AgentAttachment(BaseModel):
    __tablename__ = "agent_attachments"
    __table_args__ = (
        Index(
            "ix_core_agent_attachments_session_active",
            "session_id",
            "is_deleted",
        ),
        {"schema": "core", "comment": "会话级持久附件及可恢复解析内容"},
    )

    session_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )


class AgentToolCall(BaseModel):
    __tablename__ = "agent_tool_calls"
    __table_args__ = {"schema": "core", "comment": "Agent tool execution audit"}

    session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="started", server_default="started"
    )
    request_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentToolCatalog(BaseModel):
    __tablename__ = "agent_tool_catalog"
    __table_args__ = (
        UniqueConstraint(
            "operation",
            name="uq_core_agent_tool_catalog_operation",
        ),
        Index("ix_core_agent_tool_catalog_module_status", "module", "status"),
        {"schema": "core", "comment": "Agent 工具目录运行时事实源"},
    )

    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    module: Mapped[str | None] = mapped_column(String(64), nullable=True)
    capability_version: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    admin_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    write: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    permission_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    output_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AgentConfirmation(BaseModel):
    __tablename__ = "agent_confirmations"
    __table_args__ = {
        "schema": "core",
        "comment": "Agent write operation confirmations",
    }

    session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    risk_level: Mapped[str] = mapped_column(
        String(32), default="medium", server_default="medium"
    )
    status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default="pending"
    )
    request_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentSkill(BaseModel):
    __tablename__ = "agent_skills"
    __table_args__ = (
        UniqueConstraint("name", name="uq_core_agent_skills_name"),
        {"schema": "core", "comment": "Agent progressive disclosure skills"},
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_keywords: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="active", server_default="active", index=True
    )
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class AgentWorkflow(BaseModel):
    __tablename__ = "agent_workflows"
    __table_args__ = {"schema": "core", "comment": "Agent user workflow definitions"}

    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="enabled", server_default="enabled", index=True
    )
    trigger_phrases: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    source_skill: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentWorkflowRun(BaseModel):
    __tablename__ = "agent_workflow_runs"
    __table_args__ = {"schema": "core", "comment": "Agent workflow run state"}

    workflow_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default="pending", index=True
    )
    current_step: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    steps_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    step_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentAutomation(BaseModel):
    __tablename__ = "agent_automations"
    __table_args__ = (
        Index("ix_core_agent_automations_owner_status", "owner_user_id", "status"),
        Index("ix_core_agent_automations_scope_status", "scope_type", "status"),
        {"schema": "core", "comment": "Livzon versioned automation definitions"},
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="mine", server_default="mine", index=True
    )
    scope_ref: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft", server_default="draft", index=True
    )
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True, index=True
    )
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class AgentAutomationVersion(BaseModel):
    __tablename__ = "agent_automation_versions"
    __table_args__ = (
        UniqueConstraint(
            "automation_id", "version", name="uq_core_agent_automation_versions_number"
        ),
        Index(
            "ix_core_agent_automation_versions_automation", "automation_id", "version"
        ),
        {"schema": "core", "comment": "Immutable Livzon automation snapshots"},
    )

    automation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="1.0", server_default="1.0"
    )
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    capability_versions: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    change_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class AgentAutomationTrigger(BaseModel):
    __tablename__ = "agent_automation_triggers"
    __table_args__ = (
        Index("ix_core_agent_automation_triggers_due", "status", "next_fire_at"),
        Index("ix_core_agent_automation_triggers_automation", "automation_id"),
        {"schema": "core", "comment": "Livzon automation trigger configuration"},
    )

    automation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="enabled", server_default="enabled"
    )
    schedule: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    event_type: Mapped[str | None] = mapped_column(
        String(160), nullable=True, index=True
    )
    event_filter: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Shanghai",
        server_default="Asia/Shanghai",
    )
    next_fire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class AgentAutomationRun(BaseModel):
    __tablename__ = "agent_automation_runs"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key", name="uq_core_agent_automation_runs_idempotency"
        ),
        Index(
            "ix_core_agent_automation_runs_automation_created",
            "automation_id",
            "created_at",
        ),
        Index("ix_core_agent_automation_runs_status_created", "status", "created_at"),
        Index("ix_core_agent_automation_runs_retry_due", "status", "retry_at"),
        {"schema": "core", "comment": "Livzon automation execution instances"},
    )

    automation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    trigger_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="queued",
        server_default="queued",
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    input_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    output_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    error_code: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    service_actor: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="agent_automation_scheduler",
        server_default="agent_automation_scheduler",
    )
    trigger_actor_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="system", server_default="system"
    )
    trigger_actor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class AgentStepRun(BaseModel):
    __tablename__ = "agent_step_runs"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "step_key", "attempt", name="uq_core_agent_step_runs_attempt"
        ),
        Index("ix_core_agent_step_runs_run", "run_id", "created_at"),
        {"schema": "core", "comment": "Livzon automation step execution records"},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    step_key: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    input_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    output_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class AgentRunEvent(BaseModel):
    __tablename__ = "agent_run_events"
    __table_args__ = (
        Index("ix_core_agent_run_events_run_occurred", "run_id", "occurred_at"),
        Index("ix_core_agent_run_events_type", "event_type", "occurred_at"),
        {"schema": "core", "comment": "Livzon automation run timeline events"},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="system", server_default="system"
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    payload_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class AgentDomainEvent(BaseModel):
    """Versioned minimal event envelope for cross-module automation triggers."""

    __tablename__ = "agent_domain_events"
    __table_args__ = (
        UniqueConstraint(
            "source_module",
            "idempotency_key",
            name="uq_core_agent_domain_events_source_idempotency",
        ),
        Index("ix_core_agent_domain_events_type_occurred", "event_type", "occurred_at"),
        Index(
            "ix_core_agent_domain_events_correlation", "correlation_id", "occurred_at"
        ),
        {"schema": "core", "comment": "Livzon versioned cross-module events"},
    )

    source_module: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    event_version: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    payload_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class AgentPushTemplateVersion(BaseModel):
    """Immutable rendered-message template version used by automation delivery."""

    __tablename__ = "agent_push_template_versions"
    __table_args__ = (
        UniqueConstraint(
            "template_key",
            "version",
            name="uq_core_agent_push_template_versions_key_version",
        ),
        Index(
            "ix_core_agent_push_template_versions_key_status",
            "template_key",
            "status",
        ),
        {"schema": "core", "comment": "Livzon push message template snapshots"},
    )

    template_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title_template: Mapped[str] = mapped_column(String(500), nullable=False)
    markdown_template: Mapped[str] = mapped_column(Text, nullable=False)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class AgentPushDelivery(BaseModel):
    """One durable, idempotent Feishu delivery for one resolved local user."""

    __tablename__ = "agent_push_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key", name="uq_core_agent_push_deliveries_idempotency"
        ),
        Index("ix_core_agent_push_deliveries_run_status", "run_id", "status"),
        Index("ix_core_agent_push_deliveries_retry_due", "status", "next_attempt_at"),
        Index(
            "ix_core_agent_push_deliveries_recipient_created",
            "recipient_user_id",
            "created_at",
        ),
        {"schema": "core", "comment": "Livzon Feishu per-recipient deliveries"},
    )

    automation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    step_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    template_version_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    channel: Mapped[str] = mapped_column(
        String(32), nullable=False, default="feishu", server_default="feishu"
    )
    recipient_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    recipient_ref: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    template_key: Mapped[str] = mapped_column(String(120), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )
    external_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    aggregation_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    incident_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    card_action_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class AgentAccessScopeSnapshot(BaseModel):
    __tablename__ = "agent_access_scope_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id", name="uq_core_agent_access_scope_snapshots_user_id"
        ),
        Index(
            "ix_core_agent_access_scope_sync_status",
            "sync_status",
            "source_grant_version",
        ),
        {"schema": "core", "comment": "Livzon 有效访问范围派生快照"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    source_grant_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    agent_scope_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    modules: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    tool_names: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    workflow_tool_names: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    registry_version: Mapped[str] = mapped_column(String(64), nullable=False)
    sync_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
