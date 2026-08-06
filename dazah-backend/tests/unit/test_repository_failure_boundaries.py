"""Repository empty-result, locking, and persistence failure contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.modules.warehouse.repository import WarehouseRepository
from app.platform.identity.repository import (
    ExternalIdentityBindingRepository,
    FeishuConfigRepository,
    FeishuUserTokenRepository,
    UserRepository,
)


def _empty_result():
    return SimpleNamespace(
        scalar_one_or_none=lambda: None,
        scalars=lambda: SimpleNamespace(all=lambda: []),
    )


@pytest.mark.asyncio
async def test_identity_repository_rejects_invalid_identifiers_without_query() -> None:
    session = SimpleNamespace(execute=AsyncMock())
    users = UserRepository()
    tokens = FeishuUserTokenRepository()

    assert await users.get_by_id(session, "invalid-uuid") is None
    assert await users.find_by_livzon_recipient_identifier(session, " ") == []
    assert (
        await tokens.get_by_user_and_app(
            session,
            local_user_id="invalid-uuid",
            app_id="app",
        )
        is None
    )
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_identity_repository_returns_none_for_missing_rows() -> None:
    session = SimpleNamespace(execute=AsyncMock(return_value=_empty_result()))
    users = UserRepository()
    user_id = uuid4()

    assert await users.get_by_id(session, user_id) is None
    assert await users.get_by_username(session, "missing") is None
    assert await users.get_by_username_including_deleted(session, "missing") is None
    assert await users.get_by_login_identifier(session, "missing") is None
    assert await users.get_by_feishu_open_id(session, "open") is None
    assert await users.get_by_feishu_user_id(session, "user") is None


@pytest.mark.asyncio
async def test_identity_repository_propagates_database_unavailability() -> None:
    failure = OperationalError("SELECT", {}, Exception("database unavailable"))
    session = SimpleNamespace(execute=AsyncMock(side_effect=failure))
    with pytest.raises(OperationalError):
        await UserRepository().get_by_username(session, "user")


@pytest.mark.asyncio
async def test_identity_create_propagates_integrity_error_to_owner() -> None:
    failure = IntegrityError("INSERT", {}, Exception("duplicate username"))
    session = SimpleNamespace(
        add=lambda _value: None,
        flush=AsyncMock(side_effect=failure),
        rollback=AsyncMock(),
    )
    with pytest.raises(IntegrityError):
        await UserRepository().create(
            session,
            name="张三",
            username="duplicate",
        )
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_identity_binding_repository_lifecycle() -> None:
    binding_id = uuid4()
    local_user_id = uuid4()
    actor_id = uuid4()
    result_binding = SimpleNamespace(
        id=binding_id,
        external_user_id="user",
        external_open_id="open",
        external_union_id=None,
    )
    scalar_rows = SimpleNamespace(all=lambda: [result_binding])
    scalar_rows.unique = lambda: scalar_rows
    query_result = SimpleNamespace(
        scalar_one_or_none=lambda: result_binding,
        scalars=lambda: scalar_rows,
        all=lambda: [(result_binding, SimpleNamespace(name="张三"))],
    )
    added: list[object] = []
    session = SimpleNamespace(
        add=added.append,
        flush=AsyncMock(),
        refresh=AsyncMock(),
        scalar=AsyncMock(return_value=result_binding),
        execute=AsyncMock(return_value=query_result),
    )
    repository = ExternalIdentityBindingRepository()

    created = await repository.create(
        session,
        tenant_id="tenant",
        platform="feishu",
        app_fingerprint="app",
        external_user_id="user",
        external_open_id=None,
        external_union_id=None,
        local_user_id=local_user_id,
        source="admin",
        actor_id=actor_id,
    )
    assert created in added
    assert created.local_user_id == local_user_id
    assert created.status == "active"

    assert await repository.get(session, binding_id) is result_binding
    suspended = await repository.set_status(
        session,
        SimpleNamespace(status="active", updated_by=None),
        status_value="suspended",
        actor_id=actor_id,
    )
    assert suspended.status == "suspended"
    assert suspended.updated_by == actor_id
    session.refresh.assert_awaited_once_with(suspended)

    session.execute.reset_mock()
    assert (
        await repository.resolve(
            session,
            tenant_id="tenant",
            platform="feishu",
            app_fingerprint="app",
            external_user_id=None,
            external_open_id=None,
            external_union_id=None,
        )
        is None
    )
    session.execute.assert_not_awaited()

    resolved = await repository.resolve(
        session,
        tenant_id="tenant",
        platform="feishu",
        app_fingerprint="app",
        external_user_id="user",
        external_open_id="open",
        external_union_id=None,
    )
    assert resolved is result_binding
    assert await repository.list_for_app(
        session,
        tenant_id="tenant",
        app_fingerprint="app",
    ) == [result_binding]

    session.scalar.return_value = 1
    items, total = await repository.list_page(
        session,
        page=1,
        page_size=20,
    )
    assert items[0][0] is result_binding
    assert total == 1


@pytest.mark.asyncio
async def test_identity_config_queries_handle_empty_values() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_empty_result()),
        flush=AsyncMock(),
    )
    configs = FeishuConfigRepository()
    assert await configs.get_active(session) is None
    assert await configs.get_latest(session) is None
    assert await configs.get_by_name_including_deleted(session, "missing") is None

    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_warehouse_repository_empty_queries_and_database_failure() -> None:
    session = SimpleNamespace(execute=AsyncMock(return_value=_empty_result()))
    repository = WarehouseRepository(session)
    identifier = uuid4()

    assert await repository.get_raw_material_by_import_key("missing") is None
    assert await repository.get_packaging_material_by_import_key("missing") is None
    assert await repository.get_product_by_import_key("missing") is None
    assert await repository.get_active_feishu_config() is None
    assert await repository.get_any_feishu_config() is None
    assert (
        await repository.get_feishu_table(
            identifier,
            "app",
            "table",
        )
        is None
    )
    assert await repository.get_feishu_source_root(identifier) is None
    assert await repository.get_analysis_run(identifier) is None

    session.execute.side_effect = OperationalError(
        "SELECT",
        {},
        Exception("database unavailable"),
    )
    with pytest.raises(OperationalError):
        await repository.list_raw_materials()


@pytest.mark.asyncio
async def test_warehouse_save_propagates_integrity_error_without_rollback() -> None:
    failure = IntegrityError("INSERT", {}, Exception("duplicate import key"))
    session = SimpleNamespace(
        add=lambda _value: None,
        flush=AsyncMock(side_effect=failure),
        rollback=AsyncMock(),
    )
    repository = WarehouseRepository(session)
    with pytest.raises(IntegrityError):
        await repository.create_product(SimpleNamespace())
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_warehouse_claim_marks_rows_running_and_uses_flush() -> None:
    queued = [
        SimpleNamespace(status="queued"),
        SimpleNamespace(status="queued"),
    ]
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: queued))
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        flush=AsyncMock(),
    )
    claimed = await WarehouseRepository(session).claim_queued_analysis_runs(limit=2)
    assert claimed == queued
    assert [item.status for item in claimed] == ["running", "running"]
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_warehouse_binding_replace_propagates_flush_failure() -> None:
    failure = IntegrityError("INSERT", {}, Exception("duplicate binding"))
    added = []
    session = SimpleNamespace(
        execute=AsyncMock(),
        add=added.append,
        flush=AsyncMock(side_effect=failure),
    )
    bindings = [SimpleNamespace(id=uuid4())]
    with pytest.raises(IntegrityError):
        await WarehouseRepository(session).replace_page_bindings(
            "page",
            bindings,
        )
    assert added == bindings
