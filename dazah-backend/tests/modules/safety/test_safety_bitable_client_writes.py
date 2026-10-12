"""安全模块 Bitable 客户端的写入/上传/删除分支测试（全程 mock HTTP）。"""

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.modules.safety.feishu import bitable_client as bitable_module
from app.modules.safety.feishu.bitable_client import (
    BITABLE_BASE,
    DRIVE_UPLOAD_URL,
    SafetyBitableClient,
)


def _client(**kwargs: Any) -> SafetyBitableClient:
    client = SafetyBitableClient(app_token="app-token", table_id="tbl-1")
    client._token = AsyncMock(return_value="tenant-token")  # type: ignore[method-assign]
    return client


class _FakeHttp:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> "_FakeHttp":
        return self

    async def __aenter__(self) -> "_FakeHttp":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append(("POST", url, kwargs))
        return self.response

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append(("DELETE", url, kwargs))
        return self.response


def _json_response(payload: dict[str, Any], url: str = BITABLE_BASE) -> httpx.Response:
    return httpx.Response(
        200, json=payload, request=httpx.Request("POST", url)
    )


@pytest.mark.anyio
async def test_create_record_success_and_empty_fields() -> None:
    client = _client()
    assert await client.create_record({}, table_id="tbl-1") is None

    fake = _FakeHttp(
        _json_response({"code": 0, "data": {"record": {"record_id": "rec-1"}}})
    )

    import app.modules.safety.feishu.bitable_client as module

    original = module.httpx.AsyncClient
    module.httpx.AsyncClient = fake  # type: ignore[assignment]
    try:
        record_id = await client.create_record({"名称": "某条例"}, table_id="tbl-1")
    finally:
        module.httpx.AsyncClient = original

    assert record_id == "rec-1"
    method, url, kwargs = fake.calls[0]
    assert method == "POST"
    assert url == f"{BITABLE_BASE}/apps/app-token/tables/tbl-1/records"
    assert kwargs["json"] == {"fields": {"名称": "某条例"}}
    assert kwargs["headers"]["Authorization"] == "Bearer tenant-token"


@pytest.mark.anyio
async def test_create_record_returns_none_on_api_error() -> None:
    client = _client()
    fake = _FakeHttp(_json_response({"code": 1254005, "msg": "无权限"}))
    module = bitable_module
    original = module.httpx.AsyncClient
    module.httpx.AsyncClient = fake  # type: ignore[assignment]
    try:
        assert await client.create_record({"名称": "某条例"}, table_id="tbl-1") is None
        # 返回体缺少 record_id 时同样视为失败
        module.httpx.AsyncClient = _FakeHttp(_json_response({"code": 0, "data": {}}))  # type: ignore[assignment]
        assert await client.create_record({"名称": "某条例"}, table_id="tbl-1") is None
    finally:
        module.httpx.AsyncClient = original


@pytest.mark.anyio
async def test_upload_media_success_and_failure() -> None:
    client = _client()
    assert await client.upload_media(b"", "empty.pdf") is None

    fake = _FakeHttp(
        _json_response(
            {"code": 0, "data": {"file_token": "file-tok"}},
            url=DRIVE_UPLOAD_URL,
        )
    )
    module = bitable_module
    original = module.httpx.AsyncClient
    module.httpx.AsyncClient = fake  # type: ignore[assignment]
    try:
        token = await client.upload_media(b"pdf-bytes", "条例.pdf")
        assert token == "file-tok"
        method, url, kwargs = fake.calls[0]
        assert method == "POST" and url == DRIVE_UPLOAD_URL
        assert kwargs["data"]["file_name"] == "条例.pdf"
        assert kwargs["data"]["size"] == str(len(b"pdf-bytes"))
        assert kwargs["files"]["file"][0] == "条例.pdf"

        module.httpx.AsyncClient = _FakeHttp(  # type: ignore[assignment]
            _json_response({"code": 99991672, "msg": "限流"}, url=DRIVE_UPLOAD_URL)
        )
        assert await client.upload_media(b"pdf-bytes", "条例.pdf") is None
    finally:
        module.httpx.AsyncClient = original


@pytest.mark.anyio
async def test_delete_record_success_and_failure() -> None:
    client = _client()
    fake = _FakeHttp(_json_response({"code": 0, "data": {}}))
    module = bitable_module
    original = module.httpx.AsyncClient
    module.httpx.AsyncClient = fake  # type: ignore[assignment]
    try:
        assert await client.delete_record("rec-1", table_id="tbl-1") is True
        method, url, kwargs = fake.calls[0]
        assert method == "DELETE"
        assert url == f"{BITABLE_BASE}/apps/app-token/tables/tbl-1/records/rec-1"
        assert kwargs["headers"]["Authorization"] == "Bearer tenant-token"

        module.httpx.AsyncClient = _FakeHttp(  # type: ignore[assignment]
            _json_response({"code": 1254005, "msg": "无权限"})
        )
        assert await client.delete_record("rec-1", table_id="tbl-1") is False
    finally:
        module.httpx.AsyncClient = original
