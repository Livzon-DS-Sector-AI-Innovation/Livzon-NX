from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.agent import api
from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.automation_runner import AgentAutomationRunner
from app.modules.agent.automation_service import AgentAutomationService
from app.modules.agent.catalog import ToolCatalogService
from app.modules.agent.models import (
    AgentAutomation,
    AgentAutomationRun,
    AgentConfirmation,
    AgentMessage,
    AgentRunEvent,
    AgentStepRun,
)
from app.modules.agent.schemas import (
    AgentAutomationDraftCreate,
    AgentToolExecuteRequest,
)
from app.modules.agent.service import AgentService
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import (
    AgentToolSpec,
    EmptyToolInput,
    ToolContext,
    tool_registry,
)
from app.platform.identity import deps
from app.platform.identity.models import User, UserPageGrant
from app.platform.identity.rbac import seed_menus
from tests.modules.agent.delegation_helpers import delegated_subject


@pytest.mark.asyncio
async def test_capabilities_http_tracks_permission_disabled_and_sync_failure(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await seed_menus(db_session)
    user = User(name="能力验收", role="user", tenant_key="local")
    db_session.add(user)
    await db_session.flush()
    grant = UserPageGrant(
        user_id=user.id,
        page_key="purchasing:supplier",
        permissions=["access", "query"],
        scope_type="all",
        sensitive_actions=[],
    )
    db_session.add(grant)
    await db_session.flush()
    app = FastAPI()
    app.include_router(api.router, prefix="/agent")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[deps.get_current_user] = lambda: user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/agent/capabilities")
        assert response.status_code == 200
        data = response.json()["data"]
        tools = {tool["operation"]: tool for tool in data["tools"]}
        assert tools["analytics.aggregate"]["state"] == "available"
        assert tools["analytics.aggregate"]["permission_sources"][0]["source"] == "user"
        assert tools["quality.list_deviations"]["state"] == "unauthorized"
        assert "identity.search_personnel" not in tools
        assert any(item["state"] == "not_integrated" for item in data["modules"])
        await ToolCatalogService().set_enabled(
            db_session, operation="analytics.aggregate", enabled=False
        )
        assert (
            next(
                item
                for item in (await client.get("/agent/capabilities")).json()["data"][
                    "tools"
                ]
                if item["operation"] == "analytics.aggregate"
            )["state"]
            == "disabled"
        )
        assert (
            await client.get(f"/agent/control/capabilities/{user.id}")
        ).status_code == 403
        user.role = "admin"
        diagnosis = await client.get(f"/agent/control/capabilities/{user.id}")
        assert diagnosis.status_code == 200
        assert any(
            item["state"] == "not_integrated" and item["reason"]
            for item in diagnosis.json()["data"]["tools"]
        )
        foreign = User(name="跨租户诊断验收", role="user", tenant_key="foreign")
        db_session.add(foreign)
        await db_session.flush()
        assert (
            await client.get(f"/agent/control/capabilities/{foreign.id}")
        ).status_code == 404
        user.role = "user"
        monkeypatch.setattr(
            AgentAccessScopeService,
            "get_current_scope",
            AsyncMock(side_effect=HTTPException(403, "synthetic-secret-error")),
        )
        failed = await client.get("/agent/capabilities")
        assert failed.status_code == 200
        assert failed.json()["data"]["sync_status"] == "failed"
        assert all(
            item["state"] == "sync_failed" for item in failed.json()["data"]["tools"]
        )
        assert "synthetic-secret-error" not in failed.text
        user.status = "disabled"
        assert (await client.get("/agent/capabilities")).status_code == 403


@pytest.mark.asyncio
async def test_retry_resumes_same_run_without_replaying_completed_write(
    db_session: AsyncSession,
) -> None:
    await seed_menus(db_session)
    ensure_agent_tools_registered()
    counts = {"write": 0, "read": 0}
    write_name, read_name = (
        f"agent.acceptance_write_{uuid4().hex}",
        f"agent.acceptance_read_{uuid4().hex}",
    )

    async def write_handler(
        context: ToolContext, data: EmptyToolInput
    ) -> dict[str, int]:
        counts["write"] += 1
        return {"written": counts["write"]}

    async def read_handler(
        context: ToolContext, data: EmptyToolInput
    ) -> dict[str, bool]:
        counts["read"] += 1
        if counts["read"] == 1:
            raise RuntimeError("synthetic temporary read failure")
        return {"ready": True}

    tool_registry.register(
        AgentToolSpec(
            name=write_name,
            summary="验收写入",
            input_model=EmptyToolInput,
            handler=write_handler,
            write=True,
        )
    )
    tool_registry.register(
        AgentToolSpec(
            name=read_name,
            summary="验收读取",
            input_model=EmptyToolInput,
            handler=read_handler,
        )
    )
    try:
        user = User(name="重试验收", role="user", tenant_key="local")
        db_session.add(user)
        await db_session.flush()
        service = AgentAutomationService()
        draft = await service.create_draft(
            db_session,
            user=user,
            request=AgentAutomationDraftCreate.model_validate(
                {
                    "definition": {
                        "schema_version": "1.1",
                        "name": "断点重试",
                        "steps": [
                            {
                                "key": "write",
                                "type": "tool",
                                "operation": write_name,
                                "next": "read",
                            },
                            {
                                "key": "read",
                                "type": "tool",
                                "operation": read_name,
                                "next": "done",
                            },
                            {"key": "done", "type": "end", "status": "succeeded"},
                        ],
                    },
                    "triggers": [{"trigger_type": "manual"}],
                }
            ),
        )
        await service.confirm_automation(db_session, user=user, automation_id=draft.id)
        runner = AgentAutomationRunner()
        run = await runner.execute_manual(db_session, automation_id=draft.id)
        assert run.status == "failed"
        assert run.output_summary["steps"]["write"] == {"written": 1}
        failed_step = await db_session.scalar(
            select(AgentStepRun).where(
                AgentStepRun.run_id == run.id, AgentStepRun.step_key == "read"
            )
        )
        assert failed_step is not None
        failed_step.operation = write_name
        with pytest.raises(HTTPException) as unsafe:
            await runner.retry_failed(db_session, run_id=run.id, user=user)
        assert unsafe.value.status_code == 409
        assert counts == {"write": 1, "read": 1}
        failed_step.operation = read_name
        user.status = "disabled"
        with pytest.raises(HTTPException) as inactive:
            await runner.retry_failed(db_session, run_id=run.id, user=user)
        assert inactive.value.status_code == 403
        user.status = "active"
        retried = await runner.retry_failed(db_session, run_id=run.id, user=user)
        assert retried.id == run.id and retried.status == "succeeded"
        assert counts == {"write": 1, "read": 2}
        assert retried.output_summary["steps"]["write"] == {"written": 1}
        with pytest.raises(HTTPException) as exc:
            await runner.retry_failed(db_session, run_id=run.id, user=user)
        assert exc.value.status_code == 409
        assert counts["write"] == 1
    finally:
        tool_registry._tools.pop(write_name)
        tool_registry._tools.pop(read_name)


@pytest.mark.asyncio
async def test_run_explanation_http_owns_trace_and_omits_raw_errors(
    db_session: AsyncSession,
) -> None:
    await seed_menus(db_session)
    user = User(name="运行验收", role="user", tenant_key="local")
    other = User(name="其他用户", role="user", tenant_key="local")
    db_session.add_all([user, other])
    await db_session.flush()
    automation = AgentAutomation(owner_user_id=user.id, name="验收", status="enabled")
    db_session.add(automation)
    await db_session.flush()
    run = AgentAutomationRun(
        automation_id=automation.id,
        owner_user_id=user.id,
        version_id=uuid4(),
        correlation_id=uuid4(),
        idempotency_key=uuid4().hex,
        status="failed",
        error_code="automation.execution_failed",
        error_message="password=synthetic-secret",
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(
        AgentStepRun(
            run_id=run.id,
            step_key="failed",
            attempt=1,
            status="failed",
            operation="procurement.create_purchase_request",
        )
    )
    await db_session.flush()
    db_session.add(
        AgentRunEvent(
            run_id=run.id,
            event_type="run_retry_scheduled",
            actor_type="system",
            payload_summary={"error": "password=synthetic-secret", "retry_count": 1},
        )
    )
    await db_session.flush()
    app = FastAPI()
    app.include_router(api.router, prefix="/agent")
    app.dependency_overrides[get_db] = lambda: db_session
    actor = [user]
    app.dependency_overrides[deps.get_current_user] = lambda: actor[0]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/agent/automation-runs/{run.id}/explanation")
        assert response.status_code == 200
        assert response.json()["data"]["trace_id"] == str(run.correlation_id)
        assert "人工核对" in response.json()["data"]["recovery"]
        assert "synthetic-secret" not in response.text
        assert response.json()["data"]["facts"][0]["step_key"] == "failed"
        detail = await client.get(f"/agent/automation-runs/{run.id}")
        assert detail.status_code == 200
        assert "synthetic-secret" not in detail.text
        events = await client.get(f"/agent/automation-runs/{run.id}/events")
        assert events.status_code == 200
        assert "synthetic-secret" not in events.text
        actor[0] = other
        assert (
            await client.get(f"/agent/automation-runs/{run.id}/explanation")
        ).status_code == 404


def test_old_grant_history_is_not_model_input() -> None:
    user = User(id=uuid4(), name="上下文验收", grant_version=3)
    legacy = AgentMessage(role="assistant", content="旧业务结果", message_metadata={})
    old = AgentMessage(
        role="assistant", content="撤权前结果", message_metadata={"grant_version": 2}
    )
    current = AgentMessage(
        role="user", content="当前问题", message_metadata={"grant_version": 3}
    )
    assert AgentService._authorized_history([legacy, old, current], user) == [current]


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["web", "feishu"])
async def test_rejected_confirmation_cancellation_survives_request_transaction(
    db_session: AsyncSession,
    source: str,
) -> None:
    await seed_menus(db_session)
    connection = await db_session.connection()
    ensure_agent_tools_registered()
    operation = f"procurement.acceptance_write_{uuid4().hex}"
    handler = AsyncMock()
    tool_registry.register(
        AgentToolSpec(
            name=operation,
            summary="验收写入",
            input_model=EmptyToolInput,
            handler=handler,
            module="procurement",
            page_keys=("purchasing:supplier",),
            write=True,
        )
    )
    try:
        async with AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as db:
            user = User(name="撤权确认验收", role="user", tenant_key="local")
            db.add(user)
            await db.flush()
            await AgentAccessScopeService().synchronize(db, user_id=user.id)
            settings = get_settings().model_copy(
                update={"AGENT_TOOL_TOKEN": "synthetic-service-token"}
            )
            trusted_subject, headers = await delegated_subject(
                db, settings, user, source
            )
            request = AgentToolExecuteRequest(
                operation=operation,
                subject=trusted_subject,
            )
            confirmation = AgentConfirmation(
                user_id=user.id,
                operation=operation,
                summary="撤权前确认",
                risk_level="medium",
                status="pending",
                request_payload=request.model_dump(mode="json"),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
            db.add(confirmation)
            await db.commit()
            app = FastAPI()
            app.include_router(api.router, prefix="/agent")

            async def transaction():
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

            app.dependency_overrides[get_db] = transaction
            app.dependency_overrides[deps.get_current_user] = lambda: user
            app.dependency_overrides[get_settings] = lambda: settings
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                if source == "web":
                    response = await client.post(
                        f"/agent/confirmations/{confirmation.id}/execute"
                    )
                else:
                    foreign = await client.post(
                        f"/agent/confirmations/{confirmation.id}/resolve",
                        json={
                            "choice": "allow",
                            "subject": {
                                **request.subject.model_dump(mode="json"),
                                "tenant_id": "foreign",
                            },
                        },
                        headers=headers,
                    )
                    assert foreign.status_code == 401
                    await db.refresh(confirmation)
                    assert confirmation.status == "pending"
                    response = await client.post(
                        f"/agent/confirmations/{confirmation.id}/resolve",
                        json={
                            "choice": "allow",
                            "subject": request.subject.model_dump(mode="json"),
                        },
                        headers=headers,
                    )
                assert response.status_code == 403
            await db.refresh(confirmation)
            assert confirmation.status == "cancelled"
            handler.assert_not_awaited()
    finally:
        tool_registry._tools.pop(operation)
