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
    # FA-PREV 未录产量 → 计入待出产量；无产量时已完成产能为 None
    assert kpis["done_with_yield"] == 0
    assert kpis["yield_pending"] == 1
    assert kpis["month_done_yield_kg"] is None
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
async def test_dump_window_gates_completion() -> None:
    """计划放罐时间 + 2h 窗口内为「放罐中」；窗口结束后才算已完成。"""
    rows = _mini_rows()
    # FA-M0 计划 8/30 10:00 放罐；10:35 仍在放罐窗口内，剩余 1h25min
    payload = board.build_board(rows, [], datetime(2026, 8, 30, 10, 35))
    assert payload is not None
    tanks = {t["tank_no"]: t for t in payload["tanks"]}
    assert tanks["302A"]["status"] == "dumping"
    assert tanks["302A"]["batch_no"] == "FA-M0"
    assert tanks["302A"]["note"] == "放罐中（预计1h25min后结束）"

    # 11:00 剩余整 1 小时 → 只显示小时；窗口内批次不计入已完成 KPI，也不进入最近完成
    payload = board.build_board(rows, [], datetime(2026, 8, 30, 11, 0))
    assert payload is not None
    tanks = {t["tank_no"]: t for t in payload["tanks"]}
    assert tanks["302A"]["status"] == "dumping"
    assert tanks["302A"]["note"] == "放罐中（预计1h后结束）"
    assert payload["kpis"]["month_done_planned"] == 1  # 仅 FA-PREV
    assert all(item["batch_no"] != "FA-M0" for item in payload["recent"])
    assert payload["recent"][0]["batch_no"] == "FA-PREV"

    # 12:00 窗口结束 → 批次已完成；罐转空闲并提示下一批移种
    payload = board.build_board(rows, [], datetime(2026, 8, 30, 12, 0))
    assert payload is not None
    tanks = {t["tank_no"]: t for t in payload["tanks"]}
    assert tanks["302A"]["status"] == "idle"
    assert "移种FA-M3" in tanks["302A"]["note"]
    assert payload["kpis"]["month_done_planned"] == 2
    assert payload["recent"][0]["batch_no"] == "FA-M0"


@pytest.mark.anyio
async def test_running_dump_alert_only_within_24h() -> None:
    """运行批次的放罐播报只提醒 24h 内将要放罐的批次。"""
    rows = _mini_rows()
    # FA-M0 计划 8/30 10:00 放罐：8/29 09:00 距放罐 25h → 不播报
    payload = board.build_board(rows, [], datetime(2026, 8, 29, 9, 0))
    assert payload is not None
    assert all("距预估放罐剩余" not in a["text"] for a in payload["alerts"])

    # 8/29 11:00 距放罐 23h → 播报
    payload = board.build_board(rows, [], datetime(2026, 8, 29, 11, 0))
    assert payload is not None
    assert any(
        "FA-M0" in a["text"] and "距预估放罐剩余" in a["text"]
        for a in payload["alerts"]
    )


@pytest.mark.anyio
async def test_build_board_merges_batch_actuals() -> None:
    """已录入产量的批次回填最近完成列表，并生成按批次顺序的单批产量序列。"""
    rows = _mini_rows()
    actuals = [
        {
            "id": "1",
            "batch_no": "FA-PREV",
            "dump_date": "2026-08-27",
            "yield_kg": 100.0,
            "remark": "染菌批",
        },
        {
            "id": "2",
            "batch_no": "FA26231",
            "dump_date": "2026-08-28",
            "yield_kg": 120.5,
            "remark": None,
        },
        {"id": "3", "batch_no": "FA26232", "dump_date": "2026-08-29", "yield_kg": None},
    ]
    payload = board.build_board(rows, [], datetime(2026, 8, 28, 12, 0), actuals=actuals)
    assert payload is not None
    # 图表只含有产量的批次，按批次顺序升序（FA-PREV 无数字后缀排最前）
    assert payload["trend"] == {
        "batches": ["FA-PREV", "FA26231"],
        "outputs": [100.0, 120.5],
    }
    # 最近完成批次回填实际产量与备注
    assert payload["recent"][0]["batch_no"] == "FA-PREV"
    assert payload["recent"][0]["yield_kg"] == 100.0
    assert payload["recent"][0]["remark"] == "染菌批"
    # 已放罐批次清单：窗口已结束的批次按日期升序（供产量录入下拉）
    assert payload["dumped_batches"] == [
        {"batch_no": "FA-PREV", "dump_date": "2026-08-27"}
    ]
    # FA-PREV 已录产量 → 计入已完成；FA26231/FA26232 不在本周期块内
    payload_kpis = payload["kpis"]
    assert payload_kpis["done_with_yield"] == 1
    assert payload_kpis["yield_pending"] == 0
    # 已完成产能 = 本周期已录入产量合计
    assert payload_kpis["month_done_yield_kg"] == 100.0

    # 未传 actuals 时 trend 为 None（向后兼容）
    payload = board.build_board(rows, [], datetime(2026, 8, 28, 12, 0))
    assert payload is not None
    assert payload["trend"] is None


@pytest.mark.anyio
async def test_trend_limits_to_31_batches() -> None:
    """单批产量序列最多 31 批，超出时保留批次顺序最大的 31 条。"""
    rows = _mini_rows()
    actuals = [
        {"id": str(i), "batch_no": f"FA26{i:03d}", "dump_date": None, "yield_kg": 100.0}
        for i in range(1, 36)  # 35 批
    ]
    payload = board.build_board(rows, [], datetime(2026, 8, 28, 12, 0), actuals=actuals)
    assert payload is not None
    assert len(payload["trend"]["batches"]) == 31
    assert payload["trend"]["batches"][0] == "FA26005"  # 1~4 批被淘汰
    assert payload["trend"]["batches"][-1] == "FA26035"


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
