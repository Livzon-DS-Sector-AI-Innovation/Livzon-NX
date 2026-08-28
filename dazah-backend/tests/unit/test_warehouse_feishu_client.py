from typing import Any

import pytest

from app.modules.warehouse import feishu_client as module
from app.modules.warehouse.feishu_client import (
    TOKEN_TTL_SECONDS,
    WarehouseFeishuClient,
)


class FakeRedis:
    def __init__(self: Any) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self: Any, key: str) -> str | None:
        return self.values.get(key)  # type: ignore[no-any-return]

    async def set(self: Any, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True


class FakeResponse:
    def __init__(self: Any, body: dict[str, Any], status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self: Any) -> None:
        if self.status_code >= 400:
            raise AssertionError("飞书业务错误应在 HTTP 状态检查前转换")
        return None

    def json(self: Any) -> dict[str, Any]:
        return self.body  # type: ignore[no-any-return]


class FakeAsyncClient:
    token_calls = 0
    request_calls: list[tuple[str, str, dict[str, Any] | None]] = []
    request_bodies: list[dict[str, Any] | None] = []
    response_override: FakeResponse | None = None

    def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
        return None

    async def __aenter__(self: Any) -> "FakeAsyncClient":
        return self  # type: ignore[no-any-return]

    async def __aexit__(self: Any, *args: Any) -> None:
        return None

    async def post(self: Any, path: str, json: dict[str, Any]) -> FakeResponse:
        FakeAsyncClient.token_calls += 1
        return FakeResponse({"code": 0, "tenant_access_token": "tenant-token"})

    async def request(
        self: Any,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        FakeAsyncClient.request_calls.append((method, path, params or json))
        FakeAsyncClient.request_bodies.append(json)
        if FakeAsyncClient.response_override is not None:
            return FakeAsyncClient.response_override
        if path.endswith("/tables") and not params.get("page_token"):  # type: ignore[union-attr]
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
    fake_redis: Any = FakeRedis()
    FakeAsyncClient.token_calls = 0
    FakeAsyncClient.request_calls = []
    FakeAsyncClient.request_bodies = []
    FakeAsyncClient.response_override = None
    monkeypatch.setattr(module, "redis_client", fake_redis)
    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)  # type: ignore[attr-defined]
    return fake_redis  # type: ignore[no-any-return]


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
async def test_tenant_token_cache_changes_when_secret_changes() -> None:
    first_client = WarehouseFeishuClient(
        app_id="cli_123",
        app_secret="old-secret",
        app_token="base_token",
    )
    second_client = WarehouseFeishuClient(
        app_id="cli_123",
        app_secret="new-secret",
        app_token="base_token",
    )

    await first_client.get_tenant_access_token()
    await second_client.get_tenant_access_token()

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
async def test_feishu_http_error_preserves_business_message() -> None:
    FakeAsyncClient.response_override = FakeResponse(
        {"code": 1254040, "msg": "app_token invalid"},
        status_code=400,
    )
    client = WarehouseFeishuClient(
        app_id="cli_123",
        app_secret="secret",
        app_token="invalid_base_token",
    )

    with pytest.raises(RuntimeError, match="app_token invalid"):
        await client.list_tables()

    assert FakeAsyncClient.token_calls == 1
    assert len(FakeAsyncClient.request_calls) == 1


@pytest.mark.asyncio
async def test_invalid_access_token_forces_one_token_refresh() -> None:
    FakeAsyncClient.response_override = FakeResponse(
        {"code": 99991663, "msg": "Invalid access token for authorization."},
        status_code=400,
    )
    client = WarehouseFeishuClient(
        app_id="cli_123",
        app_secret="secret",
        app_token="base_token",
    )

    with pytest.raises(RuntimeError, match="Invalid access token"):
        await client.list_tables()

    assert FakeAsyncClient.token_calls == 2
    assert len(FakeAsyncClient.request_calls) == 2


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
