from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import AppException
from app.modules.warehouse import service
from app.modules.warehouse.schemas import WarehouseFeishuTableResponse
from app.platform.identity.data_scope import DepartmentScope


def _instance() -> service.WarehouseService:
    instance = service.WarehouseService.__new__(service.WarehouseService)
    instance._page_cache = {}
    instance._field_meta_cache = {}
    instance._table_fields_cache = {}
    instance._dashboard_cache = {}
    return instance


def test_warehouse_filter_operator_covers_text_numeric_date_and_empty_cases() -> None:
    instance = _instance()
    assert instance._match_filter_operator(
        field_name="物料名称",
        candidate_values=["原料药A"],
        operator="contains",
        value="原料",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="物料名称",
        candidate_values=["原料药A"],
        operator="not_contains",
        value="包装",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="物料名称",
        candidate_values=["原料药A"],
        operator="eq",
        value="原料药A",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="物料名称",
        candidate_values=["原料药A", "包装"],
        operator="neq",
        value="原料药A",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="物料名称",
        candidate_values=[None, ""],
        operator="empty",
        value="",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="物料名称",
        candidate_values=["A"],
        operator="not_empty",
        value="",
        value_to="",
    )
    for operator, left, right, expected in (
        ("gt", "5", "15", True),
        ("gte", "10", "15", True),
        ("lt", "15", "20", True),
        ("lte", "10", "20", True),
        ("between", "5", "15", True),
    ):
        assert (
            instance._match_filter_operator(
                field_name="库存数量",
                candidate_values=[10],
                operator=operator,
                value=left,
                value_to=right,
            )
            is expected
        )
    assert instance._match_filter_operator(
        field_name="入库日期",
        candidate_values=["2026-08-10"],
        operator="between",
        value="2026-08-01",
        value_to="2026-08-31",
    )
    with pytest.raises(HTTPException):
        instance._match_filter_operator(
            field_name="库存数量",
            candidate_values=[10],
            operator="between",
            value="5",
            value_to="bad",
        )
    with pytest.raises(HTTPException):
        instance._match_filter_operator(
            field_name="物料名称",
            candidate_values=["A"],
            operator="unsupported",
            value="",
            value_to="",
        )


@pytest.mark.asyncio
async def test_warehouse_feishu_pagination_and_material_page_scope_paths() -> None:
    instance = _instance()
    instance.feishu_client = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                {
                    "items": [{"field_name": "物料名称"}],
                    "has_more": True,
                    "page_token": "p2",
                },
                {"items": [{"field_name": "库存"}], "has_more": False},
                {
                    "items": [{"record_id": "r1", "fields": {}}],
                    "has_more": True,
                    "total": 2,
                    "page_token": "p2",
                },
                {
                    "items": [{"record_id": "r2", "fields": {}}],
                    "has_more": False,
                    "total": 2,
                },
            ]
        )
    )
    instance._get_material_client = AsyncMock(return_value=instance.feishu_client)
    fields = await instance.fetch_feishu_table_fields(app_token="app", table_id="tbl")
    records = await instance.fetch_feishu_table_records(
        app_token="app", table_id="tbl", page_size=50
    )
    assert len(fields) == 2
    assert [item["record_id"] for item in records] == ["r1", "r2"]

    config = SimpleNamespace(
        page_key="hardware-detail",
        title="五金明细",
        app_token="app",
        table_id="tbl",
    )
    instance._resolve_material_page_source = AsyncMock(return_value="feishu")
    instance._parse_advanced_filters = Mock(return_value=[])
    instance._get_material_page_config = AsyncMock(return_value=config)
    instance.fetch_material_page_from_feishu = AsyncMock(
        return_value=(
            config,
            [],
            [
                {"车间": "一车间", "物料名称": "螺栓", "__record_id": "r1"},
                {"车间": "二车间", "物料名称": "螺母", "__record_id": "r2"},
            ],
            {},
        )
    )
    instance._filter_material_page_rows = Mock(
        side_effect=lambda *_args, **kwargs: [
            {"车间": "一车间", "物料名称": "螺栓", "__record_id": "r1"},
            {"车间": "二车间", "物料名称": "螺母", "__record_id": "r2"},
        ]
    )
    instance._paginate_material_rows = Mock(
        return_value=([{"车间": "一车间", "物料名称": "螺栓"}], 1)
    )
    instance._build_material_page_response = Mock(return_value={"rows": ["r1"]})
    result = await instance.get_feishu_material_page(
        "hardware-detail",
        scope=DepartmentScope(is_all=False, department_names={"一车间"}),
    )
    assert result == {"rows": ["r1"]}

    instance._page_cache.clear()
    instance.fetch_material_page_from_feishu.side_effect = RuntimeError("offline")
    instance.get_local_material_page = AsyncMock(return_value={"source": "local"})
    fallback = await instance.get_feishu_material_page("hardware-detail")
    assert fallback == {"source": "local"}
    instance.get_local_material_page.assert_awaited_once()

    instance._resolve_material_page_source.return_value = "feishu"
    with pytest.raises(HTTPException) as exc_info:
        await instance.get_feishu_material_page("hardware-detail", force=True)
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_warehouse_snapshot_analysis_config_and_discovery_paths() -> None:
    instance = _instance()
    instance.repo = SimpleNamespace(
        session=SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock()),
        list_feishu_fields=AsyncMock(
            return_value=[
                SimpleNamespace(field_id="metric", field_name="库存数量"),
                SimpleNamespace(field_id="person", field_name="姓名"),
                SimpleNamespace(field_id="secret", field_name="API密钥"),
            ]
        ),
        list_analysis_records=AsyncMock(
            return_value=[
                SimpleNamespace(
                    record_id="r1",
                    fields={"库存数量": 10, "姓名": "张三", "API密钥": "secret"},
                ),
                SimpleNamespace(
                    record_id="r2", fields={"库存数量": None, "姓名": "李四"}
                ),
            ]
        ),
        save_analysis_profile=AsyncMock(),
        save_prompt_version=AsyncMock(),
    )
    profile = SimpleNamespace(
        input_field_ids=["metric", "person", "secret"],
        metric_field_ids=["metric"],
        max_raw_rows=10,
        allow_sensitive_fields=False,
    )
    table = SimpleNamespace(
        id=uuid4(),
        business_domain="warehouse",
        app_token="app",
        table_id="tbl",
        record_count=2,
    )
    algorithm, warnings, selected = await instance._prepare_analysis_input(
        profile, [table]
    )
    assert warnings == []
    assert algorithm["source_row_count"] == 2
    assert algorithm["missing_cell_count"] == 1
    assert selected[0]["person"] == "***"
    assert algorithm["numeric_summary"]["metric"]["mean"] == 10

    client = SimpleNamespace(
        list_fields=AsyncMock(return_value=[{"field_name": "物料名称"}]),
    )
    instance._build_feishu_client = Mock(return_value=client)
    instance._read_all_records = AsyncMock(return_value=([{"record_id": "r1"}], 1))
    instance._table_response_from_legacy = Mock(
        return_value=WarehouseFeishuTableResponse(
            id=uuid4(),
            app_token="app",
            table_id="tbl",
            name="仓储表",
        )
    )
    legacy_table = SimpleNamespace(
        id=uuid4(),
        app_token="app",
        table_id="tbl",
        field_count=0,
        record_count=0,
        last_synced_at=None,
        sync_status="queued",
        sync_error=None,
        active_mirror_version=None,
    )
    synced = await instance._sync_feishu_table_snapshot(SimpleNamespace(), legacy_table)
    assert synced.field_count == 1
    assert legacy_table.sync_status == "success"
    assert instance.repo.session.commit.await_count == 1


@pytest.mark.asyncio
async def test_warehouse_discovery_rejects_wrong_root_and_maps_base_tables() -> None:
    instance = _instance()
    config = SimpleNamespace(id=uuid4())
    root = SimpleNamespace(
        id=uuid4(),
        config_id=config.id,
        is_active=True,
        source_type="base",
        root_token="app-token",
        name="仓储数据",
        discovery_status="ready",
        discovery_error=None,
    )
    instance.repo = SimpleNamespace(
        get_active_feishu_config=AsyncMock(return_value=config),
        get_feishu_source_root=AsyncMock(return_value=root),
        session=SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock()),
    )
    client = SimpleNamespace(
        list_tables=AsyncMock(return_value=[{"table_id": "tbl-1"}])
    )
    instance._build_feishu_client = Mock(return_value=client)
    instance._save_discovered_feishu_tables = AsyncMock(return_value=[{"id": "saved"}])
    result = await instance.discover_feishu_source_root(root.id)
    assert result == [{"id": "saved"}]
    instance._save_discovered_feishu_tables.assert_awaited_once()

    root.config_id = uuid4()
    with pytest.raises(AppException):
        await instance.discover_feishu_source_root(root.id)
