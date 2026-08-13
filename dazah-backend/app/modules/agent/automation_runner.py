from __future__ import annotations

import asyncio
import json
import random
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.correlation import normalize_correlation_id
from app.core.redaction import redact_sensitive
from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.automation_runtime import apply_transforms, evaluate_condition
from app.modules.agent.automation_schedule import next_fire_at
from app.modules.agent.automation_schema import (
    AnalysisStep,
    AutomationDefinitionV1,
    AutomationRunStatus,
    AutomationStatus,
    CollectStep,
    ConcurrencyPolicy,
    ConditionStep,
    EndStep,
    EventWaitStep,
    ManualTaskStep,
    NotifyStep,
    ToolStep,
    TransformStep,
    WaitStep,
)
from app.modules.agent.automation_service import AgentAutomationService
from app.modules.agent.interaction_schemas import InteractionRequestCreate
from app.modules.agent.interaction_service import AgentInteractionService
from app.modules.agent.models import (
    AgentAutomation,
    AgentAutomationGrant,
    AgentAutomationRun,
    AgentAutomationTrigger,
    AgentAutomationVersion,
    AgentDomainEvent,
    AgentInteractionRequest,
    AgentRunEvent,
    AgentStepRun,
)
from app.modules.agent.push_delivery_service import PushDeliveryService
from app.modules.agent.schemas import AgentToolExecuteRequest, AgentTrustedSubject
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import ToolExecutor, tool_registry
from app.platform.identity.models import User

ACTIVE_RUN_STATUSES = {
    AutomationRunStatus.QUEUED.value,
    AutomationRunStatus.RUNNING.value,
    AutomationRunStatus.WAITING.value,
}


@dataclass(frozen=True)
class AutomationWorkItem:
    kind: str
    automation_id: uuid.UUID
    trigger_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    scheduled_for: datetime | None = None


class AutomationNodeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AgentAutomationRunner:
    """Claims persisted trigger windows and safely executes immutable run snapshots."""

    claim_lease = timedelta(minutes=5)
    missed_grace = timedelta(minutes=1)
    max_retries = 3
    quarantine_after_failures = 5

    def __init__(self, *, batch_size: int = 50) -> None:
        self.batch_size = batch_size
        self.access_scope_service = AgentAccessScopeService()
        self.tool_executor = ToolExecutor(
            access_scope_service=self.access_scope_service
        )
        self.push_delivery_service = PushDeliveryService()

    async def claim_due_work(self, session: AsyncSession) -> list[AutomationWorkItem]:
        now = datetime.now(UTC)
        await self._recover_expired_trigger_claims(session, now=now)
        await self._initialize_unplanned_triggers(session, now=now)
        result = await session.execute(
            select(AgentAutomationTrigger)
            .join(
                AgentAutomation,
                AgentAutomation.id == AgentAutomationTrigger.automation_id,
            )
            .where(
                AgentAutomationTrigger.is_deleted.is_(False),
                AgentAutomationTrigger.trigger_type == "schedule",
                AgentAutomationTrigger.status == "enabled",
                AgentAutomationTrigger.next_fire_at.is_not(None),
                AgentAutomationTrigger.next_fire_at <= now,
                AgentAutomation.is_deleted.is_(False),
                AgentAutomation.status == AutomationStatus.ENABLED.value,
            )
            .order_by(AgentAutomationTrigger.next_fire_at.asc())
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        )
        claimed: list[AutomationWorkItem] = []
        for trigger in result.scalars():
            scheduled_for = trigger.next_fire_at
            if scheduled_for is None:
                continue
            trigger.claim_token = uuid.uuid4().hex
            trigger.claimed_at = now
            trigger.lease_expires_at = now + self.claim_lease
            trigger.last_fired_at = scheduled_for
            trigger.next_fire_at = next_fire_at(
                schedule=trigger.schedule,
                timezone=trigger.timezone,
                after=now if now > scheduled_for else scheduled_for,
            )
            if trigger.schedule.get("kind") == "once" and trigger.next_fire_at is None:
                trigger.status = "completed"
            trigger.updated_by = trigger.updated_by or trigger.created_by
            claimed.append(
                AutomationWorkItem(
                    kind="trigger",
                    automation_id=trigger.automation_id,
                    trigger_id=trigger.id,
                    scheduled_for=scheduled_for,
                )
            )

        retry_result = await session.execute(
            select(AgentAutomationRun)
            .join(
                AgentAutomation,
                AgentAutomation.id == AgentAutomationRun.automation_id,
            )
            .where(
                AgentAutomationRun.is_deleted.is_(False),
                AgentAutomationRun.status == AutomationRunStatus.QUEUED.value,
                AgentAutomationRun.retry_at.is_not(None),
                AgentAutomationRun.retry_at <= now,
                AgentAutomation.is_deleted.is_(False),
                AgentAutomation.status == AutomationStatus.ENABLED.value,
            )
            .order_by(AgentAutomationRun.retry_at.asc())
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        )
        claimed.extend(
            AutomationWorkItem(
                kind="run",
                automation_id=item.automation_id,
                run_id=item.id,
            )
            for item in retry_result.scalars()
        )
        resume_result = await session.execute(
            select(AgentAutomationRun)
            .join(
                AgentAutomation,
                AgentAutomation.id == AgentAutomationRun.automation_id,
            )
            .where(
                AgentAutomationRun.is_deleted.is_(False),
                AgentAutomationRun.status == AutomationRunStatus.WAITING.value,
                AgentAutomationRun.resume_at.is_not(None),
                AgentAutomationRun.resume_at <= now,
                AgentAutomation.is_deleted.is_(False),
                AgentAutomation.status == AutomationStatus.ENABLED.value,
            )
            .order_by(AgentAutomationRun.resume_at.asc())
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        )
        for run in resume_result.scalars():
            run.status = AutomationRunStatus.QUEUED.value
            run.retry_at = now
            claimed.append(
                AutomationWorkItem(
                    kind="run",
                    automation_id=run.automation_id,
                    run_id=run.id,
                )
            )
        await session.flush()
        return claimed

    async def execute_work(
        self, session: AsyncSession, item: AutomationWorkItem
    ) -> None:
        if item.kind == "run":
            run = await session.get(AgentAutomationRun, item.run_id)
            if run is not None:
                await self._execute_run(session, run)
            return
        await self._create_and_execute_run(session, item)

    async def execute_manual(
        self,
        session: AsyncSession,
        *,
        automation_id: uuid.UUID,
    ) -> AgentAutomationRun:
        """Execute an enabled automation immediately after tool confirmation."""
        run = await self._create_and_execute_run(
            session,
            AutomationWorkItem(kind="manual", automation_id=automation_id),
        )
        if run is None:
            raise HTTPException(404, "未找到可运行的自动化")
        return run

    async def _initialize_unplanned_triggers(
        self, session: AsyncSession, *, now: datetime
    ) -> None:
        result = await session.execute(
            select(AgentAutomationTrigger)
            .where(
                AgentAutomationTrigger.is_deleted.is_(False),
                AgentAutomationTrigger.trigger_type == "schedule",
                AgentAutomationTrigger.status == "enabled",
                AgentAutomationTrigger.next_fire_at.is_(None),
            )
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        )
        for trigger in result.scalars():
            trigger.next_fire_at = next_fire_at(
                schedule=trigger.schedule,
                timezone=trigger.timezone,
                after=now,
            )

    async def _recover_expired_trigger_claims(
        self, session: AsyncSession, *, now: datetime
    ) -> None:
        """Return abandoned committed claims to the due queue after a lease.

        A normal claim is cleared as soon as its immutable run record is
        created.  This recovery path covers process restarts between claiming
        a trigger window and materialising that run.
        """
        result = await session.execute(
            select(AgentAutomationTrigger)
            .join(
                AgentAutomation,
                AgentAutomation.id == AgentAutomationTrigger.automation_id,
            )
            .where(
                AgentAutomationTrigger.is_deleted.is_(False),
                AgentAutomationTrigger.trigger_type == "schedule",
                AgentAutomationTrigger.status == "enabled",
                AgentAutomationTrigger.claim_token.is_not(None),
                AgentAutomationTrigger.lease_expires_at.is_not(None),
                AgentAutomationTrigger.lease_expires_at <= now,
                AgentAutomationTrigger.last_fired_at.is_not(None),
                AgentAutomation.is_deleted.is_(False),
                AgentAutomation.status == AutomationStatus.ENABLED.value,
            )
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        )
        for trigger in result.scalars():
            trigger.next_fire_at = trigger.last_fired_at
            trigger.claim_token = None
            trigger.claimed_at = None
            trigger.lease_expires_at = None

    async def _create_and_execute_run(
        self, session: AsyncSession, item: AutomationWorkItem
    ) -> AgentAutomationRun | None:
        # Serialise all trigger windows for one automation.  Trigger rows are
        # individually claimed with SKIP LOCKED, while this lock closes the
        # race between two different triggers and their concurrency policy.
        automation = (
            await session.execute(
                select(AgentAutomation)
                .where(AgentAutomation.id == item.automation_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        trigger = (
            await session.get(AgentAutomationTrigger, item.trigger_id)
            if item.trigger_id is not None
            else None
        )
        if (
            automation is None
            or automation.active_version_id is None
            or (item.kind == "trigger" and trigger is None)
        ):
            return None
        if automation.status != AutomationStatus.ENABLED.value:
            raise HTTPException(400, "自动化未启用，不能立即运行")
        version = await session.get(
            AgentAutomationVersion, automation.active_version_id
        )
        if version is None:
            return None
        scheduled_for = item.scheduled_for or datetime.now(UTC)
        idempotency_key = (
            f"schedule:{automation.id}:{version.id}:{scheduled_for.isoformat()}"
            if trigger is not None
            else f"manual:{automation.id}:{version.id}:{uuid.uuid4()}"
        )
        existing = await session.execute(
            select(AgentAutomationRun).where(
                AgentAutomationRun.idempotency_key == idempotency_key,
                AgentAutomationRun.is_deleted.is_(False),
            )
        )
        if existing.scalar_one_or_none() is not None:
            return None
        run = AgentAutomationRun(
            automation_id=automation.id,
            owner_user_id=automation.owner_user_id,
            trigger_id=trigger.id if trigger is not None else None,
            version_id=version.id,
            status=AutomationRunStatus.QUEUED.value,
            idempotency_key=idempotency_key,
            correlation_id=normalize_correlation_id(),
            scheduled_for=scheduled_for,
            trigger_actor_type=(
                "system_schedule" if trigger is not None else "user_manual"
            ),
        )
        run.created_by = automation.owner_user_id
        run.updated_by = automation.owner_user_id
        session.add(run)
        await session.flush()
        if trigger is not None:
            trigger.claim_token = None
            trigger.claimed_at = None
            trigger.lease_expires_at = None

        definition = AutomationDefinitionV1.model_validate(version.definition)
        missed = datetime.now(UTC) - scheduled_for > self.missed_grace
        if missed and definition.missed_trigger_policy.value == "skip":
            await self._finish_run(
                session,
                automation=automation,
                run=run,
                status_value=AutomationRunStatus.SKIPPED_POLICY.value,
                error_code="automation.missed_trigger_skipped",
                error_message="错过触发窗口，已按 skip 策略跳过",
            )
            return run
        active = await self._active_runs(
            session, automation_id=automation.id, exclude_id=run.id
        )
        policy = definition.concurrency_policy
        if policy == ConcurrencyPolicy.FORBID and active:
            await self._finish_run(
                session,
                automation=automation,
                run=run,
                status_value=AutomationRunStatus.SKIPPED_POLICY.value,
                error_code="automation.concurrent_forbidden",
                error_message="已有运行未结束，已按 forbid 并发策略跳过",
            )
            return run
        if policy == ConcurrencyPolicy.QUEUE_ONE and active:
            if any(item.status == AutomationRunStatus.QUEUED.value for item in active):
                await self._finish_run(
                    session,
                    automation=automation,
                    run=run,
                    status_value=AutomationRunStatus.SKIPPED_POLICY.value,
                    error_code="automation.concurrent_queue_exists",
                    error_message="已有排队运行，已合并当前触发窗口",
                )
                return run
            run.retry_at = datetime.now(UTC)
            await self._event(session, run, "run_queued", {"reason": "queue_one"})
            return run
        await self._execute_run(session, run)
        return run

    async def _execute_run(
        self, session: AsyncSession, run: AgentAutomationRun
    ) -> None:
        automation = await session.get(AgentAutomation, run.automation_id)
        version = await session.get(AgentAutomationVersion, run.version_id)
        # A scheduler session can outlive an access-scope mutation in another
        # request.  Rehydrate the owner here so grant_version is never read
        # from the identity-map cache during the runtime policy gate.
        owner = (
            await session.execute(
                select(User)
                .where(User.id == run.owner_user_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if automation is None or version is None or owner is None:
            return
        grant_result = await session.execute(
            select(AgentAutomationGrant).where(
                AgentAutomationGrant.automation_id == automation.id,
                AgentAutomationGrant.version_id == version.id,
                AgentAutomationGrant.owner_user_id == owner.id,
                AgentAutomationGrant.status == "active",
                AgentAutomationGrant.is_deleted.is_(False),
            )
        )
        grant = grant_result.scalar_one_or_none()
        if grant is None:
            automation.status = AutomationStatus.SUSPENDED_POLICY.value
            await self._finish_run(
                session,
                automation=automation,
                run=run,
                status_value=AutomationRunStatus.SKIPPED_POLICY.value,
                error_code="automation.authorization_missing",
                error_message="自动化当前版本授权已失效",
            )
            return
        try:
            await self.access_scope_service.get_current_scope(session, user=owner)
        except HTTPException as exc:
            automation.status = AutomationStatus.SUSPENDED_POLICY.value
            automation.updated_by = owner.id
            await self._finish_run(
                session,
                automation=automation,
                run=run,
                status_value=AutomationRunStatus.SKIPPED_POLICY.value,
                error_code="automation.policy_revalidation_failed",
                error_message=str(exc.detail),
            )
            return

        definition = AutomationDefinitionV1.model_validate(version.definition)
        try:
            await AgentAutomationService(
                access_scope_service=self.access_scope_service
            )._compile_for_user(session, user=owner, definition=definition)
        except HTTPException as exc:
            automation.status = AutomationStatus.SUSPENDED_POLICY.value
            automation.updated_by = owner.id
            await self._finish_run(
                session,
                automation=automation,
                run=run,
                status_value=AutomationRunStatus.SKIPPED_POLICY.value,
                error_code="automation.policy_revalidation_failed",
                error_message=str(exc.detail),
            )
            return
        if run.status == AutomationRunStatus.QUEUED.value:
            active = await self._active_runs(
                session, automation_id=automation.id, exclude_id=run.id
            )
            if definition.concurrency_policy == ConcurrencyPolicy.FORBID and active:
                await self._finish_run(
                    session,
                    automation=automation,
                    run=run,
                    status_value=AutomationRunStatus.SKIPPED_POLICY.value,
                    error_code="automation.concurrent_forbidden",
                    error_message="已有运行未结束，已按 forbid 并发策略跳过",
                )
                return
            if definition.concurrency_policy == ConcurrencyPolicy.QUEUE_ONE and active:
                run.retry_at = datetime.now(UTC) + timedelta(seconds=5)
                return
        run.status = AutomationRunStatus.RUNNING.value
        run.retry_at = None
        run.resume_at = None
        run.started_at = run.started_at or datetime.now(UTC)
        run.updated_by = owner.id
        await self._event(session, run, "run_started", {"retry_count": run.retry_count})
        outputs = self._resumed_outputs(run)
        try:
            by_key = {step.key: step for step in definition.steps}
            order = [step.key for step in definition.steps]
            current_key = run.current_step_key or order[0]
            while current_key:
                step = by_key[current_key]
                run.current_step_key = step.key
                timed_out = False
                if isinstance(step, ToolStep):
                    completed = await self._execute_tool_step(
                        session,
                        run=run,
                        owner=owner,
                        grant=grant,
                        step=step,
                        outputs=outputs,
                    )
                    if not completed:
                        return
                elif isinstance(step, ConditionStep):
                    context = self._runtime_context(outputs)
                    matched = evaluate_condition(step.expression, context)
                    outputs[step.key] = {"matched": matched}
                    await self._step(
                        session,
                        run=run,
                        step_key=step.key,
                        operation=None,
                        status_value="succeeded",
                        output_summary=outputs[step.key],
                    )
                    current_key = step.if_true if matched else step.if_false
                    run.current_step_key = current_key
                    state = dict(run.execution_state or {})
                    branches = dict(state.get("branches") or {})
                    branches[step.key] = {
                        "matched": matched,
                        "selected": current_key,
                    }
                    run.execution_state = {
                        **state,
                        "branches": branches,
                        "next_step_key": current_key,
                    }
                    run.output_summary = redact_sensitive({"steps": outputs})
                    continue
                elif isinstance(step, TransformStep):
                    result = apply_transforms(
                        step.operations, self._runtime_context(outputs)
                    )
                    outputs[step.key] = result
                    await self._step(
                        session,
                        run=run,
                        step_key=step.key,
                        operation=None,
                        status_value="succeeded",
                        output_summary=(
                            result if isinstance(result, dict) else {"value": result}
                        ),
                    )
                elif isinstance(step, AnalysisStep):
                    outputs[step.key] = await self._execute_analysis_step(
                        run=run, step=step, outputs=outputs
                    )
                    await self._step(
                        session,
                        run=run,
                        step_key=step.key,
                        operation=None,
                        status_value="succeeded",
                        output_summary=outputs[step.key],
                    )
                elif isinstance(step, EndStep):
                    await self._finish_run(
                        session,
                        automation=automation,
                        run=run,
                        status_value=step.status,
                        error_code=None,
                        error_message=None,
                        output_summary={
                            "steps": outputs,
                            **({"message": step.message} if step.message else {}),
                        },
                    )
                    return
                elif isinstance(step, NotifyStep):
                    step_run = await self._step(
                        session,
                        run=run,
                        step_key=step.key,
                        operation=None,
                        status_value="running",
                    )
                    notification = await self.push_delivery_service.dispatch_notify(
                        session,
                        automation=automation,
                        run=run,
                        owner=owner,
                        step=step,
                        step_run_id=step_run.id,
                        outputs=outputs,
                    )
                    outputs[step.key] = notification
                    step_run.status = "succeeded"
                    step_run.output_summary = redact_sensitive(notification)
                    step_run.finished_at = datetime.now(UTC)
                    await self._event(
                        session, run, "notify_step_completed", {"step_key": step.key}
                    )
                elif isinstance(step, EventWaitStep):
                    received, timed_out = await self._wait_for_event(
                        session, run=run, step=step, outputs=outputs
                    )
                    if not received:
                        return
                elif isinstance(step, ManualTaskStep):
                    completed, timed_out = await self._wait_for_manual_task(
                        session, run=run, step=step, outputs=outputs
                    )
                    if not completed:
                        return
                elif isinstance(step, CollectStep):
                    completed, timed_out = await self._wait_for_collection(
                        session,
                        automation=automation,
                        run=run,
                        owner=owner,
                        step=step,
                        outputs=outputs,
                    )
                    if not completed:
                        return
                elif isinstance(step, WaitStep):
                    completed = await self._wait_for_delay(
                        session, run=run, step=step, outputs=outputs
                    )
                    if not completed:
                        return
                else:
                    raise RuntimeError(f"不支持的自动化节点: {step.type}")
                run.output_summary = redact_sensitive({"steps": outputs})
                current_key = self._next_step_key(
                    definition=definition,
                    order=order,
                    step=step,
                    timed_out=timed_out,
                )
                run.current_step_key = current_key
                run.execution_state = {
                    **dict(run.execution_state or {}),
                    "next_step_key": current_key,
                }
            await self._finish_run(
                session,
                automation=automation,
                run=run,
                status_value=AutomationRunStatus.SUCCEEDED.value,
                error_code=None,
                error_message=None,
                output_summary={"steps": outputs},
            )
        except Exception as exc:  # noqa: BLE001
            await self._retry_or_fail(
                session,
                automation=automation,
                run=run,
                error=exc,
            )

    async def _execute_tool_step(
        self,
        session: AsyncSession,
        *,
        run: AgentAutomationRun,
        owner: User,
        grant: AgentAutomationGrant,
        step: ToolStep,
        outputs: dict[str, Any],
    ) -> bool:
        ensure_agent_tools_registered()
        spec = tool_registry.require(step.operation)
        input_payload = _resolve_references(step.input, outputs)
        step_run = await self._step(
            session,
            run=run,
            step_key=step.key,
            operation=step.operation,
            status_value="running",
            input_summary=input_payload,
        )
        request = AgentToolExecuteRequest(
            operation=step.operation,
            params=input_payload,
            subject=AgentTrustedSubject(
                tenant_id=owner.tenant_key or "default",
                user_id=owner.id,
                display_name=owner.name,
                source="automation",
            ),
            trace_id=run.correlation_id,
            execution_context={
                "workflow_id": str(run.automation_id),
                "automation_version_id": str(run.version_id),
                "automation_grant_id": str(grant.id),
            },
            reason=f"自动化运行 {run.id} 步骤 {step.key}",
        )
        timeout = step.timeout_seconds or spec.timeout_seconds
        result = await asyncio.wait_for(
            self.tool_executor.execute(session, request=request), timeout=timeout
        )
        if result.requires_confirmation:
            step_run.status = "waiting_confirmation"
            step_run.output_summary = {"requires_confirmation": True}
            run.status = AutomationRunStatus.WAITING.value
            run.error_code = "automation.confirmation_required"
            await self._event(
                session, run, "run_waiting_confirmation", {"step_key": step.key}
            )
            return False
        if not result.ok:
            raise RuntimeError(f"工具调用失败: {step.operation}")
        outputs[step.key] = redact_sensitive(result.data)
        step_run.status = "succeeded"
        step_run.output_summary = (
            outputs[step.key]
            if isinstance(outputs[step.key], dict)
            else {"value": outputs[step.key]}
        )
        step_run.finished_at = datetime.now(UTC)
        await self._event(session, run, "step_succeeded", {"step_key": step.key})
        return True

    @staticmethod
    def _runtime_context(outputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "trigger": outputs.get("trigger", {}),
            "steps": {key: value for key, value in outputs.items() if key != "trigger"},
        }

    @staticmethod
    def _next_step_key(
        *,
        definition: AutomationDefinitionV1,
        order: list[str],
        step: Any,
        timed_out: bool = False,
    ) -> str | None:
        if timed_out and getattr(step, "on_timeout", None):
            return str(step.on_timeout)
        if definition.schema_version == "1.1":
            return step.next
        index = order.index(step.key)
        return order[index + 1] if index + 1 < len(order) else None

    async def _execute_analysis_step(
        self,
        *,
        run: AgentAutomationRun,
        step: AnalysisStep,
        outputs: dict[str, Any],
    ) -> dict[str, Any]:
        context = self._runtime_context(outputs)
        inputs = {
            key: _lookup_plain_reference(value.ref, context)
            for key, value in step.inputs.items()
        }
        settings = get_settings()
        base_url = settings.HERMES_INTERNAL_URL.rstrip("/")
        if not base_url:
            if step.failure_policy == "continue_empty":
                return {}
            raise AutomationNodeError(
                "automation.analysis_unavailable", "Hermes 自动化分析接口未配置"
            )
        try:
            async with httpx.AsyncClient(timeout=step.timeout_seconds) as client:
                response = await client.post(
                    f"{base_url}/internal/automation/analyze",
                    headers={
                        "Authorization": f"Bearer {settings.HERMES_INTERNAL_TOKEN}"
                    },
                    json={
                        "run_id": str(run.id),
                        "step_key": step.key,
                        "instruction": step.instruction,
                        "inputs": inputs,
                        "output_schema": step.output_schema,
                        "max_output_chars": step.max_output_chars,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            if step.failure_policy == "continue_empty":
                return {}
            raise AutomationNodeError(
                "automation.analysis_failed", "Hermes 自动化分析失败"
            ) from exc
        result = payload.get("output") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            if step.failure_policy == "continue_empty":
                return {}
            raise AutomationNodeError(
                "automation.analysis_invalid_output",
                "Hermes 自动化分析返回无效结构",
            )
        return result

    @staticmethod
    def _resumed_outputs(run: AgentAutomationRun) -> dict[str, Any]:
        persisted = (run.output_summary or {}).get("steps", {})
        outputs = dict(persisted) if isinstance(persisted, dict) else {}
        trigger = (run.input_summary or {}).get("trigger")
        if isinstance(trigger, dict):
            outputs["trigger"] = trigger
        return outputs

    async def _wait_for_event(
        self,
        session: AsyncSession,
        *,
        run: AgentAutomationRun,
        step: EventWaitStep,
        outputs: dict[str, Any],
    ) -> tuple[bool, bool]:
        result = await session.execute(
            select(AgentStepRun)
            .where(
                AgentStepRun.run_id == run.id,
                AgentStepRun.step_key == step.key,
                AgentStepRun.status == "waiting_event",
            )
            .order_by(AgentStepRun.attempt.desc())
            .limit(1)
        )
        step_run = result.scalar_one_or_none()
        waiting_since = step_run.started_at if step_run else datetime.now(UTC)
        event_result = await session.execute(
            select(AgentDomainEvent)
            .where(
                AgentDomainEvent.is_deleted.is_(False),
                AgentDomainEvent.event_type == step.event_type,
                AgentDomainEvent.correlation_id == run.correlation_id,
                AgentDomainEvent.occurred_at >= waiting_since,
            )
            .order_by(AgentDomainEvent.occurred_at.asc())
            .limit(1)
        )
        event = event_result.scalar_one_or_none()
        if event is None:
            if step.timeout_seconds is not None and datetime.now(
                UTC
            ) >= waiting_since + timedelta(seconds=step.timeout_seconds):
                if step_run is not None:
                    step_run.status = "timed_out"
                    step_run.finished_at = datetime.now(UTC)
                outputs[step.key] = {"status": "timed_out"}
                await self._event(
                    session, run, "event_wait_timed_out", {"step_key": step.key}
                )
                if step.on_timeout is None:
                    raise RuntimeError(f"等待事件超时: {step.event_type}")
                return True, True
            if step_run is None:
                await self._step(
                    session,
                    run=run,
                    step_key=step.key,
                    operation=None,
                    status_value="waiting_event",
                )
            run.status = AutomationRunStatus.WAITING.value
            run.resume_at = (
                waiting_since + timedelta(seconds=step.timeout_seconds)
                if step.timeout_seconds is not None
                else None
            )
            run.output_summary = redact_sensitive({"steps": outputs})
            await self._event(
                session,
                run,
                "run_waiting_event",
                {"step_key": step.key, "event_type": step.event_type},
            )
            return False, False
        outputs[step.key] = {
            "event_type": event.event_type,
            "event_version": event.event_version,
            "subject_type": event.subject_type,
            "subject_id": event.subject_id,
            "payload": event.payload_summary,
        }
        if step_run is None:
            step_run = await self._step(
                session,
                run=run,
                step_key=step.key,
                operation=None,
                status_value="succeeded",
                output_summary=outputs[step.key],
            )
        else:
            step_run.status = "succeeded"
            step_run.output_summary = redact_sensitive(outputs[step.key])
            step_run.finished_at = datetime.now(UTC)
        await self._event(
            session,
            run,
            "event_wait_completed",
            {"step_key": step.key, "event_type": event.event_type},
        )
        return True, False

    async def _wait_for_manual_task(
        self,
        session: AsyncSession,
        *,
        run: AgentAutomationRun,
        step: ManualTaskStep,
        outputs: dict[str, Any],
    ) -> tuple[bool, bool]:
        result = await session.execute(
            select(AgentStepRun)
            .where(AgentStepRun.run_id == run.id, AgentStepRun.step_key == step.key)
            .order_by(AgentStepRun.attempt.desc())
            .limit(1)
        )
        task = result.scalar_one_or_none()
        if task is not None and task.status == "succeeded":
            outputs[step.key] = dict(task.output_summary or {"status": "completed"})
            return True, False
        if (
            task is not None
            and step.timeout_seconds is not None
            and task.started_at is not None
            and datetime.now(UTC)
            >= task.started_at + timedelta(seconds=step.timeout_seconds)
        ):
            task.status = "timed_out"
            task.finished_at = datetime.now(UTC)
            outputs[step.key] = {"status": "timed_out"}
            if step.on_timeout is None:
                raise RuntimeError("人工待办超时")
            return True, True
        if task is None:
            await self._step(
                session,
                run=run,
                step_key=step.key,
                operation=None,
                status_value="waiting_manual",
                input_summary={"title": step.title, "detail": step.detail},
            )
        run.status = AutomationRunStatus.WAITING.value
        run.resume_at = (
            (task.started_at if task is not None else datetime.now(UTC))
            + timedelta(seconds=step.timeout_seconds)
            if step.timeout_seconds is not None
            else None
        )
        run.output_summary = redact_sensitive({"steps": outputs})
        await self._event(
            session,
            run,
            "manual_task_created",
            {"step_key": step.key, "title": step.title},
        )
        return False, False

    async def _wait_for_delay(
        self,
        session: AsyncSession,
        *,
        run: AgentAutomationRun,
        step: WaitStep,
        outputs: dict[str, Any],
    ) -> bool:
        result = await session.execute(
            select(AgentStepRun)
            .where(
                AgentStepRun.run_id == run.id,
                AgentStepRun.step_key == step.key,
                AgentStepRun.status == "waiting_delay",
            )
            .order_by(AgentStepRun.attempt.desc())
            .limit(1)
        )
        step_run = result.scalar_one_or_none()
        if step_run is None:
            now = datetime.now(UTC)
            resume_at = (
                now + timedelta(seconds=step.duration_seconds)
                if step.duration_seconds is not None
                else datetime.fromisoformat(str(step.until).replace("Z", "+00:00"))
            )
            if resume_at.tzinfo is None:
                raise ValueError("wait until 必须包含时区")
            await self._step(
                session,
                run=run,
                step_key=step.key,
                operation=None,
                status_value="waiting_delay",
                input_summary={"resume_at": resume_at.isoformat()},
            )
            run.status = AutomationRunStatus.WAITING.value
            run.resume_at = resume_at.astimezone(UTC)
            run.output_summary = redact_sensitive({"steps": outputs})
            await self._event(
                session,
                run,
                "run_waiting_delay",
                {"step_key": step.key, "resume_at": resume_at.isoformat()},
            )
            return False
        resume_at_value = step_run.input_summary.get("resume_at")
        resume_at = datetime.fromisoformat(str(resume_at_value).replace("Z", "+00:00"))
        if datetime.now(UTC) < resume_at:
            run.status = AutomationRunStatus.WAITING.value
            run.resume_at = resume_at
            return False
        step_run.status = "succeeded"
        step_run.output_summary = {"resumed_at": datetime.now(UTC).isoformat()}
        step_run.finished_at = datetime.now(UTC)
        outputs[step.key] = dict(step_run.output_summary)
        return True

    async def _wait_for_collection(
        self,
        session: AsyncSession,
        *,
        automation: AgentAutomation,
        run: AgentAutomationRun,
        owner: User,
        step: CollectStep,
        outputs: dict[str, Any],
    ) -> tuple[bool, bool]:
        result = await session.execute(
            select(AgentInteractionRequest).where(
                AgentInteractionRequest.run_id == run.id,
                AgentInteractionRequest.step_key == step.key,
                AgentInteractionRequest.is_deleted.is_(False),
            )
        )
        requests = list(result.scalars())
        if requests:
            if all(item.status == "completed" for item in requests):
                outputs[step.key] = {
                    "status": "completed",
                    "request_ids": [str(item.id) for item in requests],
                }
                waiting = await session.execute(
                    select(AgentStepRun)
                    .where(
                        AgentStepRun.run_id == run.id,
                        AgentStepRun.step_key == step.key,
                        AgentStepRun.status == "waiting_collection",
                    )
                    .order_by(AgentStepRun.attempt.desc())
                    .limit(1)
                )
                step_run = waiting.scalar_one_or_none()
                if step_run is not None:
                    step_run.status = "succeeded"
                    step_run.output_summary = outputs[step.key]
                    step_run.finished_at = datetime.now(UTC)
                return True, False
            expired = datetime.now(UTC) >= min(item.expires_at for item in requests)
            failed = any(item.status in {"failed", "expired"} for item in requests)
            if expired or failed:
                for item in requests:
                    if item.status == "pending":
                        item.status = "expired"
                outputs[step.key] = {"status": "timed_out" if expired else "failed"}
                if failed:
                    automation.status = AutomationStatus.SUSPENDED_POLICY.value
                if step.on_timeout is None:
                    raise RuntimeError("飞书填写请求超时或失败")
                return True, True
            run.status = AutomationRunStatus.WAITING.value
            run.resume_at = min(item.expires_at for item in requests)
            return False, False

        recipients = await self.push_delivery_service.resolve_recipients(
            session,
            rules=step.recipients,
            owner=owner,
            outputs=outputs,
        )
        if not recipients:
            raise RuntimeError("飞书填写请求没有有效收件人")
        step_run = await self._step(
            session,
            run=run,
            step_key=step.key,
            operation=None,
            status_value="waiting_collection",
        )
        expires_at = datetime.now(UTC) + timedelta(seconds=step.timeout_seconds)
        interaction_service = AgentInteractionService()
        created: list[AgentInteractionRequest] = []
        for recipient, rule in recipients:
            artifact = await interaction_service.create_request(
                session,
                user=owner,
                request=InteractionRequestCreate(
                    template_id=uuid.UUID(step.template_id),
                    recipient_user_id=recipient.id,
                    mode=step.mode,
                    title=step.name or automation.name,
                    summary=step.name or "请完成自动化所需信息填写。",
                    form_schema=[
                        field.model_dump(mode="json") for field in step.fields
                    ],
                    prefill=_resolve_references(step.prefill, outputs),
                    expires_at=expires_at,
                    idempotency_key=f"interaction:{run.id}:{step.key}:{recipient.id}",
                    automation_id=automation.id,
                    run_id=run.id,
                    step_key=step.key,
                ),
                trusted_automation=True,
            )
            item = await session.get(AgentInteractionRequest, artifact.request_id)
            if item is None:
                raise RuntimeError("填写请求创建失败")
            created.append(item)
            await self.push_delivery_service.dispatch_interaction(
                session,
                automation=automation,
                run=run,
                owner=owner,
                request=item,
                recipient=recipient,
                rule=rule,
                step_run_id=step_run.id,
            )
        run.status = AutomationRunStatus.WAITING.value
        run.resume_at = expires_at
        run.output_summary = redact_sensitive({"steps": outputs})
        await self._event(
            session,
            run,
            "collection_requests_created",
            {"step_key": step.key, "request_count": len(created)},
        )
        return False, False

    async def _retry_or_fail(
        self,
        session: AsyncSession,
        *,
        automation: AgentAutomation,
        run: AgentAutomationRun,
        error: Exception,
    ) -> None:
        last_step = await session.execute(
            select(AgentStepRun)
            .where(AgentStepRun.run_id == run.id, AgentStepRun.status == "running")
            .order_by(AgentStepRun.created_at.desc())
            .limit(1)
        )
        step = last_step.scalar_one_or_none()
        spec = tool_registry.get(step.operation) if step and step.operation else None
        if spec and spec.idempotent and run.retry_count < self.max_retries:
            run.retry_count += 1
            run.status = AutomationRunStatus.QUEUED.value
            run.retry_at = datetime.now(UTC) + timedelta(
                seconds=(2**run.retry_count) + random.uniform(0, 1)
            )
            run.error_code = "automation.retry_scheduled"
            run.error_message = str(error)[:2000]
            if step:
                step.status = "retrying"
                step.error_message = str(error)[:2000]
            await self._event(
                session,
                run,
                "run_retry_scheduled",
                {"retry_count": run.retry_count, "error": str(error)[:500]},
            )
            return
        await self._finish_run(
            session,
            automation=automation,
            run=run,
            status_value=AutomationRunStatus.FAILED.value,
            error_code=getattr(error, "code", "automation.execution_failed"),
            error_message=str(error),
        )

    async def _finish_run(
        self,
        session: AsyncSession,
        *,
        automation: AgentAutomation,
        run: AgentAutomationRun,
        status_value: str,
        error_code: str | None,
        error_message: str | None,
        output_summary: dict[str, Any] | None = None,
    ) -> None:
        run.status = status_value
        run.error_code = error_code
        run.error_message = error_message[:2000] if error_message else None
        run.output_summary = redact_sensitive(output_summary or {})
        run.finished_at = datetime.now(UTC)
        run.retry_at = None
        automation.last_run_id = run.id
        automation.last_run_status = status_value
        automation.last_run_at = run.finished_at
        if status_value in {
            AutomationRunStatus.SUCCEEDED.value,
            AutomationRunStatus.PARTIALLY_SUCCEEDED.value,
        }:
            automation.consecutive_failures = 0
        elif status_value == AutomationRunStatus.FAILED.value:
            automation.consecutive_failures += 1
            if automation.consecutive_failures >= self.quarantine_after_failures:
                automation.status = AutomationStatus.QUARANTINED.value
                automation.quarantined_at = run.finished_at
        await self._event(
            session,
            run,
            "run_finished",
            {"status": status_value, "error_code": error_code},
        )

    async def _active_runs(
        self,
        session: AsyncSession,
        *,
        automation_id: uuid.UUID,
        exclude_id: uuid.UUID,
    ) -> list[AgentAutomationRun]:
        result = await session.execute(
            select(AgentAutomationRun).where(
                AgentAutomationRun.automation_id == automation_id,
                AgentAutomationRun.id != exclude_id,
                AgentAutomationRun.is_deleted.is_(False),
                AgentAutomationRun.status.in_(ACTIVE_RUN_STATUSES),
            )
        )
        return list(result.scalars())

    async def _step(
        self,
        session: AsyncSession,
        *,
        run: AgentAutomationRun,
        step_key: str,
        operation: str | None,
        status_value: str,
        input_summary: dict[str, Any] | None = None,
        output_summary: dict[str, Any] | None = None,
    ) -> AgentStepRun:
        result = await session.execute(
            select(AgentStepRun)
            .where(AgentStepRun.run_id == run.id, AgentStepRun.step_key == step_key)
            .order_by(AgentStepRun.attempt.desc())
            .limit(1)
        )
        previous = result.scalar_one_or_none()
        attempt = (
            (previous.attempt + 1) if previous and previous.status == "retrying" else 1
        )
        item = AgentStepRun(
            run_id=run.id,
            step_key=step_key,
            operation=operation,
            attempt=attempt,
            status=status_value,
            input_summary=redact_sensitive(input_summary or {}),
            output_summary=redact_sensitive(output_summary or {}),
            started_at=datetime.now(UTC),
        )
        item.created_by = run.owner_user_id
        item.updated_by = run.owner_user_id
        session.add(item)
        await session.flush()
        return item

    async def _event(
        self,
        session: AsyncSession,
        run: AgentAutomationRun,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        item = AgentRunEvent(
            run_id=run.id,
            event_type=event_type,
            actor_type="service_actor",
            actor_id=run.owner_user_id,
            payload_summary=redact_sensitive(payload),
            occurred_at=datetime.now(UTC),
        )
        item.created_by = run.owner_user_id
        item.updated_by = run.owner_user_id
        session.add(item)


_STEP_REFERENCE_PATTERN = re.compile(r"\$\{steps\.[A-Za-z0-9_.-]+\}")


def _lookup_reference(value: str, outputs: dict[str, Any]) -> Any:
    parts = value[2:-1].split(".")
    if parts[0] == "trigger":
        cursor: Any = outputs.get("trigger", {})
        parts = parts[1:]
    else:
        cursor = outputs
        parts = parts[1:]
    for part in parts:
        if not isinstance(cursor, dict) or part not in cursor:
            raise ValueError(f"找不到模板变量: {value}")
        cursor = cursor[part]
    return cursor


def _message_reference_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "无数据"
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _resolve_references(value: Any, outputs: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_references(item, outputs) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_references(item, outputs) for item in value]
    if not isinstance(value, str):
        return value
    if _STEP_REFERENCE_PATTERN.fullmatch(value):
        return _lookup_reference(value, outputs)
    return _STEP_REFERENCE_PATTERN.sub(
        lambda match: _message_reference_text(
            _lookup_reference(match.group(0), outputs)
        ),
        value,
    )


def _lookup_plain_reference(value: str, context: dict[str, Any]) -> Any:
    cursor: Any = context
    for part in value.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            raise ValueError(f"找不到分析输入引用: {value}")
        cursor = cursor[part]
    return cursor
