"""Failure and recovery tests for the reusable Feishu read mirror."""

from datetime import UTC, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.platform.integrations.feishu import read_mirror
from app.platform.integrations.feishu.read_mirror import (
    ModuleFeishuReadMirrorService,
)
from app.platform.integrations.feishu.read_scheduler import PRODUCTION_MODELS

SimpleNamespace: Any = _SimpleNamespace


def _session(**overrides: Any) -> Any:
    values = {
        "execute": AsyncMock(),
        "scalar": AsyncMock(),
        "commit": AsyncMock(),
        "rollback": AsyncMock(),
        "refresh": AsyncMock(),
        "flush": AsyncMock(),
        "add": lambda _value: None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service(
    session: Any = None, *, app_id: Any = "app", app_secret: Any = "secret"
) -> Any:
    return ModuleFeishuReadMirrorService(
        session or _session(),
        module_code="production",
        app_id=app_id,
        app_secret=app_secret,
        models=PRODUCTION_MODELS,
    )


@pytest.mark.asyncio
async def test_read_mirror_lists_roots_and_resources() -> None:
    result: Any = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: ["one", "two"])
    )
    session = _session(execute=AsyncMock(return_value=result))
    service = _service(session)
    assert await service.list_roots(uuid4()) == ["one", "two"]
    assert await service.list_resources() == ["one", "two"]


@pytest.mark.asyncio
async def test_create_root_rejects_invalid_and_duplicate_inputs(
    monkeypatch: Any,
) -> None:
    service = _service()
    with pytest.raises(AppException, match="wiki"):
        await service.create_root(
            config_id=uuid4(),
            name="",
            source_type="sheet",
            source_url="invalid",
        )

    monkeypatch.setattr(
        read_mirror,
        "parse_feishu_root_token",
        lambda *_args: (_ for _ in ()).throw(ValueError("bad URL")),
    )
    with pytest.raises(AppException, match="bad URL"):
        await service.create_root(
            config_id=uuid4(),
            name="",
            source_type="wiki",
            source_url="invalid",
        )

    monkeypatch.setattr(read_mirror, "parse_feishu_root_token", lambda *_args: "token")
    existing: Any = SimpleNamespace(is_deleted=False)
    service.session.scalar.return_value = existing
    with pytest.raises(AppException, match="已存在"):
        await service.create_root(
            config_id=uuid4(),
            name="入口",
            source_type="base",
            source_url="url",
        )


@pytest.mark.asyncio
async def test_create_root_restores_deleted_and_creates_new(monkeypatch: Any) -> None:
    monkeypatch.setattr(read_mirror, "parse_feishu_root_token", lambda *_args: "token")
    deleted: Any = SimpleNamespace(
        is_deleted=True,
        name="旧名",
        source_url="old",
        is_active=False,
        discovery_status="failed",
        discovery_error="old error",
    )
    session = _session(scalar=AsyncMock(side_effect=[deleted, None]))
    added: list[Any] = []
    session.add = added.append
    service = _service(session)

    restored = await service.create_root(
        config_id=uuid4(),
        name="新入口",
        source_type="base",
        source_url=" url ",
    )
    assert restored is deleted
    assert restored.is_deleted is False
    assert restored.discovery_status == "pending"

    created = await service.create_root(
        config_id=uuid4(),
        name="",
        source_type="base",
        source_url="url",
    )
    assert created.name == "token"
    assert added == [created]
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_delete_root_marks_it_inactive(monkeypatch: Any) -> None:
    root: Any = SimpleNamespace(is_deleted=False, is_active=True)
    service = _service()
    monkeypatch.setattr(service, "_root", AsyncMock(return_value=root))
    await service.delete_root(uuid4())
    assert root.is_deleted is True
    assert root.is_active is False


@pytest.mark.asyncio
async def test_discover_root_handles_tables_and_skips_malformed_items(
    monkeypatch: Any,
) -> None:
    root: Any = SimpleNamespace(
        source_type="base",
        root_token="app-token",
        name="入口",
        discovery_status="pending",
        discovery_error="old",
        last_discovered_at=None,
    )
    client: Any = SimpleNamespace(
        list_tables=AsyncMock(
            return_value=[
                {"table_id": "table", "name": "数据表"},
                {"name": "missing id"},
            ]
        )
    )
    service = _service()
    monkeypatch.setattr(service, "_root", AsyncMock(return_value=root))
    monkeypatch.setattr(service, "_client", lambda _token: client)
    upsert: Any = AsyncMock(return_value="resource")
    monkeypatch.setattr(service, "_upsert_resource", upsert)

    assert await service.discover_root(uuid4()) == ["resource"]
    assert root.discovery_status == "success"
    assert root.last_discovered_at is not None


@pytest.mark.asyncio
async def test_discover_root_records_sanitized_failure(monkeypatch: Any) -> None:
    root: Any = SimpleNamespace(
        source_type="wiki",
        root_token="wiki",
        discovery_status="pending",
        discovery_error=None,
    )
    service = _service()
    monkeypatch.setattr(service, "_root", AsyncMock(return_value=root))
    monkeypatch.setattr(
        service,
        "_client",
        lambda _token: (_ for _ in ()).throw(
            RuntimeError("Bearer sensitive-token unavailable")
        ),
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        await service.discover_root(uuid4())
    assert root.discovery_status == "failed"
    assert root.discovery_error == "Bearer ***sensitive-token unavailable"
    service.session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_resource_lock_conflict_and_release(monkeypatch: Any) -> None:
    service = _service()
    monkeypatch.setattr(read_mirror.redis_client, "set", AsyncMock(return_value=False))  # type: ignore[attr-defined]
    with pytest.raises(AppException, match="正在同步"):
        await service.sync_resource(uuid4())

    monkeypatch.setattr(read_mirror.redis_client, "set", AsyncMock(return_value=True))  # type: ignore[attr-defined]
    release: Any = AsyncMock()
    monkeypatch.setattr(read_mirror.redis_client, "eval", release)  # type: ignore[attr-defined]
    monkeypatch.setattr(
        service,
        "_sync_resource_locked",
        AsyncMock(side_effect=RuntimeError("sync failed")),
    )
    with pytest.raises(RuntimeError, match="sync failed"):
        await service.sync_resource(uuid4())
    release.assert_awaited_once()


@pytest.mark.asyncio
async def test_locked_sync_paginates_deduplicates_and_commits(
    monkeypatch: Any,
) -> None:
    resource: Any = SimpleNamespace(
        id=uuid4(),
        app_token="app-token",
        table_id="table",
        sync_status="pending",
        sync_error="old",
        schema_hash=None,
        active_mirror_version=None,
        last_complete_sync_at=None,
    )
    client: Any = SimpleNamespace(
        list_fields=AsyncMock(
            return_value=[{"field_id": "field", "field_name": "名称"}]
        ),
        search_records=AsyncMock(
            side_effect=[
                {
                    "total": 2,
                    "items": [
                        {
                            "record_id": "one",
                            "fields": {"名称": "A"},
                            "created_time": 1_767_225_600_000,
                        }
                    ],
                    "has_more": True,
                    "page_token": "next",
                },
                {
                    "total": 2,
                    "items": [
                        {"record_id": "one", "fields": {"名称": "duplicate"}},
                        {
                            "record_id": "two",
                            "fields": {"名称": "B"},
                            "last_modified_time": 1_767_225_600_000,
                        },
                    ],
                    "has_more": False,
                },
            ]
        ),
    )
    added: list[Any] = []
    session = _session()
    session.add = added.append
    service = _service(session)
    monkeypatch.setattr(service, "_resource", AsyncMock(return_value=resource))
    monkeypatch.setattr(service, "_client", lambda _token: client)
    monkeypatch.setattr(
        service,
        "_replace_fields",
        AsyncMock(return_value=[SimpleNamespace(field_id="field", field_name="名称")]),
    )

    result = await service._sync_resource_locked(resource.id)
    assert result == {"resource_id": str(resource.id), "record_count": 2}
    assert resource.sync_status == "success"
    assert resource.schema_hash
    assert len(added) == 3
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_locked_sync_records_incomplete_page_failure(monkeypatch: Any) -> None:
    resource: Any = SimpleNamespace(
        id=uuid4(),
        app_token="app-token",
        table_id="table",
        sync_status="pending",
        sync_error=None,
    )
    failed_run: Any = SimpleNamespace(
        status="running",
        error_message=None,
        completed_at=None,
    )
    session = _session(get=AsyncMock(return_value=failed_run))
    service = _service(session)
    monkeypatch.setattr(service, "_resource", AsyncMock(return_value=resource))
    monkeypatch.setattr(
        service,
        "_client",
        lambda _token: SimpleNamespace(
            list_fields=AsyncMock(return_value=[]),
            search_records=AsyncMock(
                return_value={
                    "items": [],
                    "has_more": True,
                    "page_token": "",
                }
            ),
        ),
    )
    monkeypatch.setattr(service, "_replace_fields", AsyncMock(return_value=[]))

    with pytest.raises(RuntimeError, match="分页链"):
        await service._sync_resource_locked(resource.id)
    assert resource.sync_status == "failed"
    assert failed_run.status == "failed"
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_replace_bindings_updates_creates_and_rejects_duplicates(
    monkeypatch: Any,
) -> None:
    existing_resource_id = uuid4()
    new_resource_id = uuid4()
    existing_binding: Any = SimpleNamespace(
        resource_id=existing_resource_id,
        is_enabled=True,
        tab_name="旧",
        sort_order=5,
        is_default=False,
        visible_field_ids=[],
    )
    result: Any = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [existing_binding])
    )
    added: list[Any] = []
    session = _session(execute=AsyncMock(return_value=result))
    session.add = added.append
    service = _service(session)
    resources = {
        existing_resource_id: SimpleNamespace(
            id=existing_resource_id,
            title="现有资源",
        ),
        new_resource_id: SimpleNamespace(
            id=new_resource_id,
            title="新资源",
        ),
    }
    monkeypatch.setattr(
        service,
        "_resource",
        AsyncMock(side_effect=lambda resource_id: resources[resource_id]),
    )
    monkeypatch.setattr(
        service,
        "page_data",
        AsyncMock(return_value={"page_key": "page", "bindings": []}),
    )

    payload = await service.replace_bindings(
        "page",
        [
            {
                "resource_id": existing_resource_id,
                "tab_name": "更新",
                "is_enabled": True,
            },
            {"resource_id": new_resource_id},
        ],
    )
    assert payload["page_key"] == "page"
    assert existing_binding.tab_name == "更新"
    assert len(added) == 1

    with pytest.raises(AppException, match="重复绑定"):
        await service.replace_bindings(
            "page",
            [
                {"resource_id": existing_resource_id},
                {"resource_id": existing_resource_id},
            ],
        )


@pytest.mark.asyncio
async def test_page_data_and_empty_page_records(monkeypatch: Any) -> None:
    binding: Any = SimpleNamespace(id=uuid4())
    resource: Any = SimpleNamespace(
        id=uuid4(),
        active_mirror_version=None,
    )
    rows: Any = SimpleNamespace(all=lambda: [(binding, resource)])
    session = _session(execute=AsyncMock(return_value=rows))
    service = _service(session)
    monkeypatch.setattr(
        service,
        "_binding_payload",
        AsyncMock(return_value={"id": str(binding.id)}),
    )
    assert (await service.page_data("page"))["bindings"] == [{"id": str(binding.id)}]

    monkeypatch.setattr(
        service,
        "_bound_resource",
        AsyncMock(return_value=(binding, resource)),
    )
    monkeypatch.setattr(
        service,
        "_fields",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    field_id="field",
                    field_name="名称",
                    field_type="1",
                    property={},
                    sort_order=0,
                )
            ]
        ),
    )
    result = await service.page_records(
        page_key="page",
        binding_id=binding.id,
        page=1,
        page_size=20,
        keyword="ignored",
    )
    assert result["records"] == []
    assert result["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_replace_fields_updates_creates_and_soft_deletes() -> None:
    retained: Any = SimpleNamespace(
        field_id="keep",
        field_name="旧",
        field_type="1",
        property={},
        sort_order=9,
        is_deleted=True,
    )
    removed: Any = SimpleNamespace(field_id="remove", is_deleted=False)
    result: Any = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [retained, removed])
    )
    added: list[Any] = []
    session = _session(execute=AsyncMock(return_value=result))
    session.add = added.append
    service = _service(session)

    fields = await service._replace_fields(
        uuid4(),
        [
            {"field_id": "", "name": "ignored"},
            {
                "field_id": "keep",
                "field_name": "新",
                "type": 2,
                "property": {"format": "number"},
            },
            {"field_id": "new", "field_name": "新增", "property": "invalid"},
        ],
    )
    assert len(fields) == 2
    assert retained.field_name == "新"
    assert retained.is_deleted is False
    assert removed.is_deleted is True
    assert len(added) == 1


@pytest.mark.asyncio
async def test_upsert_resource_handles_create_and_update() -> None:
    root: Any = SimpleNamespace(id=uuid4())
    existing: Any = SimpleNamespace(
        source_root_id=None,
        title="旧名",
        source_path=[],
    )
    added: list[Any] = []
    session = _session(scalar=AsyncMock(side_effect=[None, existing]))
    session.add = added.append
    service = _service(session)

    created = await service._upsert_resource(
        root=root,
        app_token="app-token",
        table_id="table",
        title="新增",
        source_path=[{"title": "入口"}],
    )
    assert created in added
    updated = await service._upsert_resource(
        root=root,
        app_token="app-token",
        table_id="table",
        title="更新",
        source_path=[{"title": "新入口"}],
    )
    assert updated is existing
    assert existing.title == "更新"
    assert existing.source_root_id == root.id


@pytest.mark.asyncio
async def test_lookup_and_download_reject_missing_resources(monkeypatch: Any) -> None:
    service = _service()
    service.session.scalar.return_value = None
    with pytest.raises(AppException, match="入口不存在"):
        await service._root(uuid4())
    with pytest.raises(AppException, match="资源不存在"):
        await service._resource(uuid4())

    no_row: Any = SimpleNamespace(first=lambda: None)
    service.session.execute.return_value = no_row
    with pytest.raises(AppException, match="绑定不存在"):
        await service._bound_resource("page", uuid4())
    with pytest.raises(AppException, match="附件标识"):
        await service.download_attachment(
            page_key="page",
            binding_id=uuid4(),
            record_id="record",
            field_id="field",
            file_token="../bad",
        )


def test_read_mirror_helpers_cover_nested_attachments_and_bad_values() -> None:
    service = _service(app_id="", app_secret="")
    with pytest.raises(AppException, match="未配置"):
        service._client("token")

    assert service._contains_attachment_token(
        {"files": [{"attachment_token": "target"}]},
        "target",
    )
    assert not service._contains_attachment_token("target", "target")
    assert (
        service._field_payload(
            SimpleNamespace(
                field_id="field",
                field_name="名称",
                field_type="invalid",
                property={},
                sort_order=1,
            )
        )["type"]
        is None
    )
    assert service._timestamp(None) is None
    assert service._timestamp(1_767_225_600_000) == datetime(
        2026,
        1,
        1,
        tzinfo=UTC,
    )
    assert service._timestamp("invalid") is None
    assert len(service._safe_error(RuntimeError("x" * 1100))) == 1000
