"""烟酒礼品仪表台统计纯逻辑与服务测试（不依赖数据库）。

fixture 按飞书 records/search 的真实取值形态构造（2026-11-09 用真实表核对过）：
富文本 [{"text":..}]、公式 {"type":2,"value":[x]}、关联 {"link_record_ids":[..]}、
人员 [{"id":..,"name":..}]、单选为纯字符串。
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.modules.administration import service as admin_service
from app.modules.administration.models import (
    AdministrationFeishuReadField,
    AdministrationFeishuReadRecord,
    AdministrationFeishuReadResource,
)
from app.modules.administration.repository import MirroredTable
from app.modules.administration.service import (
    AdministrationTobaccoGiftService,
    _as_link,
    _as_number,
    _as_person_names,
    _as_text,
    _chart,
    _extract_inventory,
    _extract_requisitions,
    _resolve_field_name,
)

# ---------- 值提取纯函数 ----------


def test_as_number_unwraps_feishu_shapes() -> None:
    assert _as_number(12) == 12.0
    assert _as_number({"type": 2, "value": [8000]}) == 8000.0
    assert _as_number([5]) == 5.0
    assert _as_number("1,234.56") == 1234.56
    assert _as_number("¥88.00") == 88.0
    assert _as_number("") is None
    assert _as_number(True) is None
    assert _as_number(None) is None
    assert _as_number([1, 2]) is None


def test_as_text_handles_rich_text_select_and_lists() -> None:
    rich = [{"text": "五粮", "type": "text"}, {"text": "液", "type": "text"}]
    assert _as_text(rich) == "五粮液"
    assert _as_text("已领用") == "已领用"
    assert _as_text(["烟类", "酒类"]) == "烟类、酒类"
    assert _as_text({"type": 1, "value": [{"text": "公式文本", "type": "text"}]}) == (
        "公式文本"
    )
    assert _as_text(None) == ""


def test_as_link_returns_texts_and_ids() -> None:
    assert _as_link({"link_record_ids": ["rec1"]}) == ([], ["rec1"])
    assert _as_link({"record_ids": ["rec2"], "text": ["茅台"]}) == (["茅台"], ["rec2"])
    assert _as_link({}) == ([], [])
    assert _as_link(None) == ([], [])


def test_as_person_names_extracts_display_name() -> None:
    assert _as_person_names([{"id": "ou_1", "name": "张三"}]) == ["张三"]
    assert _as_person_names("李四") == ["李四"]
    assert _as_person_names(None) == []


def test_resolve_field_name_does_not_pick_warning_stock() -> None:
    fields = ["物品名称", "预警库存", "物品总数", "总金额"]
    assert _resolve_field_name(admin_service._INVENTORY_QUANTITY_FIELDS, fields) == (
        "物品总数"
    )
    assert _resolve_field_name(admin_service._INVENTORY_TOTAL_PRICE_FIELDS, fields) == (
        "总金额"
    )
    assert _resolve_field_name(("单价",), fields) is None


def test_chart_orders_by_value_and_caps_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_service, "_CHART_LIMIT", 2)
    chart = _chart({"甲": 1.0, "乙": 3.0, "丙": 2.0})
    assert [(item.name, item.value) for item in chart] == [("乙", 3.0), ("丙", 2.0)]


# ---------- 真实形态 fixture ----------


def _fields(names: list[str]) -> list[AdministrationFeishuReadField]:
    return [
        AdministrationFeishuReadField(
            resource_id=None,  # type: ignore[arg-type]
            field_id=f"f{index}",
            field_name=name,
            field_type="1",
        )
        for index, name in enumerate(names)
    ]


def _record(record_id: str, fields: dict[str, Any]) -> AdministrationFeishuReadRecord:
    return AdministrationFeishuReadRecord(
        resource_id=None,  # type: ignore[arg-type]
        record_id=record_id,
        mirror_version=None,  # type: ignore[arg-type]
        raw_fields=fields,
    )


def _resource(title: str) -> AdministrationFeishuReadResource:
    return AdministrationFeishuReadResource(
        source_root_id=None,  # type: ignore[arg-type]
        app_token="app",
        table_id="tbl",
        title=title,
        last_complete_sync_at=datetime(2026, 11, 9, 8, 0, tzinfo=UTC),
    )


def _item(
    record_id: str, name: str, qty: int, price: int
) -> AdministrationFeishuReadRecord:
    return _record(
        record_id,
        {
            "物品名称": [{"text": name, "type": "text"}],
            "物品总数": qty,
            "物品单价/元": price,
            "预警库存": 99,
            "总金额": {"type": 2, "value": [qty * price]},
            "状态": "上架",
        },
    )


def _requisition(
    record_id: str,
    status: str,
    applicant: str,
    lines: list[tuple[str, int]],
) -> AdministrationFeishuReadRecord:
    fields: dict[str, Any] = {
        "状态": status,
        "申请人": [{"id": f"ou_{applicant}", "name": applicant, "email": ""}],
        "领用金额": {"type": 2, "value": [0]},
    }
    for label, (item_record_id, qty) in zip("一二三四五", lines, strict=False):
        fields[f"领用物品（{label}）"] = {"link_record_ids": [item_record_id]}
        fields[f"领用数量（{label}）"] = qty
    return _record(record_id, fields)


def _inventory_table() -> MirroredTable:
    return MirroredTable(
        resource=_resource("物品清单"),
        fields=_fields(
            ["物品名称", "物品单价/元", "预警库存", "物品总数", "总金额", "状态"]
        ),
        records=[
            _item("rec-wly", "五粮液", 10, 800),
            _item("rec-mt", "茅台", 5, 1499),
            _item("rec-zh", "中华", 20, 50),
        ],
    )


def _requisition_table() -> MirroredTable:
    return MirroredTable(
        resource=_resource("领用记录"),
        fields=_fields(
            [
                "领用物品（一）",
                "领用数量（一）",
                "领用物品（二）",
                "领用数量（二）",
                "领用金额",
                "申请人",
                "状态",
            ]
        ),
        records=[
            _requisition("r1", "已领用", "张三", [("rec-wly", 2), ("rec-zh", 3)]),
            _requisition("r2", "总经理已审批", "李四", [("rec-mt", 4)]),
            _requisition("r3", "已作废", "张三", [("rec-mt", 50)]),
            _requisition("r4", "申请中", "李四", [("rec-gone", 7)]),
            _requisition("r5", "", "王五", [("rec-zh", 1)]),
        ],
    )


# ---------- 聚合口径 ----------


def test_extract_inventory_matches_dashboard_definitions() -> None:
    stock = _extract_inventory(_inventory_table())
    assert stock.categories == 3
    assert stock.total_count == 35  # Σ物品总数，不是预警库存
    assert stock.total_value == 10 * 800 + 5 * 1499 + 20 * 50  # Σ总金额（公式）
    assert stock.quantity_by_item == {"五粮液": 10, "茅台": 5, "中华": 20}
    assert stock.value_by_item["茅台"] == 7495
    assert stock.name_by_record["rec-mt"] == "茅台"


def test_extract_requisitions_excludes_void_and_counts_received_only() -> None:
    stock = _extract_inventory(_inventory_table())
    usage = _extract_requisitions(
        _requisition_table(), stock.name_by_record, inventory_available=True
    )
    # 已领用物品总数只计状态为「已领用」的单：2 + 3
    assert usage.received_total == 5
    # 作废单（茅台 50）不计；未作废单不论审批状态都计入领取分析
    assert usage.quantity_by_item["茅台"] == 4
    assert usage.quantity_by_item["中华"] == 4
    assert usage.quantity_by_item["五粮液"] == 2
    # 关联到已删除物品的记录合并为一根「已删除物品」柱子，不露出原始 record_id
    assert usage.quantity_by_item["已删除物品"] == 7
    # 员工维度按申请人
    assert usage.quantity_by_employee == {"张三": 5, "李四": 11, "王五": 1}


def test_unresolved_items_are_not_called_deleted_without_inventory() -> None:
    usage = _extract_requisitions(_requisition_table(), {}, inventory_available=False)
    assert "物品·ec-wly" in usage.quantity_by_item
    assert not any(name.startswith("已删除") for name in usage.quantity_by_item)


# ---------- 仪表台服务（mock 仓库） ----------


@pytest.fixture
def _tables(monkeypatch: pytest.MonkeyPatch) -> dict[str, MirroredTable | None]:
    tables: dict[str, MirroredTable | None] = {}

    async def _get_default(self: Any, page_key: str) -> MirroredTable | None:
        return tables.get(page_key)

    monkeypatch.setattr(
        "app.modules.administration.service.AdministrationRepository.get_default_bound_table",
        _get_default,
    )
    return tables


async def test_dashboard_stats_end_to_end(
    _tables: dict[str, MirroredTable | None],
) -> None:
    _tables["admin:tobacco-gift:items"] = _inventory_table()
    _tables["admin:tobacco-gift:records"] = _requisition_table()

    stats = await AdministrationTobaccoGiftService(session=None).get_dashboard_stats()  # type: ignore[arg-type]

    assert stats.item_categories == 3
    assert stats.item_total_count == 35
    assert stats.item_total_value == 16495
    assert stats.requisitioned_total == 5
    assert {item.name for item in stats.inventory_by_item} == {"五粮液", "茅台", "中华"}
    assert stats.value_by_item[0].name == "五粮液"  # 8000 最大
    assert stats.requisition_by_employee[0].name == "李四"
    assert stats.inventory_synced_at is not None


async def test_dashboard_stats_zero_when_no_bindings(
    _tables: dict[str, MirroredTable | None],
) -> None:
    stats = await AdministrationTobaccoGiftService(session=None).get_dashboard_stats()  # type: ignore[arg-type]
    assert stats.item_categories == 0
    assert stats.requisitioned_total == 0
    assert stats.inventory_by_item == []
    assert stats.requisition_synced_at is None


async def test_dashboard_stats_tolerates_unknown_fields(
    _tables: dict[str, MirroredTable | None],
) -> None:
    _tables["admin:tobacco-gift:items"] = MirroredTable(
        resource=_resource("物品清单"),
        fields=_fields(["神秘列A", "神秘列B"]),
        records=[_record("rec-x", {"神秘列A": "x", "神秘列B": 1})],
    )
    stats = await AdministrationTobaccoGiftService(session=None).get_dashboard_stats()  # type: ignore[arg-type]
    assert stats.item_categories == 1
    assert stats.item_total_count == 0
    assert stats.inventory_by_item == []


def test_module_exports_page_keys() -> None:
    assert admin_service.ADMINISTRATION_READ_PAGE_KEYS >= {
        "admin:tobacco-gift:items",
        "admin:tobacco-gift:records",
    }
