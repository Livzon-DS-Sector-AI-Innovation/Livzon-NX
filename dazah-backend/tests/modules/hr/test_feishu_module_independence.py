"""模块飞书应用独立化测试：人事严格凭证 + 平台通知显式凭证 + WS 客户端。

覆盖：
- 人事 get_hr_feishu_app_credentials 严格模式（缺失/禁用抛错，不回退平台 env）
- 平台 notification 显式 app_id/app_secret 参数优先（透传给 client/token 构造）
- update_card 凭证解析失败时返回 False（不抛异常）
- FeishuWsClient 缺凭证时跳过启动
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.llm import encrypt_api_key
from app.modules.hr.feishu_settings_service import (
    HrFeishuNotConfigured,
    get_hr_feishu_app_credentials,
    try_get_hr_feishu_app_credentials,
)
from app.modules.hr.models import HrFeishuAppSettings
from app.platform.integrations.feishu import notification
from app.platform.integrations.feishu.ws_client import FeishuWsClient


async def _get_or_create_row(db: AsyncSession) -> HrFeishuAppSettings:
    result = await db.execute(select(HrFeishuAppSettings).limit(1))
    row = result.scalar_one_or_none()
    if row is None:
        row = HrFeishuAppSettings(app_id="", app_secret="", is_enabled=True)
        db.add(row)
        await db.flush()
    return row


@pytest.mark.asyncio
async def test_hr_credentials_strict_no_env_fallback(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = await _get_or_create_row(db_session)
    row.app_id = ""
    row.app_secret = ""
    row.is_enabled = True
    await db_session.flush()

    # 平台 env 有凭证也不得回退
    settings = get_settings()
    monkeypatch.setattr(settings, "FEISHU_APP_ID", "cli_platform_app")
    monkeypatch.setattr(settings, "FEISHU_APP_SECRET", "platform_secret")

    with pytest.raises(HrFeishuNotConfigured):
        await get_hr_feishu_app_credentials(db_session)
    assert await try_get_hr_feishu_app_credentials(db_session) is None


@pytest.mark.asyncio
async def test_hr_credentials_disabled_row_not_usable(db_session: AsyncSession) -> None:
    row = await _get_or_create_row(db_session)
    row.app_id = "cli_hr_test"
    row.app_secret = encrypt_api_key("hr_secret_plain")
    row.is_enabled = False
    await db_session.flush()

    with pytest.raises(HrFeishuNotConfigured):
        await get_hr_feishu_app_credentials(db_session)


@pytest.mark.asyncio
async def test_hr_credentials_returns_decrypted_pair(db_session: AsyncSession) -> None:
    row = await _get_or_create_row(db_session)
    row.app_id = "cli_hr_test"
    row.app_secret = encrypt_api_key("hr_secret_plain")
    row.is_enabled = True
    await db_session.flush()

    app_id, app_secret = await get_hr_feishu_app_credentials(db_session)
    assert app_id == "cli_hr_test"
    assert app_secret == "hr_secret_plain"


class _FakeSuccessResp:
    def success(self) -> bool:
        return True

    class data:  # noqa: N801
        message_id = "om_123"


@pytest.mark.asyncio
async def test_send_user_card_prefers_explicit_credentials() -> None:
    """显式传凭证时直接使用，不回退平台 env 配置。"""
    fake_client = AsyncMock()
    fake_client.im.v1.message.acreate = AsyncMock(return_value=_FakeSuccessResp())

    client_mock = AsyncMock(return_value=fake_client)
    token_mock = AsyncMock(return_value="tenant-token")
    settings = get_settings()
    with (
        patch.object(settings, "FEISHU_APP_ID", "cli_platform_app"),
        patch.object(settings, "FEISHU_APP_SECRET", "platform_secret"),
        patch.object(notification, "_get_client", new=client_mock),
        patch.object(notification, "_get_tenant_token", new=token_mock),
    ):
        ok = await notification.send_user_card(
            "ou_test",
            "标题",
            "内容",
            app_id="cli_hr_test",
            app_secret="hr_secret_plain",
        )

    assert ok is True
    client_mock.assert_awaited_once_with("cli_hr_test", "hr_secret_plain")
    token_mock.assert_awaited_once_with("cli_hr_test", "hr_secret_plain")


@pytest.mark.asyncio
async def test_update_card_returns_false_when_credentials_unavailable() -> None:
    """凭证解析失败时 update_card 返回 False（不抛异常、不影响调用方流程）。"""
    with patch.object(
        notification,
        "_get_tenant_token",
        new=AsyncMock(side_effect=RuntimeError("未配置")),
    ):
        ok = await notification.update_card("om_x", {"elements": []})

    assert ok is False


@pytest.mark.asyncio
async def test_update_card_uses_explicit_credentials() -> None:
    fake_client = AsyncMock()
    fake_client.im.v1.message.apatch = AsyncMock(return_value=_FakeSuccessResp())

    client_mock = AsyncMock(return_value=fake_client)
    with (
        patch.object(notification, "_get_client", new=client_mock),
        patch.object(
            notification,
            "_get_tenant_token",
            new=AsyncMock(return_value="tenant-token"),
        ),
    ):
        ok = await notification.update_card(
            "om_x",
            {"elements": []},
            app_id="cli_hr_test",
            app_secret="hr_secret_plain",
        )

    assert ok is True
    client_mock.assert_awaited_once_with("cli_hr_test", "hr_secret_plain")


@pytest.mark.asyncio
async def test_ws_client_skips_start_without_credentials() -> None:
    ws = FeishuWsClient(name="test-ws")
    # 空凭证：start 直接跳过，不创建任务
    ws.start("", "")
    assert ws.running is False
    ws.stop()  # 未启动时 stop 应为 no-op
