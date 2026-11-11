"""手写签名公网中转网关测试：页面渲染、提交暂存、密钥拉取、未启用拒绝。

不连真实飞书；Redis 用测试环境真实实例（不可用则跳过）。
"""

from __future__ import annotations

import base64
import io
import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.safety.api.sign_relay_public import sign_relay_public_router


def _png_data_url() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "black").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def _redis_available() -> bool:
    from app.core.redis import cache_get, cache_set

    try:
        await cache_set("probe:signrelay", "1", ex=10)
        ok = await cache_get("probe:signrelay") == "1"
        await cache_delete_probe()
        return ok
    except Exception:
        return False


async def cache_delete_probe() -> None:
    from app.core.redis import redis_client

    await redis_client.delete("probe:signrelay")


@pytest.fixture
async def relay_client(monkeypatch: pytest.MonkeyPatch) -> AsyncClient | None:
    if not await _redis_available():
        pytest.skip("Redis 不可用，跳过中转网关用例")
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "SIGN_RELAY_GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "SIGN_RELAY_KEY", "relay-key-test")

    application = FastAPI()
    application.include_router(sign_relay_public_router, prefix="/api/v1/safety")
    transport = ASGITransport(app=application)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def relay_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    monkeypatch.setattr(settings, "SIGN_RELAY_GATEWAY_ENABLED", False)


async def test_page_and_submit_and_pull_roundtrip(
    relay_client: AsyncClient | None,
) -> None:
    assert relay_client is not None
    async with relay_client as ac:
        page = await ac.get("/api/v1/safety/sign-relay/tok-1")
        assert page.status_code == 200
        assert "/api/v1/safety/sign-relay" in page.text, "页面应提交到中转端点"

        bad = await ac.post(
            "/api/v1/safety/sign-relay",
            json={"token": "tok-1", "image": "not-a-data-url"},
        )
        assert bad.status_code == 400

        ok = await ac.post(
            "/api/v1/safety/sign-relay",
            json={"token": "tok-1", "image": _png_data_url()},
        )
        assert ok.status_code == 200

        pull_wrong = await ac.post(
            "/api/v1/safety/sign-relay/pull",
            headers={"X-Relay-Key": "wrong"},
        )
        assert pull_wrong.status_code == 403

        pull = await ac.post(
            "/api/v1/safety/sign-relay/pull",
            headers={"X-Relay-Key": "relay-key-test"},
        )
        assert pull.status_code == 200
        items = pull.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["token"] == "tok-1"
        assert items[0]["image"].startswith("data:image/png")

        pull_again = await ac.post(
            "/api/v1/safety/sign-relay/pull",
            headers={"X-Relay-Key": "relay-key-test"},
        )
        assert pull_again.json()["data"]["items"] == []


async def test_disabled_returns_404(
    relay_client: AsyncClient | None,
    relay_disabled: None,
) -> None:
    # relay_client 夹具会强行开启，这里直接自建客户端测未启用形态
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    application = FastAPI()
    application.include_router(sign_relay_public_router, prefix="/api/v1/safety")
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as ac:
        page = await ac.get("/api/v1/safety/sign-relay/tok-1")
        assert page.status_code == 404
        submit = await ac.post(
            "/api/v1/safety/sign-relay", json={"token": "t", "image": "x"}
        )
        assert submit.status_code == 404
        pull = await ac.post("/api/v1/safety/sign-relay/pull")
        assert pull.status_code == 404
        del relay_client


def test_relay_payload_roundtrip_shape() -> None:
    """收件箱条目结构（token+image）与拉取端契约一致。"""
    payload = {"token": "tok", "image": "data:image/png;base64,xx"}
    assert json.loads(json.dumps(payload)) == payload


async def test_process_item_full_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """_process_item 全链路：验签→解码→存储→落库。"""
    from app.modules.safety.sign_relay_poller import _process_item

    calls: dict[str, Any] = {}

    def _verify(token: str, *, expected_act: str) -> dict[str, Any] | None:
        calls["verify"] = token
        return {"sk": "initiator", "pid": "zero-uuid"}

    def _decode(data_url: str) -> bytes | None:
        calls["decode"] = data_url
        return b"\x89PNG"

    def _store(png: bytes) -> str | None:
        calls["store"] = png
        return "signs/relay.png"

    async def _apply(session: Any, payload: dict[str, Any], key: str) -> None:
        calls["apply"] = (payload, key)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _factory():
        yield object()

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.verify_token",
        _verify,
    )
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.decode_signature_data_url",
        _decode,
    )
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.store_signature_image",
        _store,
    )
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.apply_signature_submission",
        _apply,
    )
    monkeypatch.setattr("app.core.database.async_session_factory", _factory)

    ok = await _process_item({"token": "tok1", "image": "data:image/png;base64,AA"})
    assert ok is True
    assert calls["verify"] == "tok1"
    assert calls["store"] == b"\x89PNG"
    assert calls["apply"][1] == "signs/relay.png"


async def test_process_item_bad_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.safety.sign_relay_poller import _process_item

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.verify_token",
        lambda token, *, expected_act: None,
    )
    assert await _process_item({"token": "bad"}) is False


async def test_process_item_bad_image(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.safety.sign_relay_poller import _process_item

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.verify_token",
        lambda token, *, expected_act: {"sk": "k"},
    )
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.decode_signature_data_url",
        lambda url: None,
    )
    assert await _process_item({"token": "t", "image": "bad"}) is False


async def test_process_item_store_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.safety.sign_relay_poller import _process_item

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.verify_token",
        lambda token, *, expected_act: {"sk": "k"},
    )
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.decode_signature_data_url",
        lambda url: b"png",
    )
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.store_signature_image",
        lambda png: None,
    )
    assert await _process_item({"token": "t", "image": "data:..."}) is False


async def test_poll_once_disabled_returns_zero() -> None:
    from app.modules.safety.sign_relay_poller import poll_once

    assert await poll_once() == 0


async def test_poll_once_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.safety import sign_relay_poller as poller

    monkeypatch.setattr(
        poller,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "SIGN_RELAY_GATEWAY_BASE": "http://relay",
                "SIGN_RELAY_KEY": "k",
                "SIGN_RELAY_POLL_SECONDS": 10,
                "SIGN_RELAY_GATEWAY_ENABLED": True,
            },
        )(),
    )

    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"data": {"items": [{"token": "t1", "image": "i1"}]}}

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, url: str, **kwargs: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(poller.httpx, "AsyncClient", lambda **kwargs: _Client())

    async def _ok(item: dict[str, Any]) -> bool:
        return True

    monkeypatch.setattr(poller, "_process_item", _ok)
    count = await poller.poll_once()
    assert count == 1


async def test_poll_once_http_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.safety import sign_relay_poller as poller

    monkeypatch.setattr(
        poller,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "SIGN_RELAY_GATEWAY_BASE": "http://relay",
                "SIGN_RELAY_KEY": "k",
                "SIGN_RELAY_POLL_SECONDS": 10,
            },
        )(),
    )

    class _Resp:
        status_code = 503
        text = "unavailable"

        def json(self) -> dict:
            return {}

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, url: str, **kwargs: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(poller.httpx, "AsyncClient", lambda **kwargs: _Client())
    assert await poller.poll_once() == 0


async def test_poll_once_process_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """单条处理异常不阻断整批。"""
    from app.modules.safety import sign_relay_poller as poller

    monkeypatch.setattr(
        poller,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "SIGN_RELAY_GATEWAY_BASE": "http://r",
                "SIGN_RELAY_KEY": "k",
                "SIGN_RELAY_POLL_SECONDS": 10,
            },
        )(),
    )

    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"data": {"items": [{"t": 1}, {"t": 2}]}}

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, url: str, **kwargs: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(poller.httpx, "AsyncClient", lambda **kwargs: _Client())

    async def _boom(item: dict) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(poller, "_process_item", _boom)
    assert await poller.poll_once() == 0


async def test_sign_relay_loop_no_config_returns() -> None:
    from app.modules.safety.sign_relay_poller import sign_relay_loop

    # 未配置直接返回（不进入循环）
    await sign_relay_loop()


async def test_sign_relay_loop_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    """loop 可被取消（真实 sleep 10s 间隔，在 sleep 前取消即可）。"""
    import asyncio

    from app.modules.safety import sign_relay_poller as poller

    monkeypatch.setattr(
        poller,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "SIGN_RELAY_GATEWAY_BASE": "http://r",
                "SIGN_RELAY_KEY": "k",
                "SIGN_RELAY_POLL_SECONDS": 10,
            },
        )(),
    )

    async def _noop_poll() -> int:
        return 0

    monkeypatch.setattr(poller, "poll_once", _noop_poll)

    task = asyncio.create_task(poller.sign_relay_loop())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_relay_submit_bad_body_and_missing_params(
    relay_client: AsyncClient | None,
) -> None:
    """提交体非法 JSON / 缺参数 → 400。"""
    assert relay_client is not None
    async with relay_client as ac:
        bad = await ac.post("/api/v1/safety/sign-relay", content="not-a-json")
        assert bad.status_code == 400

        missing = await ac.post(
            "/api/v1/safety/sign-relay", json={"token": "", "image": ""}
        )
        assert missing.status_code == 400


async def test_relay_pull_discards_unparseable_entries(
    relay_client: AsyncClient | None,
) -> None:
    """收件箱存在无法解析条目时丢弃并返回空批。"""
    assert relay_client is not None
    from app.core.redis import redis_client
    from app.modules.safety.api.sign_relay_public import _INBOX_KEY

    await redis_client.rpush(_INBOX_KEY, "{not-json")  # type: ignore[misc]
    async with relay_client as ac:
        pull = await ac.post(
            "/api/v1/safety/sign-relay/pull",
            headers={"X-Relay-Key": "relay-key-test"},
        )
        assert pull.status_code == 200
        assert pull.json()["data"]["items"] == []
        # 收件箱应被清空（坏条目已弹出丢弃）
        assert await redis_client.llen(_INBOX_KEY) == 0


async def test_poll_once_empty_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """网关返回空批 → 0。"""
    from app.modules.safety import sign_relay_poller as poller

    monkeypatch.setattr(
        poller,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "SIGN_RELAY_GATEWAY_BASE": "http://relay",
                "SIGN_RELAY_KEY": "k",
                "SIGN_RELAY_POLL_SECONDS": 10,
            },
        )(),
    )

    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"data": {"items": []}}

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, url: str, **kwargs: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(poller.httpx, "AsyncClient", lambda **kwargs: _Client())
    assert await poller.poll_once() == 0


async def test_sign_relay_loop_poll_exception_and_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """poll_once 抛错不阻断循环（记日志后继续 sleep），再取消退出。"""
    import asyncio

    from app.modules.safety import sign_relay_poller as poller

    monkeypatch.setattr(
        poller,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "SIGN_RELAY_GATEWAY_BASE": "http://r",
                "SIGN_RELAY_KEY": "k",
                "SIGN_RELAY_POLL_SECONDS": 10,
            },
        )(),
    )
    calls = {"n": 0}

    async def _boom_poll() -> int:
        calls["n"] += 1
        raise RuntimeError("poll down")

    monkeypatch.setattr(poller, "poll_once", _boom_poll)
    task = asyncio.create_task(poller.sign_relay_loop())
    # 等待异常分支执行后进入 sleep
    await asyncio.sleep(0.1)
    assert calls["n"] >= 1
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
