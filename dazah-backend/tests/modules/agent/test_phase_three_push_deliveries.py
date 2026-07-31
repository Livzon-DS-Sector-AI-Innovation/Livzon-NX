from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.automation_schema import NotifyStep
from app.modules.agent.models import (
    AgentAutomation,
    AgentAutomationRun,
    AgentPushDelivery,
    AgentPushTemplateVersion,
    AgentRunEvent,
)
from app.modules.agent.push_delivery_service import PushDeliveryService
from app.platform.identity.models import User


def _user() -> User:
    return User(
        name="Phase 3 Recipient",
        username=f"phase-three-{uuid.uuid4().hex[:12]}",
        role="user",
        status="active",
        auth_source="local",
        feishu_open_id="ou_phase_three",
    )


@pytest.mark.anyio
async def test_notify_creates_one_idempotent_delivery_per_local_recipient(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _user()
    db_session.add(owner)
    await db_session.flush()
    automation = AgentAutomation(
        owner_user_id=owner.id,
        name="Phase 3 通知任务",
        status="enabled",
        active_version_id=uuid.uuid4(),
    )
    automation.created_by = owner.id
    automation.updated_by = owner.id
    db_session.add(automation)
    await db_session.flush()
    run = AgentAutomationRun(
        automation_id=automation.id,
        owner_user_id=owner.id,
        version_id=automation.active_version_id,
        status="running",
        idempotency_key=f"phase-three-run:{uuid.uuid4().hex}",
        correlation_id=uuid.uuid4(),
    )
    run.created_by = owner.id
    run.updated_by = owner.id
    db_session.add(run)
    await db_session.flush()

    async def fake_send(*_args: object, **_kwargs: object) -> dict:
        return {"status": "sent", "message_id": "om_phase_three_delivery"}

    monkeypatch.setattr(
        "app.modules.agent.push_delivery_service."
        "PushDeliveryService._enqueue_gateway_delivery",
        fake_send,
    )
    step = NotifyStep.model_validate(
        {
            "key": "notify_owner",
            "type": "notify",
            "template": "phase_three_test_v1",
            "recipients": [{"type": "user", "user_id": str(owner.id)}],
            "variables": {"api_token": "must-not-leak"},
        }
    )
    service = PushDeliveryService()

    async def new_run() -> AgentAutomationRun:
        item = AgentAutomationRun(
            automation_id=automation.id,
            owner_user_id=owner.id,
            version_id=automation.active_version_id,
            status="running",
            idempotency_key=f"phase-three-run:{uuid.uuid4().hex}",
            correlation_id=uuid.uuid4(),
        )
        item.created_by = owner.id
        item.updated_by = owner.id
        db_session.add(item)
        await db_session.flush()
        return item

    step_run_id = uuid.uuid4()
    first = await service.dispatch_notify(
        db_session,
        automation=automation,
        run=run,
        owner=owner,
        step=step,
        step_run_id=step_run_id,
        outputs={},
    )
    second = await service.dispatch_notify(
        db_session,
        automation=automation,
        run=run,
        owner=owner,
        step=step,
        step_run_id=step_run_id,
        outputs={},
    )
    deliveries = await db_session.execute(
        select(AgentPushDelivery).where(AgentPushDelivery.run_id == run.id)
    )
    templates = await db_session.execute(
        select(AgentPushTemplateVersion).where(
            AgentPushTemplateVersion.template_key == "phase_three_test_v1"
        )
    )
    events = await db_session.execute(
        select(AgentRunEvent).where(AgentRunEvent.run_id == run.id)
    )

    delivery_rows = list(deliveries.scalars())
    assert len(first["deliveries"]) == 1
    assert len(second["deliveries"]) == 1
    assert len(delivery_rows) == 1
    assert all(item.status == "sent" for item in delivery_rows)
    assert "must-not-leak" not in str(delivery_rows[0].content_summary)
    assert len(list(templates.scalars())) == 1
    assert any(
        item.event_type == "push_dispatch_completed" for item in events.scalars()
    )

    delivery = delivery_rows[0]
    delivery.status = "pending"
    delivery.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    retry_ids = await service.claim_due_retries(db_session)
    assert retry_ids == [delivery.id]
    await service.retry_delivery(db_session, delivery_id=delivery.id)
    assert delivery.status == "sent"
    assert delivery.attempt_count == 2

    other_user = _user()
    db_session.add(other_user)
    await db_session.flush()
    with pytest.raises(PermissionError):
        await service.get_for_user(
            db_session, user=other_user, delivery_id=delivery.id
        )
    admin = _user()
    admin.role = "admin"
    db_session.add(admin)
    await db_session.flush()
    admin_view = await service.get_for_user(
        db_session, user=admin, delivery_id=delivery.id
    )
    assert admin_view["recipient_ref"] == {"redacted": True}
    assert "must-not-leak" not in str(admin_view["content_summary"])

    aggregation_step = NotifyStep.model_validate(
        {
            "key": "aggregate_alert",
            "type": "notify",
            "template": "phase_three_test_v1",
            "recipients": [{"type": "user", "user_id": str(owner.id)}],
            "aggregation_key": "warehouse-stockout:line-1",
            "aggregation_window_seconds": 900,
        }
    )
    aggregate_run = await new_run()
    await service.dispatch_notify(
        db_session,
        automation=automation,
        run=aggregate_run,
        owner=owner,
        step=aggregation_step,
        step_run_id=uuid.uuid4(),
        outputs={},
    )
    aggregate_repeat_run = await new_run()
    aggregated = await service.dispatch_notify(
        db_session,
        automation=automation,
        run=aggregate_repeat_run,
        owner=owner,
        step=aggregation_step,
        step_run_id=uuid.uuid4(),
        outputs={},
    )
    assert aggregated["deliveries"][0]["status"] == "suppressed"

    silence_step = NotifyStep.model_validate(
        {
            "key": "silent_alert",
            "type": "notify",
            "template": "phase_three_test_v1",
            "recipients": [{"type": "user", "user_id": str(owner.id)}],
            "silence_until": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        }
    )
    silence_run = await new_run()
    silenced = await service.dispatch_notify(
        db_session,
        automation=automation,
        run=silence_run,
        owner=owner,
        step=silence_step,
        step_run_id=uuid.uuid4(),
        outputs={},
    )
    assert silenced["deliveries"][0]["status"] == "suppressed"

    async def fake_timeout_after_accept(*_args: object, **_kwargs: object) -> dict:
        return {
            "status": "failed",
            "message_id": "om_phase_three_timeout_reconciled",
            "error_message": "gateway timeout",
        }

    monkeypatch.setattr(
        "app.modules.agent.push_delivery_service."
        "PushDeliveryService._enqueue_gateway_delivery",
        fake_timeout_after_accept,
    )
    timeout_run = await new_run()
    timeout_delivery = await service.dispatch_notify(
        db_session,
        automation=automation,
        run=timeout_run,
        owner=owner,
        step=aggregation_step.model_copy(
            update={"aggregation_key": "timeout-reconcile"}
        ),
        step_run_id=uuid.uuid4(),
        outputs={},
    )
    assert timeout_delivery["deliveries"][0]["status"] == "sent"

    async def fake_failed(*_args: object, **_kwargs: object) -> dict:
        return {"status": "failed", "error_code": "unavailable"}

    monkeypatch.setattr(
        "app.modules.agent.push_delivery_service."
        "PushDeliveryService._enqueue_gateway_delivery",
        fake_failed,
    )
    incident_step = aggregation_step.model_copy(
        update={"aggregation_key": None, "incident_key": "quality:batch-9"}
    )
    failed_run = await new_run()
    service.max_attempts = 1
    failed = await service.dispatch_notify(
        db_session,
        automation=automation,
        run=failed_run,
        owner=owner,
        step=incident_step,
        step_run_id=uuid.uuid4(),
        outputs={},
    )
    assert failed["deliveries"][0]["status"] == "failed"

    monkeypatch.setattr(
        "app.modules.agent.push_delivery_service."
        "PushDeliveryService._enqueue_gateway_delivery",
        fake_send,
    )
    service.max_attempts = 3
    recovery_run = await new_run()
    recovery = await service.dispatch_notify(
        db_session,
        automation=automation,
        run=recovery_run,
        owner=owner,
        step=incident_step,
        step_run_id=uuid.uuid4(),
        outputs={},
    )
    recovery_events = await db_session.execute(
        select(AgentRunEvent.event_type).where(AgentRunEvent.run_id == recovery_run.id)
    )
    assert recovery["deliveries"][0]["status"] == "sent"
    assert "push_recovery_sent" in set(recovery_events.scalars())
