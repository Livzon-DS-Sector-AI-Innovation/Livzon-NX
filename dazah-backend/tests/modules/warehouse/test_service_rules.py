import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.modules.warehouse.schemas import WarehouseFeishuColumn
from app.modules.warehouse.service import (
    CHINA_TIMEZONE,
    FINISHED_PRODUCT_DETAIL_PAGE_KEYS,
    WarehouseService,
    _aggregate_daily_trend,
    _matches_warning_status,
    _parse_date_value,
    _parse_number,
    _pick_dept_name,
    _safe_number,
    _should_hide_zero_stock_row,
    build_material_page_row_search_text,
    build_warehouse_import_key,
    is_material_page_date_field,
    normalize_feishu_cell_value,
    normalize_person_value,
    resolve_option_ids,
)

SimpleNamespace: Any = _SimpleNamespace


@pytest.fixture
def warehouse_service() -> WarehouseService:
    instance = WarehouseService(MagicMock())
    instance.repo = AsyncMock()
    instance._page_cache = {}
    instance._field_meta_cache = {}
    instance._table_fields_cache = {}
    instance._dashboard_cache = {}
    return instance


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("文本", "文本"),
        (12, 12),
        (["A", None, {"text": "B"}], "A, B"),
        ({"text": "标题"}, "标题"),
        ({"name": "名称"}, "名称"),
        ({"label": "标签"}, "标签"),
        ({"value": {"name": "嵌套"}}, "嵌套"),
        ({"file_token": "file-1"}, "file-1"),
        ({"unknown": 1}, "{'unknown': 1}"),
    ],
)
def test_normalize_feishu_cell_value(value: object, expected: object) -> None:
    assert normalize_feishu_cell_value(value) == expected


def test_normalize_person_value_preserves_people_and_ignores_empty_items() -> None:
    value = [
        {"id": "u1", "name": "张三", "avatar_url": "https://avatar/1"},
        {"id": "u2", "en_name": "Li Si", "avatar": "https://avatar/2"},
        {"id": "u3"},
        " 王五 ",
        123,
    ]

    normalized = normalize_person_value(value)

    assert normalized == [
        {"id": "u1", "name": "张三", "avatar_url": "https://avatar/1"},
        {"id": "u2", "name": "Li Si", "avatar_url": "https://avatar/2"},
        {"id": "", "name": "王五", "avatar_url": ""},
    ]
    assert normalize_person_value({"id": "u1", "name": "张三"})[0]["name"] == "张三"  # type: ignore[index]
    assert normalize_person_value([{"id": "u1"}]) is None
    assert normalize_person_value("普通文本") == "普通文本"


def test_option_resolution_search_text_and_import_key_are_stable() -> None:
    option_map = {"opt-a": "25kg/袋", "opt-b": "50kg/袋"}

    assert resolve_option_ids("opt-a", option_map) == "25kg/袋"
    assert resolve_option_ids(["opt-a", 3, "unknown"], option_map) == [
        "25kg/袋",
        3,
        "unknown",
    ]
    assert resolve_option_ids("opt-a", {}) == "opt-a"
    assert (
        build_material_page_row_search_text(
            {"__record_id": "secret", "物料": " 乙醇 ", "数量": 3, "空": None}
        )
        == "乙醇 3"
    )
    assert build_warehouse_import_key(" A ", None, "B") == build_warehouse_import_key(
        "a", "", " b "
    )
    assert _safe_number(None) == 0
    assert _safe_number(3) == 3.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (date(2026, 8, 20), date(2026, 8, 20)),
        (datetime(2026, 8, 20, 8), date(2026, 8, 20)),
        ("2026-08-20", date(2026, 8, 20)),
        ("2026/08/20", date(2026, 8, 20)),
        ("20260820", date(2026, 8, 20)),
        ("1777500000", datetime.fromtimestamp(1_777_500_000, tz=CHINA_TIMEZONE).date()),
        (
            1_777_500_000_000,
            datetime.fromtimestamp(1_777_500_000, tz=CHINA_TIMEZONE).date(),
        ),
        ("bad", None),
        ("", None),
    ],
)
def test_parse_date_value(value: object, expected: date | None) -> None:
    assert _parse_date_value(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), (2, 2.0), ("1,234.5", 1234.5), ("", None), ("bad", None)],
)
def test_parse_number(value: object, expected: float | None) -> None:
    assert _parse_number(value) == expected


def test_warning_status_and_department_normalization() -> None:
    assert _matches_warning_status("库存不足", "warning") is True
    assert _matches_warning_status("正常", "预警") is False
    assert _matches_warning_status("正常", "normal") is True
    assert _matches_warning_status("-", "无预警") is True
    assert _matches_warning_status("库存严重不足", "库存严重不足") is True
    assert _pick_dept_name(None) == "（未标注）"
    assert _pick_dept_name("201车间, 202车间") == "201车间"
    assert is_material_page_date_field("入库日期") is True
    assert is_material_page_date_field("物料名称") is False


@pytest.mark.parametrize(
    ("page_key", "row", "expected"),
    [
        (next(iter(FINISHED_PRODUCT_DETAIL_PAGE_KEYS)), {"库存量": 0}, True),
        (next(iter(FINISHED_PRODUCT_DETAIL_PAGE_KEYS)), {"库存量": 2}, False),
        ("raw-detail", {"本日结存": "0"}, True),
        ("packaging-detail", {"本日结存": "bad"}, True),
        ("hardware-workshop", {"结存量": -1}, True),
        ("hardware-workshop", {"结存量": 1}, False),
        ("hardware-inbound-ledger", {"结存量": 0}, False),
        ("raw-summary", {"库存量": 0}, False),
        ("raw-detail", {}, True),
    ],
)
def test_should_hide_zero_stock_row(
    page_key: str, row: dict[str, object], expected: bool
) -> None:
    assert _should_hide_zero_stock_row(page_key, row) is expected


def test_aggregate_daily_trend_filters_dates_and_uses_first_positive_quantity() -> None:
    today = datetime.now(CHINA_TIMEZONE).date()
    rows = [
        {"日期": today.isoformat(), "数量": 3},
        {"日期": today.isoformat(), "数量": -1, "备用数量": "2.5"},
        {"日期": (today - timedelta(days=1)).isoformat(), "数量": "1,000"},
        {"日期": (today - timedelta(days=10)).isoformat(), "数量": 99},
        {"日期": "bad", "数量": 10},
    ]

    trend = _aggregate_daily_trend(rows, "日期", ("数量", "备用数量"), days=3)  # type: ignore[arg-type]

    assert len(trend) == 3
    assert trend[-1] == {"date": today.isoformat(), "value": 5.5}
    assert trend[-2]["value"] == 1000
    assert trend[0]["value"] == 0


def test_build_columns_rows_pagination_and_option_extraction(
    warehouse_service: WarehouseService,
) -> None:
    fields = [
        {
            "field_name": "物料",
            "type": 1,
            "property": {"options": [{"id": "opt-a", "name": "乙醇"}]},
        },
        {"field_name": "负责人", "type": 11},
        {"field_name": " ", "type": 1},
        {
            "field_name": "规格",
            "type": 19,
            "property": {
                "type": {"ui_property": {"options": [{"id": "opt-b", "name": "25kg"}]}}
            },
        },
    ]
    columns = warehouse_service._build_columns(fields)
    option_map = warehouse_service._extract_options_from_fields(fields)
    rows = warehouse_service._build_normalized_rows(
        columns,
        [
            {
                "record_id": "r1",
                "fields": {
                    "物料": "opt-a",
                    "负责人": [{"id": "u1", "name": "张三"}],
                    "规格": "opt-b",
                },
            },
            {"record_id": "bad", "fields": "invalid"},
        ],
        option_map,
    )

    assert [column.key for column in columns] == ["物料", "负责人", "规格"]
    assert option_map == {"opt-a": "乙醇", "opt-b": "25kg"}
    assert rows[0]["物料"] == "乙醇"
    assert rows[0]["负责人"][0]["name"] == "张三"  # type: ignore[index]
    assert rows[0]["__record_id"] == "r1"
    page_rows, total = warehouse_service._paginate_material_rows(
        rows + [{"物料": "标签", "__record_id": "r2"}],
        page=1,
        page_size=1,
        keyword="乙醇",
    )
    assert total == 1
    assert page_rows[0]["__record_id"] == "r1"


@pytest.mark.asyncio
async def test_material_page_source_and_config_resolution(
    warehouse_service: WarehouseService,
) -> None:
    warehouse_service.repo.get_page_feishu_config.side_effect = [  # type: ignore[attr-defined]
        {"table_id": "tbl-db", "table_name": "数据库配置", "app_token": "app-db"},
        RuntimeError("database unavailable"),
        None,
    ]

    configured = await warehouse_service._get_material_page_config("raw-summary")
    fallback = await warehouse_service._get_material_page_config("raw-summary")

    assert configured.table_id == "tbl-db"
    assert fallback.page_key == "raw-summary"
    assert await warehouse_service._resolve_material_page_source(" remote ") == "feishu"
    assert (
        await warehouse_service._resolve_material_page_source(" DATABASE ") == "local"
    )
    with pytest.raises(HTTPException, match="仅支持 feishu 或 local"):
        await warehouse_service._resolve_material_page_source("unsupported")
    with pytest.raises(HTTPException, match="模板页不存在"):
        await warehouse_service._get_material_page_config("missing-page")


@pytest.mark.asyncio
async def test_page_option_map_loads_formula_target_and_ignores_failures(
    warehouse_service: WarehouseService,
) -> None:
    page_config: Any = SimpleNamespace(
        page_key="raw-summary", table_id="tblMain", app_token="app-1"
    )
    fields = [
        {
            "field_name": "本表",
            "property": {"options": [{"id": "self", "name": "本表选项"}]},
        },
        {"field_name": "公式", "property": {"formula": "bitable::$table[tblTarget]"}},
        {
            "field_name": "自身公式",
            "property": {"formula": "bitable::$table[tblMain]"},
        },
        {
            "field_name": "失败公式",
            "property": {"formula": "bitable::$table[tblFailed]"},
        },
    ]

    async def fetch_fields(*, app_token: str, table_id: str) -> list[dict[str, object]]:
        assert app_token == "app-1"
        if table_id == "tblFailed":
            raise RuntimeError("remote error")
        return [{"property": {"options": [{"id": "target", "name": "目标选项"}]}}]

    warehouse_service._fetch_table_fields_cached = AsyncMock(side_effect=fetch_fields)  # type: ignore[method-assign]

    option_map = await warehouse_service._build_page_option_map(page_config, fields)

    assert option_map == {"self": "本表选项", "target": "目标选项"}
    assert warehouse_service._fetch_table_fields_cached.await_count == 2


def test_parse_advanced_filters_validates_payload(
    warehouse_service: WarehouseService,
) -> None:
    payload = json.dumps(
        [{"field": "数量", "operator": "between", "value": "1", "value_to": "10"}]
    )

    assert warehouse_service._parse_advanced_filters(None) == []
    assert warehouse_service._parse_advanced_filters(payload) == [
        {"field": "数量", "operator": "between", "value": "1", "value_to": "10"}
    ]
    for invalid in ("not-json", "{}", "[1]", '[{"field": "数量"}]'):
        with pytest.raises(HTTPException):
            warehouse_service._parse_advanced_filters(invalid)


@pytest.mark.parametrize(
    ("field", "values", "operator", "value", "value_to", "expected"),
    [
        ("物料", ["无水乙醇"], "contains", "乙醇", "", True),
        ("物料", ["无水乙醇"], "not_contains", "标签", "", True),
        ("物料", ["乙醇"], "eq", "乙醇", "", True),
        ("物料", ["乙醇"], "neq", "标签", "", True),
        ("物料", [None], "empty", "", "", True),
        ("物料", ["乙醇"], "not_empty", "", "", True),
        ("数量", [10], "gt", "5", "", True),
        ("数量", [10], "gte", "10", "", True),
        ("数量", [10], "lt", "20", "", True),
        ("数量", [10], "lte", "10", "", True),
        ("数量", [10], "between", "5", "15", True),
        ("入库日期", ["2026-08-20"], "eq", "2026-08-20", "", True),
        ("入库日期", ["2026-08-20"], "between", "2026-08-01", "2026-08-31", True),
    ],
)
def test_match_filter_operator(
    warehouse_service: WarehouseService,
    field: str,
    values: list[object],
    operator: str,
    value: str,
    value_to: str,
    expected: bool,
) -> None:
    assert (
        warehouse_service._match_filter_operator(
            field_name=field,
            candidate_values=values,
            operator=operator,
            value=value,
            value_to=value_to,
        )
        is expected
    )


def test_match_filter_operator_rejects_invalid_ranges(
    warehouse_service: WarehouseService,
) -> None:
    cases = [
        {
            "field_name": "数量",
            "candidate_values": [10],
            "operator": "between",
            "value": "5",
            "value_to": "",
        },
        {
            "field_name": "入库日期",
            "candidate_values": ["2026-08-20"],
            "operator": "between",
            "value": "2026-08-01",
            "value_to": "",
        },
        {
            "field_name": "入库日期",
            "candidate_values": ["2026-08-20"],
            "operator": "eq",
            "value": "bad",
            "value_to": "",
        },
        {
            "field_name": "物料",
            "candidate_values": ["乙醇"],
            "operator": "between",
            "value": "A",
            "value_to": "B",
        },
        {
            "field_name": "物料",
            "candidate_values": ["乙醇"],
            "operator": "unsupported",
            "value": "A",
            "value_to": "",
        },
    ]
    for case in cases:
        with pytest.raises(HTTPException):
            warehouse_service._match_filter_operator(**case)  # type: ignore[arg-type]


def test_filter_material_rows_applies_business_filters_and_aliases(
    warehouse_service: WarehouseService,
) -> None:
    rows = [
        {
            "__record_id": "r1",
            "名称": "标签纸",
            "使用产品": "阿莫西林",
            "库区": "A区",
            "质量状态": "合格",
            "预警": "正常",
            "物料类别": "包材",
            "入库日期": "2026-08-20",
            "本日结存": 10,
            "数量": 20,
        },
        {
            "__record_id": "r2",
            "名称": "空库存标签",
            "使用产品": "阿莫西林",
            "库区": "A区",
            "质量状态": "合格",
            "预警": "库存不足",
            "物料类别": "包材",
            "入库日期": "2026-08-20",
            "本日结存": 0,
            "数量": 2,
        },
    ]
    advanced = [
        {"field": "物料名称", "operator": "contains", "value": "标签", "value_to": ""}
    ]

    filtered = warehouse_service._filter_material_page_rows(
        "packaging-detail",
        rows,
        keyword="标签",
        start_date="2026-08-01",
        end_date="2026-08-31",
        date_field="入库日期",
        product="阿莫西林",
        area="A区",
        quality_status="合格",
        warning_status="正常",
        material_category="包材",
        advanced_filters=advanced,
    )

    assert [row["__record_id"] for row in filtered] == ["r1"]
    with pytest.raises(HTTPException, match="开始日期格式错误"):
        warehouse_service._filter_material_page_rows(
            "raw-summary", rows, start_date="bad"
        )
    with pytest.raises(HTTPException, match="结束日期格式错误"):
        warehouse_service._filter_material_page_rows(
            "raw-summary", rows, end_date="bad"
        )


def test_build_page_stats_reports_inventory_quality_amount_and_dates(
    warehouse_service: WarehouseService,
) -> None:
    today = datetime.now(CHINA_TIMEZONE).date().isoformat()
    rows = [
        {
            "预警": "库存不足",
            "质量状态": "合格",
            "金额": "10.25",
            "库存量": 2,
            "入库日期": today,
        },
        {
            "预警": "库存严重不足",
            "质量状态": "待验",
            "金额": "2.25",
            "库存量": 0,
            "入库日期": today,
        },
        {
            "预警": "正常",
            "质量状态": "不合格",
            "金额": "bad",
            "库存量": 3,
            "入库日期": "2020-01-01",
        },
    ]

    stats = warehouse_service._build_page_stats("raw-summary", rows)

    assert stats == {
        "total": 3,
        "warning_count": 2,
        "low_stock_count": 1,
        "severe_low_stock_count": 1,
        "quality_counts": {"合格": 1, "待验": 1, "不合格": 1},
        "qualified_count": 1,
        "pending_count": 1,
        "failed_count": 1,
        "stock_count": 2,
        "amount_total": 12.5,
        "today_count": 2,
        "month_count": 2,
    }
    assert warehouse_service._build_page_stats("raw-summary", [])["stock_count"] == 0


def test_build_material_page_response_and_base_name(
    warehouse_service: WarehouseService,
) -> None:
    column = WarehouseFeishuColumn(
        key="物料",
        title="物料",
        field_type=1,
        readonly=False,
        view_only=False,
        editable=True,
    )
    now = datetime.now(UTC)
    response = warehouse_service._build_material_page_response(
        page_key="raw-summary",
        page_title="原辅料库存",
        table_name="原辅料总表",
        columns=[column],
        rows=[{"物料": "乙醇"}],
        total=1,
        page=1,
        page_size=20,
        last_sync_time=now,
        source="local",
    )

    assert response.total == 1
    assert response.stats == {}
    assert warehouse_service._get_base_name("raw-summary")
    assert warehouse_service._get_base_name("missing-page") == ""
