from __future__ import annotations

from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppException
from app.modules.production.feishu_service import ProductionFeishuService
from app.modules.warehouse.service import WarehouseService

SimpleNamespace: Any = _SimpleNamespace


def test_production_feishu_scalar_and_nested_mapping_helpers() -> Any:
    assert ProductionFeishuService._normalize_sync_value(" 1,234.5 ") == 1234.5
    assert ProductionFeishuService._normalize_sync_value(" a,b ") == "a,b"
    assert ProductionFeishuService._normalize_sync_value(" text ") == "text"
    assert ProductionFeishuService._normalize_sync_value(3) == 3
    assert ProductionFeishuService._safe_int(None) is None
    assert ProductionFeishuService._safe_int("") is None
    assert ProductionFeishuService._safe_int("4") == 4
    assert ProductionFeishuService._safe_int("bad") is None

    nested = {
        "value": [
            {"text": "A", "type": "text"},
            {"name": "B"},
            {"zh_cn": "中文"},
        ]
    }
    assert ProductionFeishuService._extract_feishu_value(nested) == [
        "A",
        "B",
        "中文",
    ]
    assert ProductionFeishuService._extract_feishu_value([{"url": "u"}]) == "u"
    assert ProductionFeishuService._extract_feishu_value(
        {"unknown": {"en_us": "value"}, "type": "ignored"}
    ) == {"unknown": "value"}

    table = ProductionFeishuService._table_from_raw(
        {"table_id": "t1", "name": "", "revision": "2"}
    )
    assert (table.table_id, table.name, table.revision) == ("t1", "t1", 2)
    field = ProductionFeishuService._field_from_raw(
        {"id": "f1", "name": "字段", "type": "bad", "property": []}
    )
    assert (field.field_id, field.field_name, field.type, field.property) == (
        "f1",
        "字段",
        None,
        None,
    )
    record = ProductionFeishuService._record_from_raw(
        {
            "record_id": "r1",
            "fields": {"A": {"text": "B"}},
            "created_time": "1",
            "last_modified_time": "bad",
        }
    )
    assert record.fields == {"A": "B"}
    assert record.created_time == 1
    assert record.last_modified_time is None


def test_production_feishu_error_body_and_redaction_helpers() -> Any:
    json_response = httpx.Response(
        400,
        json={"code": 999, "msg": "invalid"},
        request=httpx.Request("GET", "https://example.test"),
    )
    body = ProductionFeishuService._feishu_response_body(json_response)
    assert "code=999" in ProductionFeishuService._feishu_http_error_message(
        json_response, body, "读取失败"
    )
    assert "invalid" in ProductionFeishuService._feishu_business_error_message(
        body, "读取失败"
    )

    text_response = httpx.Response(
        502,
        text="gateway",
        request=httpx.Request("GET", "https://example.test"),
    )
    assert ProductionFeishuService._feishu_response_body(text_response) == {
        "raw": "gateway"
    }
    assert "/base/" in ProductionFeishuService._append_bitable_app_token_hint("失败")

    config: Any = SimpleNamespace(
        app_id="app-secret-id", bitable_app_token="token-secret"
    )
    safe = ProductionFeishuService._safe_sync_error(
        "app-secret-id token-secret " + ("x" * 600),
        config,
    )
    assert "app-secret-id" not in safe
    assert "token-secret" not in safe
    assert len(safe) == 500


def test_production_sales_plan_mapping_boundaries() -> Any:
    binding: Any = SimpleNamespace(
        field_mapping={
            "product_name": "产品",
            "month_planned_delivery": "计划",
            "ignored": "忽略",
            "remarks": "备注",
        }
    )
    record: Any = SimpleNamespace(
        fields={"产品": " P ", "计划": "1,200", "忽略": "x", "备注": ""},
    )
    mapped = ProductionFeishuService._map_sales_plan_record(binding, record)
    assert mapped == {"product_name": "P", "month_planned_delivery": 1200.0}

    record.fields["计划"] = "not-number"
    with pytest.raises(ValueError, match="不是数字"):
        ProductionFeishuService._map_sales_plan_record(binding, record)
    record.fields["计划"] = "1"
    record.fields["产品"] = ""
    with pytest.raises(ValueError, match="缺少 product_name"):
        ProductionFeishuService._map_sales_plan_record(binding, record)


def test_warehouse_generic_value_and_record_helpers() -> Any:
    assert WarehouseService._as_dict({"a": 1}) == {"a": 1}
    assert WarehouseService._as_dict("text") == {"summary": "text"}
    assert WarehouseService._as_dict_list(None) == []
    assert WarehouseService._as_dict_list("text") == [{"summary": "text"}]
    assert WarehouseService._as_dict_list([{"a": 1}, "x"]) == [
        {"a": 1},
        {"summary": "x"},
    ]
    assert WarehouseService._safe_float({"value": ["1.5"]}) == 1.5
    assert WarehouseService._safe_float("bad") is None
    assert WarehouseService._safe_int("") is None
    assert WarehouseService._safe_int("3") == 3
    assert WarehouseService._safe_int([]) is None

    field = WarehouseService._field_from_raw(
        {"id": "f1", "name": "字段", "type": "2", "property": {"x": 1}}
    )
    assert (field.field_id, field.field_name, field.type) == ("f1", "字段", 2)
    record = WarehouseService._record_from_raw(
        {
            "record_id": "r1",
            "fields": [],
            "created_time": "1",
            "last_modified_time": "bad",
        }
    )
    assert record.fields == {}
    assert record.created_time == 1
    assert record.last_modified_time is None


def test_warehouse_search_and_field_normalization_boundaries() -> Any:
    search = WarehouseService._build_search_text(
        {
            "name": " A ",
            "count": 2,
            "active": True,
            "items": [None, {"text": "B"}],
        }
    )
    assert all(value in search for value in ("name", "A", "2", "True", "B"))

    nested = {"value": {"text": [{"name": "A"}]}}
    assert WarehouseService._normalize_fields({"nested": nested}) == {"nested": ["A"]}
    deep = {"a": {"b": {"c": {"d": {"e": object()}}}}}
    assert isinstance(WarehouseService._normalize_fields({"deep": deep})["deep"], dict)


@pytest.mark.parametrize(
    ("field", "operator", "value", "expected"),
    [
        (None, None, None, (None, None)),
        ("name", None, "A", ("contains", "A")),
        ("amount", "gt", "1.2", ("gt", "1.2")),
    ],
)
def test_warehouse_field_filter_success(
    field: Any, operator: Any, value: Any, expected: Any
) -> Any:
    assert (
        WarehouseService._normalize_field_filter(
            field=field,
            field_operator=operator,
            field_value=value,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("field", "operator", "value", "message"),
    [
        (None, "contains", "A", "请选择"),
        ("name", "unknown", "A", "无效"),
        ("name", "contains", None, "请填写"),
        ("amount", "gt", "not-number", "必须填写数字"),
    ],
)
def test_warehouse_field_filter_failures(
    field: Any, operator: Any, value: Any, message: Any
) -> Any:
    with pytest.raises(AppException, match=message):
        WarehouseService._normalize_field_filter(
            field=field,
            field_operator=operator,
            field_value=value,
        )


@pytest.mark.asyncio
async def test_warehouse_repository_errors_are_mapped_at_service_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    service = WarehouseService.__new__(WarehouseService)
    service.repo = AsyncMock()
    service.repo.get_any_feishu_config.side_effect = SQLAlchemyError("db")
    with pytest.raises(AppException) as any_error:
        await service._get_any_feishu_config_or_raise()
    assert any_error.value.status_code == 500
    assert "alembic upgrade head" in any_error.value.message

    service.repo.get_active_feishu_config.side_effect = SQLAlchemyError("db")
    with pytest.raises(AppException) as active_error:
        await service._get_active_feishu_config_or_raise()
    assert active_error.value.status_code == 500
    assert "alembic upgrade head" in active_error.value.message

    service.repo.get_active_feishu_config.side_effect = None
    service.repo.get_active_feishu_config.return_value = None
    # 本机 settings 配有平台 FEISHU_APP_ID/SECRET 时会走 env 兜底而不抛错；
    # 显式禁用兜底以锁定"无任何配置"分支
    monkeypatch.setattr(
        WarehouseService,
        "_env_fallback_feishu_config",
        staticmethod(lambda: None),
    )
    with pytest.raises(AppException, match="请先启用"):
        await service._get_active_feishu_config_or_raise()

    config: Any = SimpleNamespace(id=uuid4())
    service.repo.get_active_feishu_config.return_value = config
    service.repo.get_feishu_table_by_id.side_effect = SQLAlchemyError("db")
    with pytest.raises(AppException) as table_error:
        await service._get_table_by_id_or_raise(uuid4())
    assert table_error.value.status_code == 500
    assert "alembic upgrade head" in table_error.value.message

    service.repo.get_feishu_table_by_id.side_effect = None
    service.repo.get_feishu_table_by_id.return_value = None
    with pytest.raises(AppException, match="数据表不存在"):
        await service._get_table_by_id_or_raise(uuid4(), config_id=config.id)


@pytest.mark.asyncio
async def test_warehouse_token_connectivity_all_outcomes() -> Any:
    service = WarehouseService.__new__(WarehouseService)
    steps: list[Any] = []
    incomplete: Any = SimpleNamespace(app_id="", encrypted_app_secret="")
    assert await service._test_tenant_token(incomplete, steps) is None
    assert steps[-1].status == "error"

    client: Any = AsyncMock()
    client.get_tenant_access_token.side_effect = RuntimeError("offline")
    service._build_feishu_client = lambda _config, _token: client  # type: ignore[assignment, method-assign]
    configured: Any = SimpleNamespace(app_id="app", encrypted_app_secret="encrypted")
    assert await service._test_tenant_token(configured, steps) is None
    assert "offline" in steps[-1].message

    client.get_tenant_access_token.side_effect = None
    client.get_tenant_access_token.return_value = "tenant-token"
    assert await service._test_tenant_token(configured, steps) == "tenant-token"
    assert steps[-1].status == "ok"
