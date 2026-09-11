"""物品管理仪表盘纯逻辑：数值解析、预警判定（两口径）、月度聚合、文案模板。"""

from __future__ import annotations

from app.modules.quality.schemas.inspection_items_dashboard import (
    ItemsStockAlertItem,
)
from app.modules.quality.service.items_dashboard import (
    _aggregate_monthly,
    _build_alert_content,
    _is_low_stock,
    _render_template,
    _to_number,
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
