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
