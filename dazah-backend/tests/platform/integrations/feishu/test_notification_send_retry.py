"""飞书通知发送频控（99992361）重试逻辑单测。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.platform.integrations.feishu import notification


class _FakeResponse:
    def __init__(self, success: bool, code: int = 0, message_id: str | None = None) -> None:
        self._success = success
        self.code = code
        self.data = type("D", (), {"message_id": message_id})()

    def success(self) -> bool:
        return self._success


@pytest.mark.anyio
async def test_send_retries_once_on_token_frequency_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acreate = AsyncMock(
        side_effect=[
            _FakeResponse(success=False, code=99992361),
            _FakeResponse(success=True, message_id="msg-1"),
        ]
    )
    client = AsyncMock()
    client.im.v1.message.acreate = acreate
    monkeypatch.setattr(notification, "_get_client", AsyncMock(return_value=client))
    monkeypatch.setattr(notification, "_get_tenant_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(
        notification, "build_card", AsyncMock(return_value='{"msg_type":"interactive"}')
    )
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    sent = await notification.send_user_card_with_message_id(
        "ou-1", "标题", "内容", app_id="a", app_secret="b"
    )
    assert sent == "msg-1"
    assert acreate.await_count == 2
    # 重试请求带刷新后的 Bearer 头
    heads = [call.args[0].headers.get("Authorization") for call in acreate.await_args_list]
    assert heads == ["Bearer tok", "Bearer tok"]


@pytest.mark.anyio
async def test_send_returns_none_when_non_rate_limit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acreate = AsyncMock(return_value=_FakeResponse(success=False, code=99991661))
    client = AsyncMock()
    client.im.v1.message.acreate = acreate
    monkeypatch.setattr(notification, "_get_client", AsyncMock(return_value=client))
    monkeypatch.setattr(notification, "_get_tenant_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(
        notification, "build_card", AsyncMock(return_value='{"msg_type":"interactive"}')
    )

    sent = await notification.send_user_card_with_message_id(
        "ou-1", "标题", "内容", app_id="a", app_secret="b"
    )
    assert sent is None
    assert acreate.await_count == 1