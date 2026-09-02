from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.warehouse import service
from app.modules.warehouse.feishu_material_pages import FeishuWarehouseMaterialPage
from app.modules.warehouse.schemas import WarehouseFeishuPageBindingReplace


def _service(repo: object) -> service.WarehouseService:
    instance = service.WarehouseService.__new__(service.WarehouseService)
    instance.repo = repo
    instance._page_cache = {}
    instance._field_meta_cache = {}
    instance._table_fields_cache = {}
    instance._dashboard_cache = {}
    return instance


class _Repo:
    def __init__(self) -> None:
        self.session = SimpleNamespace(
            commit=AsyncMock(), refresh=AsyncMock(), flush=AsyncMock()
        )
        self.get_feishu_source_root = AsyncMock()
        self.upsert_feishu_table = AsyncMock()
        self.list_page_feishu_configs = AsyncMock(return_value=[])
        self.upsert_page_feishu_config = AsyncMock()
        self.list_page_bindings = AsyncMock(return_value=[])
        self.replace_page_bindings = AsyncMock()


def test_material_filter_and_scalar_helpers_cover_all_operator_types() -> None:
    assert service.WarehouseService._safe_int("12") == 12
    assert service.WarehouseService._safe_int("bad") is None
    assert service.WarehouseService._safe_int(None) is None
    assert (
        service.WarehouseService._field_from_raw(
            {"id": "f1", "name": "名称", "type": "2"}
        ).type
        == 2
    )
    assert (
        service.WarehouseService._record_from_raw(
            {"record_id": "r1", "fields": {"名称": "A"}, "created_time": "3"}
        ).created_time
        == 3
    )
    assert "姓名" in service.WarehouseService._build_search_text(
        {"姓名": "张三", "列表": [1, {"x": "y"}]}
    )
    assert service.is_material_page_date_field("有效期")
    assert service._parse_date_value("20260801") == date(2026, 8, 1)
    assert service._parse_date_value(0) is not None

    instance = _service(SimpleNamespace())
    values = ["库存充足", "12", "2026-08-01"]
    assert instance._match_filter_operator(
        field_name="备注",
        candidate_values=values,
        operator="contains",
        value="充足",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="备注",
        candidate_values=values,
        operator="not_contains",
        value="缺货",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="数量",
        candidate_values=["12"],
        operator="gt",
        value="10",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="数量",
        candidate_values=["12"],
        operator="gte",
        value="12",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="数量",
        candidate_values=["12"],
        operator="lt",
        value="13",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="数量",
        candidate_values=["12"],
        operator="lte",
        value="12",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="数量",
        candidate_values=["12"],
        operator="between",
        value="10",
        value_to="15",
    )
    assert instance._match_filter_operator(
        field_name="备注",
        candidate_values=[""],
        operator="empty",
        value="",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="备注",
        candidate_values=["有值"],
        operator="not_empty",
        value="",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="日期",
        candidate_values=["2026-08-01"],
        operator="eq",
        value="2026-08-01",
        value_to="",
    )
    assert instance._match_filter_operator(
        field_name="日期",
        candidate_values=["2026-08-01"],
        operator="between",
        value="2026-08-01",
        value_to="2026-08-31",
    )
    assert service._matches_warning_status("正常", "normal")
    assert service._matches_warning_status("缺货", "warning")
    assert service._should_hide_zero_stock_row("raw-detail", {"本日结存": 0})
    assert not service._should_hide_zero_stock_row("raw-summary", {"本日结存": 0})

    rows = [
        {
            "__record_id": "r1",
            "名称": "A",
            "使用产品": "产品A",
            "库区": "一号库",
            "质量状态": "合格",
            "物料类别": "原料",
            "预警": "正常",
            "日期": "2026-08-01",
            "数量": 12,
        },
        {
            "__record_id": "r2",
            "名称": "B",
            "使用产品": "产品B",
            "库区": "二号库",
            "质量状态": "不合格",
            "物料类别": "包材",
            "预警": "缺货",
            "日期": "2026-07-01",
            "数量": 2,
        },
    ]
    result = instance._filter_material_page_rows(
        "raw-summary",
        rows,
        keyword="产品A",
        start_date="2026-01-01",
        end_date="2026-12-31",
        date_field="日期",
        product="产品A",
        area="一号库",
        quality_status="合格",
        warning_status="normal",
        material_category="原料",
        advanced_filters=[
            {"field": "数量", "operator": "gte", "value": "10", "value_to": ""}
        ],
    )
    assert [row["__record_id"] for row in result] == ["r1"]
    with pytest.raises(HTTPException):
        instance._filter_material_page_rows("raw-summary", rows, start_date="bad")
    with pytest.raises(HTTPException):
        instance._match_filter_operator(
            field_name="数量",
            candidate_values=["x"],
            operator="between",
            value="1",
            value_to="",
        )


@pytest.mark.asyncio
async def test_discovery_page_binding_and_config_compatibility_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _Repo()
    root_id = uuid4()
    root = SimpleNamespace(
        id=root_id,
        discovery_status="pending",
        discovery_error="old",
        last_discovered_at=None,
    )
    repo.get_feishu_source_root.return_value = root
    table = SimpleNamespace(
        id=uuid4(),
        app_token="token",
        table_id="tbl-1",
        name="原料表",
        revision=3,
        last_discovered_at=None,
        last_event_at=None,
        field_count=0,
        record_count=0,
        last_synced_at=None,
        sync_status="available",
        sync_error=None,
        source_root_id=root_id,
        source_path=[],
        schema_hash=None,
        active_mirror_version=None,
    )
    repo.upsert_feishu_table.return_value = table
    instance = _service(repo)
    discovered = await instance._save_discovered_feishu_tables(
        "token",
        [{"table_id": "tbl-1", "name": "原料表", "revision": "3"}, {"name": "无ID"}],
        source_root_id=root_id,
        source_path=[{"name": "根", "id": "root"}],
    )
    assert len(discovered) == 1 and root.discovery_status == "success"
    repo.get_feishu_source_root.return_value = None
    with pytest.raises(Exception):
        await instance._save_discovered_feishu_tables(
            "token", [], source_root_id=root_id, source_path=[]
        )

    raw_pages = {
        "raw-summary": FeishuWarehouseMaterialPage(
            "raw-summary", "原辅料", "tbl-raw", "token"
        )
    }
    monkeypatch.setattr(service, "FEISHU_WAREHOUSE_MATERIAL_PAGES", raw_pages)
    repo.list_page_feishu_configs.side_effect = [
        [],
        [
            {
                "page_key": "raw-summary",
                "app_token": "token",
                "table_id": "tbl-raw",
                "table_name": "原辅料",
            }
        ],
    ]
    configs = await instance.get_all_page_feishu_configs()
    assert configs[0]["page_key"] == "raw-summary"
    repo.list_page_feishu_configs.side_effect = None
    repo.list_page_feishu_configs.return_value = configs
    assert (await instance._page_binding_response("raw-summary")).tab_label == "原辅料"
    binding = SimpleNamespace(
        id=uuid4(),
        table_pk=instance._legacy_table_uuid("tbl-raw"),
        tab_label="自定义",
        display_order=2,
        is_default=False,
        visible_field_ids=["f1"],
        default_sort=[],
        history_mode="daily_snapshot",
        is_enabled=True,
        status="published",
    )
    response = await instance._page_binding_response("raw-summary", binding)
    assert response.tab_label == "自定义" and response.table.table_id == "tbl-raw"

    config = SimpleNamespace(id=uuid4())
    instance._get_active_feishu_config_or_raise = AsyncMock(return_value=config)
    instance._legacy_table_configs = AsyncMock(return_value=configs)
    instance.get_page_data = AsyncMock(return_value={"page_key": "raw-summary"})
    table_pk = instance._legacy_table_uuid("tbl-raw")
    data = WarehouseFeishuPageBindingReplace(
        bindings=[{"table_pk": table_pk, "tab_label": "原料", "is_default": True}]
    )
    page = await instance.replace_page_bindings("raw-summary", data)
    assert page["page_key"] == "raw-summary"
    repo.replace_page_bindings.assert_awaited_once()

    duplicate = WarehouseFeishuPageBindingReplace(
        bindings=[
            {"table_pk": table_pk, "tab_label": "一"},
            {"table_pk": table_pk, "tab_label": "二"},
        ]
    )
    with pytest.raises(Exception):
        await instance.replace_page_bindings("raw-summary", duplicate)

    unknown = WarehouseFeishuPageBindingReplace(
        bindings=[{"table_pk": uuid4(), "tab_label": "未知"}]
    )
    with pytest.raises(Exception):
        await instance.replace_page_bindings("raw-summary", unknown)


@pytest.mark.asyncio
async def test_feishu_page_fetch_pagination_and_error_fallbacks() -> None:
    repo = _Repo()
    instance = _service(repo)

    class _Client:
        def __init__(self) -> None:
            self.calls = 0

        async def request(self, *_args: object, **kwargs: object) -> dict[str, object]:
            self.calls += 1
            params = kwargs["params"]
            if self.calls == 1:
                assert "page_token" not in params
                return {
                    "items": [{"field_id": "f1"}],
                    "has_more": True,
                    "page_token": "next",
                }
            return {"items": [{"field_id": "f2"}], "has_more": False}

    instance.feishu_client = _Client()
    fields = await instance.fetch_feishu_table_fields(app_token="a", table_id="t")
    assert len(fields) == 2

    class _RecordClient(_Client):
        async def request(self, *_args: object, **kwargs: object) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {
                    "items": [{"record_id": "r1"}],
                    "has_more": True,
                    "total": 2,
                    "page_token": "next",
                }
            return {
                "items": [{"record_id": "r2"}],
                "has_more": True,
                "total": 2,
                "page_token": "next2",
            }

    instance.feishu_client = _RecordClient()
    records = await instance.fetch_feishu_table_records(
        app_token="a", table_id="t", page_size=10
    )
    assert [item["record_id"] for item in records] == ["r1", "r2"]
