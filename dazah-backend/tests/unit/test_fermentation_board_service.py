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
    assert kpis["running"] == 1  # FA-M0 已移种在罐（8/30 放罐窗口未结束）
    # 未开始按「本周期计划放罐」口径：FA-M1~M3 无本周期放罐计划（种子批
    # 不计入），计划放罐 FA-PREV(已完成) + FA-M0(运行中) → 未开始 0；
    # 四段之和 = month_planned
    assert kpis["pending"] == 0
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


@pytest.mark.anyio
async def test_build_board_accepts_datetime_dump_date_for_unmapped_batch() -> None:
    payload = board.build_board(
        _mini_rows(),
        [],
        datetime(2026, 8, 28, 12, 0),
        actuals=[
            {
                "batch_no": "FA-DATETIME",
                "dump_date": datetime(2026, 8, 28, 12, 0),
                "yield_kg": 8.5,
                "remark": None,
            }
        ],
    )

    assert payload is not None
    assert payload["trend"] == {
        "batches": ["FA-DATETIME"],
        "outputs": [8.5],
    }


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
            product_code="XX",  # 未接入产品（MC 已接入）
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

# ═══════════════════ DR（102车间）排产解析 ═══════════════════


def _dr_rows() -> list[list]:
    """构造 09 月 DR 块（8.27-9.26 扎帐），行布局与真实表一致。"""
    title = ["102车间2026年09月份多拉计划（09.05）"]
    date_row = ["日期"] + [str(d) for d in range(1, 31)]
    seed = ["菌种"] + [""] * 30
    seed_b = ["种子"] + [""] * 30
    seed_t = [""] * 31
    ferm_b = ["发酵"] + [""] * 30
    ferm_t = [""] * 31
    dump_b = ["放罐"] + [""] * 30
    dump_t = [""] * 31
    cycle = ["周期"] + [""] * 30
    note = ["备注"]

    def set_col(row: list, col: int, value) -> None:
        while len(row) <= col:
            row.append("")
        row[col] = value

    # B402：DR-26035 9/1 进罐 256h，9/20 放罐（运行中）
    set_col(ferm_b, 1, "DR-26035")
    set_col(ferm_t, 1, "B402")
    set_col(cycle, 1, "256h")
    set_col(dump_b, 20, "DR-26035")
    set_col(dump_t, 20, "B402")
    # B305：DR-2619 9/5 进罐 300h，9/18 放罐（运行中）
    set_col(ferm_b, 5, "DR-2619")
    set_col(ferm_t, 5, "B305")
    set_col(cycle, 5, "300h")
    set_col(dump_b, 18, "DR-2619")
    set_col(dump_t, 18, "B305")
    # B401：DR-2617 8月块遗留批次，本块 9/3 放罐（已完成）
    set_col(dump_b, 3, "DR-2617")
    set_col(dump_t, 3, "B401")
    # B304：中试-2622 9/25 进罐（未到，待进罐）
    set_col(ferm_b, 25, "中试-2622")
    set_col(ferm_t, 25, "B304")
    # 9/27 放罐的批次属下个扎帐周期，不计入本周期计划
    set_col(dump_b, 27, "DR-26040")
    set_col(dump_t, 27, "B401")
    # 纯文字说明不应识别为批次
    set_col(ferm_b, 7, "进两个种子")
    set_col(ferm_t, 7, "B301/302")
    # 复合批号：DR-26035/36 进 B401/B402 双罐，自身无放罐记录，
    # 放罐计划拆在 DR-26036（9/24 从 B401 放罐，350h）
    set_col(ferm_b, 9, "DR-26035/36")
    set_col(ferm_t, 9, "B401/2")
    set_col(dump_b, 24, "DR-26036")
    set_col(dump_t, 24, "B401")
    set_col(cycle, 24, "350h")

    block = [
        title, date_row, seed, seed_b, seed_t,
        ferm_b, ferm_t, dump_b, dump_t, cycle, note, [""] * 31,
    ]
    # 8月块：DR-2617 于 8/20 进罐 B401（周期 300h），本块 9/3 放罐 → 遗留批
    aug_title = ["102车间2026年08月份多拉计划（08.20）"]
    aug_date = ["日期"] + [str(d) for d in range(1, 32)]
    aug_ferm_b = ["发酵"] + [""] * 31
    aug_ferm_t = [""] * 32
    aug_cycle = ["周期"] + [""] * 31
    set_col(aug_ferm_b, 20, "DR-2617")
    set_col(aug_ferm_t, 20, "B401")
    set_col(aug_cycle, 20, "300h")
    prev = [aug_title, aug_date, [""] * 32, [""] * 32, [""] * 32,
            aug_ferm_b, aug_ferm_t, [""] * 32, [""] * 32, aug_cycle,
            ["备注"], [""] * 32]
    return prev + block


def test_find_dr_period_block_boundaries() -> None:
    rows = _dr_rows()
    # 9/15 → 9月块（8.27-9.26）
    block = board.find_dr_period_block(rows, datetime(2026, 9, 15, 12, 0))
    assert block is not None
    assert block["start"] == date(2026, 8, 27)
    assert block["end"] == date(2026, 9, 26)
    assert "8月27日" in block["label"]
    # 9/27 起属 10月块（本表没有 → None）
    assert board.find_dr_period_block(rows, datetime(2026, 9, 27, 12, 0)) is None
    # 8/15 属 8月块（fixture 的占位首块即 8 月标题）→ 命中并返回 7.27-8.26 周期
    aug = board.find_dr_period_block(rows, datetime(2026, 8, 15, 12, 0))
    assert aug is not None
    assert aug["start"] == date(2026, 7, 27)
    assert aug["end"] == date(2026, 8, 26)


def test_build_dr_board_tanks_and_kpis() -> None:
    rows = _dr_rows()
    now = datetime(2026, 9, 15, 12, 0)
    payload = board.build_dr_board(rows, [], now)
    assert payload is not None

    tanks = {t["tank_no"]: t for t in payload["tanks"]}
    # 拆分后罐序按当前批移种时间：B305(9/5) → B401(9/9) → B402(9/9) → B304(9/25)
    order = [t["tank_no"] for t in payload["tanks"]]
    assert order == ["B305", "B401", "B402", "B304"]

    # 复合批「DR-26035/36 + B401/2」拆分：DR-26035→B401、DR-26036→B402
    assert tanks["B401"]["batch_no"] == "DR-26035"
    assert tanks["B401"]["status"] == "running"
    assert tanks["B401"]["inoculate_at"] == "2026-09-09"
    # B401 预估放罐 = 该罐 DR-26036 的放罐计划（9/24、350h）
    assert tanks["B401"]["dump_at"] == "2026-09-24"
    assert tanks["B401"]["cycle_hours"] == 350.0
    assert tanks["B402"]["batch_no"] == "DR-26036"
    assert tanks["B402"]["inoculate_at"] == "2026-09-09"
    assert tanks["B402"]["status"] == "running"
    assert tanks["B402"]["status"] == "running"
    assert tanks["B402"]["cultured_hours"] == 6 * 24  # 9/9 移种拆分批 DR-26036
    assert tanks["B305"]["status"] == "running"
    assert tanks["B305"]["batch_no"] == "DR-2619"
    # DR-2617 为遗留已放罐批（进 recent 凑数行）：移种/周期从 8月块回查补齐
    recent_top = payload["recent"][0]
    assert recent_top["batch_no"] == "DR-2617"
    assert recent_top["inoculate_at"] == "2026-08-20"
    assert recent_top["cycle_hours"] == 300.0
    # 9/25 才进罐的 B304 待进罐
    assert tanks["B304"]["status"] == "idle"

    kpis = payload["kpis"]
    # 周期内计划放罐：DR-26035(9/20) DR-2619(9/18) DR-2617(9/3) DR-26036(9/24)，
    # 9/27 的 DR-26040 不计
    assert kpis["month_planned"] == 4
    assert kpis["month_done_planned"] == 1
    # DR-26035(B401) / DR-2619 / DR-26036(B402)，放罐均在周期内
    assert kpis["running"] == 3
    # 中试-2622（9/25 待进罐）无本周期放罐计划 → 不计入未开始；
    # 已完成 1 + 运行中 3 + 未开始 0 = month_planned 4
    assert kpis["pending"] == 0

    recent = payload["recent"]
    assert recent and recent[0]["batch_no"] == "DR-2617"
    assert payload["dumped_batches"] == [
        {"batch_no": "DR-2617", "dump_date": "2026-09-03"}
    ]
    # 播报：B305 罐 DR-2619 9/18 放罐（9/15 时点剩 68h）→ 预放罐提醒；
    # 中试-2622 9/25 待进罐；备注标签'备注'不再作为播报内容
    texts = [a["text"] for a in payload["alerts"]]
    assert any("B305" in t and "距预估放罐剩余" in t for t in texts)
    assert any("待进罐批次 中试-2622" in t and "09-25" in t for t in texts)
    assert all(t != "备注" for t in texts)
    # 周期与标题
    assert payload["period"]["start"] == "2026-08-27"
    assert payload["period"]["end"] == "2026-09-26"


def test_build_dr_board_trend_and_collect_dump_tanks() -> None:
    rows = _dr_rows()
    now = datetime(2026, 9, 25, 12, 0)
    actuals = [
        {"batch_no": "DR-26035", "dump_date": "2026-09-20", "yield_kg": 88.0},
        {"batch_no": "DR-2617", "dump_date": "2026-09-03", "yield_kg": 100.5},
        # 无产量与周期外批次不进趋势
        {"batch_no": "DR-2619", "dump_date": "2026-09-18", "yield_kg": None},
        {"batch_no": "DR-OLD", "dump_date": "2026-07-01", "yield_kg": 66.0},
    ]
    payload = board.build_dr_board(rows, [], now, actuals=actuals)
    assert payload is not None
    # 趋势按放罐日期升序，仅含周期内已放罐且有产量的批次
    assert payload["trend"] == {
        "batches": ["DR-2617", "DR-26035"],
        "outputs": [100.5, 88.0],
    }
    # 无产量录入时趋势为 None（不返回空对象）
    empty = board.build_dr_board(rows, [], now)
    assert empty is not None
    assert empty["trend"] is None
    # 罐号映射按 DR 表布局解析（回填批次产量列表罐号）
    tank_map = board.collect_dump_tanks(rows, "DR")
    assert tank_map["DR-2619"] == "B305"
    assert tank_map["DR-26036"] == "B401"
    # MP 时间线同理回填罐号；趋势同样按周期过滤
    mp_rows = _mp_rows()
    assert board.collect_dump_tanks(mp_rows, "MC")["MC-26245"] == "A307"
    mp_payload = board.build_mp_board(
        mp_rows,
        [],
        now,
        actuals=[
            {"batch_no": "MC-26244", "dump_date": "2026-09-06", "yield_kg": 55.0}
        ],
    )
    assert mp_payload is not None
    assert mp_payload["trend"] == {"batches": ["MC-26244"], "outputs": [55.0]}


def _statin_rows() -> list[list]:
    """构造 103 他汀转产排产（5月美伐块 + 6月洛伐块，自然月块）。

    行布局与真实表一致：标题行 + 日期行（列 d+1 = 第 d 日）+ 标签段行
    （发酵罐/移种/倒罐/放罐，罐号行无标签紧随其后）。6月洛伐块含美伐
    转产批（MV-26063/064 直放、MV-26069/070 倒罐入 301A）与备注文本。
    """
    def block_rows(title: str, days: int, spec: dict) -> list[list]:
        seq = ["", "日期"] + [str(d) for d in range(1, days + 1)]

        def row(label: str, values: dict) -> list:
            r = [label] + [""] * (days + 1)
            for col, v in values.items():
                r[col] = v
            return r

        out = [[title], seq, row("时间", {1: "罐号"})]
        for label in ("种子罐", "接种时间", "接种量"):
            out.append(row(label, spec.get(label, {})))
        out.append(row("发酵罐", spec.get("ferm", {})))
        out.append(row("", spec.get("ferm_tank", {})))
        out.append(row("移种", spec.get("shift", {})))
        out.append(row("倒罐", spec.get("turn", {})))
        out.append(row("倒罐时间", spec.get("turn_tank", {})))
        out.append(row("放罐", spec.get("dump", {})))
        out.append(row("", spec.get("dump_tank", {})))
        out.append(row("放罐时间", spec.get("dump_time", {})))
        out.append(row("备注：", {2: spec.get("note", "")}))
        out.append(["计划制订日期2026.05.12"] + [""] * (days + 1))
        return out

    may = block_rows("2026年5月01日～2026年5月31日103发酵美伐计划", 31, {
        "种子罐": {2: "MV-26063/064"},
        "接种量": {2: 400.0},
        "ferm": {2: "MV-26063/064"},
        "ferm_tank": {2: "304B/306B"},
        "shift": {2: 0.6666666666666666},
        "dump": {31: "MV-26059/060"},
        "dump_tank": {31: "303B/305B"},
        "dump_time": {31: 0.6666666666666666},
    })
    june = block_rows("2026年6月01日～2026年6月30日103发酵洛伐计划", 30, {
        "note": "6月份美伐放罐12批",
        "种子罐": {2: "MV-26069/070", 12: "LV-26016"},
        "接种量": {2: 400.0, 12: 65.0},
        "ferm": {2: "MV-26069/070", 12: "LV-26016"},
        "ferm_tank": {2: "303B/305B", 12: "305B"},
        "shift": {2: 0.6666666666666666, 12: 0.7916666666666666},
        "turn": {7: "MV-26069/070", 14: "LV-26016", 17: "待放302B"},
        "turn_tank": {7: "301A\n303B\n305B", 14: "305B\n301A"},
        "dump": {4: "MV-26063/064", 13: "MV-26069/070", 23: "LV-26016"},
        "dump_tank": {4: "304B/306B", 13: "301A\n303B\n305B", 23: "305B\n301A"},
        "dump_time": {
            4: 0.6666666666666666,
            13: 0.6666666666666666,
            23: 0.7083333333333334,
        },
    })
    return may + june


def test_statin_board_parsing() -> None:
    rows = _statin_rows()
    # 时间线：复合批拆分、位置对应罐号、倒罐批取 301A、备注文本忽略；
    # 全局扫描——美伐块里的发酵记录与洛伐块里的放罐记录同批号可拼上
    timeline = board._statin_batch_timeline(rows)
    assert timeline["MV-26069"]["ferm_tank"] == "303B"
    assert timeline["MV-26070"]["ferm_tank"] == "305B"
    assert timeline["MV-26069"]["inoculate"] == datetime(2026, 6, 1, 16, 0)
    assert timeline["MV-26069"]["dump"] == datetime(2026, 6, 12, 16, 0)
    assert timeline["MV-26069"]["dump_tank"] == "301A"  # 倒罐批跟随 301A
    assert timeline["LV-26016"]["inoculate"] == datetime(2026, 6, 11, 19, 0)
    assert timeline["LV-26016"]["dump_tank"] == "301A"
    # 直放批（未倒罐）：放罐罐格位置对应（第 i 批 ↔ 第 i 罐）
    assert timeline["MV-26063"]["dump"] == datetime(2026, 6, 3, 16, 0)
    assert timeline["MV-26063"]["dump_tank"] == "304B"
    assert timeline["MV-26064"]["dump_tank"] == "306B"
    # 跨产品块拼时间线：发酵在 5月美伐块、放罐在 6月洛伐块
    assert timeline["MV-26063"]["inoculate"] == datetime(2026, 5, 1, 16, 0)
    assert "待放302B" not in timeline
    # 批次折算数：美伐复合批 400/2 子批/基数 200 → 各 1.0；
    # 洛伐接种量 65/基数 100 → 0.65；无种子记录默认整批
    assert timeline["MV-26069"]["units"] == 1.0
    assert timeline["LV-26016"]["units"] == 0.65
    assert timeline["MV-26059"]["units"] == 1.0

    # 块定位：扎帐周期（上月27～本月26）；6月洛伐块 → MV 无覆盖
    blk = board.find_mp_period_block(
        rows, datetime(2026, 6, 15, 12, 0), product="LV"
    )
    assert blk is not None
    assert (blk["start"], blk["end"]) == (date(2026, 5, 27), date(2026, 6, 26))
    assert (
        board.find_mp_period_block(
            rows, datetime(2026, 6, 15, 12, 0), product="MV"
        )
        is None
    )

    # 看板组装（复用 MP 管线）：扎帐窗口内批次按接种量折算小数批——
    # 计划 = 26059(1.0)+26060(1.0)+26063(1.0)+26064(1.0)+26069(1.0)
    # +26070(1.0)+LV-26016(0.65，接种量 65/标准 100) = 6.65；
    # 完成（≤6/20）= 前 6 批 = 6.0；运行 = LV-26016（按批次数计）
    payload = board.build_mp_board(
        rows,
        [],
        datetime(2026, 6, 20, 12, 0),
        actuals=[
            {"batch_no": "MV-26063", "dump_date": "2026-06-03", "yield_kg": 10.0},
            {"batch_no": "MV-26070", "dump_date": "2026-06-12", "yield_kg": 20.0},
        ],
        product="LV",
    )
    assert payload is not None
    kpis = payload["kpis"]
    assert kpis["month_planned"] == pytest.approx(6.65)
    assert kpis["month_done_planned"] == pytest.approx(6.0)
    assert kpis["running"] == 1
    assert kpis["pending"] == 0
    # 趋势按放罐日期升序，仅含已录产量批次
    assert payload["trend"] == {
        "batches": ["MV-26063", "MV-26070"],
        "outputs": [10.0, 20.0],
    }
    # 播报：排产备注取内容格；预放罐提醒（LV-26016 6/22 16:00 放罐，
    # 6/20 12:00 时点剩 52h）；'备注：'标签本身不作为播报内容
    texts = [a["text"] for a in payload["alerts"]]
    assert any("【排产备注】6月份美伐放罐12批" in t for t in texts)
    assert any("距预估放罐剩余" in t and "305B" in t for t in texts)
    assert all(t != "备注：" for t in texts)


def test_statin_products_share_mp_pipeline() -> None:
    """LV 洛伐他汀 / MV 美伐他汀走 103 他汀解析，罐号映射按产品分派。"""
    rows = _statin_rows()
    blk = board.find_mp_period_block(
        rows, datetime(2026, 6, 15, 12, 0), product="LV"
    )
    assert blk is not None
    assert blk["start"] == date(2026, 5, 27)
    assert blk["end"] == date(2026, 6, 26)
    # 6月是洛伐块：MV 无覆盖块（美伐 Tab 提示未覆盖，手动切 5月/10月）
    assert (
        board.find_mp_period_block(
            rows, datetime(2026, 6, 15, 12, 0), product="MV"
        )
        is None
    )
    # collect_dump_tanks 对 LV/MV 走他汀时间线分支（倒罐批取 301A）
    assert board.collect_dump_tanks(rows, "LV")["MV-26069"] == "301A"
    assert board.collect_dump_tanks(rows, "MV")["MV-26063"] == "304B"
    # 扎帐月设置/取档的周期解析同样按产品分派（概览打通的前提）
    assert board.current_period(
        rows, datetime(2026, 6, 15, 12, 0), product_code="LV"
    ) == (date(2026, 5, 27), date(2026, 6, 26))
    assert (
        board.current_period(
            rows, datetime(2026, 6, 15, 12, 0), product_code="MV"
        )
        is None
    )


def test_summary_rate_and_extract_planned_helpers() -> None:
    """生产汇总纯函数：比率计算与提炼计划 KG 行筛选。"""
    from types import SimpleNamespace

    # 比率：正常/封顶无关（原值返回）、分母缺失或非正 → None
    assert board._summary_rate(64.2, 100) == 64.2
    assert board._summary_rate(50, 0) is None
    assert board._summary_rate(50, None) is None

    # 提炼计划：只累计非发酵车间行；发酵行与删除行不计；无行 → None
    plan_rows = [
        SimpleNamespace(
            product_name="洛伐他汀",
            workshop="201-1车间",
            planned_yield=45200,
            is_deleted=False,
        ),
        SimpleNamespace(
            product_name="洛伐他汀",
            workshop="103发酵车间",
            planned_yield=13.5,
            is_deleted=False,
        ),
        SimpleNamespace(
            product_name="洛伐他汀",
            workshop="201-1车间",
            planned_yield=999,
            is_deleted=True,
        ),
        SimpleNamespace(
            product_name="美伐他汀",
            workshop="201-1车间",
            planned_yield=777,
            is_deleted=False,
        ),
    ]
    assert board._extract_planned_yield_kg(plan_rows, "洛伐他汀") == 45200
    assert board._extract_planned_yield_kg(plan_rows, "美伐他汀") == 777
    assert board._extract_planned_yield_kg(plan_rows, "不存在的产品") is None


def test_dr_batch_and_tank_helpers() -> None:
    assert board._dr_is_batch_no("DR-26035")
    assert board._dr_is_batch_no("中试-2620")
    assert board._dr_is_batch_no("ZS-006")
    assert not board._dr_is_batch_no("两个发酵")
    assert not board._dr_is_batch_no("进两个种子")
    assert board._dr_norm_tank("B401/2") == "B401"
    assert board._dr_norm_tank("B301/302") == "B301"
    assert board._dr_norm_tank("两个发酵") is None

# ═══════════════════ MP（101车间）排产解析 ═══════════════════


def _mp_rows() -> list[list]:
    """构造 09 月 MC 放罐计划块（8.27-9.26 扎帐），批号四级流转。

    流转节奏：一级种子16:00 → 2天后二级种子15:00 → 次日发酵14:00 →
    7天后放罐08:00（发酵→放罐 186h）。构造跨块的 MC-26244：
    8月块 8/30 发酵（14:00），09月块 9/6 放罐（08:00）。
    """
    def block_rows(title: str, days: int, batches: dict) -> list[list]:
        seq = ["序号"] + [str(d) for d in range(1, days + 1)]
        blank = [""] * (days + 1)

        def row(label: str, values: dict) -> list:
            r = [label] + [""] * days
            for col, v in values.items():
                r[col] = v
            return r

        s1 = batches.get("seed1", {})
        s1_t = batches.get("seed1_tank", {})
        s2 = batches.get("seed2", {})
        s2_t = batches.get("seed2_tank", {})
        ferm = batches.get("ferm", {})
        ferm_t = batches.get("ferm_tank", {})
        dump = batches.get("dump", {})
        dump_t = batches.get("dump_tank", {})
        return [
            [title],
            seq,
            row("一级种子罐", s1),
            row("", s1_t),
            row("", {c: "16:00:00" for c in s1}),
            row("二级种子罐", s2),
            row("", s2_t),
            row("", {c: "15:00:00" for c in s2}),
            row("发酵罐", ferm),
            row("", ferm_t),
            row("", {c: "14:00:00" for c in ferm}),
            row("放罐", dump),
            row("", dump_t),
            row("", {c: "08:00:00" for c in dump}),
            blank,
            blank,
            blank,
            blank,
            ["备注", "黄色正常罐批。"],
            blank,
        ]

    aug = block_rows("2026年08月MC放罐计划", 31, {
        "ferm": {30: "MC-26244"}, "ferm_tank": {30: "A302"},
    })
    sep_ferm = {c: f"MC-2624{n}" for n, c in enumerate(range(8, 13), start=5)}
    sep_ferm_t = {8: "A307", 9: "A306", 10: "A310", 11: "A303", 12: "A305"}
    sep_dump = {2: "MC-26238", 6: "MC-26244", 16: "MC-26245"}
    sep_dump_t = {2: "A304", 6: "A302", 16: "A307"}
    sep = block_rows("2026年09月MC放罐计划", 30, {
        "ferm": sep_ferm, "ferm_tank": sep_ferm_t,
        "dump": sep_dump, "dump_tank": sep_dump_t,
    })
    return aug + sep


def test_find_mp_period_block_boundaries() -> None:
    rows = _mp_rows()
    block = board.find_mp_period_block(rows, datetime(2026, 9, 15, 12, 0))
    assert block is not None
    assert block["start"] == date(2026, 8, 27)
    assert block["end"] == date(2026, 9, 26)
    # 9/27 起属 10月块（无 → None）
    assert board.find_mp_period_block(rows, datetime(2026, 9, 27, 12, 0)) is None
    # 8/15 属 8月块（有，8.27-9.26 的前一个月周期 7.27-8.26）
    aug = board.find_mp_period_block(rows, datetime(2026, 8, 15, 12, 0))
    assert aug is not None
    assert aug["start"] == date(2026, 7, 27)
    assert aug["end"] == date(2026, 8, 26)


def test_build_mp_board_tank_states_and_kpis() -> None:
    rows = _mp_rows()
    now = datetime(2026, 9, 15, 12, 0)
    payload = board.build_mp_board(rows, [], now)
    assert payload is not None

    tanks = {t["tank_no"]: t for t in payload["tanks"]}
    # 跨块批 MC-26244：8/30 14:00 发酵（A302）、9/6 08:00 放罐 → 已放罐
    assert tanks["A302"]["batch_no"] == "MC-26244"
    assert tanks["A302"]["status"] == "dumped"
    assert tanks["A302"]["inoculate_at"] == "2026-08-30T14:00:00"
    assert tanks["A302"]["dump_at"] == "2026-09-06T08:00:00"
    assert tanks["A302"]["cycle_hours"] == 162.0  # 8/30 14:00 → 9/6 08:00
    # 运行中：A307 MC-26245 9/8 14:00 进罐、9/16 08:00 计划放罐 → 运行中
    assert tanks["A307"]["batch_no"] == "MC-26245"
    assert tanks["A307"]["status"] == "running"
    assert tanks["A307"]["dump_at"] == "2026-09-16T08:00:00"
    # 罐序按移种时间：A302(8/30) → A307(9/8) → A306(9/9) → A310(9/10)
    # → A303(9/11) → A305(9/12)；A304 仅有放罐记录（无移种时间）置末
    order = [t["tank_no"] for t in payload["tanks"]]
    assert order == ["A302", "A307", "A306", "A310", "A303", "A305", "A304"]

    kpis = payload["kpis"]
    # 周期内放罐：MC-26238(9/2) MC-26244(9/6) MC-26245(9/16)
    assert kpis["month_planned"] == 3
    assert kpis["month_done_planned"] == 2
    assert kpis["running"] == 1  # MC-26245（9/16 放罐）；
    # MC-26246..49 虽在罐但无本周期放罐计划，不计入 KPI；
    # 已完成 2 + 运行中 1 = month_planned 3
    # 播报：A307 预放罐提醒（9/16 08:00 放罐，9/15 12:00 剩 20h）+
    # 排产备注内容格（'黄色正常罐批。'在'备注'标签后一格）
    texts = [a["text"] for a in payload["alerts"]]
    assert any("A307" in t and "距预估放罐剩余" in t for t in texts)
    assert any("【排产备注】黄色正常罐批。" in t for t in texts)
    # recent 取最近已放罐（9/6 的跨块批）
    assert payload["recent"][0]["batch_no"] == "MC-26244"


# ═══════════════════ 漏录/进度/排产告警 ═══════════════════


def _alert(payload: dict, prefix: str) -> list[dict]:
    return [a for a in payload["alerts"] if a["text"].startswith(prefix)]


def test_fmt_batches() -> None:
    """批次数文案：整数批不带小数；他汀折算小数批保留有效小数。"""
    assert board._fmt_batches(7) == "7"
    assert board._fmt_batches(9) == "9"
    assert board._fmt_batches(9.65) == "9.65"
    assert board._fmt_batches(9.0) == "9"
    assert board._fmt_batches(0.65) == "0.65"


@pytest.mark.anyio
async def test_kpi_alert_yield_entry_tiers_fa() -> None:
    """FA 漏录提醒三档：窗口后 24h 内不播；24~72h info；超 72h 升级 warn。"""
    rows = _mini_rows()
    # FA-PREV 8/27 10:00 放罐（窗口 12:00 结束）：8/28 11:00 = 23h，宽限期内
    payload = board.build_board(rows, [], datetime(2026, 8, 28, 11, 0))
    assert payload is not None
    assert _alert(payload, "【待录】") == []

    # 8/28 13:00 = 25h → info 单条
    payload = board.build_board(rows, [], datetime(2026, 8, 28, 13, 0))
    assert payload is not None
    assert _alert(payload, "【待录】") == [
        {
            "level": "info",
            "text": "【待录】1 批已放罐超 1 天未录产量（FA-PREV），请录入",
        }
    ]

    # 8/30 13:00 = 73h → warn；FA-M0 窗口 8/30 12:00 刚结束（1h）不计入
    payload = board.build_board(rows, [], datetime(2026, 8, 30, 13, 0))
    assert payload is not None
    pending = _alert(payload, "【待录】")
    assert len(pending) == 1
    assert pending[0]["level"] == "warn"
    assert "FA-PREV" in pending[0]["text"]
    assert "超 3 天" in pending[0]["text"]


@pytest.mark.anyio
async def test_kpi_alert_yield_entry_dr() -> None:
    """DR 漏录提醒：排产无放罐时刻，宽限按放罐日零点折算。"""
    rows = _dr_rows()
    # DR-2617 9/3 放罐：9/4 00:01 起 24h 宽限过 → info
    payload = board.build_dr_board(rows, [], datetime(2026, 9, 4, 0, 1))
    assert payload is not None
    pending = _alert(payload, "【待录】")
    assert len(pending) == 1
    assert pending[0]["level"] == "info"
    assert "DR-2617" in pending[0]["text"]


@pytest.mark.anyio
async def test_kpi_alert_yield_entry_mp_warn_takes_precedence() -> None:
    """MP：warn 档存在时不重复播 info 档（录入抽屉已列全部未录批次）。"""
    rows = _mp_rows()
    # 9/7 11:00：MC-26238（9/2 放罐，超 72h）→ warn；
    # MC-26244（9/6 放罐，25h）落在 info 档但被 warn 抑制
    payload = board.build_mp_board(rows, [], datetime(2026, 9, 7, 11, 0))
    assert payload is not None
    pending = _alert(payload, "【待录】")
    assert len(pending) == 1
    assert pending[0]["level"] == "warn"
    assert "MC-26238" in pending[0]["text"]


@pytest.mark.anyio
async def test_kpi_alert_progress_lag_fa() -> None:
    """周期末进度预警：剩余 ≤7 天且录产量进度落后时间进度 ≥10 个百分点。"""
    rows = _mini_rows()
    # 9/26 为周期最后一天：2 计划批均未录产量 → 落后 100 个百分点
    payload = board.build_board(rows, [], datetime(2026, 9, 26, 12, 0))
    assert payload is not None
    progress = _alert(payload, "【进度】")
    assert len(progress) == 1
    assert progress[0]["level"] == "warn"
    assert "剩 0 天" in progress[0]["text"]
    assert "0/2 批（0%）" in progress[0]["text"]

    # 录满产量 → 进度跟上不再播；【待录】同时消失
    actuals = [
        {"batch_no": "FA-PREV", "dump_date": "2026-08-27", "yield_kg": 100.0},
        {"batch_no": "FA-M0", "dump_date": "2026-08-30", "yield_kg": 120.0},
    ]
    payload = board.build_board(
        rows, [], datetime(2026, 9, 26, 12, 0), actuals=actuals
    )
    assert payload is not None
    assert _alert(payload, "【进度】") == []
    assert _alert(payload, "【待录】") == []


@pytest.mark.anyio
async def test_kpi_alert_progress_statin_decimal_batches() -> None:
    """他汀小数批文案：9.65 批保留两位小数展示。"""
    alerts: list[dict] = []
    board._append_kpi_alerts(
        alerts,
        block={"start": date(2026, 9, 20), "end": date(2026, 10, 26)},
        now=datetime(2026, 10, 24, 12, 0),
        kpis={"month_planned": 9.65, "done_with_yield": 3},
        missing_dumps=[],
        today=date(2026, 10, 24),
    )
    progress = [a for a in alerts if a["text"].startswith("【进度】")]
    assert len(progress) == 1
    assert "3/9.65 批" in progress[0]["text"]


@pytest.mark.anyio
async def test_kpi_alerts_muted_outside_current_period() -> None:
    """真实今天不在块内（历史回看/未来周期）→ 漏录与进度告警静音。"""
    rows = _mini_rows()
    hist_block = {
        "start": date(2026, 8, 27),
        "end": date(2026, 9, 26),
        "label": "8月27日～9月26日",
        "start_row": 0,
    }
    # now 已到 10 月：真实今天在块后 → 历史回看不播旧账
    payload = board.build_board(
        rows, [], datetime(2026, 10, 20, 12, 0), block=hist_block
    )
    assert payload is not None
    assert _alert(payload, "【待录】") == []
    assert _alert(payload, "【进度】") == []

    # 未来周期（真实今天早于块首）→ 静音
    alerts: list[dict] = []
    board._append_kpi_alerts(
        alerts,
        block={"start": date(2026, 10, 27), "end": date(2026, 11, 26)},
        now=datetime(2026, 11, 20, 12, 0),
        kpis={"month_planned": 2, "done_with_yield": 0},
        missing_dumps=[("FA-X", datetime(2026, 11, 1, 12, 0))],
        today=date(2026, 10, 20),
    )
    assert alerts == []


@pytest.mark.anyio
async def test_next_period_coverage_alert_windows(monkeypatch) -> None:
    """排产上传提醒：剩 ≤3 天才查存档；无覆盖播 warn；有覆盖/历史/远期不播。"""
    block = {"start": date(2026, 9, 27), "end": date(2026, 10, 26)}
    calls: list[tuple[date, str]] = []

    async def fake_load(session, ref_date, product_code="FA"):
        calls.append((ref_date, product_code))
        return None

    monkeypatch.setattr(board, "load_archive_covering", fake_load)

    # 剩余 9 天：未到临期窗口，不查存档
    assert (
        await board.next_period_coverage_alert(
            None, product_code="FA", block=block, today=date(2026, 10, 17)
        )
        is None
    )
    assert calls == []

    # 剩余 3 天且无覆盖存档 → warn；查询按「周期结束次日」定位
    alert = await board.next_period_coverage_alert(
        None, product_code="FA", block=block, today=date(2026, 10, 23)
    )
    assert alert is not None
    assert alert["level"] == "warn"
    assert "【排产】" in alert["text"]
    assert "2026-09-27～2026-10-26" in alert["text"]
    assert calls == [(date(2026, 10, 27), "FA")]

    # 剩余 4 天（窗口外）→ 不播
    assert (
        await board.next_period_coverage_alert(
            None, product_code="FA", block=block, today=date(2026, 10, 22)
        )
        is None
    )

    # 已有存档覆盖下一周期 → 不播
    async def fake_hit(session, ref_date, product_code="FA"):
        return object()

    monkeypatch.setattr(board, "load_archive_covering", fake_hit)
    assert (
        await board.next_period_coverage_alert(
            None, product_code="FA", block=block, today=date(2026, 10, 23)
        )
        is None
    )

    # 历史周期（块已结束）→ 不播，且不再触发查询
    monkeypatch.setattr(board, "load_archive_covering", fake_load)
    assert (
        await board.next_period_coverage_alert(
            None, product_code="FA", block=block, today=date(2026, 11, 1)
        )
        is None
    )
    assert calls == [(date(2026, 10, 27), "FA")]
