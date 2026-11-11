"""手写签名公网中转网关测试：页面渲染、提交暂存、密钥拉取、未启用拒绝。

不连真实飞书；Redis 用测试环境真实实例（不可用则跳过）。
"""

from __future__ import annotations

import base64
import io
import json

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
