"""飞书 WebSocket 长连接客户端测试：生命周期、URL 获取、重连、事件分发。"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.platform.integrations.feishu import ws_client as svc


def _client(**kw: Any) -> svc.FeishuWsClient:
    return svc.FeishuWsClient(**kw)


# ── start_ws_client / stop_ws_client ────────────────────


def test_start_ws_client_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = MagicMock()
    settings.FEISHU_APP_ID = ""
    settings.FEISHU_APP_SECRET = ""
    monkeypatch.setattr(
        "app.core.config.get_settings", lambda: settings
    )
    svc.start_ws_client()  # 空凭据 → 跳过（不启动线程）
    assert "feishu-ws" not in svc._ws_threads


def test_start_and_stop_ws_client_named(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = MagicMock()
    settings.FEISHU_APP_ID = "cli_x"
    settings.FEISHU_APP_SECRET = "sec"
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    thread_mock = MagicMock()
    monkeypatch.setattr(
        svc.threading, "Thread", lambda *a, **kw: thread_mock
    )
    svc.start_ws_client(app_id="a", app_secret="b", name="test-ws")
    thread_mock.start.assert_called_once()
    assert "test-ws" in svc._ws_threads

    svc.stop_ws_client("test-ws")
    assert "test-ws" not in svc._ws_threads
    assert "test-ws" not in svc._stop_flags

    # 停止全部
    svc._stop_flags["w1"] = MagicMock()
    svc._stop_flags["w2"] = MagicMock()
    svc._ws_threads["w1"] = MagicMock()
    svc.stop_ws_client()  # name=None → 停止所有
    assert not svc._ws_threads and not svc._stop_flags


# ── FeishuWsClient 生命周期 ─────────────────────────────


@pytest.mark.asyncio
async def test_client_start_stop_no_creds() -> None:
    client = _client(name="test")
    client.start("", "")  # 空凭据 → 跳过
    assert client._task is None
    assert client.running is False
    client.stop()  # 无 _stop 时不报错


@pytest.mark.asyncio
async def test_client_start_creates_task() -> None:
    client = _client(name="test")
    client._run_ws = AsyncMock()  # type: ignore[method-assign]
    client.start("a", "b")
    assert client._task is not None
    assert client.running is True
    client.stop()
    await asyncio.sleep(0)  # 让任务感知 stop
    client._task.cancel()
    try:
        await client._task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass


# ── _get_ws_url ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_ws_url_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(name="t")
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "code": 0,
        "data": {
            "URL": "wss://example.com/ws?service_id=12345",
            "ClientConfig": {"PingInterval": 120},
        },
    }
    http = AsyncMock()
    http.post = AsyncMock(return_value=resp)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=http)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(svc.httpx, "AsyncClient", lambda **kw: cm)

    url, service_id = await client._get_ws_url("a", "b")
    assert url == "wss://example.com/ws?service_id=12345"
    assert service_id == 12345
    assert client._ping_interval == 120


@pytest.mark.asyncio
async def test_get_ws_url_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(name="t")
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"code": 999, "msg": "bad credentials"}
    http = AsyncMock()
    http.post = AsyncMock(return_value=resp)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=http)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(svc.httpx, "AsyncClient", lambda **kw: cm)
    assert await client._get_ws_url("a", "b") == (None, 0)

    # 非 200 状态码
    resp.status_code = 500
    assert await client._get_ws_url("a", "b") == (None, 0)


# ── _run_ws 重连逻辑 ────────────────────────────────────


@pytest.mark.asyncio
async def test_run_ws_url_failure_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(name="t")
    client._stop = asyncio.Event()
    calls = 0

    async def _fail_url(app_id: str, app_secret: str) -> tuple[str | None, int]:
        nonlocal calls
        calls += 1
        if calls >= 3:
            client._stop.set()  # URL 失败路径 continue 不检查 attempt，需 stop 退出
        return None, 0

    monkeypatch.setattr(client, "_get_ws_url", _fail_url)
    monkeypatch.setattr(svc.asyncio, "sleep", AsyncMock())
    await client._run_ws("a", "b")
    assert calls == 3


@pytest.mark.asyncio
async def test_run_ws_connection_closed_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(name="t")
    client._stop = asyncio.Event()
    monkeypatch.setattr(
        client, "_get_ws_url", AsyncMock(return_value=("wss://x", 1))
    )
    monkeypatch.setattr(svc.asyncio, "sleep", AsyncMock())

    connect_count = 0

    def _connect(*a: Any, **kw: Any) -> Any:
        nonlocal connect_count
        connect_count += 1
        cm = AsyncMock()
        exc = svc.websockets.exceptions.ConnectionClosed(
            MagicMock(), MagicMock(), MagicMock()
        )
        cm.__aenter__ = AsyncMock(side_effect=exc)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    monkeypatch.setattr(svc.websockets, "connect", _connect)
    await client._run_ws("a", "b")
    assert connect_count == 3


# ── 默认事件分发器 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_default_dispatcher_routes_message_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.platform.integrations.feishu.event_handler as real_eh

    # 非消息事件 → 直接返回
    await svc._default_other_event_dispatcher("other.event", {})

    # 消息事件 + 无 raw handler → 静默跳过
    monkeypatch.delattr(real_eh, "_on_message_receive_raw", raising=False)
    await svc._default_other_event_dispatcher("im.message.receive_v1", {})

    # 消息事件 + raw handler → 被调用
    called: list[Any] = []

    async def _raw(event: Any) -> None:
        called.append(event)

    monkeypatch.setattr(real_eh, "_on_message_receive_raw", _raw, raising=False)
    await svc._default_other_event_dispatcher("im.message.receive_v1", {"k": 1})
    assert called == [{"k": 1}]

    # raw handler 抛异常 → 被捕获
    async def _boom(event: Any) -> None:
        raise RuntimeError("handler down")

    monkeypatch.setattr(real_eh, "_on_message_receive_raw", _boom, raising=False)
    await svc._default_other_event_dispatcher("im.message.receive_v1", {})  # 不抛
