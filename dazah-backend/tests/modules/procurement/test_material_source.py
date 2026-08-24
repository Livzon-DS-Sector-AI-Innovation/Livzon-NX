from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.modules.procurement import material_source
from app.modules.procurement.material_source import (
    MaterialSourceCredentialsError,
    MaterialSourcePermissionError,
    MaterialSourceTimeoutError,
    MaterialSourceUpstreamError,
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
        material_unit_field="主要单位",
        material_template_field="物料模板",
        material_category_field="物料大类",
        material_subcategory_field="物料小类",
        material_cost_category_field="物料成本大类",
        last_test_status="success",
    )


@pytest.mark.anyio
async def test_probe_accepts_legacy_specification_field(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        material_source,
        "get_platform_feishu_app_credentials",
        AsyncMock(return_value=FeishuAppCredentials("app-id", "app-secret")),
    )

    class FakeBitableClient:
        def __init__(self: Any, **kwargs: Any) -> None:
            assert kwargs["app_id"] == "app-id"
            assert kwargs["app_secret"] == "app-secret"

        async def list_fields(self: Any, table_id: Any) -> Any:
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
    monkeypatch: Any,
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
    cache_get: Any = AsyncMock(return_value=None)
    cache_set: Any = AsyncMock()
    monkeypatch.setattr(material_source, "cache_get", cache_get)
    monkeypatch.setattr(material_source, "cache_set", cache_set)

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def search_records(self: Any, table_id: Any, **kwargs: Any) -> Any:
            assert table_id == "tbl123456"
            assert kwargs["view_id"] == "vew123456"
            condition = kwargs["filter_info"]["conditions"][0]
            assert condition["field_name"] == "物料编码"
            assert condition["value"] == ["MAT"]
            if condition["operator"] == "is":
                return []
            assert condition["operator"] == "contains"
            return [
                {
                    "record_id": "rec-1",
                    "fields": {
                        "物料编码": [{"text": "MAT-001"}],
                        "物料说明": {"value": [{"text": "第一条"}]},
                        "规则型号": "A",
                        "主要单位": [{"text": "件"}],
                        "物料模板": "模板A",
                        "物料大类": {"text": "五金"},
                        "物料小类": {"value": ["螺丝"]},
                        "物料成本大类": "成本A",
                    },
                },
                {
                    "record_id": "rec-2",
                    "fields": {
                        "物料编码": "MAT-001",
                        "物料说明": [{"text": "第二条"}],
                        "规则型号": {"text": "B"},
                        "主要单位": {"value": [{"text": "箱"}]},
                        "物料模板": "模板B",
                        "物料大类": "化工",
                        "物料小类": {"text": "溶剂"},
                        "物料成本大类": "成本B",
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
            "material_unit": "件",
            "material_template": "模板A",
            "material_category": "五金",
            "material_subcategory": "螺丝",
            "material_cost_category": "成本A",
        },
        {
            "record_id": "rec-2",
            "material_code": "MAT-001",
            "material_description": "第二条",
            "rule_model": "B",
            "material_unit": "箱",
            "material_template": "模板B",
            "material_category": "化工",
            "material_subcategory": "溶剂",
            "material_cost_category": "成本B",
        },
    ]
    cache_set.assert_awaited_once()
    assert cache_set.await_args.kwargs["ex"] == 60


@pytest.mark.anyio
async def test_number_material_code_uses_paginated_client_filter(
    monkeypatch: Any,
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
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def list_fields(self: Any, table_id: Any) -> Any:
            assert table_id == "tbl123456"
            return [{"field_name": "物料编码", "type": 2}]

        async def search_records(self: Any, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("number fields must not use contains")

        async def search_records_page(self: Any, table_id: Any, **kwargs: Any) -> Any:
            assert table_id == "tbl123456"
            assert kwargs["view_id"] == "vew123456"
            assert kwargs["field_names"] == [
                "物料编码",
                "物料说明",
                "规则型号",
                "主要单位",
                "物料模板",
                "物料大类",
                "物料小类",
                "物料成本大类",
            ]
            expected_token = None if len(pages) == 2 else "next-page"
            assert kwargs["page_token"] == expected_token
            return pages.pop(0)

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    db: Any = AsyncMock()
    options = await material_source.list_material_options(
        db,
        keyword="5",
        limit=20,
    )

    # Prefix matches ("51") rank above plain contains hits ("15"), matching
    # the ordering the frontend applies to the same options.
    assert options == [
        {
            "record_id": "rec-2",
            "material_code": "51",
            "material_description": "第二条",
            "rule_model": "B",
            "material_unit": "",
            "material_template": "",
            "material_category": "",
            "material_subcategory": "",
            "material_cost_category": "",
        },
        {
            "record_id": "rec-1",
            "material_code": "15",
            "material_description": "第一条",
            "rule_model": "A",
            "material_unit": "",
            "material_template": "",
            "material_category": "",
            "material_subcategory": "",
            "material_cost_category": "",
        },
    ]
    assert config.material_code_field_type == 2
    db.flush.assert_awaited_once()


def _material_options_harness(monkeypatch: Any, field_type: int | None = 1) -> Any:
    config = _config(field_type=field_type)
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
    return config


def _option_record(
    record_id: str, code: str, description: str = "物料"
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "fields": {
            "物料编码": code,
            "物料说明": description,
            "规则型号": "A",
            "主要单位": "件",
            "物料模板": "模板A",
            "物料大类": "五金",
            "物料小类": "螺丝",
            "物料成本大类": "成本A",
        },
    }


@pytest.mark.anyio
async def test_text_options_keep_exact_match_above_limit_truncation(
    monkeypatch: Any,
) -> None:
    _material_options_harness(monkeypatch)

    records = [
        _option_record(f"rec-broad-{i}", f"MAT-001-EXT-{i}", f"扩展{i}")
        for i in range(20)
    ]
    # The exact record is the last one the API returns; the old page cut of
    # `limit` records would have dropped it entirely.
    records.append(_option_record("rec-exact", "MAT-001", "精确物料"))

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def search_records(self: Any, table_id: Any, **kwargs: Any) -> Any:
            assert table_id == "tbl123456"
            operator = kwargs["filter_info"]["conditions"][0]["operator"]
            if operator == "is":
                assert kwargs["page_size"] == 20
                return [_option_record("rec-exact", "MAT-001", "精确物料")]
            assert operator == "contains"
            assert kwargs["page_size"] == 100
            return records

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    options = await material_source.list_material_options(
        AsyncMock(), keyword="MAT-001", limit=20
    )

    assert len(options) == 20
    assert options[0] == {
        "record_id": "rec-exact",
        "material_code": "MAT-001",
        "material_description": "精确物料",
        "rule_model": "A",
        "material_unit": "件",
        "material_template": "模板A",
        "material_category": "五金",
        "material_subcategory": "螺丝",
        "material_cost_category": "成本A",
    }
    assert {item["record_id"] for item in options[1:]} == {
        f"rec-broad-{i}" for i in range(19)
    }


@pytest.mark.anyio
async def test_options_prefer_exact_then_prefix_then_contains(monkeypatch: Any) -> None:
    _material_options_harness(monkeypatch)

    records = [
        _option_record("rec-contains", "X-MAT-001", "包含型"),
        _option_record("rec-exact", "MAT-001", "精确型"),
        _option_record("rec-prefix", "MAT-001-EXT", "前缀型"),
        _option_record("rec-other", "MAT-002", "其他"),
    ]

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def search_records(self: Any, table_id: Any, **kwargs: Any) -> Any:
            assert table_id == "tbl123456"
            operator = kwargs["filter_info"]["conditions"][0]["operator"]
            if operator == "is":
                return [_option_record("rec-exact", "MAT-001", "精确型")]
            assert operator == "contains"
            return records

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    options = await material_source.list_material_options(
        AsyncMock(), keyword="MAT-001", limit=20
    )

    assert [item["record_id"] for item in options] == [
        "rec-exact",
        "rec-prefix",
        "rec-contains",
        "rec-other",
    ]


@pytest.mark.anyio
async def test_number_options_keep_exact_match_across_pages(monkeypatch: Any) -> None:
    config = _material_options_harness(monkeypatch, field_type=None)
    pages = [
        {
            "items": [
                _option_record(f"rec-broad-{i}", 500 + i, f"扩展{i}")  # type: ignore[arg-type]
                for i in range(5)
            ],
            "has_more": True,
            "page_token": "next-page",
        },
        {
            "items": [_option_record("rec-exact", 50, "精确物料")],  # type: ignore[arg-type]
            "has_more": False,
            "page_token": None,
        },
    ]

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def list_fields(self: Any, table_id: Any) -> Any:
            assert table_id == "tbl123456"
            return [{"field_name": "物料编码", "type": 2}]

        async def search_records(self: Any, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("number fields must not use contains")

        async def search_records_page(self: Any, table_id: Any, **kwargs: Any) -> Any:
            assert table_id == "tbl123456"
            assert kwargs["view_id"] == "vew123456"
            assert kwargs["field_names"] == [
                "物料编码",
                "物料说明",
                "规则型号",
                "主要单位",
                "物料模板",
                "物料大类",
                "物料小类",
                "物料成本大类",
            ]
            expected_token = None if len(pages) == 2 else "next-page"
            assert kwargs["page_token"] == expected_token
            return pages.pop(0)

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    options = await material_source.list_material_options(
        AsyncMock(), keyword="50", limit=5
    )

    # The first page alone already matched the old `limit` cut; the exact
    # record on the second page must still win and stay on top.
    assert len(options) == 5
    assert options[0]["record_id"] == "rec-exact"
    assert config.material_code_field_type == 2


@pytest.mark.anyio
async def test_number_options_exact_match_survives_fuzzy_collect_fill(
    monkeypatch: Any,
) -> None:
    config = _material_options_harness(monkeypatch, field_type=None)
    pages = [
        {
            "items": [
                _option_record(f"rec-fuzzy-{i}", 5000 + i, f"模糊{i}")  # type: ignore[arg-type]
                for i in range(100)
            ],
            "has_more": True,
            "page_token": "next-page",
        },
        {
            "items": [_option_record("rec-exact", 50, "精确物料")],  # type: ignore[arg-type]
            "has_more": False,
            "page_token": None,
        },
    ]

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def list_fields(self: Any, table_id: Any) -> Any:
            assert table_id == "tbl123456"
            return [{"field_name": "物料编码", "type": 2}]

        async def search_records(self: Any, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("number fields must not use contains")

        async def search_records_page(self: Any, table_id: Any, **kwargs: Any) -> Any:
            assert table_id == "tbl123456"
            expected_token = None if len(pages) == 2 else "next-page"
            assert kwargs["page_token"] == expected_token
            return pages.pop(0)

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    options = await material_source.list_material_options(
        AsyncMock(), keyword="50", limit=20
    )

    # The first page alone fills the fuzzy collection budget; the scan must
    # continue so the exact record on the second page is still returned.
    assert len(options) == 20
    assert options[0]["record_id"] == "rec-exact"
    assert {item["record_id"] for item in options} >= {
        "rec-exact",
        "rec-fuzzy-0",
    }
    assert config.material_code_field_type == 2


@pytest.mark.anyio
async def test_text_options_fall_back_when_exact_lookup_fails(monkeypatch: Any) -> None:
    _material_options_harness(monkeypatch)

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def search_records(self: Any, table_id: Any, **kwargs: Any) -> Any:
            assert table_id == "tbl123456"
            operator = kwargs["filter_info"]["conditions"][0]["operator"]
            if operator == "is":
                raise MaterialSourcePermissionError("飞书多维表格访问失败")
            assert operator == "contains"
            return [_option_record("rec-fuzzy", "MAT-001-EXT", "模糊型")]

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    options = await material_source.list_material_options(
        AsyncMock(), keyword="MAT", limit=20
    )

    # A failed equality lookup degrades to the fuzzy-only result instead of
    # taking the whole autocomplete down.
    assert [item["record_id"] for item in options] == ["rec-fuzzy"]


@pytest.mark.anyio
async def test_material_options_uses_cache_and_survives_redis_failure(
    monkeypatch: Any,
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
        AsyncMock(return_value=material_source.json.dumps(options)),  # type: ignore[attr-defined]
    )
    cached_search_records: Any = AsyncMock()

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def search_records(self: Any, *_args: Any, **_kwargs: Any) -> Any:
            return await cached_search_records()

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    assert (
        await material_source.list_material_options(AsyncMock(), keyword="MAT")
        == options
    )
    cached_search_records.assert_not_awaited()

    async def redis_down(_key: Any) -> Any:
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(material_source, "cache_get", redis_down)
    search_records: Any = AsyncMock(return_value=[])

    class SearchableBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def search_records(self: Any, *_args: Any, **_kwargs: Any) -> Any:
            return await search_records()

    monkeypatch.setattr(material_source, "BitableClient", SearchableBitableClient)
    monkeypatch.setattr(material_source, "cache_set", AsyncMock())
    assert await material_source.list_material_options(AsyncMock(), keyword="MAT") == []
    search_records.assert_awaited()


@pytest.mark.anyio
async def test_external_errors_are_mapped_without_raw_response() -> None:
    async def timeout() -> Any:
        raise httpx.ReadTimeout("secret response should not leak")

    with pytest.raises(MaterialSourceTimeoutError, match="请求超时"):
        await material_source._run_feishu("search", timeout)

    request = httpx.Request("GET", "https://example.invalid")
    response = httpx.Response(403, request=request)

    async def forbidden() -> Any:
        raise httpx.HTTPStatusError(
            "raw third party body",
            request=request,
            response=response,
        )

    with pytest.raises(MaterialSourcePermissionError, match="无权访问") as exc_info:
        await material_source._run_feishu("fields", forbidden)
    assert "raw third party body" not in str(exc_info.value)

    async def no_credentials(_db: Any) -> Any:
        raise RuntimeError("decrypt failed")

    original = material_source.get_platform_feishu_app_credentials  # type: ignore[attr-defined]
    material_source.get_platform_feishu_app_credentials = no_credentials  # type: ignore[attr-defined, assignment]
    try:
        with pytest.raises(MaterialSourceCredentialsError):
            await material_source._get_credentials(AsyncMock())
    finally:
        material_source.get_platform_feishu_app_credentials = original  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_feishu_api_business_errors_are_mapped_as_retryable() -> None:
    async def feishu_fail() -> Any:
        raise RuntimeError(
            "Feishu API error: code=1254002, msg=Fail, "
            "path=/bitable/v1/apps/x/tables/y/records/search"
        )

    with pytest.raises(MaterialSourceUpstreamError, match="暂时繁忙") as exc_info:
        await material_source._run_feishu("search", feishu_fail)
    assert "1254002" not in str(exc_info.value)
    assert "Fail" not in str(exc_info.value)

    async def rate_limited() -> Any:
        raise RuntimeError(
            "Feishu API error: code=99991600, msg=Rate limit, "
            "path=/bitable/v1/apps/x/tables/y/records/search"
        )

    with pytest.raises(MaterialSourceUpstreamError, match="暂时繁忙"):
        await material_source._run_feishu("search", rate_limited)

    async def other_business_error() -> Any:
        raise RuntimeError(
            "Feishu API error: code=91402, msg=permission denied, "
            "path=/bitable/v1/apps/x/tables/y/records/search"
        )

    with pytest.raises(MaterialSourcePermissionError):
        await material_source._run_feishu("search", other_business_error)


@pytest.mark.anyio
async def test_sync_backfills_optional_fields_for_legacy_config(
    monkeypatch: Any,
) -> None:
    """存量配置没有可选字段映射时，同步自动补全并继续，不要求重新保存。"""
    config = _config()
    config.material_unit_field = None
    config.material_template_field = None
    config.material_category_field = None
    config.material_subcategory_field = None
    config.material_cost_category_field = None
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
    upserted: list[dict[str, object]] = []

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def list_fields(self: Any, table_id: Any) -> Any:
            assert table_id == config.table_id
            return [
                {"field_name": "物料编码", "type": 1},
                {"field_name": "物料说明", "type": 1},
                {"field_name": "规则型号", "type": 1},
                {"field_name": "主要单位", "type": 1},
                {"field_name": "物料模板", "type": 1},
                {"field_name": "物料大类", "type": 1},
                {"field_name": "物料小类", "type": 1},
                {"field_name": "物料成本大类", "type": 1},
            ]

        async def search_records_page(self: Any, table_id: Any, **kwargs: Any) -> Any:
            assert table_id == config.table_id
            return {
                "items": [
                    {
                        "record_id": "rec-1",
                        "fields": {
                            "物料编码": "MAT-001",
                            "物料说明": "第一条",
                            "规则型号": "A",
                            "主要单位": "件",
                            "物料模板": "模板A",
                            "物料大类": "五金",
                            "物料小类": "螺丝",
                            "物料成本大类": "成本A",
                        },
                    }
                ],
                "has_more": False,
                "page_token": None,
                "total": 1,
            }

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)

    class FakeCatalogRepository:
        def __init__(self: Any, _db: Any) -> None:
            pass

        async def list_feishu_record_ids(self: Any, source_config_id: Any) -> Any:
            return set()

        async def bulk_upsert(self: Any, records: Any) -> Any:
            upserted.extend(records)
            return len(records)

        async def deactivate_missing(
            self: Any, source_config_id: Any, missing_record_ids: Any
        ) -> Any:
            return 0

    monkeypatch.setattr(
        material_source,
        "MaterialCatalogRepository",
        FakeCatalogRepository,
    )

    result = await material_source.sync_material_source(AsyncMock(), user_id=uuid4())

    assert result.synced_count == 1
    assert config.material_unit_field == "主要单位"
    assert config.material_template_field == "物料模板"
    assert config.material_category_field == "物料大类"
    assert config.material_subcategory_field == "物料小类"
    assert config.material_cost_category_field == "物料成本大类"
    assert upserted[0]["material_unit"] == "件"
    assert upserted[0]["material_cost_category"] == "成本A"


@pytest.mark.anyio
async def test_sync_reads_all_pages_and_updates_the_local_material_mirror(
    monkeypatch: Any,
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

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def list_fields(self: Any, table_id: Any) -> Any:
            assert table_id == config.table_id
            return [
                {"field_name": "物料编码", "type": 1},
                {"field_name": "物料说明", "type": 1},
                {"field_name": "规则型号", "type": 1},
                {"field_name": "主要单位", "type": 1},
                {"field_name": "物料模板", "type": 1},
                {"field_name": "物料大类", "type": 1},
                {"field_name": "物料小类", "type": 1},
                {"field_name": "物料成本大类", "type": 1},
            ]

        async def search_records_page(self: Any, table_id: Any, **kwargs: Any) -> Any:
            assert table_id == config.table_id
            assert kwargs["field_names"] == [
                "物料编码",
                "物料说明",
                "规则型号",
                "主要单位",
                "物料模板",
                "物料大类",
                "物料小类",
                "物料成本大类",
            ]
            assert (
                kwargs["timeout"] == material_source.MATERIAL_SYNC_PAGE_TIMEOUT_SECONDS
            )
            if kwargs["page_token"] is None:
                return {
                    "items": [
                        {
                            "record_id": "rec-1",
                            "created_time": 100,
                            "last_modified_time": 200,
                            "fields": {
                                "物料编码": "MAT-001",
                                "物料说明": "第一条",
                                "规则型号": "A",
                                "主要单位": "件",
                                "物料模板": "模板A",
                                "物料大类": "五金",
                                "物料小类": "螺丝",
                                "物料成本大类": "成本A",
                            },
                        }
                    ],
                    "has_more": True,
                    "page_token": "page-2",
                    "total": 2,
                }
            return {
                "items": [
                    {
                        "record_id": "rec-2",
                        "fields": {
                            "物料编码": [{"text": "MAT-002"}],
                            "物料说明": "第二条",
                            "规则型号": {"text": "B"},
                            "主要单位": [{"text": "箱"}],
                            "物料模板": "模板B",
                            "物料大类": "化工",
                            "物料小类": {"text": "溶剂"},
                            "物料成本大类": "成本B",
                        },
                    }
                ],
                "has_more": False,
                "page_token": None,
                "total": 2,
            }

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)

    upserted: list[Any] = []
    deactivated: Any = AsyncMock(return_value=0)

    class FakeCatalogRepository:
        def __init__(self: Any, _db: Any) -> None:
            pass

        async def list_feishu_record_ids(self: Any, source_config_id: Any) -> Any:
            assert source_config_id == config.id
            return {"rec-0"}

        async def bulk_upsert(self: Any, records: Any) -> Any:
            upserted.extend(records)

        async def deactivate_missing(
            self: Any, source_config_id: Any, missing_record_ids: Any
        ) -> Any:
            await deactivated(source_config_id, missing_record_ids)
            return 0

    monkeypatch.setattr(
        material_source,
        "MaterialCatalogRepository",
        FakeCatalogRepository,
    )
    db: Any = AsyncMock()

    result = await material_source.sync_material_source(db, user_id=uuid4())

    assert result.synced_count == 2
    assert result.deactivated_count == 0
    assert config.sync_status == "success"
    assert config.last_sync_record_count == 2
    assert config.sync_total_records == 2
    assert config.sync_fetched_count == 2
    assert [(item["feishu_record_id"], item["material_code"]) for item in upserted] == [
        ("rec-1", "MAT-001"),
        ("rec-2", "MAT-002"),
    ]
    assert [
        (item["material_unit"], item["material_cost_category"]) for item in upserted
    ] == [
        ("件", "成本A"),
        ("箱", "成本B"),
    ]
    assert all(item["is_deleted"] is False for item in upserted)
    deactivated.assert_awaited_once_with(config.id, ["rec-0"])
    # 初始状态、每次分页请求前心跳、每页持久化、收尾和成功提交
    assert db.commit.await_count == 7


@pytest.mark.anyio
async def test_sync_publishes_progress_after_each_fetched_page(
    monkeypatch: Any,
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
    pages = [
        {
            "items": [
                {
                    "record_id": f"rec-{index}",
                    "fields": {
                        "物料编码": f"MAT-{index:03d}",
                        "物料说明": "",
                        "规则型号": "",
                    },
                }
                for index in range(2)
            ],
            "has_more": True,
            "page_token": "page-2",
            "total": 6,
        },
        {
            "items": [
                {
                    "record_id": f"rec-{index}",
                    "fields": {
                        "物料编码": f"MAT-{index:03d}",
                        "物料说明": "",
                        "规则型号": "",
                    },
                }
                for index in range(2, 4)
            ],
            "has_more": True,
            "page_token": "page-3",
            "total": 6,
        },
        {
            "items": [
                {
                    "record_id": f"rec-{index}",
                    "fields": {
                        "物料编码": f"MAT-{index:03d}",
                        "物料说明": "",
                        "规则型号": "",
                    },
                }
                for index in range(4, 6)
            ],
            "has_more": False,
            "page_token": None,
            "total": 6,
        },
    ]
    observed: list[tuple[int, int | None]] = []

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def list_fields(self: Any, table_id: Any) -> Any:
            assert table_id == config.table_id
            return [
                {"field_name": "物料编码", "type": 1},
                {"field_name": "物料说明", "type": 1},
                {"field_name": "规则型号", "type": 1},
                {"field_name": "主要单位", "type": 1},
                {"field_name": "物料模板", "type": 1},
                {"field_name": "物料大类", "type": 1},
                {"field_name": "物料小类", "type": 1},
                {"field_name": "物料成本大类", "type": 1},
            ]

        async def search_records_page(self: Any, table_id: Any, **kwargs: Any) -> Any:
            assert table_id == config.table_id
            assert (
                kwargs["timeout"] == material_source.MATERIAL_SYNC_PAGE_TIMEOUT_SECONDS
            )
            observed.append((config.sync_fetched_count, config.sync_total_records))  # type: ignore[arg-type]
            return pages.pop(0)

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)

    class FakeCatalogRepository:
        def __init__(self: Any, _db: Any) -> None:
            pass

        async def list_feishu_record_ids(self: Any, source_config_id: Any) -> Any:
            return set()

        async def bulk_upsert(self: Any, records: Any) -> Any:
            return len(records)

        async def deactivate_missing(
            self: Any, source_config_id: Any, missing_record_ids: Any
        ) -> Any:
            return 0

    monkeypatch.setattr(
        material_source,
        "MaterialCatalogRepository",
        FakeCatalogRepository,
    )
    db: Any = AsyncMock()
    await material_source.sync_material_source(db, user_id=uuid4())

    assert observed == [(0, None), (2, 6), (4, 6)]
    assert config.sync_fetched_count == 6
    assert config.sync_total_records == 6
    assert db.commit.await_count == 9


@pytest.mark.anyio
async def test_reset_interrupted_syncs_marks_stale_as_error(monkeypatch: Any) -> None:
    config = _config()
    config.sync_status = "syncing"

    class FakeConfigRepository:
        def __init__(self: Any, _db: Any) -> None:
            pass

        async def get(self: Any) -> Any:
            return config

    monkeypatch.setattr(
        material_source,
        "MaterialSourceConfigRepository",
        FakeConfigRepository,
    )
    db: Any = AsyncMock()
    await material_source.reset_interrupted_syncs(db)

    assert config.sync_status == "error"
    assert config.sync_error == "上次同步因服务器重启中断，请重新同步"
    db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_reset_interrupted_syncs_leaves_finished_or_missing_config(
    monkeypatch: Any,
) -> None:
    config = _config()
    config.sync_status = "success"

    class FakeConfigRepository:
        def __init__(self: Any, _db: Any) -> None:
            pass

        async def get(self: Any) -> Any:
            return config

    monkeypatch.setattr(
        material_source,
        "MaterialSourceConfigRepository",
        FakeConfigRepository,
    )
    db: Any = AsyncMock()
    await material_source.reset_interrupted_syncs(db)
    assert config.sync_status == "success"
    db.commit.assert_not_awaited()

    class MissingRepository:
        def __init__(self: Any, _db: Any) -> None:
            pass

        async def get(self: Any) -> Any:
            return None

    monkeypatch.setattr(
        material_source,
        "MaterialSourceConfigRepository",
        MissingRepository,
    )
    await material_source.reset_interrupted_syncs(db)
    db.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_sync_rejects_incomplete_feishu_pagination(monkeypatch: Any) -> None:
    config = _config()

    class BrokenClient:
        async def search_records_page(self: Any, *_args: Any, **_kwargs: Any) -> Any:
            return {
                "items": [{"record_id": "rec-1", "fields": {}}],
                "has_more": True,
                "page_token": None,
                "total": 2,
            }

    with pytest.raises(MaterialSourcePermissionError, match="分页数据异常"):
        await material_source._list_all_material_records(BrokenClient(), config)  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_sync_page_fetch_retries_after_timeout_and_succeeds(
    monkeypatch: Any,
) -> None:
    sleep: Any = AsyncMock()
    monkeypatch.setattr(material_source.asyncio, "sleep", sleep)  # type: ignore[attr-defined]
    attempts = 0

    async def fetch_page() -> Any:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise MaterialSourceTimeoutError("飞书多维表格请求超时")
        return {"items": [], "has_more": False, "page_token": None, "total": 0}

    page = await material_source._fetch_sync_page_with_retry(fetch_page)

    assert attempts == 3
    assert page["has_more"] is False
    assert sleep.await_count == 2


@pytest.mark.anyio
async def test_sync_page_fetch_raises_after_max_retries(monkeypatch: Any) -> None:
    monkeypatch.setattr(material_source.asyncio, "sleep", AsyncMock())  # type: ignore[attr-defined]
    attempts = 0

    async def fetch_page() -> Any:
        nonlocal attempts
        attempts += 1
        raise MaterialSourceTimeoutError("飞书多维表格请求超时")

    with pytest.raises(MaterialSourceTimeoutError):
        await material_source._fetch_sync_page_with_retry(fetch_page)
    assert attempts == material_source.MATERIAL_SYNC_PAGE_RETRIES


@pytest.mark.anyio
async def test_sync_page_fetch_retries_after_upstream_error_and_succeeds(
    monkeypatch: Any,
) -> None:
    sleep: Any = AsyncMock()
    monkeypatch.setattr(material_source.asyncio, "sleep", sleep)  # type: ignore[attr-defined]
    attempts = 0

    async def fetch_page() -> Any:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise MaterialSourceUpstreamError("飞书多维表格暂时繁忙，请稍后重试")
        return {"items": [], "has_more": False, "page_token": None, "total": 0}

    page = await material_source._fetch_sync_page_with_retry(fetch_page)

    assert attempts == 3
    assert page["has_more"] is False
    assert sleep.await_count == 2


@pytest.mark.anyio
async def test_sync_page_fetch_does_not_retry_permission_errors(
    monkeypatch: Any,
) -> None:
    sleep: Any = AsyncMock()
    monkeypatch.setattr(material_source.asyncio, "sleep", sleep)  # type: ignore[attr-defined]
    attempts = 0

    async def fetch_page() -> Any:
        nonlocal attempts
        attempts += 1
        raise MaterialSourcePermissionError("飞书多维表格访问失败")

    with pytest.raises(MaterialSourcePermissionError):
        await material_source._fetch_sync_page_with_retry(fetch_page)
    assert attempts == 1
    sleep.assert_not_awaited()


@pytest.mark.anyio
async def test_text_options_pass_short_timeout_to_both_feishu_searches(
    monkeypatch: Any,
) -> None:
    _material_options_harness(monkeypatch)
    calls: list[float] = []

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def search_records(self: Any, _table_id: Any, **kwargs: Any) -> Any:
            calls.append(kwargs["timeout"])
            return []

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    await material_source.list_material_options(AsyncMock(), keyword="MAT")

    assert calls == [material_source.MATERIAL_OPTION_REQUEST_TIMEOUT_SECONDS] * 2


@pytest.mark.anyio
async def test_text_options_total_timeout_budget_uses_constant(
    monkeypatch: Any,
) -> None:
    _material_options_harness(monkeypatch)

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def search_records(self: Any, _table_id: Any, **kwargs: Any) -> Any:
            return []

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)
    captured: dict[str, object] = {}

    async def fake_wait_for(coro: Any, timeout: Any) -> Any:
        captured["timeout"] = timeout
        return await coro

    monkeypatch.setattr(material_source.asyncio, "wait_for", fake_wait_for)  # type: ignore[attr-defined]
    await material_source.list_material_options(AsyncMock(), keyword="MAT")

    assert captured["timeout"] == material_source.MATERIAL_OPTION_TOTAL_TIMEOUT_SECONDS


@pytest.mark.anyio
async def test_number_options_timeout_is_mapped_to_material_source_timeout(
    monkeypatch: Any,
) -> None:
    _material_options_harness(monkeypatch, field_type=2)

    class FakeBitableClient:
        def __init__(self: Any, **_kwargs: Any) -> None:
            pass

        async def search_records_page(self: Any, *_args: Any, **_kwargs: Any) -> Any:
            raise httpx.ReadTimeout("upstream timeout")

    monkeypatch.setattr(material_source, "BitableClient", FakeBitableClient)

    with pytest.raises(MaterialSourceTimeoutError, match="请求超时"):
        await material_source.list_material_options(AsyncMock(), keyword="MAT")


@pytest.mark.anyio
async def test_options_prefer_successfully_synced_local_catalog(
    monkeypatch: Any,
) -> None:
    config = _config()
    config.sync_status = "success"
    config.last_synced_at = object()  # type: ignore[assignment]
    monkeypatch.setattr(
        material_source,
        "get_material_source_config",
        AsyncMock(return_value=config),
    )
    local_record = type(
        "LocalRecord",
        (),
        {
            "feishu_record_id": "rec-local",
            "material_code": "MAT-001",
            "material_description": "本地镜像",
            "rule_model": "A",
            "material_unit": "件",
            "material_template": "模板A",
            "material_category": "五金",
            "material_subcategory": "螺丝",
            "material_cost_category": "成本A",
        },
    )()
    repository: Any = AsyncMock()
    repository.list_option_records.return_value = [local_record]
    monkeypatch.setattr(
        material_source,
        "MaterialCatalogRepository",
        lambda _db: repository,
    )
    client: Any = AsyncMock()
    monkeypatch.setattr(material_source, "BitableClient", lambda **_kwargs: client)

    options = await material_source.list_material_options(AsyncMock(), keyword="MAT")

    assert options == [
        {
            "record_id": "rec-local",
            "material_code": "MAT-001",
            "material_description": "本地镜像",
            "rule_model": "A",
            "material_unit": "件",
            "material_template": "模板A",
            "material_category": "五金",
            "material_subcategory": "螺丝",
            "material_cost_category": "成本A",
        }
    ]
    client.search_records.assert_not_awaited()
    client.search_records_page.assert_not_awaited()


@pytest.mark.anyio
async def test_options_keep_local_catalog_after_failed_resync(monkeypatch: Any) -> None:
    """同步失败后仍使用最近一次成功同步的本地镜像，不打回慢速飞书实时查询。"""
    config = _config()
    config.sync_status = "error"
    config.sync_error = "飞书多维表格请求超时"
    config.last_synced_at = object()  # type: ignore[assignment]
    monkeypatch.setattr(
        material_source,
        "get_material_source_config",
        AsyncMock(return_value=config),
    )
    local_record = type(
        "LocalRecord",
        (),
        {
            "feishu_record_id": "rec-local",
            "material_code": "MAT-001",
            "material_description": "本地镜像",
            "rule_model": "A",
            "material_unit": "件",
            "material_template": "模板A",
            "material_category": "五金",
            "material_subcategory": "螺丝",
            "material_cost_category": "成本A",
        },
    )()
    repository: Any = AsyncMock()
    repository.list_option_records.return_value = [local_record]
    monkeypatch.setattr(
        material_source,
        "MaterialCatalogRepository",
        lambda _db: repository,
    )
    client: Any = AsyncMock()
    monkeypatch.setattr(material_source, "BitableClient", lambda **_kwargs: client)

    options = await material_source.list_material_options(AsyncMock(), keyword="MAT")

    assert options == [
        {
            "record_id": "rec-local",
            "material_code": "MAT-001",
            "material_description": "本地镜像",
            "rule_model": "A",
            "material_unit": "件",
            "material_template": "模板A",
            "material_category": "五金",
            "material_subcategory": "螺丝",
            "material_cost_category": "成本A",
        }
    ]
    client.search_records.assert_not_awaited()
    client.search_records_page.assert_not_awaited()
