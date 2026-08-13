from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.automation_runner import AgentAutomationRunner
from app.modules.agent.automation_schedule import preview_next_fires
from app.modules.agent.automation_service import AgentAutomationService
from app.modules.agent.models import (
    AgentAccessScopeSnapshot,
    AgentAutomation,
    AgentAutomationGrant,
    AgentAutomationRun,
    AgentAutomationTrigger,
    AgentAutomationVersion,
    AgentConfirmation,
    AgentRunEvent,
    AgentStepRun,
)
from app.modules.agent.repository import AgentRepository
from app.modules.agent.schemas import AgentAutomationDraftCreate
from app.modules.agent.tools import tool_registry
from app.platform.audit.models import AuditLog
from app.platform.identity.models import PermissionOutboxEvent, User, UserModuleGrant
from app.platform.identity.permissions import IdentityPermissionService
from app.platform.identity.schemas import (
    ModulePermissionGrantInput,
    UserModulePermissionsUpdate,
)
from tests.conftest import _test_session_factory


def _user(*, role: str = "user") -> User:
    return User(
        name=f"Phase 2 {role}",
        username=f"phase-two-{role}-{uuid.uuid4().hex[:12]}",
        role=role,
        status="active",
        auth_source="local",
    )


async def _grant_automation(
    db_session: AsyncSession,
    *,
    admin: User,
    owner: User,
) -> None:
    await IdentityPermissionService().replace_user_permissions(
        db_session,
        target_user_id=owner.id,
        request=UserModulePermissionsUpdate(
            expected_grant_version=owner.grant_version,
            reason="Phase 2 调度集成测试授权",
            grants=[
                ModulePermissionGrantInput(
                    module_code="quality",
                    permissions=[
                        "module.view",
                        "module.agent.read",
                        "module.agent.automate",
                    ],
                    data_scope={"factory_ids": ["F-1"]},
                )
            ],
        ),
        current_user=admin,
    )


def _draft_payload(
    *,
    missed_trigger_policy: str = "run_once",
    concurrency_policy: str = "forbid",
    include_quality_tool: bool = False,
) -> dict:
    steps = []
    if include_quality_tool:
        steps.append(
            {
                "key": "list_deviations",
                "type": "tool",
                "operation": "quality.list_deviations",
                "input": {"page": 1, "page_size": 1},
            }
        )
    steps.append({"key": "finish", "type": "end", "status": "succeeded"})
    return {
        "definition": {
            "name": "每分钟调度验收",
            "missed_trigger_policy": missed_trigger_policy,
            "concurrency_policy": concurrency_policy,
            "steps": steps,
        },
        "triggers": [
            {
                "trigger_type": "schedule",
                "schedule": {"cron": "* * * * *"},
                "timezone": "Asia/Shanghai",
            }
        ],
    }


async def _create_enabled(
    db_session: AsyncSession,
    *,
    owner: User,
    missed_trigger_policy: str = "run_once",
    concurrency_policy: str = "forbid",
    include_quality_tool: bool = False,
):
    service = AgentAutomationService()
    draft = await service.create_draft(
        db_session,
        user=owner,
        request=AgentAutomationDraftCreate.model_validate(
            _draft_payload(
                missed_trigger_policy=missed_trigger_policy,
                concurrency_policy=concurrency_policy,
                include_quality_tool=include_quality_tool,
            )
        ),
    )
    return await service.confirm_automation(
        db_session, user=owner, automation_id=draft.id
    )


@pytest.mark.anyio
async def test_scheduler_claims_once_and_executes_immutable_run_snapshot(
    db_session: AsyncSession,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_automation(db_session, admin=admin, owner=owner)
    automation = await _create_enabled(db_session, owner=owner)
    trigger = await db_session.get(AgentAutomationTrigger, automation.triggers[0].id)
    assert trigger is not None
    trigger.next_fire_at = datetime.now(UTC)

    runner = AgentAutomationRunner()
    claimed = await runner.claim_due_work(db_session)
    assert len(claimed) == 1
    assert claimed[0].scheduled_for is not None
    await runner.execute_work(db_session, claimed[0])
    second_claim = await runner.claim_due_work(db_session)
    runs = await db_session.execute(
        select(AgentAutomationRun).where(
            AgentAutomationRun.automation_id == automation.id
        )
    )

    run_rows = list(runs.scalars())
    assert second_claim == []
    assert len(run_rows) == 1
    assert run_rows[0].status == "succeeded"
    assert trigger.next_fire_at is not None
    assert trigger.next_fire_at > datetime.now(UTC)


@pytest.mark.anyio
async def test_enabled_automation_can_run_immediately_after_confirmation(
    db_session: AsyncSession,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_automation(db_session, admin=admin, owner=owner)
    automation = await _create_enabled(db_session, owner=owner)

    run = await AgentAutomationRunner().execute_manual(
        db_session,
        automation_id=automation.id,
    )

    assert run.automation_id == automation.id
    assert run.trigger_id is None
    assert run.trigger_actor_type == "user_manual"
    assert run.status == "succeeded"


@pytest.mark.anyio
async def test_v11_wait_run_resumes_from_persisted_cursor(
    db_session: AsyncSession,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_automation(db_session, admin=admin, owner=owner)
    service = AgentAutomationService()
    draft = await service.create_draft(
        db_session,
        user=owner,
        request=AgentAutomationDraftCreate.model_validate(
            {
                "definition": {
                    "schema_version": "1.1",
                    "name": "等待恢复",
                    "steps": [
                        {
                            "key": "prepare",
                            "type": "transform",
                            "operations": [{"op": "template", "template": "准备恢复"}],
                            "next": "pause",
                        },
                        {
                            "key": "pause",
                            "type": "wait",
                            "duration_seconds": 1,
                            "next": "done",
                        },
                        {"key": "done", "type": "end", "status": "succeeded"},
                    ],
                },
                "triggers": [{"trigger_type": "manual"}],
            }
        ),
    )
    await service.confirm_automation(db_session, user=owner, automation_id=draft.id)
    runner = AgentAutomationRunner()

    run = await runner.execute_manual(db_session, automation_id=draft.id)

    assert run.status == "waiting"
    assert run.current_step_key == "pause"
    assert run.resume_at is not None
    await asyncio.sleep(1.05)
    claimed = await runner.claim_due_work(db_session)
    resume_item = next(item for item in claimed if item.run_id == run.id)
    await runner.execute_work(db_session, resume_item)

    assert run.status == "succeeded"
    assert run.output_summary["steps"]["prepare"] == "准备恢复"


@pytest.mark.anyio
async def test_executed_confirmation_is_refetched_before_serialization(
    db_session: AsyncSession,
) -> None:
    user = _user()
    db_session.add(user)
    await db_session.flush()
    confirmation = AgentConfirmation(
        user_id=user.id,
        operation="identity.deliver_feishu_message",
        summary="发送测试卡片",
        risk_level="medium",
        status="pending",
        request_payload={},
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        created_by=user.id,
        updated_by=user.id,
    )
    db_session.add(confirmation)
    await db_session.flush()

    updated = await AgentRepository().execute_confirmation(
        db_session,
        confirmation,
        result_payload={"ok": True},
        user_id=user.id,
    )

    assert updated.status == "executed"
    assert updated.updated_at is not None
    assert updated.result_payload == {"ok": True}


@pytest.mark.anyio
async def test_expired_trigger_claim_is_recovered_after_restart(
    db_session: AsyncSession,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_automation(db_session, admin=admin, owner=owner)
    automation = await _create_enabled(db_session, owner=owner)
    trigger = await db_session.get(AgentAutomationTrigger, automation.triggers[0].id)
    assert trigger is not None
    trigger.next_fire_at = datetime.now(UTC)

    runner = AgentAutomationRunner()
    initial_claim = await runner.claim_due_work(db_session)
    assert len(initial_claim) == 1
    assert trigger.claim_token is not None
    trigger.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    recovered_claim = await runner.claim_due_work(db_session)
    assert len(recovered_claim) == 1
    await runner.execute_work(db_session, recovered_claim[0])
    runs = await db_session.execute(
        select(AgentAutomationRun).where(
            AgentAutomationRun.automation_id == automation.id
        )
    )

    assert len(list(runs.scalars())) == 1
    assert trigger.claim_token is None


@pytest.mark.anyio
async def test_two_scheduler_instances_do_not_claim_one_trigger_window(
    db_session: AsyncSession,
) -> None:
    """A second database session must skip the row locked by the first one."""
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_automation(db_session, admin=admin, owner=owner)
    automation = await _create_enabled(db_session, owner=owner)
    trigger = await db_session.get(AgentAutomationTrigger, automation.triggers[0].id)
    assert trigger is not None
    trigger.next_fire_at = datetime.now(UTC)
    automation_id = automation.id
    owner_ids = [admin.id, owner.id]
    await db_session.commit()

    try:
        async with _test_session_factory() as first_session:
            first_runner = AgentAutomationRunner()
            first_claim = await first_runner.claim_due_work(first_session)
            assert len(first_claim) == 1

            async with _test_session_factory() as second_session:
                second_claim = await AgentAutomationRunner().claim_due_work(
                    second_session
                )
                assert second_claim == []
                await second_session.rollback()

            await first_runner.execute_work(first_session, first_claim[0])
            await first_session.commit()
    finally:
        async with _test_session_factory() as cleanup_session:
            run_ids = select(AgentAutomationRun.id).where(
                AgentAutomationRun.automation_id == automation_id
            )
            await cleanup_session.execute(
                delete(AgentRunEvent).where(AgentRunEvent.run_id.in_(run_ids))
            )
            await cleanup_session.execute(
                delete(AgentStepRun).where(AgentStepRun.run_id.in_(run_ids))
            )
            await cleanup_session.execute(
                delete(AgentAutomationRun).where(
                    AgentAutomationRun.automation_id == automation_id
                )
            )
            await cleanup_session.execute(
                delete(AgentAutomationTrigger).where(
                    AgentAutomationTrigger.automation_id == automation_id
                )
            )
            await cleanup_session.execute(
                delete(AgentAutomationGrant).where(
                    AgentAutomationGrant.automation_id == automation_id
                )
            )
            await cleanup_session.execute(
                delete(AgentAutomationVersion).where(
                    AgentAutomationVersion.automation_id == automation_id
                )
            )
            await cleanup_session.execute(
                delete(AgentAutomation).where(AgentAutomation.id == automation_id)
            )
            await cleanup_session.execute(
                delete(AgentAccessScopeSnapshot).where(
                    AgentAccessScopeSnapshot.user_id.in_(owner_ids)
                )
            )
            await cleanup_session.execute(
                delete(PermissionOutboxEvent).where(
                    PermissionOutboxEvent.user_id.in_(owner_ids)
                )
            )
            await cleanup_session.execute(
                delete(UserModuleGrant).where(UserModuleGrant.user_id.in_(owner_ids))
            )
            await cleanup_session.execute(
                delete(AuditLog).where(AuditLog.user_id.in_(owner_ids))
            )
            await cleanup_session.execute(delete(User).where(User.id.in_(owner_ids)))
            await cleanup_session.commit()


@pytest.mark.anyio
async def test_missed_skip_creates_a_skipped_policy_run(
    db_session: AsyncSession,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_automation(db_session, admin=admin, owner=owner)
    automation = await _create_enabled(
        db_session, owner=owner, missed_trigger_policy="skip"
    )
    trigger = await db_session.get(AgentAutomationTrigger, automation.triggers[0].id)
    assert trigger is not None
    trigger.next_fire_at = datetime.now(UTC) - timedelta(minutes=2)

    runner = AgentAutomationRunner()
    claimed = await runner.claim_due_work(db_session)
    await runner.execute_work(db_session, claimed[0])
    runs = await db_session.execute(
        select(AgentAutomationRun).where(
            AgentAutomationRun.automation_id == automation.id
        )
    )

    run = runs.scalar_one()
    assert run.status == "skipped_policy"
    assert run.error_code == "automation.missed_trigger_skipped"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("concurrency_policy", "expected_status"),
    [
        ("forbid", "skipped_policy"),
        ("queue_one", "queued"),
        ("allow", "succeeded"),
    ],
)
async def test_scheduler_applies_concurrency_policy(
    db_session: AsyncSession,
    concurrency_policy: str,
    expected_status: str,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_automation(db_session, admin=admin, owner=owner)
    automation = await _create_enabled(
        db_session, owner=owner, concurrency_policy=concurrency_policy
    )
    active = AgentAutomationRun(
        automation_id=automation.id,
        owner_user_id=owner.id,
        version_id=automation.active_version_id,
        status="running",
        idempotency_key=f"phase-two-active:{uuid.uuid4().hex}",
        correlation_id=uuid.uuid4(),
        started_at=datetime.now(UTC),
    )
    active.created_by = owner.id
    active.updated_by = owner.id
    db_session.add(active)
    trigger = await db_session.get(AgentAutomationTrigger, automation.triggers[0].id)
    assert trigger is not None
    trigger.next_fire_at = datetime.now(UTC)

    runner = AgentAutomationRunner()
    claimed = await runner.claim_due_work(db_session)
    await runner.execute_work(db_session, claimed[0])
    result = await db_session.execute(
        select(AgentAutomationRun)
        .where(
            AgentAutomationRun.automation_id == automation.id,
            AgentAutomationRun.id != active.id,
        )
        .order_by(AgentAutomationRun.created_at.desc())
    )

    assert result.scalar_one().status == expected_status


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("idempotent", "expected_status", "expected_retry_count"),
    [(True, "queued", 1), (False, "failed", 0)],
)
async def test_scheduler_retries_only_idempotent_failed_steps(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    idempotent: bool,
    expected_status: str,
    expected_retry_count: int,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_automation(db_session, admin=admin, owner=owner)
    automation = await _create_enabled(
        db_session, owner=owner, include_quality_tool=True
    )
    trigger = await db_session.get(AgentAutomationTrigger, automation.triggers[0].id)
    assert trigger is not None
    trigger.next_fire_at = datetime.now(UTC)

    runner = AgentAutomationRunner()
    original_spec = tool_registry.require("quality.list_deviations")
    monkeypatch.setitem(
        tool_registry._tools,  # noqa: SLF001 - registry mutation is test-only
        "quality.list_deviations",
        replace(original_spec, idempotent=idempotent),
    )

    async def fail_tool(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("模拟步骤超时")

    monkeypatch.setattr(runner.tool_executor, "execute", fail_tool)
    claimed = await runner.claim_due_work(db_session)
    await runner.execute_work(db_session, claimed[0])
    result = await db_session.execute(
        select(AgentAutomationRun).where(
            AgentAutomationRun.automation_id == automation.id
        )
    )
    run = result.scalar_one()

    assert run.status == expected_status
    assert run.retry_count == expected_retry_count
    if idempotent:
        assert run.retry_at is not None
        assert run.error_code == "automation.retry_scheduled"
    else:
        assert run.retry_at is None
        assert run.error_code == "automation.execution_failed"


@pytest.mark.anyio
async def test_scheduler_quarantines_after_consecutive_failures(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_automation(db_session, admin=admin, owner=owner)
    automation = await _create_enabled(
        db_session, owner=owner, include_quality_tool=True
    )
    trigger = await db_session.get(AgentAutomationTrigger, automation.triggers[0].id)
    assert trigger is not None
    trigger.next_fire_at = datetime.now(UTC)

    runner = AgentAutomationRunner()
    runner.quarantine_after_failures = 1

    async def fail_tool(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("模拟不可重试失败")

    monkeypatch.setattr(runner.tool_executor, "execute", fail_tool)
    claimed = await runner.claim_due_work(db_session)
    await runner.execute_work(db_session, claimed[0])
    current = await db_session.get(AgentAutomation, automation.id)

    assert current is not None
    assert current.status == "quarantined"
    assert current.consecutive_failures == 1
    assert current.quarantined_at is not None


@pytest.mark.anyio
async def test_revoked_scope_suspends_scheduled_automation(
    db_session: AsyncSession,
) -> None:
    admin = _user(role="admin")
    owner = _user()
    db_session.add_all([admin, owner])
    await db_session.flush()
    await _grant_automation(db_session, admin=admin, owner=owner)
    automation = await _create_enabled(
        db_session, owner=owner, include_quality_tool=True
    )
    trigger = await db_session.get(AgentAutomationTrigger, automation.triggers[0].id)
    assert trigger is not None
    trigger.next_fire_at = datetime.now(UTC)
    await IdentityPermissionService().replace_user_permissions(
        db_session,
        target_user_id=owner.id,
        request=UserModulePermissionsUpdate(
            expected_grant_version=owner.grant_version,
            reason="撤销 Phase 2 调度权限",
            grants=[],
        ),
        current_user=admin,
    )

    runner = AgentAutomationRunner()
    claimed = await runner.claim_due_work(db_session)
    await runner.execute_work(db_session, claimed[0])
    run_rows = await db_session.execute(
        select(AgentAutomationRun).where(
            AgentAutomationRun.automation_id == automation.id
        )
    )
    current = await db_session.get(AgentAutomation, automation.id)

    assert run_rows.scalar_one().status == "skipped_policy"
    assert current is not None
    assert current.status == "suspended_policy"


def test_schedule_preview_returns_future_utc_windows() -> None:
    future = preview_next_fires(
        schedule={"cron": "0 9 * * 1-5"},
        timezone="Asia/Shanghai",
        count=3,
        after=datetime(2026, 7, 10, 0, 0, tzinfo=UTC),
    )

    assert len(future) == 3
    assert future == sorted(future)
    assert all(item.tzinfo == UTC for item in future)
