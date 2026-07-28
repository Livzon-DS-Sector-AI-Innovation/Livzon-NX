"""Repository empty-result, locking, and persistence failure contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.modules.warehouse.repository import WarehouseRepository
from app.platform.identity.repository import (
    FeishuCardActionRepository,
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
    actions = FeishuCardActionRepository()
    tokens = FeishuUserTokenRepository()

    assert await users.get_by_id(session, "invalid-uuid") is None
    assert await users.find_by_livzon_recipient_identifier(session, " ") == []
    assert await actions.get_pending_by_id(session, "invalid-uuid") is None
    assert await actions.get_by_id_for_update(session, "invalid-uuid") is None
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
    assert (
        await users.get_by_username_including_deleted(session, "missing")
        is None
    )
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
async def test_identity_config_and_card_updates_handle_empty_values() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(return_value=_empty_result()),
        flush=AsyncMock(),
    )
    configs = FeishuConfigRepository()
    assert await configs.get_active(session) is None
    assert await configs.get_latest(session) is None
    assert await configs.get_by_name_including_deleted(session, "missing") is None

    actions = FeishuCardActionRepository()
    await actions.set_message_id_for_card(
        session,
        card_id="card",
        message_id=None,
    )
    session.flush.assert_not_awaited()

    first = SimpleNamespace(message_id=None)
    second = SimpleNamespace(message_id=None)
    session.execute.return_value = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [first, second])
    )
    await actions.set_message_id_for_card(
        session,
        card_id="card",
        message_id="message",
    )
    assert first.message_id == "message"
    assert second.message_id == "message"
    session.flush.assert_awaited_once()


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
    result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: queued)
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        flush=AsyncMock(),
    )
    claimed = await WarehouseRepository(session).claim_queued_analysis_runs(
        limit=2
    )
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
