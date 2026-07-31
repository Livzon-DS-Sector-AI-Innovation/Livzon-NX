from __future__ import annotations

import asyncio
import json
import random
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import normalize_correlation_id
from app.core.redaction import redact_sensitive
from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.automation_schedule import next_fire_at
from app.modules.agent.automation_schema import (
    AutomationDefinitionV1,
    AutomationRunStatus,
    AutomationStatus,
    ConcurrencyPolicy,
    EndStep,
    EventWaitStep,
    ManualTaskStep,
    NotifyStep,
    ToolStep,
)
from app.modules.agent.automation_service import AgentAutomationService
from app.modules.agent.models import (
    AgentAutomation,
    AgentAutomationRun,
    AgentAutomationTrigger,
    AgentAutomationVersion,
    AgentDomainEvent,
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
        run.started_at = run.started_at or datetime.now(UTC)
        run.updated_by = owner.id
        await self._event(session, run, "run_started", {"retry_count": run.retry_count})
        outputs = self._resumed_outputs(run)
        try:
            for step in definition.steps:
                if step.key in outputs:
                    continue
                if isinstance(step, ToolStep):
                    completed = await self._execute_tool_step(
                        session, run=run, owner=owner, step=step, outputs=outputs
                    )
                    if not completed:
                        return
                elif isinstance(step, EndStep):
                    await self._finish_run(
                        session,
                        automation=automation,
                        run=run,
                        status_value=step.status,
                        error_code=None,
                        error_message=None,
                        output_summary={"message": step.message}
                        if step.message
                        else {},
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
                    received = await self._wait_for_event(
                        session, run=run, step=step, outputs=outputs
                    )
                    if not received:
                        return
                elif isinstance(step, ManualTaskStep):
                    completed = await self._wait_for_manual_task(
                        session, run=run, step=step, outputs=outputs
                    )
                    if not completed:
                        return
                else:
                    outputs[step.key] = {"status": "succeeded", "type": step.type}
                    await self._step(
                        session,
                        run=run,
                        step_key=step.key,
                        operation=None,
                        status_value="succeeded",
                        output_summary=outputs[step.key],
                    )
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
    ) -> bool:
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
            if step_run is None:
                await self._step(
                    session,
                    run=run,
                    step_key=step.key,
                    operation=None,
                    status_value="waiting_event",
                )
            run.status = AutomationRunStatus.WAITING.value
            run.output_summary = redact_sensitive({"steps": outputs})
            await self._event(
                session,
                run,
                "run_waiting_event",
                {"step_key": step.key, "event_type": step.event_type},
            )
            return False
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
        return True

    async def _wait_for_manual_task(
        self,
        session: AsyncSession,
        *,
        run: AgentAutomationRun,
        step: ManualTaskStep,
        outputs: dict[str, Any],
    ) -> bool:
        result = await session.execute(
            select(AgentStepRun)
            .where(AgentStepRun.run_id == run.id, AgentStepRun.step_key == step.key)
            .order_by(AgentStepRun.attempt.desc())
            .limit(1)
        )
        task = result.scalar_one_or_none()
        if task is not None and task.status == "succeeded":
            outputs[step.key] = dict(task.output_summary or {"status": "completed"})
            return True
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
        run.output_summary = redact_sensitive({"steps": outputs})
        await self._event(
            session,
            run,
            "manual_task_created",
            {"step_key": step.key, "title": step.title},
        )
        return False

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
            error_code="automation.execution_failed",
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
