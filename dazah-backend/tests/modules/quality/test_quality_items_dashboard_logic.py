"""物品管理仪表盘纯逻辑：数值解析、预警判定（两口径）、月度聚合、文案模板。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.quality.schemas.inspection_items_dashboard import (
    ItemsStockAlertItem,
)
from app.modules.quality.service.items_dashboard import (
    _aggregate_monthly,
    _build_alert_content,
    _cell_text,
    _is_low_stock,
    _pick_cell_value,
    _render_template,
    _row_month,
    _to_number,
    find_low_stock_items,
)
from app.modules.quality.service.quality_notification_settings import (
    ItemsStockAlertConfig,
)


def test_to_number_variants() -> None:
    assert _to_number("1,200") == 1200.0
    assert _to_number(5) == 5.0
    assert _to_number(["3"]) == 3.0
    assert _to_number("") is None
    assert _to_number("abc") is None
    assert _to_number(True) is None


def test_is_low_stock_feishu_source() -> None:
    assert _is_low_stock({"库存报警": "库存不足"}, "feishu") is True
    assert _is_low_stock({"库存报警": "正常"}, "feishu") is False


def test_is_low_stock_local_threshold() -> None:
    assert _is_low_stock({"当前库存": 2, "警戒库存": 5}, "local_threshold") is True
    assert _is_low_stock({"当前库存": 8, "警戒库存": 5}, "local_threshold") is False
    # 缺数值不误判
    assert _is_low_stock({"当前库存": None, "警戒库存": 5}, "local_threshold") is False


def test_aggregate_monthly_fills_12_months() -> None:
    # epoch ms: 2026-01-15 与 2026-03-10（UTC）
    jan = 1_768_435_200_000  # 2026-01-15
    mar = 1_773_100_800_000  # 2026-03-10
    inbound = [{"入库日期": jan, "入库数量": "10"}, {"入库日期": mar, "入库数量": "5"}]
    outbound = [{"领用日期": mar, "领取数量": "3"}]
    points = _aggregate_monthly(inbound, outbound, 2026)
    assert len(points) == 12
    m1 = next(p for p in points if p.month == 1)
    m3 = next(p for p in points if p.month == 3)
    assert m1.inbound == 10
    assert m3.inbound == 5
    assert m3.outbound == 3


def test_render_and_build_content() -> None:
    assert _render_template("", "默认 {count}", {"count": "3"}) == "默认 3"
    assert _render_template("抬头 {d}", "x", {"d": "09"}) == "抬头 09"

    items = [
        ItemsStockAlertItem(record_id=f"r{i}", name=f"物{i}", current_stock="1")
        for i in range(12)
    ]
    config = ItemsStockAlertConfig(
        header_template="预警 {count}",
        footer_template="共 {count} 种",
    )
    title, content = _build_alert_content(items, config, "2026-09-11")
    assert title == "预警 12"
    assert "物0" in content
    # 超过预览上限(10)出现溢出提示
    assert "其余 2 种" in content
    assert "共 12 种" in content
def test_cell_text_variants() -> None:
    assert _cell_text(None) == ""
    assert _cell_text("  abc  ") == "abc"
    assert _cell_text(12) == "12"
    assert _cell_text([1, "二"]) == "1 二"
    assert _cell_text({"text": "T"}) == "T"
    assert _cell_text({"name": "N"}) == "N"
    assert _cell_text(3.5) == "3.5"


def test_pick_cell_value_falls_through_keys() -> None:
    assert _pick_cell_value({"a": "", "b": "ok"}, ["a", "b"]) == "ok"
    assert _pick_cell_value({"a": None}, ["a", "b"]) is None
    assert _pick_cell_value({}, ["a"]) is None


def test_row_month_parses_timestamps_and_dates() -> None:
    # 毫秒时间戳
    assert _row_month({"日期": "1735689600000"}, ["日期"]) == 1
    # ISO 日期串
    assert _row_month({"日期": "2026-09-03T10:00:00+08:00"}, ["日期"]) == 9
    # 列表取首项
    assert _row_month({"日期": ["2026-05-12"]}, ["日期"]) == 5
    # 非法值回退 created_at
    assert _row_month({"日期": "bad"}, ["日期"]) is None
    assert _row_month({"created_at": "2026-07-01T00:00:00"}, ["日期"]) == 7
    assert _row_month({}, ["日期"]) is None


async def test_find_low_stock_items_uses_inventory_page(
    monkeypatch: Any,
) -> None:
    async def fake_list(db: Any, page_key: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "items": [
                {"record_id": "r1", "当前库存": 1, "警戒库存": 5},
                {"record_id": "r2", "当前库存": 9, "警戒库存": 5},
            ],
            "configured": True,
            "last_sync_time": None,
        }

    monkeypatch.setattr("app.modules.quality.service.items_dashboard.list_items_mirror", fake_list)

    found = await find_low_stock_items(
        None, ItemsStockAlertConfig(warning_source="local_threshold")
    )
    assert [item["record_id"] for item in found] == ["r1"]
def test_build_deep_link_appends_feishu_filter(monkeypatch: Any) -> None:
    from app.modules.quality.service.items_dashboard import _build_deep_link

    monkeypatch.setenv("FRONTEND_URL", "https://qa.example.cn")
    from app.core.config import get_settings

    get_settings.cache_clear()
    link = _build_deep_link(ItemsStockAlertConfig(warning_source="feishu"))
    assert link == "https://qa.example.cn/quality/inspection/items/inventory?filter_库存报警=库存不足"
    local = _build_deep_link(ItemsStockAlertConfig(warning_source="local_threshold"))
    assert local == "https://qa.example.cn/quality/inspection/items/inventory"
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_resolve_recipients_fills_open_id_by_name(monkeypatch: Any) -> None:
    from app.modules.quality.service.items_dashboard import _resolve_recipients

    async def fake_by_name(db: Any, name: str) -> dict[str, Any] | None:
        return {"open_id": f"ou_{name}"} if name == "张三" else None

    monkeypatch.setattr(
        "app.modules.quality.service.items_dashboard.resolve_person_by_name",
        fake_by_name,
    )
    config = ItemsStockAlertConfig(
        is_enabled=True,
        recipients=[
            {"open_id": "ou_direct", "name": "直连人"},
            {"name": "张三"},
            {"name": "无名氏"},
            {"name": "  "},
        ],
    )
    resolved = await _resolve_recipients(None, config)
    assert resolved == [
        ("ou_direct", "open_id", "直连人"),
        ("ou_张三", "open_id", "张三"),
    ]
@pytest.mark.anyio
async def test_push_low_stock_alert_test_mode_sends_and_reports(
    monkeypatch: Any,
) -> None:
    """测试推送：两个接收人都发送成功，不写幂等记录。"""
    from unittest.mock import AsyncMock as _AM

    from app.modules.quality.schemas.inspection_items_dashboard import (
        PushLowStockResult,
    )
    from app.modules.quality.service import items_dashboard as svc
    from app.modules.quality.service.items_dashboard import (
        _STOCK_ALARM_LOW_VALUES,
    )

    assert _STOCK_ALARM_LOW_VALUES  # 常量存在

    low_rows = [
        {"record_id": "r1", "当前库存": 1, "警戒库存": 5, "物资名称": "酒精"},
        {"record_id": "r2", "当前库存": 2, "警戒库存": 5, "物资名称": "纱布"},
    ]
    monkeypatch.setattr(
        svc, "load_items_stock_alert_config",
        _AM(return_value=ItemsStockAlertConfig(is_enabled=True, warning_source="local_threshold")),
    )
    monkeypatch.setattr(svc, "find_low_stock_items", _AM(return_value=low_rows))
    monkeypatch.setattr(
        svc, "_build_deep_link",
        lambda config: "https://qa.example.cn/inventory",
    )
    monkeypatch.setattr(
        svc, "_resolve_recipients",
        _AM(return_value=[("ou_a", "open_id", "甲"), ("ou_b", "open_id", "乙")]),
    )
    send_mock = _AM(return_value="msg-1")
    monkeypatch.setattr(
        svc.feishu_notification,
        "send_user_card_with_message_id",
        send_mock,
    )
    record_mock = _AM()
    monkeypatch.setattr(svc, "_record_notifications", record_mock)

    db = SimpleNamespace(commit=_AM(), flush=_AM(), add=lambda *_: None)
    result = await svc.push_low_stock_alert(db, test=True)
    assert isinstance(result, PushLowStockResult)
    assert result.status == "sent"
    assert result.sent == 2
    assert send_mock.await_count == 2
    record_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_push_low_stock_alert_returns_unmapped_without_recipients(
    monkeypatch: Any,
) -> None:
    from app.modules.quality.service import items_dashboard as svc

    monkeypatch.setattr(
        svc, "load_items_stock_alert_config",
        AsyncMock(return_value=ItemsStockAlertConfig(is_enabled=True)),
    )
    monkeypatch.setattr(svc, "find_low_stock_items", AsyncMock(return_value=[
        {"record_id": "r1", "当前库存": 1, "警戒库存": 5}
    ]))
    monkeypatch.setattr(svc, "_resolve_recipients", AsyncMock(return_value=[]))

    db = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock(), add=lambda *_: None)
    result = await svc.push_low_stock_alert(db, test=True)
    assert result.status == "unmapped"

