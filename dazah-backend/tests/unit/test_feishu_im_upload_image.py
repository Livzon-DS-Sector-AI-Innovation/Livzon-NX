"""平台层飞书图片上传（凭证参数化）单测。"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.platform.integrations.feishu import im
from app.platform.integrations.feishu.auth import FeishuAuth


def _patch_client(monkeypatch: Any, handler: Any) -> None:
    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def fake_client(*, timeout: float) -> Any:
        return real(transport=transport, timeout=timeout)

    monkeypatch.setattr(im.httpx, "AsyncClient", fake_client)


@pytest.mark.anyio
async def test_upload_empty_bytes_returns_none() -> None:
    assert await im.upload_image_to_feishu(b"", app_id="a", app_secret="b") is None


@pytest.mark.anyio
async def test_upload_missing_credentials_returns_none() -> None:
    assert await im.upload_image_to_feishu(b"x", app_id="", app_secret="") is None


@pytest.mark.anyio
async def test_upload_returns_image_key(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        FeishuAuth,
        "get_tenant_access_token",
        classmethod(lambda cls, a, b: _coro("tenant-token")),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/open-apis/im/v1/images"
        assert request.headers.get("Authorization") == "Bearer tenant-token"
        return httpx.Response(
            200,
            json={"code": 0, "msg": "ok", "data": {"image_key": "img_v3_abc"}},
        )

    _patch_client(monkeypatch, handler)
    key = await im.upload_image_to_feishu(b"PNGDATA", app_id="a", app_secret="s")
    assert key == "img_v3_abc"


@pytest.mark.anyio
async def test_upload_nonzero_code_returns_none(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        FeishuAuth,
        "get_tenant_access_token",
        classmethod(lambda cls, a, b: _coro("tok")),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 99992, "msg": "no permission"})

    _patch_client(monkeypatch, handler)
    assert await im.upload_image_to_feishu(b"X", app_id="a", app_secret="s") is None


async def _coro(value: str) -> str:
    return value
