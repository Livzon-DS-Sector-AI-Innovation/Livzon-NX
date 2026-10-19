"""他汀倒罐复合批产量：单条总量录入的展开、合并与回填。"""

from __future__ import annotations

from datetime import datetime

from app.modules.production import fermentation_board_service as board
from tests.unit.test_fermentation_board_service import _statin_rows


def test_statin_composite_yield_entry_expansion() -> None:
    """倒罐复合批产量：录一条总量（复合批号）→ 统计按子批计数与均摊柱，
    录入下拉合并复合选项，复合批号罐号回填大罐（301A）。"""
    rows = _statin_rows()
    now = datetime(2026, 6, 15, 12, 0)
    actuals = [
        {"batch_no": "MV-26063", "dump_date": "2026-06-03", "yield_kg": 800.0},
        # 倒罐对 26069/070 从 301A 称一次总量，按复合批号录一条
        {"batch_no": "MV-26069/070", "dump_date": "2026-06-12", "yield_kg": 2400.0},
    ]
    payload = board.build_mp_board(rows, [], now, actuals=actuals, product="LV")
    assert payload is not None

    kpis = payload["kpis"]
    # 已放罐 6 批（59/60/63/64/69/70）；复合记录按 2 子批计数：
    # 已录 3（63 + 69/70 两条均摊），待录 3（59/60/64）
    assert kpis["done_with_yield"] == 3
    assert kpis["yield_pending"] == 3
    # 总产量 = 800 + 2400（分摊 1200+1200 严格合计为总量）
    assert kpis["month_done_yield_kg"] == 3200.0

    trend = payload["trend"]
    assert trend["batches"] == ["MV-26063", "MV-26069", "MV-26070"]
    assert trend["outputs"] == [800.0, 1200.0, 1200.0]
    # 复合组：子批柱对的罐号与合计总量（前端托架标注来源）
    assert trend["composite_groups"] == [
        {
            "batch_nos": ["MV-26069", "MV-26070"],
            "tank_no": "301A",
            "total_kg": 2400.0,
        }
    ]

    # 录入下拉：倒罐对合并为一条复合批号选项；直放批保持逐条
    dumped = {e["batch_no"] for e in payload["dumped_batches"]}
    assert "MV-26069/070" in dumped
    assert "MV-26063" in dumped
    assert "MV-26064" in dumped
    assert "MV-26069" not in dumped
    assert "MV-26070" not in dumped

    # 复合批号罐号回填大罐；子批各自也回 301A（倒罐跟随）
    tanks_map = board.collect_dump_tanks(rows, "LV")
    assert tanks_map["MV-26069/070"] == "301A"
    assert tanks_map["MV-26069"] == "301A"
