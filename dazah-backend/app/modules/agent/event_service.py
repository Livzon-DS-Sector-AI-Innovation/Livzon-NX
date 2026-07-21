from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redaction import redact_sensitive
from app.modules.agent.automation_schema import AutomationDefinitionV1, EventWaitStep
from app.modules.agent.models import (
    AgentAutomation,
    AgentAutomationRun,
    AgentAutomationTrigger,
    AgentAutomationVersion,
    AgentDomainEvent,
    AgentStepRun,
)
from app.platform.identity.models import User


class DomainEventEnvelope(BaseModel):
    """Public, minimal envelope that business modules may publish by public API."""

    model_config = ConfigDict(extra="forbid")

    source_module: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)
    event_type: str = Field(
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[0-9]+$",
        max_length=160,
    )
    event_version: str = Field(pattern=r"^v[0-9]+$", max_length=16)
    subject_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=80)
    subject_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=240)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID


class AgentDomainEventService:
    """Persists envelopes and queues matching automations without module imports."""

    async def publish(
        self, db: AsyncSession, *, envelope: DomainEventEnvelope
    ) -> AgentDomainEvent:
        existing = await db.execute(
            select(AgentDomainEvent).where(
                AgentDomainEvent.source_module == envelope.source_module,
                AgentDomainEvent.idempotency_key == envelope.idempotency_key,
                AgentDomainEvent.is_deleted.is_(False),
            )
        )
        event = existing.scalar_one_or_none()
        if event is not None:
            return event
        event = AgentDomainEvent(
            source_module=envelope.source_module,
            event_type=envelope.event_type,
            event_version=envelope.event_version,
            subject_type=envelope.subject_type,
            subject_id=envelope.subject_id,
            correlation_id=envelope.correlation_id,
            idempotency_key=envelope.idempotency_key,
            payload_summary=redact_sensitive(envelope.payload),
            occurred_at=datetime.now(UTC),
        )
        db.add(event)
        await db.flush()
        await self._queue_matching_triggers(db, event=event)
        await self._resume_waiting_runs(db, event=event)
        return event

    async def list_for_user(
        self, db: AsyncSession, *, user: User, correlation_id: UUID
    ) -> list[dict[str, Any]]:
        statement = select(AgentDomainEvent).where(
            AgentDomainEvent.is_deleted.is_(False),
            AgentDomainEvent.correlation_id == correlation_id,
        )
        if user.role != "admin":
            statement = statement.where(
                AgentDomainEvent.correlation_id.in_(
                    select(AgentAutomationRun.correlation_id).where(
                        AgentAutomationRun.owner_user_id == user.id,
                        AgentAutomationRun.is_deleted.is_(False),
                    )
                )
            )
        result = await db.execute(
            statement.order_by(AgentDomainEvent.occurred_at.asc())
        )
        return [
            {
                "id": str(item.id),
                "source_module": item.source_module,
                "event_type": item.event_type,
                "event_version": item.event_version,
                "subject_type": item.subject_type,
                "subject_id": item.subject_id,
                "correlation_id": str(item.correlation_id),
                "payload_summary": redact_sensitive(item.payload_summary),
                "occurred_at": item.occurred_at,
            }
            for item in result.scalars()
        ]

    async def _queue_matching_triggers(
        self, db: AsyncSession, *, event: AgentDomainEvent
    ) -> None:
        result = await db.execute(
            select(AgentAutomationTrigger, AgentAutomation)
            .join(
                AgentAutomation,
                AgentAutomation.id == AgentAutomationTrigger.automation_id,
            )
            .where(
                AgentAutomationTrigger.is_deleted.is_(False),
                AgentAutomationTrigger.trigger_type.in_(
                    ["data_event", "platform_event"]
                ),
                AgentAutomationTrigger.status == "enabled",
                AgentAutomationTrigger.event_type == event.event_type,
                AgentAutomation.is_deleted.is_(False),
                AgentAutomation.status == "enabled",
                AgentAutomation.active_version_id.is_not(None),
            )
            .with_for_update(skip_locked=True)
        )
        for trigger, automation in result.tuples():
            if not _matches_event_filter(trigger.event_filter, event.payload_summary):
                continue
            version_id = automation.active_version_id
            if version_id is None:
                continue
            idempotency_key = f"event:{event.id}:{trigger.id}"
            existing = await db.execute(
                select(AgentAutomationRun.id).where(
                    AgentAutomationRun.idempotency_key == idempotency_key,
                    AgentAutomationRun.is_deleted.is_(False),
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            run = AgentAutomationRun(
                automation_id=automation.id,
                owner_user_id=automation.owner_user_id,
                trigger_id=trigger.id,
                version_id=version_id,
                status="queued",
                idempotency_key=idempotency_key,
                correlation_id=event.correlation_id,
                input_summary={"trigger": event.payload_summary},
                retry_at=datetime.now(UTC),
                trigger_actor_type="domain_event",
            )
            run.created_by = automation.owner_user_id
            run.updated_by = automation.owner_user_id
            db.add(run)

    async def _resume_waiting_runs(
        self, db: AsyncSession, *, event: AgentDomainEvent
    ) -> None:
        result = await db.execute(
            select(AgentAutomationRun, AgentAutomationVersion)
            .join(
                AgentAutomationVersion,
                AgentAutomationVersion.id == AgentAutomationRun.version_id,
            )
            .where(
                AgentAutomationRun.is_deleted.is_(False),
                AgentAutomationRun.status == "waiting",
                AgentAutomationRun.correlation_id == event.correlation_id,
            )
            .with_for_update(skip_locked=True)
        )
        for run, version in result.tuples():
            definition = AutomationDefinitionV1.model_validate(version.definition)
            waiting = await db.execute(
                select(AgentStepRun.step_key).where(
                    AgentStepRun.run_id == run.id,
                    AgentStepRun.status == "waiting_event",
                )
            )
            waiting_keys = set(waiting.scalars())
            if any(
                isinstance(step, EventWaitStep)
                and step.key in waiting_keys
                and step.event_type == event.event_type
                for step in definition.steps
            ):
                run.status = "queued"
                run.retry_at = datetime.now(UTC)


def _matches_event_filter(
    event_filter: dict[str, Any], payload: dict[str, Any]
) -> bool:
    """Keep v1 filters deterministic: exact scalar fields only."""
    return all(payload.get(key) == value for key, value in event_filter.items())
