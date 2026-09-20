"""生产计划 / 销售计划飞书同步服务测试（纯辅助 + mock 客户端与 session）。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.production.production_plan_service import (
    SALES_FIELD_MAP,
    SYNC_TARGETS,
    _extract_date,
    _extract_number,
    _extract_text,
    _sales_plan_data_month,
    _sync_production_plan,
    _sync_sales_plan,
    sync_config_by_target,
)


def make_config(**over: Any) -> Any:
    cfg = {
        "app_id": "app-id",
        "encrypted_app_secret": "enc-secret",
        "bitable_app_token": "token",
        "table_id": "tbl1",
        "product_name": "霉酚酸",
        "sync_target": "production_plan",
    }
    cfg.update(over)
    return SimpleNamespace(**cfg)


def make_session(scalar_result: Any=None) -> Any:
    s = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_result
    s.execute = AsyncMock(return_value=result)
    s.add = MagicMock()
    s.flush = AsyncMock()
    return s


# ═══════════ 纯辅助函数 ═══════════


def test_extract_text_variants() -> Any:
    assert _extract_text(None) is None
    assert _extract_text("  值  ") == "值"
    assert _extract_text("") is None
    assert _extract_text({"name": "甲", "text": "乙"}) == "甲"
    assert _extract_text({"text": "乙"}) == "乙"
    assert _extract_text(["甲", "乙"]) == "甲"
    assert _extract_text([{"name": "丙"}]) == "丙"
    assert _extract_text([]) is None
    assert _extract_text(123) is None


def test_extract_number_variants() -> Any:
    assert _extract_number({"type": 2, "value": [12.5]}) == 12.5
    assert _extract_number({"type": 2, "value": ["x"]}) is None
    assert _extract_number({"type": 1, "value": [3]}) is None
    assert _extract_number(" 45.6 ") == 45.6
    assert _extract_number("not-a-number") is None
    assert _extract_number(None) is None


def test_extract_date_variants() -> Any:
    assert _extract_date(None) is None
    # 毫秒时间戳按飞书口径 = 北京时间零点；不锚定时区会差一天
    assert _extract_date(1782835200000) == date(2026, 7, 1)  # 2026-07-01 00:00 +08:00
    assert _extract_date(1700000000000) == date(2023, 11, 15)  # 2023-11-15 06:13 +08:00
    assert _extract_date(0) is None
    assert _extract_date(-5) is None
    assert _extract_date("2026-03-01") == date(2026, 3, 1)
    assert _extract_date("bad-date") is None


# ═══════════ _sync_production_plan ═══════════


def _records_page(items: Any, has_more: Any=False, page_token: Any=None) -> Any:
    return {"items": items, "has_more": has_more, "page_token": page_token}


def test_sync_production_plan_creates_records() -> Any:
    import asyncio

    client = MagicMock()
    client.list_records = AsyncMock(
        return_value=_records_page(
            [
                {
                    "fields": {
                        "车间": "201-2",
                        "产品": "霉酚酸",
                        "日期": 1700000000000,
                        "单位": "kg",
                        "计划产量": {"type": 2, "value": [1000]},
                        "实际完成": "800",
                        "完成率": "80%",
                        "安环情况": "正常",
                        "质量情况": "合格",
                        "备注": " 备注 ",
                    }
                }
            ]
        )
    )
    with (
        patch(
            "app.modules.production.production_plan_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.production_plan_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(
            _sync_production_plan(make_config(), make_session(scalar_result=None))
        )
    assert result == {"created": 1, "updated": 0, "product": "霉酚酸"}


def test_sync_production_plan_creates_and_paginates() -> Any:
    import asyncio

    client = MagicMock()
    client.list_records = AsyncMock(
        side_effect=[
            _records_page(
                [
                    {
                        "fields": {
                            "车间": "201-2",
                            "产品": "霉酚酸",
                            "日期": "2026-03-01",
                            "单位": "kg",
                        }
                    }
                ],
                has_more=True,
                page_token="tok1",
            ),
            _records_page(
                [
                    {
                        "fields": {
                            "车间": "201-2",
                            "产品": "霉酚酸",
                            "日期": "2026-03-02",
                            "单位": "kg",
                        }
                    }
                ],
                has_more=False,
            ),
        ]
    )
    with (
        patch(
            "app.modules.production.production_plan_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.production_plan_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(
            _sync_production_plan(make_config(), make_session(scalar_result=None))
        )
    assert result["created"] == 2
    assert client.list_records.await_args_list[1].kwargs["page_token"] == "tok1"


def test_sync_production_plan_assigns_row_order() -> Any:
    """飞书行序跨分页累加写入 row_order，用于台账稳定排序。"""
    import asyncio

    session = make_session(scalar_result=None)
    client = MagicMock()
    client.list_records = AsyncMock(
        side_effect=[
            _records_page(
                [
                    {
                        "fields": {
                            "车间": "201-1车间",
                            "产品": "洛伐他汀",
                            "日期": "2026-07-01",
                        }
                    },
                    {
                        "fields": {
                            "车间": "201-2车间",
                            "产品": "霉酚酸",
                            "日期": "2026-07-01",
                        }
                    },
                ],
                has_more=True,
                page_token="tok1",
            ),
            _records_page(
                [
                    {
                        "fields": {
                            "车间": "菌种中心",
                            "产品": "供种/接种/培养基",
                            "日期": "2026-07-01",
                        }
                    }
                ],
                has_more=False,
            ),
        ]
    )
    with (
        patch(
            "app.modules.production.production_plan_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.production_plan_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(_sync_production_plan(make_config(), session))

    assert result["created"] == 3
    row_orders = [call.args[0].row_order for call in session.add.call_args_list]
    assert row_orders == [1, 2, 3]


def test_sync_production_plan_updates_existing_and_skips() -> Any:
    import asyncio

    existing = SimpleNamespace(product_name="霉酚酸", workshop="201-2", plan_date=None)
    client = MagicMock()
    client.list_records = AsyncMock(
        return_value=_records_page(
            [
                {
                    "fields": {
                        "车间": "201-2",
                        "产品": "霉酚酸",
                        "日期": "2026-03-01",
                        "完成率": "90",
                    }
                },
                {
                    "fields": {"车间": "201-2", "日期": "2026-03-02"}
                },  # 无产品名且配置无默认 → 跳过
            ]
        )
    )
    session = make_session(scalar_result=existing)
    with (
        patch(
            "app.modules.production.production_plan_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.production_plan_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(
            _sync_production_plan(make_config(product_name=None), session)
        )
    assert result["created"] == 0
    assert result["updated"] == 1
    assert existing.completion_rate == 90.0
    assert existing.source == "feishu"
    session.flush.assert_awaited()


# ═══════════ _sync_sales_plan ═══════════


def test_sales_plan_data_month_from_table_name() -> Any:
    """数据月份从源数据表名解析：月份取表名，年份取同步时当前年。"""
    today = date(2026, 9, 18)
    assert _sales_plan_data_month("5月份销售计划执行表", today) == "2026-05"
    assert _sales_plan_data_month("12月份销售计划执行表", today) == "2026-12"
    # 解析失败（无月份/越界）回退当前月
    assert _sales_plan_data_month("执行表", today) == "2026-09"
    assert _sales_plan_data_month("13月份表", today) == "2026-09"
    assert _sales_plan_data_month("", today) == "2026-09"


def test_sync_sales_plan_creates_and_updates() -> Any:
    import asyncio

    existing = SimpleNamespace(product_name="霉酚酸", unit=None)
    client = MagicMock()
    client.list_tables = AsyncMock(
        return_value=[{"table_id": "tbl1", "name": "9月份销售计划执行表"}]
    )
    client.list_records = AsyncMock(
        return_value=_records_page(
            [
                {
                    "fields": {
                        "产品名称": "霉酚酸",
                        "单位": "kg",
                        "本月计划发货量": {"type": 2, "value": [500]},
                        "本月已发货量": "300",
                        "未发货量": "200",
                        "2025年当月发货量": {"type": 2, "value": [12000]},
                        "备注": "x",
                    }
                }
            ]
        )
    )
    session = make_session(scalar_result=existing)
    with (
        patch(
            "app.modules.production.production_plan_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.production_plan_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(
            _sync_sales_plan(make_config(sync_target="sales_plan"), session)
        )
    assert result["created"] == 0
    assert result["updated"] == 1
    assert existing.month_planned_delivery == 500.0
    assert existing.month_delivered_qty == 300.0
    # 数据月份按源数据表名解析，写入行上
    assert existing.data_month == f"{date.today().year}-09"
    # 同步时记录来源飞书数据表名，供前端展示真实来源
    assert existing.source_table_name == "9月份销售计划执行表"
    # 同比参照列按“<上一年>年当月发货量”动态匹配
    assert existing.current_year_delivered == 12000.0


def test_sync_sales_plan_creates_new_without_product_field() -> Any:
    import asyncio

    client = MagicMock()
    client.list_tables = AsyncMock(
        return_value=[{"table_id": "tbl1", "name": "9月份销售计划执行表"}]
    )
    client.list_records = AsyncMock(
        return_value=_records_page(
            [
                {
                    "fields": {
                        "单位": "kg",
                        "本月已发货量": "10",
                        "备注": "无产品名用配置默认",
                    }
                }
            ]
        )
    )
    session = make_session(scalar_result=None)
    with (
        patch(
            "app.modules.production.production_plan_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.production_plan_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(
            _sync_sales_plan(make_config(sync_target="sales_plan"), session)
        )
    assert result["created"] == 1
    assert result["updated"] == 0
    added = session.add.call_args_list[0].args[0]
    assert added.data_month == f"{date.today().year}-09"
    assert added.source_table_name == "9月份销售计划执行表"


def test_sync_sales_plan_targets_first_table_when_table_id_empty() -> Any:
    """数据表 ID 留空：自动取多维表格中第一个数据表（当月执行表）。"""
    import asyncio

    session = make_session(scalar_result=None)
    client = MagicMock()
    client.list_tables = AsyncMock(
        return_value=[
            {"table_id": "tbl-first", "name": "5月份销售计划执行表"},
            {"table_id": "tbl-second", "name": "次日发货量"},
        ]
    )
    client.list_records = AsyncMock(return_value=_records_page([]))
    with (
        patch(
            "app.modules.production.production_plan_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.production_plan_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(
            _sync_sales_plan(
                make_config(sync_target="sales_plan", table_id=""), session
            )
        )
    # 仅同步第一个数据表，数据月份按其表名归属当年 5 月
    client.list_records.assert_awaited_once()
    assert client.list_records.await_args_list[0].args[0] == "tbl-first"
    assert result["data_month"] == f"{date.today().year}-05"


# ═══════════ sync_config_by_target 路由 ═══════════


def test_sync_config_by_target_production_plan() -> Any:
    import asyncio

    with patch(
        "app.modules.production.production_plan_service._sync_production_plan",
        AsyncMock(return_value={"created": 1, "updated": 0, "product": "霉酚酸"}),
    ) as mock_sync:
        result = asyncio.run(sync_config_by_target(make_config(), make_session()))
    assert result["created"] == 1
    mock_sync.assert_awaited_once()


def test_sync_config_by_target_sales_plan() -> Any:
    import asyncio

    with patch(
        "app.modules.production.production_plan_service._sync_sales_plan",
        AsyncMock(return_value={"created": 0, "updated": 2, "product": "霉酚酸"}),
    ) as mock_sync:
        result = asyncio.run(
            sync_config_by_target(make_config(sync_target="sales_plan"), make_session())
        )
    assert result["updated"] == 2
    mock_sync.assert_awaited_once()


def test_sync_config_by_target_fermentation_record() -> Any:
    import asyncio

    with patch(
        "app.modules.production.production_feishu_service.sync_config",
        AsyncMock(return_value={"created": 3, "updated": 0}),
    ) as mock_sync:
        result = asyncio.run(
            sync_config_by_target(
                make_config(sync_target="fermentation_record"), make_session()
            )
        )
    assert result["created"] == 3
    mock_sync.assert_awaited_once()


def test_sync_config_by_target_seed_culture() -> Any:
    import asyncio

    with patch(
        "app.modules.production.seed_culture_sync.sync_seed_culture_to_table",
        AsyncMock(return_value={"created": 1, "updated": 1}),
    ) as mock_sync:
        result = asyncio.run(
            sync_config_by_target(
                make_config(sync_target="seed_culture"), make_session()
            )
        )
    assert result["created"] == 1
    mock_sync.assert_awaited_once()


def test_sync_config_by_target_dr_and_fallback() -> Any:
    import asyncio

    with (
        patch(
            "app.modules.production.dr_feishu_sync.sync_dr_extraction",
            AsyncMock(return_value={"created": 1, "updated": 0}),
        ) as mock_dr,
        patch(
            "app.modules.production.auto_sync_service.auto_sync_config",
            AsyncMock(return_value={"created": 0, "updated": 3}),
        ) as mock_auto,
    ):
        r1 = asyncio.run(
            sync_config_by_target(
                make_config(sync_target="dr_extraction"), make_session()
            )
        )
        r3 = asyncio.run(
            sync_config_by_target(make_config(sync_target="batch"), make_session())
        )
    assert r1["created"] == 1
    assert r3["updated"] == 3
    mock_dr.assert_awaited_once()
    mock_auto.assert_awaited_once()


def test_sync_targets_catalog() -> Any:
    assert SYNC_TARGETS["production_plan"] == "生产计划"
    assert SYNC_TARGETS["sales_plan"] == "销售计划执行表"
    assert SYNC_TARGETS["dr_fourth_refinement"] == "DR 四次精制"
    # 同比列（“<上一年>年当月发货量”）按动态年份匹配，不在静态映射中
    assert len(SALES_FIELD_MAP) == 13


def test_sync_config_by_target_dr_ledger() -> Any:
    import asyncio

    with patch(
        "app.modules.production.dr_feishu_sync.sync_dr_ledger",
        AsyncMock(
            return_value={
                "extraction": {"created": 88},
                "first_refinement": {"created": 300},
            }
        ),
    ) as mock_sync:
        result = asyncio.run(
            sync_config_by_target(
                make_config(sync_target="dr_ledger"), make_session()
            )
        )
    assert result["first_refinement"]["created"] == 300
    mock_sync.assert_awaited_once()
