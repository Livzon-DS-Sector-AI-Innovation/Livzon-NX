from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.models import AgentAutomation, AgentAutomationRun
from app.modules.agent.operations_service import AgentOperationsService
from app.platform.identity.models import User


def _user(role: str = "user") -> User:
    return User(
        name="Phase 5 User",
        username=f"phase-five-{uuid.uuid4().hex[:12]}",
        role=role,
        status="active",
        auth_source="local",
    )


@pytest.mark.anyio
async def test_operations_health_trends_suggestions_and_admin_report(
    db_session: AsyncSession,
) -> None:
    owner = _user()
    admin = _user("admin")
    db_session.add_all([owner, admin])
    await db_session.flush()
    automation = AgentAutomation(
        owner_user_id=owner.id,
        name="不稳定任务",
        status="enabled",
        active_version_id=uuid.uuid4(),
    )
    automation.created_by = owner.id
    automation.updated_by = owner.id
    db_session.add(automation)
    await db_session.flush()
    for status_value in ("failed", "waiting", "succeeded"):
        run = AgentAutomationRun(
            automation_id=automation.id,
            owner_user_id=owner.id,
            version_id=automation.active_version_id,
            status=status_value,
            idempotency_key=f"phase-five:{status_value}:{uuid.uuid4().hex}",
            correlation_id=uuid.uuid4(),
        )
        run.created_by = owner.id
        run.updated_by = owner.id
        db_session.add(run)
    await db_session.flush()

    service = AgentOperationsService()
    health = await service.health(db_session, user=owner)
    trends = await service.trends(db_session, user=owner)
    suggestions = await service.suggestions(db_session, user=owner)
    assert health[0]["failure_count"] == 1
    assert health[0]["waiting_count"] == 1
    assert health[0]["health_score"] < 100
    assert trends["failure_count"] == 1
    assert trends["waiting_count"] == 1
    assert suggestions[0]["requires_owner_confirmation"] is True
    assert len(service.templates()) >= 2
    report = await service.admin_report(db_session, user=admin)
    assert "失败运行 1 次" in report["summary"]
    with pytest.raises(HTTPException):
        await service.admin_report(db_session, user=owner)
