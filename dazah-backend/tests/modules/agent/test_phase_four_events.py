from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.automation_runner import AgentAutomationRunner
from app.modules.agent.automation_schema import (
    AutomationDefinitionV1,
    EventWaitStep,
    ManualTaskStep,
)
from app.modules.agent.automation_service import AgentAutomationService
from app.modules.agent.event_service import AgentDomainEventService, DomainEventEnvelope
from app.modules.agent.manual_task_service import AgentManualTaskService
from app.modules.agent.models import (
    AgentAutomation,
    AgentAutomationRun,
    AgentAutomationTrigger,
    AgentAutomationVersion,
    AgentDomainEvent,
)
from app.modules.procurement.public_api import publish_purchase_arrival
from app.platform.identity.models import User


def _owner() -> User:
    return User(
        name="Phase 4 Owner",
        username=f"phase-four-{uuid.uuid4().hex[:12]}",
        role="user",
        status="active",
        auth_source="local",
    )


@pytest.mark.anyio
async def test_versioned_event_envelope_is_idempotent_and_queues_event_trigger(
    db_session: AsyncSession,
) -> None:
    owner = _owner()
    db_session.add(owner)
    await db_session.flush()
    version_id = uuid.uuid4()
    automation = AgentAutomation(
        owner_user_id=owner.id,
        name="采购到货后仓储入库提醒",
        status="enabled",
        active_version_id=version_id,
    )
    automation.created_by = owner.id
    automation.updated_by = owner.id
    db_session.add(automation)
    await db_session.flush()
    version = AgentAutomationVersion(
        id=version_id,
        automation_id=automation.id,
        version=1,
        definition={
            "schema_version": "1.0",
            "name": "采购到货后仓储入库提醒",
            "steps": [
                {
                    "key": "wait_arrival",
                    "type": "event_wait",
                    "event_type": "procurement.purchase_arrival.v1",
                },
                {"key": "done", "type": "end", "status": "succeeded"},
            ],
        },
    )
    trigger = AgentAutomationTrigger(
        automation_id=automation.id,
        trigger_type="data_event",
        status="enabled",
        event_type="procurement.purchase_arrival.v1",
        event_filter={"warehouse_code": "WH-01"},
    )
    for item in (version, trigger):
        item.created_by = owner.id
        item.updated_by = owner.id
    db_session.add_all([version, trigger])
    await db_session.flush()

    definition = AutomationDefinitionV1.model_validate(version.definition)
    assert isinstance(definition.steps[0], EventWaitStep)

    correlation_id = uuid.uuid4()
    assert DomainEventEnvelope.model_validate(
        {
            "source_module": "procurement",
            "event_type": "procurement.purchase_arrival.v1",
            "event_version": "v1",
            "subject_type": "purchase_arrival",
            "subject_id": "arrival-20260710-001",
            "idempotency_key": "procurement.purchase_arrival:arrival-20260710-001",
            "correlation_id": correlation_id,
            "payload": {"warehouse_code": "WH-01", "api_token": "must-not-leak"},
        }
    )
    first = await publish_purchase_arrival(
        db_session,
        arrival_id="arrival-20260710-001",
        purchase_request_id=automation.id,
        warehouse_code="WH-01",
        material_code="MAT-01",
        material_name="原辅料",
        received_quantity=Decimal("12.5"),
        correlation_id=correlation_id,
    )
    second = await publish_purchase_arrival(
        db_session,
        arrival_id="arrival-20260710-001",
        purchase_request_id=automation.id,
        warehouse_code="WH-01",
        material_code="MAT-01",
        material_name="原辅料",
        received_quantity=Decimal("12.5"),
        correlation_id=correlation_id,
    )
    await db_session.flush()

    events = await db_session.execute(
        select(AgentDomainEvent).where(
            AgentDomainEvent.idempotency_key
            == "procurement.purchase_arrival:arrival-20260710-001"
        )
    )
    runs = await db_session.execute(
        select(AgentAutomationRun).where(
            AgentAutomationRun.automation_id == automation.id
        )
    )
    event_rows = list(events.scalars())
    run_rows = list(runs.scalars())
    assert first.id == second.id
    assert len(event_rows) == 1
    assert "must-not-leak" not in str(event_rows[0].payload_summary)
    assert len(run_rows) == 1
    assert run_rows[0].correlation_id == correlation_id
    assert run_rows[0].idempotency_key == f"event:{first.id}:{trigger.id}"
    assert run_rows[0].input_summary["trigger"]["warehouse_code"] == "WH-01"
    assert len(
        await AgentDomainEventService().list_for_user(
            db_session, user=owner, correlation_id=correlation_id
        )
    ) == 1

    version.capability_versions = {"warehouse.list_raw_materials": "0.1"}
    impacts = await AgentAutomationService().list_capability_impacts(
        db_session, user=owner
    )
    assert any(item["reason"] == "major_version_changed" for item in impacts)

    wait_run = AgentAutomationRun(
        automation_id=automation.id,
        owner_user_id=owner.id,
        version_id=version.id,
        status="running",
        idempotency_key=f"event-wait:{uuid.uuid4().hex}",
        correlation_id=correlation_id,
    )
    wait_run.created_by = owner.id
    wait_run.updated_by = owner.id
    db_session.add(wait_run)
    await db_session.flush()
    runner = AgentAutomationRunner()
    wait_step = definition.steps[0]
    assert isinstance(wait_step, EventWaitStep)
    outputs: dict[str, object] = {}
    assert not await runner._wait_for_event(
        db_session, run=wait_run, step=wait_step, outputs=outputs
    )

    resumed = await publish_purchase_arrival(
        db_session,
        arrival_id="arrival-20260710-002",
        purchase_request_id=automation.id,
        warehouse_code="WH-01",
        material_code="MAT-01",
        material_name="原辅料",
        received_quantity=Decimal("12.5"),
        correlation_id=correlation_id,
    )
    assert wait_run.status == "queued"
    assert await runner._wait_for_event(
        db_session, run=wait_run, step=wait_step, outputs=outputs
    )
    assert outputs["wait_arrival"]["subject_id"] == resumed.subject_id

    manual_step = ManualTaskStep.model_validate(
        {"key": "confirm_inbound", "type": "manual_task", "title": "确认仓储入库"}
    )
    manual_run = AgentAutomationRun(
        automation_id=automation.id,
        owner_user_id=owner.id,
        version_id=version.id,
        status="running",
        idempotency_key=f"manual-task:{uuid.uuid4().hex}",
        correlation_id=uuid.uuid4(),
    )
    manual_run.created_by = owner.id
    manual_run.updated_by = owner.id
    db_session.add(manual_run)
    await db_session.flush()
    manual_outputs: dict[str, object] = {}
    assert not await runner._wait_for_manual_task(
        db_session, run=manual_run, step=manual_step, outputs=manual_outputs
    )
    assert manual_run.status == "waiting"
    await AgentManualTaskService().complete(
        db_session, user=owner, run_id=manual_run.id
    )
    assert await runner._wait_for_manual_task(
        db_session, run=manual_run, step=manual_step, outputs=manual_outputs
    )
