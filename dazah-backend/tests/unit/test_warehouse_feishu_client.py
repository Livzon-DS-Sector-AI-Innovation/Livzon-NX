from typing import Any

import pytest

from app.modules.warehouse import feishu_client as module
from app.modules.warehouse.feishu_client import (
    TOKEN_TTL_SECONDS,
    WarehouseFeishuClient,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True


class FakeResponse:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.body


class FakeAsyncClient:
    token_calls = 0
    request_calls: list[tuple[str, str, dict[str, Any] | None]] = []
    request_bodies: list[dict[str, Any] | None] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(self, path: str, json: dict[str, Any]) -> FakeResponse:
        FakeAsyncClient.token_calls += 1
        return FakeResponse({"code": 0, "tenant_access_token": "tenant-token"})

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        FakeAsyncClient.request_calls.append((method, path, params or json))
        FakeAsyncClient.request_bodies.append(json)
        if path.endswith("/tables") and not params.get("page_token"):
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [{"table_id": "tbl1", "name": "表1"}],
                        "has_more": True,
                        "page_token": "next",
                    },
                }
            )
        if path.endswith("/tables"):
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [{"table_id": "tbl2", "name": "表2"}],
                        "has_more": False,
                    },
                }
            )
        if path.endswith("/records/search"):
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [{"record_id": "rec1", "fields": {"名称": "A"}}],
                        "has_more": False,
                        "total": 1,
                    },
                }
            )
        return FakeResponse({"code": 0, "data": {}})


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    fake_redis = FakeRedis()
    FakeAsyncClient.token_calls = 0
    FakeAsyncClient.request_calls = []
    FakeAsyncClient.request_bodies = []
    monkeypatch.setattr(module, "redis_client", fake_redis)
    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)
    return fake_redis


@pytest.mark.asyncio
async def test_tenant_token_is_cached_for_90_minutes(
    patch_dependencies: FakeRedis,
) -> None:
    client = WarehouseFeishuClient(
        app_id="cli_123",
        app_secret="secret",
        app_token="base_token",
    )

    first = await client.get_tenant_access_token()
    second = await client.get_tenant_access_token()

    assert first == "tenant-token"
    assert second == "tenant-token"
    assert FakeAsyncClient.token_calls == 1
    assert list(patch_dependencies.ttls.values()) == [TOKEN_TTL_SECONDS]


@pytest.mark.asyncio
async def test_tenant_token_force_refresh_overwrites_cache() -> None:
    client = WarehouseFeishuClient(
        app_id="cli_123",
        app_secret="secret",
        app_token="base_token",
    )

    await client.get_tenant_access_token()
    await client.get_tenant_access_token(force_refresh=True)

    assert FakeAsyncClient.token_calls == 2


@pytest.mark.asyncio
async def test_list_tables_reads_all_pages() -> None:
    client = WarehouseFeishuClient(
        app_id="cli_123",
        app_secret="secret",
        app_token="base_token",
    )

    tables = await client.list_tables()

    assert [item["table_id"] for item in tables] == ["tbl1", "tbl2"]


@pytest.mark.asyncio
async def test_search_records_returns_raw_items() -> None:
    client = WarehouseFeishuClient(
        app_id="cli_123",
        app_secret="secret",
        app_token="base_token",
    )

    result = await client.search_records("tbl1")

    assert result["items"] == [{"record_id": "rec1", "fields": {"名称": "A"}}]
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_search_records_sends_pagination_in_query_params() -> None:
    client = WarehouseFeishuClient(
        app_id="cli_123",
        app_secret="secret",
        app_token="base_token",
    )

    await client.search_records("tbl1", page_size=500, page_token="next-page")

    method, path, params = FakeAsyncClient.request_calls[-1]
    assert method == "POST"
    assert path.endswith("/records/search")
    assert params == {"page_size": 500, "page_token": "next-page"}
    assert FakeAsyncClient.request_bodies[-1] == {}
