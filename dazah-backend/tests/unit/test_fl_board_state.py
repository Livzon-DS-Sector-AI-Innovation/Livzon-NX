"""FL 看板状态机与仓储台账解析单测（纯函数，不触库）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.production import fl_board_api as api
from app.modules.production.fl_models import FlBatch


def _batch(**overrides: Any) -> FlBatch:
    defaults: dict[str, Any] = {"batch_no": "FL-2609001"}
    defaults.update(overrides)
    return FlBatch(**defaults)


# ── 投料开始时刻 ──


def test_charge_start_with_time_range() -> None:
    item = _batch(charge_date=date(2026, 9, 22), charge_time="8:00~10:00")
    assert api._charge_start(item) == datetime(2026, 9, 22, 8, 0)


def test_charge_start_without_time_or_date() -> None:
    assert api._charge_start(_batch(charge_date=date(2026, 9, 22))) == datetime(
        2026, 9, 22, 0, 0
    )
    assert api._charge_start(_batch()) is None


# ── 批次状态机 ──


def test_state_inbound_when_confirmed() -> None:
    anchor = datetime(2026, 9, 22, 12)
    state, actual = api._batch_state(
        _batch(), {"confirmed": True, "inbound_date": date(2026, 9, 1)}, anchor
    )
    assert state == api.STATE_INBOUND
    assert actual == date(2026, 9, 1)


def test_state_confirm_pending_when_registered_unconfirmed() -> None:
    # 已登记未勾确认：即使计划入库日未到也视为待仓库确认
    anchor = datetime(2026, 9, 22, 12)
    state, _ = api._batch_state(
        _batch(charge_date=date(2026, 9, 22), inbound_date=date(2026, 9, 23)),
        {"confirmed": False, "inbound_date": date(2026, 9, 22)},
        anchor,
    )
    assert state == api.STATE_CONFIRM_PENDING


def test_state_upcoming_running_stalled_by_time_window() -> None:
    item = _batch(charge_date=date(2026, 9, 22), inbound_date=date(2026, 9, 23))
    # 锚点未到投料时刻 → 待投料
    assert api._batch_state(item, None, datetime(2026, 9, 21, 12))[0] == (
        api.STATE_UPCOMING
    )
    # 投料后、计划入库日次日前 → 在制
    assert api._batch_state(item, None, datetime(2026, 9, 22, 12))[0] == (
        api.STATE_RUNNING
    )
    # 已过计划入库日且无登记 → 滞留
    assert api._batch_state(item, None, datetime(2026, 9, 24, 12))[0] == (
        api.STATE_STALLED
    )


def test_state_stalled_when_plan_inbound_missing() -> None:
    # 排产漏填入库日：投料后无台账登记即滞留
    item = _batch(charge_date=date(2026, 9, 20))
    assert api._batch_state(item, None, datetime(2026, 9, 22, 12))[0] == (
        api.STATE_STALLED
    )


# ── 当前工序（按计划时间推导）──


def test_current_stage_by_time() -> None:
    item = _batch(
        order_date=date(2026, 9, 21),
        charge_date=date(2026, 9, 22),
        charge_time="8:00~10:00",
        mix_date=date(2026, 9, 22),
        mix_time="10:00~12:00",
        pack_date=date(2026, 9, 23),
        pack_time="14:00~16:00",
        inbound_date=date(2026, 9, 23),
    )
    # 投料当日 7:00：指令已到（前日末刻），投料未开始
    key, label = api._current_stage(item, datetime(2026, 9, 22, 7))
    assert (key, label) == ("order", "指令")
    # 投料当日 9:00：投料已开始、混合（10:00）未到
    key, _ = api._current_stage(item, datetime(2026, 9, 22, 9))
    assert key == "charge"
    # 9/23 15:00：包装已开始、入库（当日末刻）未到
    key, _ = api._current_stage(item, datetime(2026, 9, 23, 15))
    assert key == "pack"
    # 9/24：入库节点到期
    key, label = api._current_stage(item, datetime(2026, 9, 24, 12))
    assert (key, label) == ("inbound", "入库")


# ── 台账行归并 ──


def test_build_batch_index_merges_rows() -> None:
    rows = [
        {
            "batch_no": "FL-2602007",
            "inbound_date": date(2026, 2, 13),
            "qty": 1860.0,
            "confirmed": True,
        },
        {
            "batch_no": "FL-2602007",
            "inbound_date": date(2026, 3, 4),
            "qty": 0.0,
            "confirmed": True,
        },
        {
            "batch_no": "FL-2609003",
            "inbound_date": date(2026, 9, 3),
            "qty": 1980.0,
            "confirmed": False,
        },
    ]
    index = api._build_batch_index(rows)
    assert index["FL-2602007"] == {
        "confirmed": True,
        "inbound_date": date(2026, 3, 4),
        "kg": 1860.0,
        "registered": True,
    }
    assert index["FL-2609003"]["confirmed"] is False
    assert api._build_batch_index(None) == {}


# ── 仓储台账（明细）解析 ──


@pytest.mark.anyio
async def test_warehouse_service_parses_detail_cells() -> None:
    from app.modules.warehouse.service import WarehouseService

    service = WarehouseService(MagicMock())
    service.repo = MagicMock()
    service.repo.get_material_page_snapshot = AsyncMock(return_value=object())
    service.repo.list_finished_inbound_cells = AsyncMock(
        return_value=[
            {
                "产品名称": "2%氟苯尼考预混剂",
                "入库标签批号": "fl－2609007",
                "入库日期": 1_789_790_400_000,  # 2026-09-19 12:00 北京
                "入库量": "1980",
                "入库确认": "true",
            },
            {
                "产品名称": "2%氟苯尼考预混剂",
                "入库标签批号": "FL-2609008",
                "入库日期": 1_789_876_800_000,  # 2026-09-20 12:00 北京
                "入库量": 1980,
                "入库确认": False,
            },
            {"产品名称": "2%氟苯尼考预混剂", "入库标签批号": None},
        ]
    )
    batches = await service.get_finished_inbound_batches(
        product_name="2%氟苯尼考预混剂"
    )
    assert batches == [
        {
            "batch_no": "FL-2609007",
            "inbound_date": date(2026, 9, 19),
            "qty": 1980.0,
            "confirmed": True,
        },
        {
            "batch_no": "FL-2609008",
            "inbound_date": date(2026, 9, 20),
            "qty": 1980.0,
            "confirmed": False,
        },
    ]
