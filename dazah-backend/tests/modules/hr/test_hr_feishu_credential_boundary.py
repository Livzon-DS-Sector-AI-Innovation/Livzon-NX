from unittest.mock import AsyncMock

import pytest

from app.modules.hr.feishu import notification as notification


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
async def test_legacy_hr_client_resolves_only_hr_database_credentials(monkeypatch):
    from app.modules.hr import feishu_settings_service
    from app.modules.hr.feishu import auth
    from app.platform.integrations.feishu.auth import FeishuAuth

    monkeypatch.setattr(auth, "async_session_factory", lambda: AsyncMock())
    resolve = AsyncMock(return_value=("hr-app", "hr-secret"))
    monkeypatch.setattr(
        feishu_settings_service, "get_hr_feishu_app_credentials", resolve
    )
    token = AsyncMock(return_value="hr-token")
    monkeypatch.setattr(FeishuAuth, "get_tenant_access_token", token)
    assert await auth.FeishuAuth.get_tenant_access_token() == "hr-token"
    token.assert_awaited_once_with("hr-app", "hr-secret")


@pytest.mark.asyncio
async def test_hr_partial_pair_never_fills_from_database(monkeypatch):
    from app.modules.hr.feishu import auth
    from app.platform.integrations.feishu.auth import FeishuCredentialsRequiredError

    session = AsyncMock()
    monkeypatch.setattr(auth, "async_session_factory", session)
    with pytest.raises(FeishuCredentialsRequiredError):
        await auth.FeishuAuth.get_tenant_access_token("hr-app", None)
    session.assert_not_called()
