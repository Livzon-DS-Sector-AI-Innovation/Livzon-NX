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
        ["备注", "本周期共放罐2批", "旧备注不播", "FA26236 菌种复检", "", ""],
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
    # 排产备注：周期级汇总（备注行第 2 格）整月播报；
    # 按日期备注今天(8/28)的进跑马灯，过去(8/27)的不播
    note_alerts = [
        a["text"] for a in payload["alerts"] if a["text"].startswith("【排产备注】")
    ]
    assert note_alerts == [
        "【排产备注】本周期共放罐2批",
        "【排产备注】08-28：FA26236 菌种复检",
    ]


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
async def test_running_note_counts_down_to_dump() -> None:
    """运行中备注分级：≥1h 按小时取整；30min~1h「不足 1h」；≤30min「即将放罐」"""
    rows = _mini_rows()
    # FA-M0 计划 8/30 10:00 放罐
    cases = [
        (datetime(2026, 8, 30, 9, 0), "距放罐约 1h"),
        (datetime(2026, 8, 30, 9, 20), "不足 1h"),
        (datetime(2026, 8, 30, 9, 30), "即将放罐"),
        (datetime(2026, 8, 30, 9, 40), "即将放罐"),
    ]
    for now, expected in cases:
        payload = board.build_board(rows, [], now)
        assert payload is not None
        tanks = {t["tank_no"]: t for t in payload["tanks"]}
        assert tanks["302A"]["status"] == "running"
        assert tanks["302A"]["note"] == expected


@pytest.mark.anyio
async def test_tank_dumped_when_last_batch_window_passed() -> None:
    """罐的最后批次放罐窗口已结束且无后续移种 → 已放罐（历史回看语义）。"""
    rows = _mini_rows()
    # 8/31：FA-M0（302A）8/30 10:00 放罐、窗口 12:00 已过；
    # FA-M3（302A）8/30 21:00 移种但排产无其放罐日期，不参与状态判定
    payload = board.build_board(rows, [], datetime(2026, 8, 31, 12, 0))
    assert payload is not None
    tank = next(t for t in payload["tanks"] if t["tank_no"] == "302A")
    assert tank["status"] == "dumped"
    assert tank["batch_no"] == "FA-M0"
    assert tank["note"] == "该罐本批次放罐作业完成"
    # 有后续移种时仍显示空闲+预计移种
    payload = board.build_board(rows, [], datetime(2026, 8, 30, 13, 0))
    assert payload is not None
    tank = next(t for t in payload["tanks"] if t["tank_no"] == "302A")
    assert tank["status"] == "idle"
    assert "移种FA-M3" in tank["note"]


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
        # 其他周期的批次：不在本周期放罐清单内，图表不统计
        {
            "id": "4",
            "batch_no": "FA99999",
            "dump_date": "2026-10-01",
            "yield_kg": 999.0,
        },
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
        {
            "id": str(i),
            "batch_no": f"FA26{i:03d}",
            "dump_date": "2026-09-01",
            "yield_kg": 100.0,
        }
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


def test_collect_dump_tanks_maps_batches_across_rows() -> None:
    rows = _mini_rows()
    mapping = board.collect_dump_tanks(rows)
    # 放罐行批号 → 对应罐号行的罐号
    assert mapping["FA-PREV"] == "302A"
    assert mapping["FA-M0"] == "302A"
    # 无周期块或空行时返回空映射
    assert board.collect_dump_tanks([[], ["占位"]]) == {}
    assert board.collect_dump_tanks([]) == {}


@pytest.mark.anyio
async def test_load_archive_covering_selects_first_covering_archive() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    covering = SimpleNamespace(rows=_mini_rows(), product_code="FA")
    other = SimpleNamespace(rows=[["无关内容"]], product_code="FA")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [other, covering]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    got = await board.load_archive_covering(session, date(2026, 8, 28), "FA")
    assert got is covering

    result.scalars.return_value.all.return_value = [other]
    assert await board.load_archive_covering(session, date(2026, 8, 28), "FA") is None


@pytest.mark.anyio
async def test_build_board_excludes_actuals_with_unparseable_dump_date() -> None:
    rows = _mini_rows()
    now = datetime(2026, 8, 28, 12, 0)
    payload = board.build_board(
        rows,
        [],
        now,
        actuals=[
            {
                "id": "a-1",
                "batch_no": "FA-ZZZ",  # 不在排产 dump_map 中 → 回退 dump_date
                "dump_date": "昨天",  # 非 ISO 日期 → 解析失败分支
                "yield_kg": 5.0,
                "remark": None,
            },
            {
                "id": "a-2",
                "batch_no": "FA-M1",
                "dump_date": "2026-08-29",
                "yield_kg": 100.0,
                "remark": None,
            },
        ],
    )
    assert payload is not None
    # 解析失败的批次不计入趋势，有效批次正常计入
    assert payload["trend"] is not None
    assert "FA-ZZZ" not in payload["trend"]["batches"]
    assert "FA-M1" in payload["trend"]["batches"]


# ═══════════════════ 提炼工段汇总（收率两口径） ═══════════════════


def test_summarize_extraction_rates_and_counts() -> None:
    """Σ放罐、Σ成品、实时/配对收率与批数统计。"""
    actuals = [
        {"batch_no": "FA26231", "yield_kg": 100.0, "extract_kg": 90.0},
        {"batch_no": "FA26232", "yield_kg": 200.0, "extract_kg": 170.0},
        {"batch_no": "FA26233", "yield_kg": 300.0, "extract_kg": None},
        {"batch_no": "FA26234", "yield_kg": None, "extract_kg": 50.0},
    ]
    summary = board.summarize_extraction(actuals)
    assert summary["ferment_total_kg"] == 600.0
    assert summary["extract_total_kg"] == 310.0
    assert summary["ferment_batches"] == 3
    assert summary["extract_batches"] == 3
    # 实时口径：Σ成品 ÷ Σ放罐（含未提炼批次）
    assert summary["rate_realtime"] == pytest.approx(310 / 600 * 100, abs=0.1)
    # 配对口径：仅已出成品批次 90+170 ÷ 100+200
    assert summary["rate_paired"] == pytest.approx(260 / 300 * 100, abs=0.1)


def test_summarize_extraction_empty_and_partial() -> None:
    """无数据/仅单边数据时 totals 为 None、收率为 None。"""
    assert board.summarize_extraction([])["ferment_total_kg"] is None
    assert board.summarize_extraction([])["rate_paired"] is None

    only_ferment = board.summarize_extraction(
        [{"batch_no": "FA1", "yield_kg": 100.0, "extract_kg": None}]
    )
    assert only_ferment["ferment_total_kg"] == 100.0
    assert only_ferment["extract_total_kg"] is None
    assert only_ferment["rate_realtime"] is None


def test_build_board_recent_carries_extract_fields() -> None:
    """最近完成批次带提炼成品与单批收率（最近完成表新增列的数据源）。"""
    rows = _mini_rows()
    # FA-PREV 已于 8/27 10:00 放罐（窗口外）→ 进入 recent
    now = datetime(2026, 8, 28, 12, 0)
    payload = board.build_board(
        rows,
        [],
        now,
        actuals=[
            {
                "batch_no": "FA-PREV",
                "yield_kg": 100.0,
                "extract_kg": 88.0,
                "remark": None,
            }
        ],
    )
    assert payload is not None
    recent = {item["batch_no"]: item for item in payload["recent"]}
    assert recent["FA-PREV"]["extract_kg"] == 88.0
    assert recent["FA-PREV"]["batch_yield_rate"] == 88.0
    # 提炼汇总块随看板返回
    assert payload["extraction"]["ferment_total_kg"] == 100.0
    assert payload["extraction"]["extract_total_kg"] == 88.0
    # 提炼批次台账：已放罐批次逐批带放罐产量与成品量（FA-EX 格式转换在前端展示层做）
    ledger = {row["batch_no"]: row for row in payload["extraction_ledger"]}
    assert ledger["FA-PREV"]["yield_kg"] == 100.0
    assert ledger["FA-PREV"]["extract_kg"] == 88.0
    assert ledger["FA-PREV"]["dump_date"] == "2026-08-27"


# ═══════════════════ 成品日报作为「提炼已出成品」权威数据源 ═══════════════════


def test_apply_daily_extract_source_overrides_totals() -> None:
    """有日报记录时：成品合计/天数/实时收率按日报口径覆盖，配对口径保留台账值。"""
    summary = board.summarize_extraction(
        [{"batch_no": "FA1", "yield_kg": 600.0, "extract_kg": 500.0}]
    )
    updated = board.apply_daily_extract_source(summary, [300.0, 250.0])
    assert updated["extract_total_kg"] == 550.0
    assert updated["extract_batches"] == 2  # 两天，而非批次
    assert updated["rate_realtime"] == pytest.approx(550 / 600 * 100, abs=0.1)
    # 配对口径仍来自批次台账
    assert updated["rate_paired"] == pytest.approx(500 / 600 * 100, abs=0.1)
    assert updated["ferment_total_kg"] == 600.0


def test_apply_daily_extract_source_empty_and_none() -> None:
    """无日报记录时成品合计记空；汇总块缺失时原样返回 None。"""
    summary = board.summarize_extraction(
        [{"batch_no": "FA1", "yield_kg": 600.0, "extract_kg": 500.0}]
    )
    emptied = board.apply_daily_extract_source(summary, [])
    assert emptied["extract_total_kg"] is None
    assert emptied["extract_batches"] == 0
    assert emptied["rate_realtime"] is None

    assert board.apply_daily_extract_source(None, [100.0]) is None


@pytest.mark.anyio
async def test_warehouse_inbound_skips_unwired_product() -> None:
    """未接入产品：不触碰仓储模块，直接返回 None。"""
    from unittest.mock import AsyncMock, MagicMock

    import app.modules.warehouse.public_api as warehouse_public

    original = warehouse_public.get_finished_inbound_kg_total
    inbound_mock = AsyncMock(
        side_effect=AssertionError("未接入产品不应调用仓储公开接口")
    )
    warehouse_public.get_finished_inbound_kg_total = inbound_mock
    try:
        result = await board.get_warehouse_finished_inbound_kg(
            MagicMock(),
            product_code="MC",
            period_start=date(2026, 8, 27),
            period_end=date(2026, 9, 26),
        )
    finally:
        warehouse_public.get_finished_inbound_kg_total = original
    assert result is None
    inbound_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_warehouse_inbound_passes_period_and_product() -> None:
    """已接入产品：透传产品名与周期边界，返回仓储合计。"""
    from unittest.mock import AsyncMock, MagicMock

    import app.modules.warehouse.public_api as warehouse_public

    session = MagicMock()
    original = warehouse_public.get_finished_inbound_kg_total
    inbound_mock = AsyncMock(return_value=410490.0)
    warehouse_public.get_finished_inbound_kg_total = inbound_mock
    try:
        result = await board.get_warehouse_finished_inbound_kg(
            session,
            product_code="FA",
            period_start=date(2026, 8, 27),
            period_end=date(2026, 9, 26),
        )
    finally:
        warehouse_public.get_finished_inbound_kg_total = original
    assert result == 410490.0
    inbound_mock.assert_awaited_once_with(
        session,
        product_name="L-苯丙氨酸",
        start_date=date(2026, 8, 27),
        end_date=date(2026, 9, 26),
    )


@pytest.mark.anyio
async def test_warehouse_inbound_degrades_on_warehouse_failure() -> None:
    """仓储侧异常：降级为 None，不向看板传播故障。"""
    from unittest.mock import AsyncMock, MagicMock

    import app.modules.warehouse.public_api as warehouse_public

    original = warehouse_public.get_finished_inbound_kg_total
    warehouse_public.get_finished_inbound_kg_total = AsyncMock(
        side_effect=RuntimeError("warehouse down")
    )
    try:
        result = await board.get_warehouse_finished_inbound_kg(
            MagicMock(),
            product_code="FA",
            period_start=date(2026, 8, 27),
            period_end=date(2026, 9, 26),
        )
    finally:
        warehouse_public.get_finished_inbound_kg_total = original
    assert result is None
