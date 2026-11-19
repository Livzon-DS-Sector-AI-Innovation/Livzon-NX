from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.quality import feishu_notification as notification


@pytest.mark.asyncio
async def test_notifications_pass_module_credentials_and_stable_recipient(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(notification, "async_session_factory", lambda: session)
    monkeypatch.setattr(
        notification,
        "_get_credentials",
        AsyncMock(return_value=("business-app", "business-secret")),
    )
    monkeypatch.setattr(
        notification,
        "resolve_feishu_notification_recipient",
        AsyncMock(return_value=("employee-id", "user_id")),
    )
    send = AsyncMock(return_value="message-id")
    monkeypatch.setattr(
        notification.notification, "send_user_card_with_message_id", send
    )
    assert await notification.send_user_card("login-open-id", "title", "body")
    assert send.await_args.args[0] == "employee-id"
    assert send.await_args.args[4] == "user_id"
    assert send.await_args.kwargs == {
        "app_id": "business-app",
        "app_secret": "business-secret",
    }
    update = AsyncMock(return_value=True)
    monkeypatch.setattr(notification.notification, "update_card", update)
    assert await notification.update_card("message-id", {})
    assert update.await_args.kwargs == send.await_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("credentials", [("", ""), ("app", "")])
async def test_missing_module_credentials_skip_sending(monkeypatch, credentials):
    monkeypatch.setattr(notification, "async_session_factory", lambda: AsyncMock())
    monkeypatch.setattr(
        notification, "_get_credentials", AsyncMock(return_value=credentials)
    )
    send = AsyncMock()
    monkeypatch.setattr(
        notification.notification, "send_user_card_with_message_id", send
    )
    assert not await notification.send_user_card("ou-user", "title", "body")
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_quality_does_not_seed_login_application(monkeypatch):
    from app.modules.quality.service import quality_feishu_settings as settings

    db = AsyncMock()
    monkeypatch.setattr(
        settings, "_get_app_settings_model", AsyncMock(return_value=None)
    )
    assert await settings._ensure_quality_feishu_app_settings_seeded(db) is None
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_quality_runtime_without_module_config_is_disabled():
    from app.modules.quality.service.quality_feishu_sync import QualityFeishuSync

    db = AsyncMock()
    result = Mock()
    result.scalars.return_value.first.return_value = None
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    runtime = await QualityFeishuSync()._resolve_runtime(db)
    assert not runtime.is_app_enabled
    assert not runtime.app_id and not runtime.app_secret


@pytest.mark.asyncio
async def test_quality_notification_resolves_only_enabled_module_app(monkeypatch):
    from types import SimpleNamespace

    from app.core.llm import encryption
    from app.modules.quality.service import quality_feishu_settings

    row = SimpleNamespace(
        app_id="quality-app", app_secret="encrypted", is_enabled=True, is_deleted=False
    )
    monkeypatch.setattr(
        quality_feishu_settings, "_get_app_settings_model", AsyncMock(return_value=row)
    )
    monkeypatch.setattr(encryption, "decrypt_api_key", lambda value: "quality-secret")
    assert await notification._get_credentials(AsyncMock()) == (
        "quality-app",
        "quality-secret",
    )
    row.is_enabled = False
    assert await notification._get_credentials(AsyncMock()) == ("", "")



@pytest.mark.asyncio
async def test_page_runtime_queries_one_binding_and_observes_config_changes(
    monkeypatch,
):
    from types import SimpleNamespace

    from app.core.exceptions import AppException
    from app.modules.quality.models import QualityFeishuEntitySetting
    from app.modules.quality.service import quality_feishu_sync as sync
    from app.modules.quality.service.quality_feishu_pages import _resolve_runtime_entity
    from app.modules.quality.service.quality_feishu_settings import (
        _entity_setting_defaults,
    )

    code = "complaint_ledger"
    model = QualityFeishuEntitySetting(
        **{
            **_entity_setting_defaults(code),
            "app_token": "test-base",
            "base_table_id": "test-table",
            "is_enabled": True,
            "is_deleted": False,
        }
    )
    app_result = Mock()
    app_result.scalars.return_value.first.return_value = SimpleNamespace(
        is_enabled=True,
        app_id="quality-test-app",
        app_secret="encrypted",
        app_token=None,
    )
    row_result = Mock()
    row_result.scalar_one_or_none.return_value = model
    db = AsyncMock()
    db.execute.side_effect = [app_result, row_result] * 3
    monkeypatch.setattr(sync, "decrypt_api_key", lambda value: "quality-test-secret")

    runtime, entity = await _resolve_runtime_entity(db, code, direction="pull")
    assert list(runtime.entities) == [code]
    assert entity.table_id == "test-table"
    model.base_table_id = "updated-test-table"
    _, updated = await _resolve_runtime_entity(db, code, direction="pull")
    assert updated.table_id == "updated-test-table"

    model.is_deleted = True
    with pytest.raises(AppException, match="Base"):
        await _resolve_runtime_entity(db, code, direction="pull")
    assert db.execute.await_count == 6
    for call in db.execute.await_args_list[1::2]:
        statement = call.args[0].compile()
        assert "WHERE quality.quality_feishu_entity_settings.entity_code =" in str(
            statement
        )
        assert set(statement.params.values()) == {code}
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_defaults_seed_only_requested_entity(db_session, monkeypatch):
    from sqlalchemy import delete, select

    from app.modules.quality.models import QualityFeishuEntitySetting
    from app.modules.quality.service import quality_feishu_settings as settings

    code = "qc_solid_ys002"
    row = QualityFeishuEntitySetting
    await db_session.execute(delete(row).where(row.entity_code == code))
    monkeypatch.setattr(
        settings,
        "_get_entity_prefill",
        lambda entity: ("test-base", "test-table", None),
    )
    inserted = await settings.get_quality_feishu_runtime_entity(
        db_session, code, ensure_defaults=True
    )
    assert inserted and inserted.is_enabled and inserted.base_table_id == "test-table"
    saved = await db_session.scalar(select(row).where(row.entity_code == code))
    assert saved is not None and saved.id == inserted.id
    await db_session.delete(saved)
    await db_session.commit()



@pytest.mark.asyncio
async def test_filtered_search_reuses_one_runtime_lookup(monkeypatch):
    from types import SimpleNamespace

    from app.modules.quality.models import QualityFeishuEntitySetting
    from app.modules.quality.service import quality_feishu_sync as sync
    from app.modules.quality.service.quality_feishu_pages import _search_entity_records

    row = QualityFeishuEntitySetting(
        entity_code="complaint_ledger",
        is_deleted=False,
        is_enabled=True,
        app_token="test-app-token",
        base_table_id="test-table",
        enable_pull_from_feishu=True,
        enable_push_to_feishu=False,
        field_mappings=[{"system_field": "编号", "feishu_field": "投诉编号"}],
    )
    app_result = Mock()
    app_result.scalars.return_value.first.return_value = SimpleNamespace(
        is_enabled=True,
        app_id="quality-test-app",
        app_secret="encrypted",
        app_token=None,
    )
    row_result = Mock()
    row_result.scalar_one_or_none.return_value = row
    db = AsyncMock()
    db.execute.side_effect = [app_result, row_result]
    monkeypatch.setattr(sync, "decrypt_api_key", lambda value: "quality-test-secret")
    search = AsyncMock(return_value=[{"record_id": "result"}])
    monkeypatch.setattr(
        sync, "BitableClient", lambda **kwargs: SimpleNamespace(search_records=search)
    )
    result = await _search_entity_records(
        db, "complaint_ledger", filters={"编号": "T1"}
    )
    assert result == [{"record_id": "result"}]
    assert db.execute.await_count == 2
    assert "投诉编号" in search.await_args.kwargs["filter_str"]
