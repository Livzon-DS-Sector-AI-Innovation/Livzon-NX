"""Shared batch ownership is independent of the production-line display label."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.production.models import Batch
from app.modules.production.repository import ProductionRepository
from app.platform.identity.data_scope import current_page_actor, current_page_key


@pytest.mark.asyncio
async def test_workshop_repository_filters_list_detail_and_mutation(db_session):
    own = Batch(
        batch_no=f"SCOPE-{uuid4()}",
        product_code="TEST",
        workshop_code="101-1",
        production_line="A线",
    )
    outside = Batch(
        batch_no=f"SCOPE-{uuid4()}",
        product_code="TEST",
        workshop_code="201-3",
        production_line="A线",
    )
    unknown = Batch(
        batch_no=f"SCOPE-{uuid4()}", product_code="TEST", workshop_code=None
    )
    db_session.add_all([own, outside, unknown])
    await db_session.flush()
    actor = current_page_actor.set(SimpleNamespace(id=uuid4(), role="user"))
    page = current_page_key.set("production:batches:workshop-101-1")
    try:
        repo = ProductionRepository(db_session)
        rows, total = await repo.get_batches(batch_no="SCOPE-", limit=100)
        assert {row.id for row in rows} == {own.id}
        assert total == 1
        assert await repo.get_batch_by_id(own.id) is own
        assert await repo.get_batch_by_id(outside.id) is None
        assert await repo.get_batch_by_id(unknown.id) is None
        assert await repo.update_batch(outside.id, {"notes": "unauthorized"}) is None
        assert not await repo.delete_batch(outside.id)
        assert outside.notes is None
        assert not outside.is_deleted
        current_page_key.set("production:overview")
        rows, total = await repo.get_batches(batch_no="SCOPE-", limit=100)
        assert {row.id for row in rows} == {own.id, outside.id, unknown.id}
        assert total == 3
    finally:
        current_page_key.reset(page)
        current_page_actor.reset(actor)


@pytest.mark.asyncio
async def test_real_batch_routes_deny_foreign_detail_and_creation(
    monkeypatch, db_session
):
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.modules.production import api
    from tests.modules.production.test_page_permission_acceptance import acceptance_app

    outside = Batch(
        batch_no=f"SCOPE-{uuid4()}", product_code="TEST", workshop_code="201-3"
    )
    db_session.add(outside)
    await db_session.flush()
    key = "production:batches:workshop-101-1"
    app, _ = acceptance_app(api.router, monkeypatch, key)
    app.dependency_overrides[get_db] = lambda: db_session
    monkeypatch.setattr(db_session, "commit", AsyncMock())
    actor = current_page_actor.set(None)
    page = current_page_key.set(None)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Dazah-Page-Key": key},
        ) as client:
            denied = await client.get(f"/api/v1/production/batches/{outside.id}")
            assert denied.status_code == 404
            denied = await client.post(
                "/api/v1/production/batches",
                json={
                    "batch_no": f"SCOPE-{uuid4()}",
                    "product_code": "TEST",
                    "workshop_code": "201-3",
                },
            )
            assert denied.status_code == 403
            db_session.commit.assert_not_awaited()
            created = await client.post(
                "/api/v1/production/batches",
                json={
                    "batch_no": f"SCOPE-{uuid4()}",
                    "product_code": "TEST",
                    "production_line": "A线",
                },
            )
            assert created.status_code == 200
            assert created.json()["data"]["workshop_code"] == "101-1"
            assert created.json()["data"]["production_line"] == "A线"
            db_session.commit.assert_awaited_once()
    finally:
        current_page_key.reset(page)
        current_page_actor.reset(actor)


@pytest.mark.asyncio
async def test_overview_query_does_not_authorize_cross_workshop_writes(monkeypatch):
    from app.modules.production.batch_scope import allowed_batch_workshops
    from app.platform.identity.page_permissions import PagePermissionService

    actor = current_page_actor.set(SimpleNamespace(id=uuid4(), role="user"))
    page = current_page_key.set("production:overview")
    monkeypatch.setattr(
        PagePermissionService, "effective_grants", AsyncMock(return_value=[])
    )
    try:
        assert await allowed_batch_workshops(AsyncMock()) is None
        assert await allowed_batch_workshops(AsyncMock(), write=True) == frozenset()
    finally:
        current_page_key.reset(page)
        current_page_actor.reset(actor)
