from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redaction import redact_sensitive
from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.automation_schedule import (
    next_fire_at,
    normalize_schedule_config,
    preview_next_fires,
)
from app.modules.agent.automation_schema import (
    AutomationCompileReport,
    AutomationDefinitionV1,
    AutomationErrorCode,
    AutomationStatus,
    ToolStep,
    compile_automation_definition,
)
from app.modules.agent.models import (
    AgentAutomation,
    AgentAutomationGrant,
    AgentAutomationRun,
    AgentAutomationTrigger,
    AgentAutomationVersion,
    AgentFeishuResourceTemplate,
    AgentRunEvent,
    AgentStepRun,
    AgentWorkflow,
)
from app.modules.agent.repository import AgentRepository
from app.modules.agent.schemas import (
    AgentAutomationDraftCreate,
    AgentAutomationOut,
    AgentAutomationPage,
    AgentAutomationRunOut,
    AgentAutomationRunPage,
    AgentAutomationTriggerCreate,
    AgentAutomationTriggerOut,
    AgentAutomationUpdate,
    AgentAutomationVersionOut,
    AgentRunEventOut,
    AgentStepRunOut,
)
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.platform.identity.models import User


def _major_version(value: str) -> str:
    return str(value).split(".", maxsplit=1)[0].removeprefix("v")


class AgentAutomationService:
    """Versioned automation lifecycle with server-enforced view scopes."""

    def __init__(
        self,
        repo: AgentRepository | None = None,
        access_scope_service: AgentAccessScopeService | None = None,
    ) -> None:
        self.repo = repo or AgentRepository()
        self.access_scope_service = access_scope_service or AgentAccessScopeService()

    async def create_draft(
        self,
        db: AsyncSession,
        *,
        user: User,
        request: AgentAutomationDraftCreate,
    ) -> AgentAutomationOut:
        report, policy_snapshot, capability_versions = await self._compile_for_user(
            db, user=user, definition=request.definition
        )
        automation = await self.repo.create_automation(
            db,
            owner_user_id=user.id,
            source_session_id=request.source_session_id,
            name=report.definition.name,
            description=report.definition.description,
            scope_type=request.scope_type,
            scope_ref=self._normalize_scope_ref(request.scope_type, request.scope_ref),
        )
        version = await self.repo.create_automation_version(
            db,
            automation_id=automation.id,
            version=1,
            definition=report.definition.model_dump(mode="json", by_alias=True),
            policy_snapshot=policy_snapshot,
            capability_versions=capability_versions,
            created_by=user.id,
            change_summary=request.change_summary or "创建自动化草案",
        )
        automation.active_version_id = version.id
        await self.repo.replace_automation_triggers(
            db,
            automation=automation,
            triggers=self._trigger_payloads(request.triggers),
            actor_id=user.id,
        )
        await db.flush()
        return await self.get_automation_out(db, user=user, automation_id=automation.id)

    async def preview(
        self,
        db: AsyncSession,
        *,
        user: User,
        definition: AutomationDefinitionV1,
        triggers: list[AgentAutomationTriggerCreate] | None = None,
    ) -> dict[str, Any]:
        report, policy_snapshot, capability_versions = await self._compile_for_user(
            db, user=user, definition=definition
        )
        trigger_previews: list[dict[str, Any]] = []
        for trigger in triggers or []:
            if trigger.trigger_type != "schedule":
                continue
            normalized = normalize_schedule_config(
                trigger_type="schedule",
                schedule=trigger.schedule,
                timezone=trigger.timezone,
            )
            trigger_previews.append(
                {
                    "schedule": normalized,
                    "timezone": trigger.timezone,
                    "future_fire_at": preview_next_fires(
                        schedule=normalized,
                        timezone=trigger.timezone,
                        count=5,
                    ),
                }
            )
        template_ids = {
            uuid.UUID(step.template_id)
            for step in report.definition.steps
            if step.type == "collect"
        }
        template_checks: list[dict[str, Any]] = []
        for template_id in sorted(template_ids, key=str):
            template = await db.get(AgentFeishuResourceTemplate, template_id)
            template_checks.append(
                {
                    "template_id": str(template_id),
                    "valid": bool(
                        template
                        and not template.is_deleted
                        and template.status == "active"
                        and (
                            user.role == "admin"
                            or template.owner_user_id in {None, user.id}
                        )
                    ),
                    "status": template.status if template else "missing",
                }
            )
        return {
            "valid": report.valid,
            "required_operations": report.required_operations,
            "required_modules": report.required_modules,
            "issues": [item.model_dump(mode="json") for item in report.issues],
            "policy_snapshot": policy_snapshot,
            "capability_versions": capability_versions,
            "control_flow": [
                {
                    "step_key": step.key,
                    "type": step.type,
                    "next": getattr(step, "next", None),
                    "if_true": getattr(step, "if_true", None),
                    "if_false": getattr(step, "if_false", None),
                }
                for step in report.definition.steps
            ],
            "schedule_previews": trigger_previews,
            "feishu_template_checks": template_checks,
            "authorization_scope": {
                "operations": report.required_operations,
                "templates": [str(item) for item in template_ids],
                "schema_version": report.definition.schema_version,
            },
        }

    async def list_capability_impacts(
        self, db: AsyncSession, *, user: User
    ) -> list[dict[str, Any]]:
        """Locate immutable versions affected by removed or incompatible tools."""
        ensure_agent_tools_registered()
        statement = (
            select(AgentAutomationVersion, AgentAutomation)
            .join(
                AgentAutomation,
                AgentAutomation.id == AgentAutomationVersion.automation_id,
            )
            .where(
                AgentAutomationVersion.is_deleted.is_(False),
                AgentAutomation.is_deleted.is_(False),
            )
        )
        if user.role != "admin":
            statement = statement.where(AgentAutomation.owner_user_id == user.id)
        result = await db.execute(statement)
        impacts: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        for version, automation in result.tuples():
            for operation, recorded_version in version.capability_versions.items():
                current = tool_registry.get(operation)
                reason: str | None = None
                replacement: str | None = None
                if current is None:
                    reason = "operation_removed"
                elif current.deprecated_at and current.deprecated_at <= now:
                    reason = "operation_deprecated"
                    replacement = current.replacement_operation
                elif _major_version(current.capability_version) != _major_version(
                    recorded_version
                ):
                    reason = "major_version_changed"
                    replacement = current.replacement_operation
                if reason:
                    impacts.append(
                        {
                            "automation_id": str(automation.id),
                            "automation_name": automation.name,
                            "version": version.version,
                            "operation": operation,
                            "recorded_version": recorded_version,
                            "current_version": current.capability_version
                            if current
                            else None,
                            "reason": reason,
                            "replacement_operation": replacement,
                            "owner_user_id": str(automation.owner_user_id),
                        }
                    )
        return impacts

    async def update_automation(
        self,
        db: AsyncSession,
        *,
        user: User,
        automation_id: uuid.UUID,
        request: AgentAutomationUpdate,
    ) -> AgentAutomationOut:
        automation = await self._require_owner(
            db, user=user, automation_id=automation_id
        )
        if automation.status == AutomationStatus.ARCHIVED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "自动化已归档，不能修改")
        version = await self._active_version(db, automation)
        definition = request.definition or AutomationDefinitionV1.model_validate(
            version.definition
        )
        report, policy_snapshot, capability_versions = await self._compile_for_user(
            db, user=user, definition=definition
        )
        next_version = version.version + 1
        created = await self.repo.create_automation_version(
            db,
            automation_id=automation.id,
            version=next_version,
            definition=report.definition.model_dump(mode="json", by_alias=True),
            policy_snapshot=policy_snapshot,
            capability_versions=capability_versions,
            created_by=user.id,
            change_summary=request.change_summary or "更新自动化定义",
        )
        automation.name = report.definition.name
        automation.description = report.definition.description
        automation.active_version_id = created.id
        automation.status = AutomationStatus.DRAFT
        await self._revoke_grants(db, automation_id=automation.id, actor_id=user.id)
        if request.scope_type is not None:
            automation.scope_type = request.scope_type
            automation.scope_ref = self._normalize_scope_ref(
                request.scope_type, request.scope_ref or automation.scope_ref
            )
        if request.triggers is not None:
            await self.repo.replace_automation_triggers(
                db,
                automation=automation,
                triggers=self._trigger_payloads(request.triggers),
                actor_id=user.id,
            )
        automation.updated_by = user.id
        await db.flush()
        return await self.get_automation_out(db, user=user, automation_id=automation.id)

    async def confirm_automation(
        self, db: AsyncSession, *, user: User, automation_id: uuid.UUID
    ) -> AgentAutomationOut:
        automation = await self._require_owner(
            db, user=user, automation_id=automation_id
        )
        await self._revalidate_active_version(db, user=user, automation=automation)
        version = await self._active_version(db, automation)
        await self._revoke_grants(db, automation_id=automation.id, actor_id=user.id)
        definition = AutomationDefinitionV1.model_validate(version.definition)
        triggers = await self.repo.list_automation_triggers(
            db, automation_ids=[automation.id]
        )
        collect_steps = [step for step in definition.steps if step.type == "collect"]
        notify_steps = [step for step in definition.steps if step.type == "notify"]
        grant = AgentAutomationGrant(
            automation_id=automation.id,
            version_id=version.id,
            owner_user_id=user.id,
            status="active",
            authorization_scope={
                "operations": [
                    step.operation
                    for step in definition.steps
                    if hasattr(step, "operation")
                ],
                "schema_version": definition.schema_version,
                "schedules": [
                    {
                        "schedule": trigger.schedule,
                        "timezone": trigger.timezone,
                    }
                    for trigger in triggers
                    if trigger.trigger_type == "schedule"
                ],
                "feishu_templates": [step.template_id for step in collect_steps],
                "writable_fields": {
                    step.template_id: [field.key for field in step.fields]
                    for step in collect_steps
                },
                "recipients": [
                    [rule.model_dump(mode="json") for rule in step.recipients]
                    for step in notify_steps
                ]
                + [
                    [rule.model_dump(mode="json") for rule in step.recipients]
                    for step in collect_steps
                ],
            },
            authorized_at=datetime.now(UTC),
        )
        grant.created_by = user.id
        grant.updated_by = user.id
        db.add(grant)
        automation.status = AutomationStatus.ENABLED
        automation.updated_by = user.id
        await db.flush()
        return await self.get_automation_out(db, user=user, automation_id=automation.id)

    async def set_enabled(
        self,
        db: AsyncSession,
        *,
        user: User,
        automation_id: uuid.UUID,
        enabled: bool,
    ) -> AgentAutomationOut:
        automation = await self._require_owner(
            db, user=user, automation_id=automation_id
        )
        if enabled:
            await self._revalidate_active_version(db, user=user, automation=automation)
            grant = await self._active_grant(db, automation=automation)
            if grant is None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "自动化当前版本尚未确认，请重新确认后启用",
                )
            automation.status = AutomationStatus.ENABLED
        elif automation.status != AutomationStatus.ARCHIVED:
            automation.status = AutomationStatus.PAUSED
        automation.updated_by = user.id
        await db.flush()
        return await self.get_automation_out(db, user=user, automation_id=automation.id)

    async def archive(
        self, db: AsyncSession, *, user: User, automation_id: uuid.UUID
    ) -> AgentAutomationOut:
        automation = await self._require_owner(
            db, user=user, automation_id=automation_id
        )
        automation.status = AutomationStatus.ARCHIVED
        await self._revoke_grants(db, automation_id=automation.id, actor_id=user.id)
        automation.updated_by = user.id
        await db.flush()
        return await self.get_automation_out(db, user=user, automation_id=automation.id)

    async def simulate_schedule(
        self,
        db: AsyncSession,
        *,
        user: User,
        automation_id: uuid.UUID,
        count: int,
    ) -> dict[str, Any]:
        automation = await self._require_owner(
            db, user=user, automation_id=automation_id
        )
        version = await self._active_version(db, automation)
        definition = AutomationDefinitionV1.model_validate(version.definition)
        triggers = await self.repo.list_automation_triggers(
            db, automation_ids=[automation.id]
        )
        scheduled = [item for item in triggers if item.trigger_type == "schedule"]
        ensure_agent_tools_registered()
        return {
            "automation_id": str(automation.id),
            "version": version.version,
            "concurrency_policy": definition.concurrency_policy.value,
            "missed_trigger_policy": definition.missed_trigger_policy.value,
            "scheduled_triggers": [
                {
                    "trigger_id": str(item.id),
                    "timezone": item.timezone,
                    "cron": item.schedule.get("cron"),
                    "next_fire_at": item.next_fire_at,
                    "future_fire_at": preview_next_fires(
                        schedule=item.schedule,
                        timezone=item.timezone,
                        count=count,
                    ),
                }
                for item in scheduled
            ],
            "dry_run_plan": [
                {
                    "step_key": step.key,
                    "type": step.type,
                    "operation": (
                        step.operation if isinstance(step, ToolStep) else None
                    ),
                    "input_summary": redact_sensitive(getattr(step, "input", {}) or {}),
                    "suppressed": (
                        step.type in {"notify", "collect"}
                        or bool(
                            isinstance(step, ToolStep)
                            and tool_registry.get(step.operation)
                            and tool_registry.require(step.operation).write
                        )
                    ),
                    "simulation": "would_execute",
                }
                for step in definition.steps
            ],
        }

    async def list_automations(
        self,
        db: AsyncSession,
        *,
        user: User,
        scope: str,
        status_value: str | None,
        page: int,
        page_size: int,
    ) -> AgentAutomationPage:
        effective_scope = await self._effective_query_scope(db, user=user, scope=scope)
        owner_id = user.id if effective_scope == "mine" else None
        items, _ = await self.repo.list_automations(
            db,
            owner_user_id=owner_id,
            scope=effective_scope,
            status_value=status_value,
            page=1,
            page_size=500,
        )
        visible = [
            item for item in items if self._can_view(user, item, effective_scope)
        ]
        triggers = await self.repo.list_automation_triggers(
            db, automation_ids=[item.id for item in visible]
        )
        by_automation: dict[uuid.UUID, list[AgentAutomationTrigger]] = defaultdict(list)
        for trigger in triggers:
            by_automation[trigger.automation_id].append(trigger)
        result_items = [
            self._automation_out(
                item,
                triggers=by_automation[item.id],
                payload_redacted=self._should_redact(user, item),
            )
            for item in visible
        ]
        if effective_scope in {"mine", "platform"}:
            legacy_workflows = await self.repo.list_legacy_workflows(
                db,
                owner_user_id=user.id,
                platform=effective_scope == "platform",
            )
            result_items.extend(
                self._legacy_workflow_out(
                    item,
                    payload_redacted=item.user_id != user.id,
                )
                for item in legacy_workflows
                if status_value is None
                or self._legacy_status(item.status) == status_value
            )
        result_items.sort(
            key=lambda item: (
                item.updated_at or item.created_at or datetime.min.replace(tzinfo=UTC)
            ),
            reverse=True,
        )
        total = len(result_items)
        start = (page - 1) * page_size
        return AgentAutomationPage(
            items=result_items[start : start + page_size],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def get_automation_out(
        self,
        db: AsyncSession,
        *,
        user: User,
        automation_id: uuid.UUID,
    ) -> AgentAutomationOut:
        await self.access_scope_service.get_current_scope(db, user=user)
        automation = await self.repo.get_automation(db, automation_id)
        if automation is None:
            workflow = await self.repo.get_legacy_workflow_any(db, automation_id)
            if (
                workflow is None
                or workflow.user_id is None
                or (workflow.user_id != user.id and user.role != "admin")
            ):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "自动化不存在")
            return self._legacy_workflow_out(
                workflow,
                payload_redacted=workflow.user_id != user.id,
            )
        if not self._can_view(user, automation, "platform"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "自动化不存在")
        triggers = await self.repo.list_automation_triggers(
            db, automation_ids=[automation.id]
        )
        return self._automation_out(
            automation,
            triggers=triggers,
            payload_redacted=self._should_redact(user, automation),
        )

    async def list_versions(
        self, db: AsyncSession, *, user: User, automation_id: uuid.UUID
    ) -> list[AgentAutomationVersionOut]:
        automation = await self.repo.get_automation(db, automation_id)
        if automation is not None:
            if not self._can_view(user, automation, "platform"):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "自动化不存在")
            redact = self._should_redact(user, automation)
            return [
                self._version_out(item, payload_redacted=redact)
                for item in await self.repo.list_automation_versions(
                    db, automation_id=automation.id
                )
            ]
        await self.access_scope_service.get_current_scope(db, user=user)
        workflow = await self.repo.get_legacy_workflow_any(db, automation_id)
        if (
            workflow is None
            or workflow.user_id is None
            or (workflow.user_id != user.id and user.role != "admin")
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "自动化不存在")
        return [
            self._legacy_version_out(
                workflow,
                payload_redacted=workflow.user_id != user.id,
            )
        ]

    async def list_scheduled_triggers(
        self,
        db: AsyncSession,
        *,
        user: User,
        scope: str,
        page: int,
        page_size: int,
    ) -> AgentAutomationPage:
        page_result = await self.list_automations(
            db,
            user=user,
            scope=scope,
            status_value=None,
            page=page,
            page_size=page_size,
        )
        page_result.items = [
            item
            for item in page_result.items
            if any(trigger.trigger_type == "schedule" for trigger in item.triggers)
        ]
        page_result.total = len(page_result.items)
        return page_result

    async def list_runs(
        self,
        db: AsyncSession,
        *,
        user: User,
        scope: str,
        status_value: str | None,
        page: int,
        page_size: int,
    ) -> AgentAutomationRunPage:
        effective_scope = await self._effective_query_scope(db, user=user, scope=scope)
        automations, _ = await self.repo.list_automations(
            db,
            owner_user_id=user.id if effective_scope == "mine" else None,
            scope=effective_scope,
            status_value=None,
            page=1,
            page_size=500,
        )
        visible = [
            item for item in automations if self._can_view(user, item, effective_scope)
        ]
        items, total = await self.repo.list_automation_runs(
            db,
            automation_ids=[item.id for item in visible],
            status_value=status_value,
            page=page,
            page_size=page_size,
        )
        automation_by_id = {item.id: item for item in visible}
        return AgentAutomationRunPage(
            items=[
                self._run_out(
                    item,
                    payload_redacted=self._should_redact(
                        user, automation_by_id[item.automation_id]
                    ),
                )
                for item in items
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def get_run(
        self, db: AsyncSession, *, user: User, run_id: uuid.UUID
    ) -> dict[str, Any]:
        await self.access_scope_service.get_current_scope(db, user=user)
        run = await self.repo.get_automation_run(db, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "自动化运行不存在")
        automation = await self._visible_automation(
            db, user=user, automation_id=run.automation_id
        )
        redact = self._should_redact(user, automation)
        step_runs = await self.repo.list_step_runs(db, run_id=run.id)
        return {
            "run": self._run_out(run, payload_redacted=redact),
            "steps": [
                self._step_out(item, payload_redacted=redact) for item in step_runs
            ],
        }

    async def list_run_events(
        self, db: AsyncSession, *, user: User, run_id: uuid.UUID
    ) -> list[AgentRunEventOut]:
        await self.get_run(db, user=user, run_id=run_id)
        run = await self.repo.get_automation_run(db, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "自动化运行不存在")
        automation = await self._visible_automation(
            db, user=user, automation_id=run.automation_id
        )
        redact = self._should_redact(user, automation)
        return [
            self._event_out(item, payload_redacted=redact)
            for item in await self.repo.list_run_events(db, run_id=run.id)
        ]

    async def _compile_for_user(
        self,
        db: AsyncSession,
        *,
        user: User,
        definition: AutomationDefinitionV1,
    ) -> tuple[AutomationCompileReport, dict[str, Any], dict[str, str]]:
        scope = await self.access_scope_service.get_current_scope(db, user=user)
        if not scope.workflow_tool_names:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "当前 Livzon 范围未授予自动化能力"
            )
        ensure_agent_tools_registered()
        capabilities = {
            spec.name: {
                "module": spec.module,
                "workflow_allowed": spec.workflow_allowed,
                "human_decision_required": spec.human_decision_required,
                "risk_level": spec.risk_level,
                "capability_version": spec.capability_version,
            }
            for spec in tool_registry.list()
        }
        report = compile_automation_definition(
            definition,
            capabilities=capabilities,
            allowed_tool_names=set(scope.workflow_tool_names),
        )
        if not report.valid:
            permission_denied = any(
                issue.code
                in {
                    AutomationErrorCode.PERMISSION_DENIED,
                    AutomationErrorCode.STALE_ACCESS_SCOPE,
                }
                for issue in report.issues
            )
            raise HTTPException(
                (
                    status.HTTP_403_FORBIDDEN
                    if permission_denied
                    else status.HTTP_400_BAD_REQUEST
                ),
                {
                    "message": "自动化定义未通过当前权限与能力校验",
                    "issues": [item.model_dump(mode="json") for item in report.issues],
                },
            )
        policy_snapshot = {
            "source_grant_version": scope.source_grant_version,
            "agent_scope_version": scope.agent_scope_version,
            "registry_version": scope.registry_version,
            "workflow_tool_names": sorted(scope.workflow_tool_names),
        }
        capability_versions = {
            operation: str(capabilities[operation].get("capability_version") or "1")
            for operation in report.required_operations
        }
        return report, policy_snapshot, capability_versions

    async def _revalidate_active_version(
        self, db: AsyncSession, *, user: User, automation: AgentAutomation
    ) -> None:
        version = await self._active_version(db, automation)
        definition = AutomationDefinitionV1.model_validate(version.definition)
        try:
            await self._compile_for_user(db, user=user, definition=definition)
        except HTTPException:
            automation.status = AutomationStatus.SUSPENDED_POLICY
            automation.updated_by = user.id
            await db.flush()
            raise

    async def _active_version(
        self, db: AsyncSession, automation: AgentAutomation
    ) -> AgentAutomationVersion:
        if automation.active_version_id is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "自动化没有可用版本")
        version = await self.repo.get_automation_version(
            db, automation.active_version_id
        )
        if version is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "自动化当前版本不存在")
        return version

    @staticmethod
    async def _active_grant(
        db: AsyncSession, *, automation: AgentAutomation
    ) -> AgentAutomationGrant | None:
        if automation.active_version_id is None:
            return None
        result = await db.execute(
            select(AgentAutomationGrant).where(
                AgentAutomationGrant.automation_id == automation.id,
                AgentAutomationGrant.version_id == automation.active_version_id,
                AgentAutomationGrant.status == "active",
                AgentAutomationGrant.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _revoke_grants(
        db: AsyncSession, *, automation_id: uuid.UUID, actor_id: uuid.UUID
    ) -> None:
        result = await db.execute(
            select(AgentAutomationGrant).where(
                AgentAutomationGrant.automation_id == automation_id,
                AgentAutomationGrant.status == "active",
                AgentAutomationGrant.is_deleted.is_(False),
            )
        )
        for grant in result.scalars():
            grant.status = "revoked"
            grant.revoked_at = datetime.now(UTC)
            grant.updated_by = actor_id

    async def _require_owner(
        self, db: AsyncSession, *, user: User, automation_id: uuid.UUID
    ) -> AgentAutomation:
        await self.access_scope_service.get_current_scope(db, user=user)
        automation = await self.repo.get_automation(db, automation_id)
        if automation is None or automation.owner_user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "自动化不存在")
        return automation

    async def _visible_automation(
        self, db: AsyncSession, *, user: User, automation_id: uuid.UUID
    ) -> AgentAutomation:
        await self.access_scope_service.get_current_scope(db, user=user)
        automation = await self.repo.get_automation(db, automation_id)
        if automation is None or not self._can_view(user, automation, "platform"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "自动化不存在")
        return automation

    async def _effective_query_scope(
        self, db: AsyncSession, *, user: User, scope: str
    ) -> str:
        await self.access_scope_service.get_current_scope(db, user=user)
        normalized = scope if scope in {"mine", "shared", "platform"} else "mine"
        if normalized == "platform" and user.role != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "仅管理员可查询平台自动化")
        return normalized

    @staticmethod
    def _normalize_scope_ref(
        scope_type: str, scope_ref: dict[str, Any]
    ) -> dict[str, Any]:
        if scope_type == "mine":
            return {}
        values = scope_ref.get("user_ids") if isinstance(scope_ref, dict) else None
        if not isinstance(values, list):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "共享自动化必须指定 user_ids"
            )
        user_ids: list[str] = []
        for value in values:
            try:
                user_ids.append(str(uuid.UUID(str(value))))
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "共享用户标识无效"
                ) from exc
        return {"user_ids": sorted(set(user_ids))}

    @staticmethod
    def _trigger_payloads(triggers: list[Any]) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for item in triggers:
            raw = item.model_dump(mode="json")
            trigger_type = str(raw["trigger_type"])
            timezone = str(raw["timezone"])
            schedule = normalize_schedule_config(
                trigger_type=trigger_type,
                schedule=dict(raw.get("schedule") or {}),
                timezone=timezone,
            )
            raw["schedule"] = schedule
            raw["next_fire_at"] = (
                next_fire_at(
                    schedule=schedule,
                    timezone=timezone,
                    after=datetime.now(UTC),
                )
                if trigger_type == "schedule"
                else None
            )
            payloads.append(raw)
        return payloads

    @staticmethod
    def _can_view(
        user: User, automation: AgentAutomation, requested_scope: str
    ) -> bool:
        if automation.owner_user_id == user.id:
            return True
        if requested_scope == "platform" and user.role == "admin":
            return True
        if automation.scope_type != "shared":
            return False
        return str(user.id) in set(automation.scope_ref.get("user_ids") or [])

    @staticmethod
    def _should_redact(user: User, automation: AgentAutomation) -> bool:
        return automation.owner_user_id != user.id

    @staticmethod
    def _automation_out(
        automation: AgentAutomation,
        *,
        triggers: list[AgentAutomationTrigger],
        payload_redacted: bool,
    ) -> AgentAutomationOut:
        return AgentAutomationOut(
            id=automation.id,
            owner_user_id=automation.owner_user_id,
            source_session_id=automation.source_session_id,
            name=automation.name,
            description=automation.description,
            scope_type=automation.scope_type,
            scope_ref=automation.scope_ref,
            status=automation.status,
            active_version_id=automation.active_version_id,
            triggers=[AgentAutomationService._trigger_out(item) for item in triggers],
            last_run_id=automation.last_run_id,
            last_run_status=automation.last_run_status,
            last_run_at=automation.last_run_at,
            created_at=automation.created_at,
            updated_at=automation.updated_at,
            payload_redacted=payload_redacted,
        )

    @staticmethod
    def _legacy_status(status_value: str) -> str:
        return "paused" if status_value == "disabled" else "enabled"

    @staticmethod
    def _legacy_workflow_out(
        workflow: AgentWorkflow,
        *,
        payload_redacted: bool,
    ) -> AgentAutomationOut:
        return AgentAutomationOut(
            id=workflow.id,
            owner_user_id=workflow.user_id,
            source_session_id=workflow.session_id,
            name=workflow.name,
            description=workflow.description,
            scope_type="mine",
            status=AgentAutomationService._legacy_status(workflow.status),
            active_version_id=workflow.id,
            last_run_id=workflow.last_run_id,
            last_run_status=workflow.last_run_status,
            last_run_at=workflow.last_run_at,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
            payload_redacted=payload_redacted,
            legacy_source_workflow_id=workflow.id,
        )

    @staticmethod
    def _legacy_version_out(
        workflow: AgentWorkflow,
        *,
        payload_redacted: bool,
    ) -> AgentAutomationVersionOut:
        definition = {
            "schema_version": "legacy-agent-workflow-v1",
            "name": workflow.name,
            "description": workflow.description,
            "steps": redact_sensitive(workflow.steps),
        }
        return AgentAutomationVersionOut(
            id=workflow.id,
            automation_id=workflow.id,
            version=1,
            schema_version="legacy-agent-workflow-v1",
            definition={} if payload_redacted else definition,
            policy_snapshot={},
            capability_versions={},
            change_summary="由旧 AgentWorkflow 兼容适配",
            created_by=workflow.created_by,
            created_at=workflow.created_at,
        )

    @staticmethod
    def _version_out(
        item: AgentAutomationVersion, *, payload_redacted: bool
    ) -> AgentAutomationVersionOut:
        return AgentAutomationVersionOut(
            id=item.id,
            automation_id=item.automation_id,
            version=item.version,
            schema_version=item.schema_version,
            definition={} if payload_redacted else redact_sensitive(item.definition),
            policy_snapshot={}
            if payload_redacted
            else redact_sensitive(item.policy_snapshot),
            capability_versions=item.capability_versions,
            change_summary=item.change_summary,
            created_by=item.created_by,
            created_at=item.created_at,
        )

    @staticmethod
    def _trigger_out(item: AgentAutomationTrigger) -> AgentAutomationTriggerOut:
        return AgentAutomationTriggerOut(
            id=item.id,
            automation_id=item.automation_id,
            trigger_type=item.trigger_type,
            status=item.status,
            schedule=item.schedule,
            event_type=item.event_type,
            event_filter=item.event_filter,
            timezone=item.timezone,
            next_fire_at=item.next_fire_at,
            last_fired_at=item.last_fired_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _run_out(
        item: AgentAutomationRun, *, payload_redacted: bool
    ) -> AgentAutomationRunOut:
        return AgentAutomationRunOut(
            id=item.id,
            automation_id=item.automation_id,
            owner_user_id=item.owner_user_id,
            trigger_id=item.trigger_id,
            version_id=item.version_id,
            status=item.status,
            correlation_id=item.correlation_id,
            input_summary={}
            if payload_redacted
            else redact_sensitive(item.input_summary),
            output_summary={}
            if payload_redacted
            else redact_sensitive(item.output_summary),
            error_code=item.error_code,
            error_message="已脱敏"
            if payload_redacted and item.error_message
            else item.error_message,
            started_at=item.started_at,
            finished_at=item.finished_at,
            created_at=item.created_at,
            payload_redacted=payload_redacted,
        )

    @staticmethod
    def _step_out(item: AgentStepRun, *, payload_redacted: bool) -> AgentStepRunOut:
        return AgentStepRunOut(
            id=item.id,
            run_id=item.run_id,
            step_key=item.step_key,
            operation=item.operation,
            attempt=item.attempt,
            status=item.status,
            input_summary={}
            if payload_redacted
            else redact_sensitive(item.input_summary),
            output_summary={}
            if payload_redacted
            else redact_sensitive(item.output_summary),
            error_code=item.error_code,
            error_message="已脱敏"
            if payload_redacted and item.error_message
            else item.error_message,
            started_at=item.started_at,
            finished_at=item.finished_at,
            payload_redacted=payload_redacted,
        )

    @staticmethod
    def _event_out(item: AgentRunEvent, *, payload_redacted: bool) -> AgentRunEventOut:
        return AgentRunEventOut(
            id=item.id,
            run_id=item.run_id,
            event_type=item.event_type,
            actor_type=item.actor_type,
            actor_id=item.actor_id,
            payload_summary={}
            if payload_redacted
            else redact_sensitive(item.payload_summary),
            occurred_at=item.occurred_at,
            payload_redacted=payload_redacted,
        )
