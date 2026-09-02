"""仓储自有飞书客户端 Retry-After 兼容性测试。

- 数字 Retry-After 按其值退避
- 非数字 Retry-After（HTTP 日期格式 / 非法值）回退指数退避，不抛异常
全部使用 fake HTTP 响应与 mock sleep，不访问真实飞书服务与 Redis。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.modules.warehouse.feishu_client import WarehouseFeishuClient


class _FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload: dict[str, Any] = {"code": 0, "data": {"ok": True}}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=request, response=response
            )

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
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


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state() -> None:
    WarehouseFeishuClient._rate_locks.clear()
    WarehouseFeishuClient._last_request_at.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("retry_after_header", "min_delay"),
    [
        ("7", 7.0),
        ("Mon, 29 Aug 2026 00:00:00 GMT", 1.0),
        ("not-a-number", 1.0),
        ("", 1.0),
    ],
)
async def test_retry_after_header_handling(
    monkeypatch: pytest.MonkeyPatch, retry_after_header: str, min_delay: float
) -> None:
    """Retry-After 数字照用；非数字回退指数退避而非请求失败。"""
    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.warehouse.feishu_client.asyncio",
        SimpleNamespace(sleep=sleep_mock, Lock=asyncio.Lock),
    )
    monkeypatch.setattr(
        "app.modules.warehouse.feishu_client.redis_client", SimpleNamespace()
    )
    created: list[_FakeAsyncClient] = []
    # 队列对象在多次重试间共享（每次 attempt 都会新建 AsyncClient）
    queue: list[Any] = [
        _FakeResponse(502, {"Retry-After": retry_after_header}),
        _FakeResponse(200),
    ]

    def factory(**kwargs: Any) -> _FakeAsyncClient:
        client = _FakeAsyncClient(queue)
        created.append(client)
        return client

    monkeypatch.setattr(
        "app.modules.warehouse.feishu_client.httpx.AsyncClient", factory
    )

    client = WarehouseFeishuClient(
        app_id="app", app_secret="secret", app_token="base-x"
    )
    client.get_tenant_access_token = AsyncMock(return_value="token")

    result = await client.request(
        "POST", "/bitable/v1/apps/base-x/tables/t/records/search"
    )

    assert result == {"ok": True}
    assert sum(c.calls for c in created) == 2
    # sleep 调用中既有 QPS 限速等待（~0.2s）也有退避；按退避基准值筛选
    retry_delays = [
        call.args[0]
        for call in sleep_mock.await_args_list
        if call.args and call.args[0] >= min_delay
    ]
    assert len(retry_delays) == 1
    assert retry_delays[0] < min_delay + 0.31  # 基础值 + 随机抖动上限
