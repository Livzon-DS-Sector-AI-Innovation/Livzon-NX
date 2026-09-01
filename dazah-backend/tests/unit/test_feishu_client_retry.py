"""飞书平台客户端重试退避测试。

覆盖外部 API 容错策略的关键分支：
- 429/5xx 与连接层错误按指数退避重试后成功
- GET 偶发 400 纳入重试；POST 400 不重试（写语义）
- ReadTimeout（可能已送达）不重试，避免写操作重复
- 非重试状态码立即抛出
- 重试耗尽后抛出最后一次异常

全部使用 fake HTTP 响应与 mock sleep，不访问真实飞书服务。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.platform.integrations.feishu.auth import FeishuAuth
from app.platform.integrations.feishu.client import FeishuClient


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload or {"code": 0, "data": {"ok": True}}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=request, response=response
            )

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    """按序返回预置响应/异常的 httpx.AsyncClient 替身。"""

    def __init__(self, queue: list[Any]):
        self._queue = queue
        self.calls = 0

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls += 1
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        FeishuAuth, "get_tenant_access_token", AsyncMock(return_value="fake-token")
    )


@pytest.fixture
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """把客户端内的 asyncio.sleep 替换为记录调用的 mock，避免真实退避等待。"""
    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "app.platform.integrations.feishu.client.asyncio",
        SimpleNamespace(sleep=sleep_mock),
    )
    return sleep_mock


def _install_client(
    monkeypatch: pytest.MonkeyPatch, queue: list[Any]
) -> list[_FakeAsyncClient]:
    created: list[_FakeAsyncClient] = []

    def factory(**kwargs: Any) -> _FakeAsyncClient:
        client = _FakeAsyncClient(queue)
        created.append(client)
        return client

    monkeypatch.setattr(
        "app.platform.integrations.feishu.client.httpx.AsyncClient", factory
    )
    return created


async def test_retry_on_429_then_success(
    monkeypatch: pytest.MonkeyPatch, fake_auth: None, fast_sleep: AsyncMock
) -> None:
    """429 触发一次退避重试，第二次成功返回 data。"""
    created = _install_client(
        monkeypatch,
        [_FakeResponse(429), _FakeResponse(200)],
    )
    result = await FeishuClient().request("GET", "/x/v1/y")
    assert result == {"ok": True}
    assert sum(c.calls for c in created) == 2
    fast_sleep.assert_awaited_once_with(1.0)


async def test_retry_on_connect_error_then_success(
    monkeypatch: pytest.MonkeyPatch, fake_auth: None, fast_sleep: AsyncMock
) -> None:
    """连接层错误（请求未送达）按退避重试后成功。"""
    created = _install_client(
        monkeypatch,
        [httpx.ConnectError("boom"), _FakeResponse(200)],
    )
    result = await FeishuClient().request("GET", "/x/v1/y")
    assert result == {"ok": True}
    assert sum(c.calls for c in created) == 2
    fast_sleep.assert_awaited_once_with(1.0)


async def test_get_400_retried_but_post_400_not(
    monkeypatch: pytest.MonkeyPatch, fake_auth: None, fast_sleep: AsyncMock
) -> None:
    """GET 偶发 400 纳入重试；POST 400 属请求语义错误，立即抛出。"""
    created = _install_client(monkeypatch, [_FakeResponse(400)])
    with pytest.raises(httpx.HTTPStatusError):
        await FeishuClient().request("POST", "/x/v1/y", json={"a": 1})
    assert sum(c.calls for c in created) == 1
    fast_sleep.assert_not_awaited()

    created = _install_client(
        monkeypatch,
        [_FakeResponse(400), _FakeResponse(200)],
    )
    result = await FeishuClient().request("GET", "/x/v1/y")
    assert result == {"ok": True}
    assert sum(c.calls for c in created) == 2


async def test_read_timeout_not_retried(
    monkeypatch: pytest.MonkeyPatch, fake_auth: None, fast_sleep: AsyncMock
) -> None:
    """ReadTimeout（响应可能已送达）不重试，避免写操作重复。"""
    created = _install_client(
        monkeypatch,
        [httpx.ReadTimeout("slow")],
    )
    with pytest.raises(httpx.ReadTimeout):
        await FeishuClient().request("POST", "/x/v1/y", json={"a": 1})
    assert sum(c.calls for c in created) == 1
    fast_sleep.assert_not_awaited()


async def test_retries_exhausted_raises(
    monkeypatch: pytest.MonkeyPatch, fake_auth: None, fast_sleep: AsyncMock
) -> None:
    """持续 500 时重试 3 次后抛出，总请求 4 次，退避 1s/2s/4s。"""
    created = _install_client(
        monkeypatch,
        [
            _FakeResponse(500),
            _FakeResponse(500),
            _FakeResponse(500),
            _FakeResponse(500),
        ],
    )
    with pytest.raises(httpx.HTTPStatusError):
        await FeishuClient().request("GET", "/x/v1/y")
    assert sum(c.calls for c in created) == 4
    assert [call.args[0] for call in fast_sleep.await_args_list] == [1.0, 2.0, 4.0]


async def test_success_first_try_no_retry(
    monkeypatch: pytest.MonkeyPatch, fake_auth: None, fast_sleep: AsyncMock
) -> None:
    """成功路径零额外请求、零等待，重试不改变正常行为。"""
    created = _install_client(monkeypatch, [_FakeResponse(200)])
    result = await FeishuClient().request("GET", "/x/v1/y")
    assert result == {"ok": True}
    assert sum(c.calls for c in created) == 1
    fast_sleep.assert_not_awaited()
