import json
from typing import Any

import httpx
import pytest

from app.platform.integrations.feishu import im


@pytest.mark.anyio
async def test_reply_message_uses_feishu_reply_endpoint(monkeypatch: Any) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": {"message_id": "om_reply"},
            },
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(*, timeout: float) -> Any:
        return real_async_client(transport=transport, timeout=timeout)

    monkeypatch.setattr(im.httpx, "AsyncClient", fake_async_client)  # type: ignore[attr-defined]

    result = await im.reply_feishu_message(
        tenant_access_token="tenant-token",
        message_id="om_group_message",
        msg_type="text",
        content='{"text":"库存充足"}',
    )

    assert result.ok is True
    assert result.message_id == "om_reply"
    assert requests[0].method == "POST"
    assert requests[0].url.path == ("/open-apis/im/v1/messages/om_group_message/reply")
    assert json.loads(requests[0].read()) == {
        "msg_type": "text",
        "content": '{"text":"库存充足"}',
    }


@pytest.mark.anyio
async def test_get_bot_info_returns_open_id_used_for_mentions(monkeypatch: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "bot": {
                    "open_id": "ou_livzon_bot",
                    "app_name": "Livzon 助手",
                },
            },
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(*, timeout: float) -> Any:
        return real_async_client(transport=transport, timeout=timeout)

    monkeypatch.setattr(im.httpx, "AsyncClient", fake_async_client)  # type: ignore[attr-defined]

    result = await im.get_feishu_bot_info(tenant_access_token="tenant-token")

    assert result.ok is True
    assert result.open_id == "ou_livzon_bot"
    assert result.app_name == "Livzon 助手"


@pytest.mark.anyio
async def test_create_message_reaction_uses_feishu_reaction_endpoint(
    monkeypatch: Any,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": {"reaction_id": "reaction_test"},
            },
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(*, timeout: float) -> Any:
        return real_async_client(transport=transport, timeout=timeout)

    monkeypatch.setattr(im.httpx, "AsyncClient", fake_async_client)  # type: ignore[attr-defined]

    result = await im.create_feishu_message_reaction(
        tenant_access_token="tenant-token",
        message_id="om_test",
        emoji_type="OK",
    )

    assert result.ok is True
    assert result.reaction_id == "reaction_test"
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/open-apis/im/v1/messages/om_test/reactions"
    assert requests[0].headers["authorization"] == "Bearer tenant-token"
    assert requests[0].read() == b'{"reaction_type":{"emoji_type":"OK"}}'


@pytest.mark.anyio
async def test_create_message_reaction_returns_feishu_api_error(
    monkeypatch: Any,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"code": 231001, "msg": "reaction type is invalid."},
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(*, timeout: float) -> Any:
        return real_async_client(transport=transport, timeout=timeout)

    monkeypatch.setattr(im.httpx, "AsyncClient", fake_async_client)  # type: ignore[attr-defined]

    result = await im.create_feishu_message_reaction(
        tenant_access_token="tenant-token",
        message_id="om_test",
        emoji_type="INVALID",
    )

    assert result.ok is False
    assert result.code == 231001
    assert result.error_message == "reaction type is invalid."


@pytest.mark.anyio
async def test_delete_message_reaction_uses_feishu_reaction_endpoint(
    monkeypatch: Any,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 0, "msg": "success", "data": {}})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(*, timeout: float) -> Any:
        return real_async_client(transport=transport, timeout=timeout)

    monkeypatch.setattr(im.httpx, "AsyncClient", fake_async_client)  # type: ignore[attr-defined]

    result = await im.delete_feishu_message_reaction(
        tenant_access_token="tenant-token",
        message_id="om_test",
        reaction_id="reaction_typing",
    )

    assert result.ok is True
    assert len(requests) == 1
    assert requests[0].method == "DELETE"
    assert requests[0].url.path == (
        "/open-apis/im/v1/messages/om_test/reactions/reaction_typing"
    )
    assert requests[0].headers["authorization"] == "Bearer tenant-token"
