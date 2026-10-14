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


# ── 带错误信息的结果方法与 list_tables ──


class _QueueHttp:
    """按调用顺序消费响应队列；post/get 各自一条队列。"""

    def __init__(
        self,
        post_responses: list[httpx.Response],
        get_responses: list[httpx.Response] | None = None,
    ) -> None:
        self.post_queue = list(post_responses)
        self.get_queue = list(get_responses or [])
        self.posts: list[str] = []
        self.gets: list[str] = []

    def __call__(self, *args: Any, **kwargs: Any) -> "_QueueHttp":
        return self

    async def __aenter__(self) -> "_QueueHttp":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.posts.append(url)
        return self.post_queue.pop(0)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        self.posts.append(url)
        return self.post_queue.pop(0)

    async def get(
        self, url: str, params: Any = None, headers: Any = None
    ) -> httpx.Response:
        self.gets.append(url)
        return self.get_queue.pop(0)


def _payload(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200, json=payload, request=httpx.Request("POST", BITABLE_BASE)
    )


def _swap_http(fake: _QueueHttp) -> Any:
    original = bitable_module.httpx.AsyncClient
    bitable_module.httpx.AsyncClient = fake  # type: ignore[assignment]
    return original


@pytest.mark.anyio
async def test_update_record_with_result_reports_feishu_error() -> None:
    client = _client()
    # 空字段视为成功（无可写内容）
    assert await client.update_record("rec-1", {}) is True

    fake = _QueueHttp(
        [
            _payload({"code": 1254040, "msg": "FieldNameNotFound"}),
            _payload({"code": 1254040, "msg": "FieldNameNotFound"}),
        ]
    )
    original = _swap_http(fake)
    try:
        ok, message = await client.update_record_with_result(
            "rec-1", {"名称": "x"}, table_id="tbl-1"
        )
        assert ok is False and message == "FieldNameNotFound"
        # update_record 保留布尔语义，失败返回 False
        assert await client.update_record("rec-1", {"名称": "x"}) is False
    finally:
        bitable_module.httpx.AsyncClient = original


@pytest.mark.anyio
async def test_search_records_with_result_paginates_and_reports_errors() -> None:
    client = _client()
    # 第一页报错：返回已聚合的空列表与错误信息
    error_fake = _QueueHttp([_payload({"code": 91402, "msg": "NOTEXIST"})])
    original = _swap_http(error_fake)
    try:
        rows, error = await client.search_records_with_result(
            "tbl-1", filter_str='CurrentValue.[记录编号]="YH-1"'
        )
        assert rows == [] and error == "NOTEXIST"
    finally:
        bitable_module.httpx.AsyncClient = original

    # 两页翻页：第二页 has_more=False 收尾
    def _page_one() -> httpx.Response:
        return _payload(
            {
                "code": 0,
                "data": {
                    "items": [{"record_id": "rec-1", "fields": {}}],
                    "page_token": "p2",
                    "has_more": True,
                },
            }
        )

    def _page_two() -> httpx.Response:
        return _payload(
            {"code": 0, "data": {"items": [{"record_id": "rec-2"}], "has_more": False}}
        )

    ok_fake = _QueueHttp([_page_one(), _page_two(), _page_one(), _page_two()])
    original = _swap_http(ok_fake)
    try:
        rows, error = await client.search_records_with_result("tbl-1", page_size=1)
        assert error is None
        assert [row["record_id"] for row in rows] == ["rec-1", "rec-2"]
        assert len(ok_fake.posts) == 2
        # search_records 复用带结果版本，只取列表
        assert await client.search_records("tbl-1") == rows
    finally:
        bitable_module.httpx.AsyncClient = original


@pytest.mark.anyio
async def test_list_tables_paginates_and_requires_app_token() -> None:
    # 未提供 app_token 且客户端未绑定 → 空列表
    empty_client = SafetyBitableClient()
    empty_client._token = AsyncMock(return_value="t")  # type: ignore[method-assign]
    assert await empty_client.list_tables() == []

    client = _client()
    fake = _QueueHttp(
        [],
        [
            _payload(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {"table_id": "tblA", "name": "A"},
                            {"name": "缺 id"},
                        ],
                        "page_token": "p2",
                        "has_more": True,
                    },
                }
            ),
            _payload(
                {"code": 0, "data": {"items": [{"table_id": "tblB", "name": "B"}]}}
            ),
        ],
    )
    original = _swap_http(fake)
    try:
        tables = await client.list_tables("app-token")
        assert [table.get("table_id") for table in tables] == ["tblA", None, "tblB"]
        assert len(fake.gets) == 2

        fake.get_queue.append(_payload({"code": 91403, "msg": "forbidden"}))
        assert await client.list_tables("app-token") == []
    finally:
        bitable_module.httpx.AsyncClient = original
