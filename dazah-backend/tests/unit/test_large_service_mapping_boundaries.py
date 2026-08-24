from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppException
from app.modules.warehouse.service import WarehouseService


def test_warehouse_generic_value_and_record_helpers():
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


def test_warehouse_search_and_field_normalization_boundaries():
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
    assert WarehouseService._normalize_fields({"nested": nested}) == {
        "nested": ["A"]
    }
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
def test_warehouse_field_filter_success(field, operator, value, expected):
    assert WarehouseService._normalize_field_filter(
        field=field,
        field_operator=operator,
        field_value=value,
    ) == expected


@pytest.mark.parametrize(
    ("field", "operator", "value", "message"),
    [
        (None, "contains", "A", "请选择"),
        ("name", "unknown", "A", "无效"),
        ("name", "contains", None, "请填写"),
        ("amount", "gt", "not-number", "必须填写数字"),
    ],
)
def test_warehouse_field_filter_failures(field, operator, value, message):
    with pytest.raises(AppException, match=message):
        WarehouseService._normalize_field_filter(
            field=field,
            field_operator=operator,
            field_value=value,
        )


@pytest.mark.asyncio
async def test_warehouse_repository_errors_are_mapped_at_service_boundary():
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
    with pytest.raises(AppException, match="请先启用"):
        await service._get_active_feishu_config_or_raise()

    config = SimpleNamespace(id=uuid4())
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
async def test_warehouse_token_connectivity_all_outcomes():
    service = WarehouseService.__new__(WarehouseService)
    steps = []
    incomplete = SimpleNamespace(app_id="", encrypted_app_secret="")
    assert await service._test_tenant_token(incomplete, steps) is None
    assert steps[-1].status == "error"

    client = AsyncMock()
    client.get_tenant_access_token.side_effect = RuntimeError("offline")
    service._build_feishu_client = lambda _config, _token: client
    configured = SimpleNamespace(app_id="app", encrypted_app_secret="encrypted")
    assert await service._test_tenant_token(configured, steps) is None
    assert "offline" in steps[-1].message

    client.get_tenant_access_token.side_effect = None
    client.get_tenant_access_token.return_value = "tenant-token"
    assert await service._test_tenant_token(configured, steps) == "tenant-token"
    assert steps[-1].status == "ok"
