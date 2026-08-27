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
    from datetime import datetime

    assert _extract_date(None) is None
    # 毫秒时间戳 → 本地时区日期（与实现同源计算期望值）
    assert _extract_date(1700000000000) == datetime.fromtimestamp(1700000000).date()
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


def test_sync_sales_plan_creates_and_updates() -> Any:
    import asyncio

    existing = SimpleNamespace(product_name="霉酚酸", unit=None)
    client = MagicMock()
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


def test_sync_sales_plan_creates_new_without_product_field() -> Any:
    import asyncio

    client = MagicMock()
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
    assert len(SALES_FIELD_MAP) >= 14
