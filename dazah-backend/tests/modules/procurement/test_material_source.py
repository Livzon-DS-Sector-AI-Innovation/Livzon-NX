from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.modules.procurement import material_source
from app.modules.procurement.material_source import (
    MaterialSourceCredentialsError,
    MaterialSourcePermissionError,
    MaterialSourceTimeoutError,
)
from app.modules.procurement.models import MaterialSourceConfig
from app.modules.procurement.schemas import MaterialSourceConfigUpsert
from app.platform.identity.public_api import FeishuAppCredentials


def _payload() -> MaterialSourceConfigUpsert:
    return MaterialSourceConfigUpsert(
        source_url=(
            "https://feishu.cn/base/appToken123456?table=tbl123456&view=vew123456"
        )
    )


def _config(field_type: int | None = 1) -> MaterialSourceConfig:
    return MaterialSourceConfig(
        id=uuid4(),
        source_url=_payload().source_url,
        app_token="appToken123456",
        table_id="tbl123456",
        view_id="vew123456",
        material_code_field="物料编码",
        material_code_field_type=field_type,
        material_description_field="物料说明",
        rule_model_field="规则型号",
        last_test_status="success",
    )


@pytest.mark.anyio
async def test_probe_accepts_legacy_specification_field(monkeypatch) -> None:
    monkeypatch.setattr(
        material_source,
        "get_platform_feishu_app_credentials",
        AsyncMock(return_value=FeishuAppCredentials("app-id", "app-secret")),
    )

    class FakeBitableClient:
        def __init__(self, **kwargs) -> None:
            assert kwargs["app_id"] == "app-id"
            assert kwargs["app_secret"] == "app-secret"

        async def list_fields(self, table_id):
            assert table_id == "tbl123456"
            return [
                {"field_name": "物料编码", "type": 1},
                {"field_name": "物料说明", "type": 1},
                {"field_name": "规则型号", "type": 1},
            ]

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    probe = await material_source.probe_material_source(AsyncMock(), _payload())

    assert probe.rule_model_field == "规则型号"
    assert probe.material_code_field_type == 1
    assert probe.status == "success"
    assert probe.view_id == "vew123456"


@pytest.mark.anyio
async def test_list_material_options_converts_field_shapes_and_keeps_duplicates(
    monkeypatch,
) -> None:
    config = _config()
    monkeypatch.setattr(
        material_source,
        "get_material_source_config",
        AsyncMock(return_value=config),
    )
    monkeypatch.setattr(
        material_source,
        "_get_credentials",
        AsyncMock(return_value=FeishuAppCredentials("app-id", "app-secret")),
    )
    cache_get = AsyncMock(return_value=None)
    cache_set = AsyncMock()
    monkeypatch.setattr(material_source, "cache_get", cache_get)
    monkeypatch.setattr(material_source, "cache_set", cache_set)

    class FakeBitableClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def search_records(self, table_id, **kwargs):
            assert table_id == "tbl123456"
            assert kwargs["view_id"] == "vew123456"
            assert kwargs["filter_info"] == {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": "物料编码",
                        "operator": "contains",
                        "value": ["MAT"],
                    }
                ],
            }
            return [
                {
                    "record_id": "rec-1",
                    "fields": {
                        "物料编码": [{"text": "MAT-001"}],
                        "物料说明": {"value": [{"text": "第一条"}]},
                        "规则型号": "A",
                    },
                },
                {
                    "record_id": "rec-2",
                    "fields": {
                        "物料编码": "MAT-001",
                        "物料说明": [{"text": "第二条"}],
                        "规则型号": {"text": "B"},
                    },
                },
            ]

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    options = await material_source.list_material_options(
        AsyncMock(), keyword="MAT", limit=20
    )

    assert options == [
        {
            "record_id": "rec-1",
            "material_code": "MAT-001",
            "material_description": "第一条",
            "rule_model": "A",
        },
        {
            "record_id": "rec-2",
            "material_code": "MAT-001",
            "material_description": "第二条",
            "rule_model": "B",
        },
    ]
    cache_set.assert_awaited_once()
    assert cache_set.await_args.kwargs["ex"] == 60


@pytest.mark.anyio
async def test_number_material_code_uses_paginated_client_filter(
    monkeypatch,
) -> None:
    config = _config(field_type=None)
    monkeypatch.setattr(
        material_source,
        "get_material_source_config",
        AsyncMock(return_value=config),
    )
    monkeypatch.setattr(
        material_source,
        "_get_credentials",
        AsyncMock(return_value=FeishuAppCredentials("app-id", "app-secret")),
    )
    monkeypatch.setattr(material_source, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(material_source, "cache_set", AsyncMock())
    pages = [
        {
            "items": [
                {
                    "record_id": "rec-1",
                    "fields": {
                        "物料编码": 15,
                        "物料说明": "第一条",
                        "规则型号": "A",
                    },
                },
                {
                    "record_id": "rec-no-match",
                    "fields": {"物料编码": 42},
                },
            ],
            "has_more": True,
            "page_token": "next-page",
        },
        {
            "items": [
                {
                    "record_id": "rec-2",
                    "fields": {
                        "物料编码": 51,
                        "物料说明": "第二条",
                        "规则型号": "B",
                    },
                }
            ],
            "has_more": False,
            "page_token": None,
        },
    ]

    class FakeBitableClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def list_fields(self, table_id):
            assert table_id == "tbl123456"
            return [{"field_name": "物料编码", "type": 2}]

        async def search_records(self, *_args, **_kwargs):
            raise AssertionError("number fields must not use contains")

        async def search_records_page(self, table_id, **kwargs):
            assert table_id == "tbl123456"
            assert kwargs["view_id"] == "vew123456"
            assert kwargs["field_names"] == ["物料编码", "物料说明", "规则型号"]
            expected_token = None if len(pages) == 2 else "next-page"
            assert kwargs["page_token"] == expected_token
            return pages.pop(0)

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    db = AsyncMock()
    options = await material_source.list_material_options(
        db,
        keyword="5",
        limit=20,
    )

    assert options == [
        {
            "record_id": "rec-1",
            "material_code": "15",
            "material_description": "第一条",
            "rule_model": "A",
        },
        {
            "record_id": "rec-2",
            "material_code": "51",
            "material_description": "第二条",
            "rule_model": "B",
        },
    ]
    assert config.material_code_field_type == 2
    db.flush.assert_awaited_once()


@pytest.mark.anyio
async def test_material_options_uses_cache_and_survives_redis_failure(
    monkeypatch,
) -> None:
    config = _config()
    options = [
        {
            "record_id": "rec-1",
            "material_code": "MAT-001",
            "material_description": "已缓存",
            "rule_model": "A",
        }
    ]
    monkeypatch.setattr(
        material_source,
        "get_material_source_config",
        AsyncMock(return_value=config),
    )
    monkeypatch.setattr(
        material_source,
        "_get_credentials",
        AsyncMock(return_value=FeishuAppCredentials("app-id", "app-secret")),
    )
    monkeypatch.setattr(
        material_source,
        "cache_get",
        AsyncMock(return_value=material_source.json.dumps(options)),
    )
    cached_search_records = AsyncMock()

    class FakeBitableClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def search_records(self, *_args, **_kwargs):
            return await cached_search_records()

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    assert await material_source.list_material_options(
        AsyncMock(), keyword="MAT"
    ) == options
    cached_search_records.assert_not_awaited()

    async def redis_down(_key):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(material_source, "cache_get", redis_down)
    search_records = AsyncMock(return_value=[])

    class SearchableBitableClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def search_records(self, *_args, **_kwargs):
            return await search_records()

    monkeypatch.setattr(material_source, "BitableClient", SearchableBitableClient)
    monkeypatch.setattr(material_source, "cache_set", AsyncMock())
    assert await material_source.list_material_options(
        AsyncMock(), keyword="MAT"
    ) == []
    search_records.assert_awaited_once()


@pytest.mark.anyio
async def test_external_errors_are_mapped_without_raw_response() -> None:
    async def timeout():
        raise httpx.ReadTimeout("secret response should not leak")

    with pytest.raises(MaterialSourceTimeoutError, match="请求超时"):
        await material_source._run_feishu("search", timeout)

    request = httpx.Request("GET", "https://example.invalid")
    response = httpx.Response(403, request=request)

    async def forbidden():
        raise httpx.HTTPStatusError(
            "raw third party body",
            request=request,
            response=response,
        )

    with pytest.raises(MaterialSourcePermissionError, match="无权访问") as exc_info:
        await material_source._run_feishu("fields", forbidden)
    assert "raw third party body" not in str(exc_info.value)

    async def no_credentials(_db):
        raise RuntimeError("decrypt failed")

    original = material_source.get_platform_feishu_app_credentials
    material_source.get_platform_feishu_app_credentials = no_credentials
    try:
        with pytest.raises(MaterialSourceCredentialsError):
            await material_source._get_credentials(AsyncMock())
    finally:
        material_source.get_platform_feishu_app_credentials = original
