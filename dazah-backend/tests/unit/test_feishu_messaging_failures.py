"""Unit tests for Feishu message delivery failure handling."""

import json
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.platform.integrations.feishu import message, notification

SimpleNamespace: Any = _SimpleNamespace


def _message_client(response: Any) -> Any:
    api: Any = SimpleNamespace(acreate=AsyncMock(return_value=response))
    return SimpleNamespace(im=SimpleNamespace(v1=SimpleNamespace(message=api)))


@pytest.mark.asyncio
async def test_notification_token_uses_explicit_credentials(monkeypatch):
    token = AsyncMock(return_value="token")
    monkeypatch.setattr(notification.FeishuAuth, "get_tenant_access_token", token)
    assert await notification._get_tenant_token("app", "secret") == "token"
    token.assert_awaited_once_with("app", "secret")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (SimpleNamespace(success=lambda: True, code=0, msg=""), True),
        (
            SimpleNamespace(
                success=lambda: False,
                code=1,
                msg="rejected",
                status_code=400,
            ),
            False,
        ),
    ],
)
async def test_send_user_card_handles_api_outcomes(
    monkeypatch: Any,
    response: Any,
    expected: Any,
) -> None:
    client = _message_client(response)
    monkeypatch.setattr(notification, "_get_client", AsyncMock(return_value=client))
    monkeypatch.setattr(
        notification,
        "_get_tenant_token",
        AsyncMock(return_value="token"),
    )
    result = await notification.send_user_card(
        "open-id",
        "标题",
        "正文",
        [{"tag": "hr"}],
    )
    assert result is expected


@pytest.mark.asyncio
async def test_send_user_card_contains_client_exception(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        notification,
        "_get_client",
        AsyncMock(side_effect=TimeoutError("connect timeout")),
    )
    assert not await notification.send_user_card("open-id", "标题", "正文")


@pytest.mark.asyncio
async def test_build_card_includes_custom_elements() -> None:
    payload = json.loads(
        await notification.build_card(
            "标题",
            "正文",
            "red",
            [{"tag": "hr"}],
        )
    )
    assert payload["header"]["template"] == "red"
    assert payload["elements"][-1] == {"tag": "hr"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (SimpleNamespace(success=lambda: True, msg=""), True),
        (SimpleNamespace(success=lambda: False, code=1, msg="rejected"), False),
    ],
)
async def test_send_group_card_handles_api_outcomes(
    monkeypatch: Any,
    response: Any,
    expected: Any,
) -> None:
    client = _message_client(response)
    monkeypatch.setattr(notification, "_get_client", AsyncMock(return_value=client))
    monkeypatch.setattr(
        notification,
        "_get_tenant_token",
        AsyncMock(return_value="token"),
    )
    result = await message.send_group_card(
        "chat",
        "标题",
        "正文",
        [{"tag": "hr"}],
    )
    assert result is expected


@pytest.mark.asyncio
async def test_send_group_card_contains_token_exception(monkeypatch: Any) -> None:
    monkeypatch.setattr(notification, "_get_client", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        notification,
        "_get_tenant_token",
        AsyncMock(side_effect=RuntimeError("token unavailable")),
    )
    assert not await message.send_group_card("chat", "标题", "正文")


@pytest.mark.asyncio
async def test_work_order_notifications_skip_or_delegate(monkeypatch: Any) -> None:
    from app.modules.equipment.feishu import message

    monkeypatch.setattr(
        message,
        "settings",
        SimpleNamespace(FEISHU_EQUIPMENT_CHAT_ID=""),
    )
    assert not await message.send_work_order_card(
        "WO-1",
        "反应釜",
        "",
        "高",
        "张三",
        "https://example.test/claim",
    )
    assert not await message.send_claim_notification("WO-1", "李四")
    assert not await message.send_timeout_notification("WO-1", "反应釜", "主管")

    monkeypatch.setattr(
        message,
        "settings",
        SimpleNamespace(FEISHU_EQUIPMENT_CHAT_ID="chat"),
    )
    send: Any = AsyncMock(return_value=True)
    monkeypatch.setattr(message, "send_group_card", send)
    assert await message.send_work_order_card(
        "WO-1",
        "反应釜",
        "",
        "高",
        "张三",
        "https://example.test/claim",
    )
    assert await message.send_claim_notification("WO-1", "李四")
    assert await message.send_timeout_notification("WO-1", "反应釜", "主管")
    assert send.await_count == 3
