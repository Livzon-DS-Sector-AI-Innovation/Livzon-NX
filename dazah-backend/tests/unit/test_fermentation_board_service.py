"""发酵车间看板：排产表解析与状态推算单测（构造小型排产块）。"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.modules.production import fermentation_board_service as board

# 构造一个 4 列（8/27~8/30）的单块排产表，行布局与真实表一致
_TITLE = "2026年08月27日～2026年09月26日103车间FA450T罐排产"


def _mini_rows() -> list[list]:
    return [
        [_TITLE, "", "", "", ""],
        ["", "日期", 27, 28, 29, 30],
        ["时间", "罐号", "", "", "", ""],
        ["种子罐", "", "FA-S0", "FA-S1", "FA-S2", "FA-S3"],
        ["罐号", "", "202A", "201A", "202A", "201A"],
        ["接种时间", "", "20:00", "20:00", "20:00", "20:00"],
        ["发酵罐", "", "FA-M0", "FA-M1", "FA-M2", "FA-M3"],
        ["罐号", "", "302A", "303A", "304A", "302A"],
        ["移种时间", "", "21:00", "21:00", "21:00", "21:00"],
        ["放罐", "", "FA-PREV", "", "", "FA-M0"],
        ["罐号", "", "302A", "", "", "302A"],
        ["放罐时间", "", "10:00", "", "", "10:00"],
        ["备注", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
    ]


@pytest.mark.anyio
async def test_find_period_block_and_col_dates() -> None:
    rows = _mini_rows()
    now = datetime(2026, 8, 28, 12, 0)
    block = board.find_period_block(rows, now)
    assert block is not None
    assert block["start"] == date(2026, 8, 27)
    assert block["end"] == date(2026, 9, 26)

    parsed = board.parse_block(rows, block)
    assert len(parsed["days"]) == 4
    assert parsed["days"][0]["date"] == date(2026, 8, 27)
    assert parsed["days"][0]["seed_batch"] == "FA-S0"
    assert parsed["days"][0]["ferm_tank"] == "302A"
    assert parsed["days"][0]["seed_time"].strftime("%H:%M") == "20:00"

    # 超出块范围的日期找不到当前周期
    assert (
        board.find_period_block(rows, datetime(2026, 10, 1, 12, 0)) is None
    )


@pytest.mark.anyio
async def test_build_board_tank_states_and_kpis() -> None:
    rows = _mini_rows()
    now = datetime(2026, 8, 28, 12, 0)
    payload = board.build_board(rows, [], now)
    assert payload is not None

    tanks = {t["tank_no"]: t for t in payload["tanks"]}
    # 302A：8/27 21:00 移种 FA-M0，8/30 10:00 放罐 → 运行中
    assert tanks["302A"]["status"] == "running"
    assert tanks["302A"]["batch_no"] == "FA-M0"
    assert tanks["302A"]["cultured_hours"] == pytest.approx(15.0)
    assert tanks["302A"]["dump_at"].isoformat() == "2026-08-30T10:00:00"
    # 303A/304A 移种尚未开始 → 空闲
    assert tanks["303A"]["status"] == "idle"
    assert tanks["304A"]["status"] == "idle"

    kpis = payload["kpis"]
    assert kpis["month_planned"] == 2  # FA-PREV + FA-M0 两列有放罐批
    assert kpis["month_done_planned"] == 1  # FA-PREV 8/27 已过
    assert kpis["running"] == 1
    assert kpis["pending"] == 3  # 8/28~8/30 三批种子未接种
    assert kpis["avg_yield_rate"] is None  # 实际指标一期为空

    # 最近完成（计划口径）
    assert payload["recent"][0]["batch_no"] == "FA-PREV"
    assert payload["recent"][0]["yield_kg"] is None

    # 今日 8/28 20:00 待接种提醒
    assert any("待接种批次 FA-S1" in a["text"] for a in payload["alerts"])


@pytest.mark.anyio
async def test_build_board_returns_none_outside_period() -> None:
    rows = _mini_rows()
    assert (
        board.build_board(rows, [], datetime(2026, 10, 1, 12, 0)) is None
    )


@pytest.mark.anyio
async def test_maintenance_overrides_tank_state() -> None:
    rows = _mini_rows()
    now = datetime(2026, 8, 28, 12, 0)
    maintenance = [
        {"tank_no": "302A", "reason": "滤芯更换", "started_at": "2026-08-28T08:00:00"}
    ]
    payload = board.build_board(rows, maintenance, now)
    assert payload is not None
    tank = next(t for t in payload["tanks"] if t["tank_no"] == "302A")
    assert tank["status"] == "maintenance"
    assert "滤芯更换" in tank["note"]
    # 看板响应携带检修标注（前端解除操作需要 id）
    assert payload["maintenance"][0]["tank_no"] == "302A"
    # 检修与移种计划冲突告警
    assert any("302A罐检修中" in a["text"] for a in payload["alerts"])
