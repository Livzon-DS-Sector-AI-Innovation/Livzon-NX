import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import maintenance
from app.core.database import get_db
from app.core.exceptions import AppException
from app.modules.quality.api import read_mirror as quality_api
from app.modules.quality.api.read_mirror import MODELS
from app.modules.quality.models import (
    QualityFeishuReadField,
    QualityFeishuReadRecord,
    QualityFeishuReadResource,
    QualityFeishuReadSyncRun,
)
from app.platform.identity import deps, page_policy
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import EffectivePageGrantOut, PageDataScopeInput
from app.platform.integrations.feishu import read_mirror
from app.platform.integrations.feishu.read_mirror import ModuleFeishuReadMirrorService

pytestmark = pytest.mark.asyncio
pytest_plugins = ("tests.maintenance_fixtures",)


class LeaseStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.unavailable = False

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        assert ex == 1800 and nx
        if self.unavailable:
            raise RedisConnectionError("simulated outage")
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def eval(self, _script: str, count: int, key: str, value: str) -> int:
        assert count == 1
        if self.values.get(key) != value:
            return 0
        del self.values[key]
        return 1


class FeishuSample:
    def __init__(self, label: str = "sample") -> None:
        self.label = label
        self.entered = asyncio.Event()
        self.proceed = asyncio.Event()
        self.proceed.set()
        self.fail_second_page = False

    async def list_fields(self, _table: str, *, page_size: int) -> list[dict[str, str]]:
        assert page_size == 100
        return [{"field_id": "name", "field_name": "Name", "type": "text"}]

    async def search_records(
        self, _table: str, *, page_size: int, page_token: str | None
    ) -> dict[str, Any]:
        assert page_size == 500
        self.entered.set()
        await self.proceed.wait()
        if page_token and self.fail_second_page:
            raise RuntimeError(
                "unavailable page containing simulated sensitive details"
            )
        return {
            "total": 2,
            "items": [
                {
                    "record_id": "two" if page_token else "one",
                    "fields": {"Name": self.label},
                }
            ],
            "has_more": page_token is None,
            "page_token": "next" if page_token is None else None,
        }


@pytest.fixture
async def resource_id(
    mirror_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[UUID]:
    resource_id = uuid4()
    async with mirror_session_factory() as db:
        db.add(
            QualityFeishuReadResource(
                id=resource_id,
                source_root_id=uuid4(),
                app_token=f"fixture-{resource_id}",
                table_id="fixture",
                title="Fixture",
            )
        )
        await db.commit()
    try:
        yield resource_id
    finally:
        async with mirror_session_factory() as db:
            for model in (
                QualityFeishuReadField,
                QualityFeishuReadRecord,
                QualityFeishuReadSyncRun,
            ):
                await db.execute(delete(model).where(model.resource_id == resource_id))
            await db.execute(
                delete(QualityFeishuReadResource).where(
                    QualityFeishuReadResource.id == resource_id
                )
            )
            await db.commit()


@pytest.fixture
def leases(monkeypatch: pytest.MonkeyPatch) -> LeaseStore:
    instance = LeaseStore()
    monkeypatch.setattr(read_mirror, "redis_client", instance)
    return instance


def mirror(
    db: AsyncSession, sample: FeishuSample, monkeypatch: pytest.MonkeyPatch
) -> ModuleFeishuReadMirrorService:
    service = ModuleFeishuReadMirrorService(
        db, module_code="quality", app_id="fake", app_secret="fake", models=MODELS
    )
    monkeypatch.setattr(service, "_client", lambda _app_token: sample)
    return service


async def snapshot(
    db: AsyncSession, resource_id: UUID
) -> tuple[QualityFeishuReadResource, list[QualityFeishuReadRecord], list[str]]:
    resource = await db.get(QualityFeishuReadResource, resource_id)
    assert resource is not None
    records = await db.scalars(
        select(QualityFeishuReadRecord)
        .where(
            QualityFeishuReadRecord.resource_id == resource_id,
            QualityFeishuReadRecord.mirror_version == resource.active_mirror_version,
        )
        .order_by(QualityFeishuReadRecord.record_id)
    )
    statuses = await db.scalars(
        select(QualityFeishuReadSyncRun.status)
        .where(QualityFeishuReadSyncRun.resource_id == resource_id)
        .order_by(QualityFeishuReadSyncRun.started_at)
    )
    return resource, list(records), list(statuses)


async def test_duplicate_candidates_and_manual_lock(
    mirror_session_factory: async_sessionmaker[AsyncSession],
    resource_id: UUID,
    leases: LeaseStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    due_on = datetime.now(UTC).date()
    sample = FeishuSample()
    sample.proceed.clear()
    async with mirror_session_factory() as first, mirror_session_factory() as second:
        initial = mirror(first, sample, monkeypatch)
        contender = mirror(second, FeishuSample(), monkeypatch)
        async with asyncio.TaskGroup() as tasks:
            run = tasks.create_task(initial.sync_due_resource(resource_id, due_on))
            try:
                await asyncio.wait_for(sample.entered.wait(), timeout=5)
                assert await contender.sync_due_resource(resource_id, due_on) is None
                with pytest.raises(AppException, match="正在同步"):
                    await contender.sync_resource(resource_id)
            finally:
                sample.proceed.set()
        assert run.result() == {"resource_id": str(resource_id), "record_count": 2}
        assert await contender.sync_due_resource(resource_id, due_on) is None
    async with mirror_session_factory() as db:
        resource, records, runs = await snapshot(db, resource_id)
        assert resource.last_complete_sync_at is not None
        assert [(row.record_id, row.raw_fields, row.is_deleted) for row in records] == [
            ("one", {"Name": "sample"}, False),
            ("two", {"Name": "sample"}, False),
        ]
        assert runs == ["success"]
    assert leases.values == {}


async def test_expired_owner_cannot_overwrite_successor(
    mirror_session_factory: async_sessionmaker[AsyncSession],
    resource_id: UUID,
    leases: LeaseStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = FeishuSample("old")
    sample.proceed.clear()
    due_on = datetime.now(UTC).date()

    async def run_expired(service: ModuleFeishuReadMirrorService) -> None:
        with pytest.raises(AppException, match="失去资源锁"):
            await service.sync_due_resource(resource_id, due_on)

    async with mirror_session_factory() as first, mirror_session_factory() as second:
        stale = mirror(first, sample, monkeypatch)
        current = mirror(second, FeishuSample("new"), monkeypatch)
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(run_expired(stale))
            try:
                await asyncio.wait_for(sample.entered.wait(), timeout=5)
                leases.values.clear()
                result = await current.sync_due_resource(resource_id, due_on)
                assert result is not None and result["record_count"] == 2
            finally:
                sample.proceed.set()
    async with mirror_session_factory() as db:
        resource, records, runs = await snapshot(db, resource_id)
        assert resource.sync_status == "success"
        assert [row.raw_fields for row in records] == [{"Name": "new"}] * 2
        assert runs == ["failed", "success"]


async def test_failed_page_and_redis_outage_preserve_mirror_and_retry(
    mirror_session_factory: async_sessionmaker[AsyncSession],
    resource_id: UUID,
    leases: LeaseStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(UTC)
    async with mirror_session_factory() as db:
        await mirror(db, FeishuSample("baseline"), monkeypatch).sync_resource(
            resource_id
        )
        resource = await db.get(QualityFeishuReadResource, resource_id)
        assert resource is not None
        previous = today - timedelta(days=1)
        resource.last_complete_sync_at = previous
        await db.commit()

    async with mirror_session_factory() as db:
        sample = FeishuSample("replacement")
        sample.fail_second_page = True
        service = mirror(db, sample, monkeypatch)
        with pytest.raises(RuntimeError, match="unavailable page"):
            await service.sync_due_resource(resource_id, today.date())
        leases.unavailable = True
        with pytest.raises(RedisConnectionError):
            await service.sync_due_resource(resource_id, today.date())
    async with mirror_session_factory() as db:
        resource, records, runs = await snapshot(db, resource_id)
        assert resource.last_complete_sync_at == previous
        assert "simulated sensitive" not in (resource.sync_error or "")
        assert [row.raw_fields for row in records] == [{"Name": "baseline"}] * 2
        assert runs == ["success", "failed"]

    leases.unavailable = False
    async with mirror_session_factory() as db:
        result = await mirror(db, FeishuSample(), monkeypatch).sync_due_resource(
            resource_id, today.date()
        )
        assert result is not None and result["record_count"] == 2
    async with mirror_session_factory() as db:
        resource, records, runs = await snapshot(db, resource_id)
        assert resource.last_complete_sync_at is not None
        assert resource.last_complete_sync_at >= today
        assert [row.raw_fields for row in records] == [{"Name": "sample"}] * 2
        assert runs == ["success", "failed", "success"]


async def test_manual_sync_requires_configuration_action(
    mirror_session_factory: async_sessionmaker[AsyncSession],
    resource_id: UUID,
    leases: LeaseStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "quality:quality-settings"
    app = FastAPI()
    app.include_router(
        quality_api.router,
        prefix="/api/v1/quality",
        dependencies=[Depends(deps.require_module_view("quality"))],
    )
    user = SimpleNamespace(id=uuid4(), role="user")
    app.dependency_overrides[deps.get_current_user] = lambda: user
    app.dependency_overrides[deps.get_settings] = lambda: SimpleNamespace(
        effective_module_access_mode="all"
    )
    monkeypatch.setattr(
        page_policy,
        "_api_catalog_provider",
        lambda: page_policy.collect_http_route_catalog(app.routes),
    )
    grant = EffectivePageGrantOut(
        page_key=key,
        module_code="quality",
        permissions=["access", "operate"],
        sensitive_actions=[],
        data_scope=PageDataScopeInput(scope_type="not_applicable"),
        source="user",
    )
    effective_grants = AsyncMock(return_value=[grant])
    monkeypatch.setattr(PagePermissionService, "effective_grants", effective_grants)
    path = f"/api/v1/quality/feishu-read/resources/{resource_id}/sync"
    async with mirror_session_factory() as db:
        service = mirror(db, FeishuSample(), monkeypatch)
        app.dependency_overrides[get_db] = lambda: db
        make_service = AsyncMock(return_value=(service, None))
        monkeypatch.setattr(quality_api, "_service", make_service)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            denied = await client.post(path, headers={"X-Dazah-Page-Key": key})
            assert denied.status_code == 403
            make_service.assert_not_awaited()
            effective_grants.return_value = [
                grant.model_copy(update={"sensitive_actions": ["sync_config"]})
            ]
            allowed = await client.post(path, headers={"X-Dazah-Page-Key": key})
            assert allowed.status_code == 200, allowed.text
            assert allowed.json() == {
                "code": 200,
                "message": "success",
                "data": {"resource_id": str(resource_id), "record_count": 2},
                "meta": None,
            }


@pytest.mark.parametrize(
    "route,method,result",
    [
        ("resources/{id}/sync", "sync_resource", {}),
        ("roots/{id}/discover", "discover_root", []),
    ],
)
async def test_manual_mirror_work_pauses_until_release_resumes(
    isolated_redis, monkeypatch, route, method, result,
) -> None:
    app = FastAPI()
    app.include_router(quality_api.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[quality_api.get_current_user] = lambda: None
    entered, complete = asyncio.Event(), asyncio.Event()

    async def finish_work(*_args):
        entered.set()
        await complete.wait()
        return result

    work = AsyncMock(side_effect=finish_work)
    make_service = AsyncMock(return_value=(SimpleNamespace(**{method: work}), None))
    monkeypatch.setattr(quality_api, "_service", make_service)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = "/feishu-read/" + route.format(id=uuid4())
        existing = asyncio.create_task(client.post(path))
        try:
            await asyncio.wait_for(entered.wait(), timeout=3)
            assert await maintenance.pause_background_work("release", 60)
            report = await maintenance.release_preflight("release")
            assert report["activities"]["sync"]["count"] == 1
            paused = await client.post(path)
            assert paused.status_code == 409
            assert "X-Dazah-Maintenance" not in paused.headers
            make_service.assert_awaited_once()
        finally:
            complete.set()
            finished = await existing
        assert finished.status_code == 200
        assert (await maintenance.release_preflight("release"))["blocking"] == 0

        await maintenance.resume_background_work("release")
        served = await client.post(path)
        assert served.status_code == 200
        assert work.await_count == 2
