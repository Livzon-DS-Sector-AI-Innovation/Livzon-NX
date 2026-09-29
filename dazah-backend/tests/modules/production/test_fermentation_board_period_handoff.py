"""发酵看板周期交接回归：倒罐待进罐守卫与跨周期在制批次。"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.modules.production import fermentation_board_service as board


def test_apply_batch_actual_times_turn_in_pending_not_flipped() -> None:
    """倒罐目的罐待进罐行：来源批的实际移种不得提前翻转或覆盖展示。

    确认 303B 移种会写入批号 MV-26071 的实际移种时刻；301A 的待倒罐行
    按设计继承该批号，必须保持排产口径（idle、倒罐时刻、无"实"角标）。
    """
    now = datetime(2026, 9, 29, 11, 25)
    src_tank = {
        "tank_no": "303B",
        "status": "running",
        "batch_no": "MV-26071",
        "inoculate_at": "2026-09-24T19:25:00",
        "cultured_hours": 100.0,
        "cycle_hours": 264.0,
        "dump_at": "2026-09-29T23:00:00",
        "note": "运行中（预计09-29 23:00倒罐至301A）",
    }
    turn_in_pending = {
        "tank_no": "301A",
        "status": "idle",
        "batch_no": None,
        "batch_nos": ["MV-26071"],
        "turn_in": True,
        "inoculate_at": "2026-09-29T23:00:00",
        "inoculate_mark": "（倒罐）",
        "cultured_hours": None,
        "cycle_hours": None,
        "dump_at": "2026-10-05T16:00:00",
        "note": "预计09-29 23:00自303B倒罐至301A（MV-26071）",
    }
    turn_in_running = {
        "tank_no": "302A",
        "status": "running",
        "batch_no": "MV-26070",
        "batch_nos": ["MV-26070"],
        "turn_in": True,
        "inoculate_at": "2026-09-24T19:25:00",
        "cultured_hours": 100.0,
        "cycle_hours": 264.0,
        "dump_at": "2026-10-05T16:00:00",
        "note": "运行中（09-24 19:25自304B倒罐）",
    }
    rows = board._apply_batch_actual_times(
        [src_tank, turn_in_pending, turn_in_running],
        {
            "MV-26071": {"inoculated_at": "2026-09-24T19:25:00"},
            "MV-26070": {"inoculated_at": "2026-09-24T19:25:00"},
        },
        now,
    )
    src, pending, running = rows
    # 来源罐：正常按实际移种覆盖展示并重算培养时长
    assert src["inoculate_actual_at"] == "2026-09-24T19:25:00"
    assert src["cultured_hours"] == 112.0
    # 待倒罐行：保持排产口径，不翻运行中、不覆盖进罐时刻、不带"实"角标
    assert pending["status"] == "idle"
    assert pending["inoculate_at"] == "2026-09-29T23:00:00"
    assert pending["inoculate_actual_at"] is None
    assert pending["cultured_hours"] is None
    assert pending["note"] == "预计09-29 23:00自303B倒罐至301A（MV-26071）"
    # 已倒罐的 turn_in 运行行：仍按来源批实际移种连续累计培养时长
    assert running["inoculate_actual_at"] == "2026-09-24T19:25:00"
    assert running["cultured_hours"] == 112.0


# ── 跨周期在制批次：上周期末移种、本周期放罐（回归：罐状态漏批次）──
# 场景来自 FA 排产：FA26252 于 09-26 21:00（上一周期块最后一列）移种 302A，
# 09-29 10:00 在当前周期块的放罐行放罐；修复前当前块发酵罐行没有该事件，
# 302A 被误判为"检修待投料"等待下一批。


def _cross_period_rows() -> list[list]:
    """两个相邻扎帐周期块：FA-CROSS 跨块发酵，其余批次均在块内闭环。"""
    title_curr = "2026年09月27日～2026年10月26日103车间FA450T罐排产"
    block_prev = [
        ["2026年08月27日～2026年09月26日103车间FA450T罐排产", "", "", "", ""],
        ["", "日期", 24, 25, 26],
        ["时间", "罐号", "", "", ""],
        ["种子罐", "", "", "", ""],
        ["罐号", "", "", "", ""],
        ["接种时间", "", "", "", ""],
        ["发酵罐", "", "FA-X1", "FA-X2", "FA-CROSS"],
        ["罐号", "", "303A", "304A", "302A"],
        ["移种时间", "", "21:00", "21:00", "21:00"],
        ["放罐", "", "FA-W1", "FA-W2", ""],
        ["罐号", "", "303A", "304A", ""],
        ["放罐时间", "", "10:00", "10:00", ""],
        ["备注", ""],
        ["", "", "", "", ""],
    ]
    block_curr = [
        [title_curr, "", "", "", "", "", "", ""],
        ["", "日期", 27, 28, 29, 30, 1, 2],
        ["时间", "罐号", "", "", "", "", "", ""],
        ["种子罐", "", "", "", "", "", "", ""],
        ["罐号", "", "", "", "", "", "", ""],
        ["接种时间", "", "", "", "", "", "", ""],
        ["发酵罐", "", "FA-Y1", "FA-Y2", "FA-Y3", "", "", ""],
        ["罐号", "", "303A", "304A", "302A", "", "", ""],
        ["移种时间", "", "21:00", "21:00", "21:00", "", "", ""],
        ["放罐", "", "FA-X1", "FA-X2", "FA-CROSS", "FA-Y1", "FA-Y2", "FA-Y3"],
        ["罐号", "", "303A", "304A", "302A", "303A", "304A", "302A"],
        ["放罐时间", "", "10:00", "10:00", "10:00", "10:00", "10:00", "10:00"],
        ["备注", ""],
    ]
    return block_prev + [["", "", "", ""]] + block_curr


def test_collect_ferm_events_spans_period_blocks() -> None:
    rows = _cross_period_rows()
    events = board.collect_ferm_events(rows)
    # 上一周期块末列的移种事件与当前块事件同列，且按移种时间升序
    cross = next(ev for ev in events if ev["batch_no"] == "FA-CROSS")
    assert cross["tank_no"] == "302A"
    assert cross["start"] == datetime(2026, 9, 26, 21, 0)
    starts = [ev["start"] for ev in events]
    assert starts == sorted(starts)


def test_build_board_cross_period_batch_shows_on_tank() -> None:
    rows = _cross_period_rows()

    # 放罐窗口前：302A 显示上一周期移种的 FA-CROSS 运行中
    payload = board.build_board(rows, [], datetime(2026, 9, 29, 9, 50))
    assert payload is not None
    tanks = {t["tank_no"]: t for t in payload["tanks"]}
    assert tanks["302A"]["status"] == "running"
    assert tanks["302A"]["batch_no"] == "FA-CROSS"
    assert tanks["302A"]["inoculate_at"] == datetime(2026, 9, 26, 21, 0)
    assert tanks["302A"]["dump_at"] == datetime(2026, 9, 29, 10, 0)
    assert tanks["302A"]["cultured_hours"] == pytest.approx(60.8)
    assert tanks["303A"]["batch_no"] == "FA-Y1"
    assert tanks["304A"]["batch_no"] == "FA-Y2"
    # KPI 运行中包含已在罐的跨周期批次（本周期计划放罐口径）
    assert payload["kpis"]["running"] == 3
    assert payload["kpis"]["pending"] == 1
    assert payload["kpis"]["month_done_planned"] == 2

    # 放罐窗口内：放罐中
    payload = board.build_board(rows, [], datetime(2026, 9, 29, 10, 30))
    assert payload is not None
    tanks = {t["tank_no"]: t for t in payload["tanks"]}
    assert tanks["302A"]["status"] == "dumping"
    assert tanks["302A"]["batch_no"] == "FA-CROSS"

    # 放罐窗口后：302A 等下一批 FA-Y3；FA-CROSS 进最近完成并带移种时间
    payload = board.build_board(rows, [], datetime(2026, 9, 29, 13, 0))
    assert payload is not None
    tanks = {t["tank_no"]: t for t in payload["tanks"]}
    assert tanks["302A"]["status"] == "idle"
    assert tanks["302A"]["batch_nos"] == ["FA-Y3"]
    assert "预计09-29 21:00移种FA-Y3" in tanks["302A"]["note"]
    recent = payload["recent"][0]
    assert recent["batch_no"] == "FA-CROSS"
    assert recent["dump_date"] == "2026-09-29"
    assert recent["tank_no"] == "302A"
    assert recent["inoculate_at"] == "2026-09-26T21:00:00"
    assert recent["cycle_hours"] == pytest.approx(61.0)


def test_maintenance_conflict_ignores_past_events() -> None:
    rows = _cross_period_rows()
    maintenance = [
        {"tank_no": "302A", "reason": "滤芯更换", "started_at": "2026-09-29T11:00:00"}
    ]
    payload = board.build_board(rows, maintenance, datetime(2026, 9, 29, 13, 0))
    assert payload is not None
    conflicts = [a["text"] for a in payload["alerts"] if "检修中" in a["text"]]
    # 只有未来移种计划（FA-Y3）构成冲突；已放罐的 FA-CROSS 不误报
    assert conflicts == [
        "【冲突】302A罐检修中，但本周期仍有移种计划（如 FA-Y3），请确认"
    ]
