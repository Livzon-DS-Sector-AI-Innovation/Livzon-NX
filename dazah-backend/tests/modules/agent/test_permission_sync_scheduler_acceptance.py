"""Run the real scheduler loop against isolated PostgreSQL savepoints."""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.agent import scheduled
from app.modules.agent.models import AgentAccessScopeSnapshot
from app.modules.agent.scheduled import AgentAccessScopeSyncGenerator
from app.platform.identity.models import PermissionOutboxEvent, User, UserPageGrant
from app.platform.identity.rbac import seed_menus
from app.platform.scheduler import engine as engine_module


@pytest.mark.asyncio
async def test_scheduler_commits_page_permission_sync_and_revocation(
    db_session, monkeypatch
):
    connection = await db_session.connection()
    factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    user_id = uuid4()
    async with factory() as setup:
        await seed_menus(setup)
        setup.add(
            User(id=user_id, name="后台同步隔离验收", role="user", grant_version=1)
        )
        setup.add(
            UserPageGrant(
                user_id=user_id,
                page_key="purchasing:supplier",
                permissions=["access", "query"],
                sensitive_actions=[],
                scope_type="all",
                department_ids=[],
            )
        )
        setup.add(
            PermissionOutboxEvent(
                user_id=user_id,
                grant_version=1,
                event_type="identity.user_page_grants.changed.v1",
                payload={},
                status="pending",
            )
        )
        await setup.commit()

    # Only the Redis admission boundary is faked; scanning, grants, version
    # checks, engine lifecycle and transaction commits use production code.
    @asynccontextmanager
    async def admission(kind):
        yield

    monkeypatch.setattr(engine_module, "business_activity", admission)
    generator = AgentAccessScopeSyncGenerator(batch_size=10000)
    original_scan = generator.find_due

    async def isolated_scan(session):
        return [
            event for event in await original_scan(session) if event.user_id == user_id
        ]

    monkeypatch.setattr(generator, "find_due", isolated_scan)
    monkeypatch.setattr(scheduled, "AgentAccessScopeSyncGenerator", lambda: generator)

    async def run_one_cycle():
        completed = asyncio.Event()

        @asynccontextmanager
        async def scheduler_session():
            async with factory() as session:
                yield session
            completed.set()

        monkeypatch.setattr(engine_module, "async_session_factory", scheduler_session)
        engine = scheduled.create_access_scope_sync_engine()
        task = asyncio.create_task(engine.run())
        try:
            await asyncio.wait_for(completed.wait(), timeout=10)
        finally:
            engine.stop()
            await asyncio.wait_for(task, timeout=10)

    await run_one_cycle()
    async with factory() as check:
        snapshot = await check.scalar(
            select(AgentAccessScopeSnapshot).where(
                AgentAccessScopeSnapshot.user_id == user_id
            )
        )
        assert snapshot.source_grant_version == 1
        assert snapshot.sync_status == "synced"
        assert "analytics.aggregate" in snapshot.tool_names
        event = await check.scalar(
            select(PermissionOutboxEvent).where(
                PermissionOutboxEvent.user_id == user_id
            )
        )
        assert event.status == "processed"
        assert event.processed_at is not None
        user = await check.get(User, user_id)
        user.grant_version = 2
        grant = await check.scalar(
            select(UserPageGrant).where(UserPageGrant.user_id == user_id)
        )
        grant.permissions = []
        check.add(
            PermissionOutboxEvent(
                user_id=user_id,
                grant_version=2,
                event_type="identity.user_page_grants.changed.v1",
                payload={},
                status="pending",
            )
        )
        await check.commit()
    await run_one_cycle()
    async with factory() as check:
        snapshot = await check.scalar(
            select(AgentAccessScopeSnapshot).where(
                AgentAccessScopeSnapshot.user_id == user_id
            )
        )
        assert snapshot.source_grant_version == 2
        assert "analytics.aggregate" not in snapshot.tool_names
        events = (
            await check.scalars(
                select(PermissionOutboxEvent).where(
                    PermissionOutboxEvent.user_id == user_id
                )
            )
        ).all()
        assert len(events) == 2
        assert all(
            event.status == "processed" and event.processed_at is not None
            for event in events
        )
