"""FA 苯丙氨酸 飞书同步 helper 覆盖（mock httpx，无真实网络）。"""

import importlib
from unittest.mock import patch

import httpx
import pytest


@pytest.mark.anyio
async def test_fa_feishu_sync_token_and_read_sheet():
    mod = importlib.import_module("app.modules.production.fa_feishu_sync")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "ftok"})
        if "/values/" in request.url.path:
            return httpx.Response(
                200,
                json={"code": 0, "data": {"valueRange": {"values": [[1, None, "x"], ["a", "b", "c"]]}}},  # noqa: E501
            )
        return httpx.Response(200, json={"code": 0})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_async_client(*, base_url=None, timeout=30, **kw):
        return real_client(transport=transport, timeout=timeout, base_url=base_url)

    mod._token_cache.clear()
    with patch.object(mod.httpx, "AsyncClient", fake_async_client):
        token = await mod._get_token("app", "sec")
        assert token == "ftok"
        assert await mod._get_token("app", "sec") == "ftok"  # cached
        rows = await mod._read_sheet("spread", "app", "sec")
        assert rows[0] == ["1", "", "x"]
        assert rows[1] == ["a", "b", "c"]
