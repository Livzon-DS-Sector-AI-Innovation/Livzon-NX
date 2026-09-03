"""Real SQL/API tests for authorization transactions, revocation and lifecycle."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_db
from app.platform.audit.models import AuditLog
from app.platform.identity import api, deps, page_permissions, page_policy, rbac_api
from app.platform.identity.models import (
    Menu,
    PermissionModuleRollout,
    PermissionOutboxEvent,
    Role,
    User,
    UserPageGrant,
    UserRole,
)
from app.platform.identity.page_permission_repository import (
    ActiveMenuPage,
    PagePermissionRepository,
)
from app.platform.identity.permission_repository import PermissionGrantRepository


def application(db_provider, actor_provider, monkeypatch):
    app = FastAPI()
    app.include_router(rbac_api.rbac_router, prefix="/identity")
    app.include_router(api.user_router, prefix="/identity")
    app.dependency_overrides[get_db] = db_provider
    app.dependency_overrides[deps.get_current_user] = actor_provider
    monkeypatch.setattr(rbac_api, "publish_permissions_changed", AsyncMock())
    monkeypatch.setattr(rbac_api, "publish_permissions_changed_all", AsyncMock())
    monkeypatch.setattr(api, "publish_permissions_changed", AsyncMock())
    monkeypatch.setattr(api, "publish_data_scope_changed", AsyncMock())
    return app


@pytest.mark.asyncio
async def test_legacy_role_paths_cannot_self_elevate_and_deletion_expires_versions(
    db_session, monkeypatch
):
    async with AsyncSession(
        bind=await db_session.connection(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        actor = User(name="受委托权限经办人", role="user")
        target = User(name="撤权目标用户", role="user")
        role = Role(name="核心角色撤销测试", code=uuid4().hex)
        db.add_all([actor, target, role])
        await db.flush()
        db.add_all(
            [
                UserRole(user_id=actor.id, role_id=role.id, source="manual"),
                UserRole(user_id=target.id, role_id=role.id, source="manual"),
            ]
        )
        await db.flush()
        monkeypatch.setattr(
            rbac_api,
            "resolve_user_permissions",
            AsyncMock(return_value=["identity:admin"]),
        )
        app = application(lambda: db, lambda: actor, monkeypatch)
        url = f"/identity/admin/roles/{role.id}"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (
                await client.post(url + "/permissions", json={"permission_ids": []})
            ).status_code == 403
            assert (
                await client.put(url + "/menus", json={"menu_ids": []})
            ).status_code == 403
            assert (await client.delete(url)).status_code == 403
            actor.role = "admin"
            await db.flush()
            version = target.grant_version
            result = await client.delete(url)
            assert result.status_code == 200, result.text
            assert target.grant_version == version + 1
            event = await db.scalar(
                select(PermissionOutboxEvent).where(
                    PermissionOutboxEvent.user_id == target.id
                )
            )
            assert event.grant_version == target.grant_version
            assert not await rbac_api.resolve_user_roles(db, target.id)


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_grants_version_and_outbox(
    db_session, monkeypatch
):
    connection = await db_session.connection()
    actor = User(name="授权事务管理员", role="admin")
    target = User(name="授权事务用户", role="user")
    db_session.add_all([actor, target])
    await db_session.flush()
    target_id = target.id
    version = target.grant_version
    db_session.add(
        UserPageGrant(
            user_id=target_id,
            page_key="hr:recruitment",
            permissions=["access", "query"],
        )
    )
    await db_session.flush()
    from app.core import database as database_module

    monkeypatch.setattr(
        database_module,
        "async_session_factory",
        async_sessionmaker(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ),
    )
    app = application(get_db, lambda: actor, monkeypatch)
    monkeypatch.setattr(
        rbac_api, "_audit", AsyncMock(side_effect=RuntimeError("audit unavailable"))
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.put(
            f"/identity/admin/users/{target_id}/page-permissions",
            json={
                "expected_grant_version": version,
                "reason": "测试审计失败回滚",
                "grants": [],
            },
        )
        assert response.status_code == 500
    await db_session.refresh(target)
    assert target.grant_version == version
    retained = await db_session.scalar(
        select(UserPageGrant).where(UserPageGrant.user_id == target_id)
    )
    assert retained.permissions == ["access", "query"]
    assert not await db_session.scalar(
        select(PermissionOutboxEvent).where(PermissionOutboxEvent.user_id == target_id)
    )
    assert not await db_session.scalar(
        select(AuditLog).where(AuditLog.resource_id == target_id)
    )
    rbac_api.publish_permissions_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_locking_reads_refresh_stale_identity_map(db_session):
    user = User(name="核心版本测试", role="user")
    role = Role(name="核心版本角色", code=uuid4().hex)
    rollout = PermissionModuleRollout(module_code="test-" + uuid4().hex)
    db_session.add_all([user, role, rollout])
    await db_session.flush()
    for model, obj, column in [
        (User, user, "grant_version"),
        (Role, role, "grant_version"),
        (PermissionModuleRollout, rollout, "version"),
    ]:
        await db_session.execute(
            update(model)
            .where(model.id == obj.id)
            .values({column: 40})
            .execution_options(synchronize_session=False)
        )
        assert getattr(obj, column) != 40
    assert (
        await PermissionGrantRepository().get_user_for_update(db_session, user.id)
    ).grant_version == 40
    assert (
        await PagePermissionRepository().get_role_for_update(
            db_session, role_id=role.id
        )
    ).grant_version == 40
    assert (
        await PagePermissionRepository().get_rollout(
            db_session, module_code=rollout.module_code, for_update=True
        )
    ).version == 40
    users = await PagePermissionRepository().bump_active_user_versions(
        db_session, actor_id=user.id
    )
    assert next(item for item in users if item.id == user.id).grant_version == 41


@pytest.mark.asyncio
async def test_menu_key_is_immutable_and_deleted_key_cannot_be_recreated(
    db_session, monkeypatch
):
    async with AsyncSession(
        bind=await db_session.connection(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        actor = User(name="生命周期管理员", role="admin")
        db.add(actor)
        await db.flush()
        app = application(lambda: db, lambda: actor, monkeypatch)
        body = {
            "key": "test:" + uuid4().hex,
            "name": "待退役页面",
            "type": "menu",
            "route_path": "/test-lifecycle",
        }
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/identity/admin/menus", json=body)
            assert response.status_code == 200, response.text
            menu_id = response.json()["data"]["id"]
            url = f"/identity/admin/menus/{menu_id}"
            assert (
                await client.put(url, json={"key": body["key"] + "-new"})
            ).status_code == 409
            assert (await client.put(url, json={"name": "中文改名"})).status_code == 200
            assert (
                await client.put(url, json={"status": "disabled"})
            ).status_code == 200
            assert (await client.put(url, json={"status": "active"})).status_code == 200
            assert (await client.delete(url)).status_code == 200
            assert (
                await client.post("/identity/admin/menus", json=body)
            ).status_code == 409
            row = await db.scalar(select(Menu).where(Menu.key == body["key"]))
            assert row.is_deleted


@pytest.mark.asyncio
async def test_parallel_grant_writes_and_queued_actor_revocation(
    db_session, monkeypatch
):
    # This test needs independent committed connections; cleanup is restricted to
    # these generated test identities, never application/development identities.
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    actor_id, user_id = uuid4(), uuid4()
    try:
        async with factory() as seed:
            seed.add_all(
                [
                    User(id=actor_id, name="并发授权管理员", role="admin"),
                    User(id=user_id, name="并发授权经办人", role="user"),
                ]
            )
            await seed.commit()

        async def database():
            async with factory() as session:
                yield session

        async def actor():
            async with factory() as session:
                return await session.get(User, actor_id)

        app = application(database, actor, monkeypatch)
        async with factory() as read:
            version = (await read.get(User, user_id)).grant_version
        url = f"/identity/admin/users/{user_id}/page-permissions"
        body = {
            "expected_grant_version": version,
            "reason": "并发替换验证",
            "grants": [],
        }
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first, second = await asyncio.wait_for(
                asyncio.gather(client.put(url, json=body), client.put(url, json=body)),
                timeout=10,
            )
            assert sorted([first.status_code, second.status_code]) == [200, 409]
            async with factory() as read:
                assert (await read.get(User, user_id)).grant_version == version + 1
                events = (
                    await read.scalars(
                        select(PermissionOutboxEvent).where(
                            PermissionOutboxEvent.user_id == user_id
                        )
                    )
                ).all()
                assert len(events) == 1
            # An authenticated object held before demotion must not authorize a
            # subsequent write after waiting for the administrative lock.
            old_actor = await actor()
            app.dependency_overrides[deps.get_current_user] = lambda: old_actor
            async with factory() as demote:
                await demote.execute(
                    update(User).where(User.id == actor_id).values(role="user")
                )
                await demote.commit()
            rejected = await client.put(
                url, json={**body, "expected_grant_version": version + 1}
            )
            assert rejected.status_code == 403, rejected.text
            async with factory() as promote:
                await promote.execute(
                    update(User)
                    .where(User.id.in_([actor_id, user_id]))
                    .values(role="admin")
                )
                await promote.commit()

            async def selected_actor(request: Request):
                async with factory() as session:
                    return await session.get(
                        User,
                        actor_id
                        if request.headers.get("x-test-actor") == "first"
                        else user_id,
                    )

            app.dependency_overrides[deps.get_current_user] = selected_actor
            results = await asyncio.wait_for(
                asyncio.gather(
                    client.put(
                        f"/identity/users/{user_id}",
                        json={"role": "user"},
                        headers={"x-test-actor": "first"},
                    ),
                    client.put(
                        f"/identity/users/{actor_id}",
                        json={"role": "user"},
                        headers={"x-test-actor": "second"},
                    ),
                ),
                timeout=10,
            )
            assert sorted(result.status_code for result in results) == [200, 403]
            async with factory() as read:
                remaining = (
                    await read.scalars(
                        select(User).where(
                            User.id.in_([actor_id, user_id]), User.role == "admin"
                        )
                    )
                ).all()
                assert len(remaining) == 1
    finally:
        async with factory() as cleanup:
            await cleanup.execute(
                delete(UserPageGrant).where(
                    UserPageGrant.user_id.in_([actor_id, user_id])
                )
            )
            await cleanup.execute(
                delete(PermissionOutboxEvent).where(
                    PermissionOutboxEvent.user_id.in_([actor_id, user_id])
                )
            )
            await cleanup.execute(
                delete(AuditLog).where(AuditLog.user_id.in_([actor_id, user_id]))
            )
            await cleanup.execute(delete(User).where(User.id.in_([actor_id, user_id])))
            await cleanup.commit()


@pytest.mark.asyncio
async def test_publish_rechecks_grants_then_rollback_preserves_authorization_facts(
    db_session, monkeypatch
):
    async with AsyncSession(
        bind=await db_session.connection(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        actor = User(name="发布核心管理员", role="admin")
        target = User(name="发布核心用户", role="user")
        db.add_all([actor, target])
        await db.flush()
        # Catalog business coverage is intentionally outside this core test.
        monkeypatch.setattr(page_permissions, "page_api_catalog_gaps", lambda _: [])
        monkeypatch.setattr(page_permissions, "tool_page_bindings", lambda: [])
        monkeypatch.setattr(
            PagePermissionRepository,
            "active_page_keys",
            AsyncMock(return_value=set(page_policy.PAGES_BY_KEY)),
        )
        monkeypatch.setattr(
            PagePermissionRepository,
            "active_menu_page_catalog",
            AsyncMock(
                return_value=[
                    ActiveMenuPage(
                        key=page.page_key,
                        name=page.page_name,
                        route_path=page.route_path,
                        root_key=page.page_key.split(":", 1)[0],
                    )
                    for page in page_policy.PAGE_DEFINITIONS
                ]
            ),
        )
        app = application(lambda: db, lambda: actor, monkeypatch)
        root = "/identity/admin/page-permissions/modules/hr"
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            preview = (await client.get(root + "/preview")).json()["data"]
            body = {
                "expected_version": preview["current_version"],
                "preview_hash": preview["preview_hash"],
                "reason": "核心发布事务验证",
                "confirmed": True,
            }
            response = await client.put(
                f"/identity/admin/users/{target.id}/page-permissions",
                json={
                    "expected_grant_version": target.grant_version,
                    "reason": "发布前权限变化",
                    "grants": [],
                },
            )
            assert response.status_code == 200, response.text
            assert (await client.post(root + "/publish", json=body)).status_code == 409
            preview = (await client.get(root + "/preview")).json()["data"]
            body.update(
                expected_version=preview["current_version"],
                preview_hash=preview["preview_hash"],
            )
            published = await client.post(root + "/publish", json=body)
            assert published.status_code == 200, published.text
            assert published.json()["data"]["status"] == "enforced"
            assert (await client.post(root + "/publish", json=body)).status_code == 409
            version = published.json()["data"]["version"]
            assert (
                await client.post(
                    root + "/rollback",
                    json={
                        "expected_version": version - 1,
                        "reason": "过期回退测试",
                        "confirmed": True,
                    },
                )
            ).status_code == 409
            response = await client.post(
                root + "/rollback",
                json={
                    "expected_version": version,
                    "reason": "核心回退验证",
                    "confirmed": True,
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["data"]["status"] == "legacy"
            assert response.json()["data"]["version"] == version + 1
            assert not (
                await PagePermissionRepository().list_user_grants(db, user_id=target.id)
            )
            events = (
                await db.scalars(
                    select(PermissionOutboxEvent).where(
                        PermissionOutboxEvent.user_id == target.id
                    )
                )
            ).all()
            assert len(events) == 3
            assert len({event.grant_version for event in events}) == 3
            logs = (
                await db.scalars(select(AuditLog).where(AuditLog.user_id == actor.id))
            ).all()
            assert {log.action for log in logs} >= {
                "publish_page_permission_module",
                "rollback_page_permission_module",
            }
