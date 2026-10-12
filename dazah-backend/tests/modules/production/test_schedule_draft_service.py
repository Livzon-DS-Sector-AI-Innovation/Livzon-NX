"""FA 排产草稿生成器测试：接续/跳过/占用 + 黄金断言 + round-trip。

上一期排产表构造沿用 FA 块格式（与 test_schedule_validation_service
同模式）：稳态每日一放一移，期末在制批次与「备好待进罐」的种子构成
草稿期初状态；黄金断言要求各场景草稿过一期校验器零 warn。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from app.modules.production import fermentation_board_service as board
from app.modules.production import schedule_draft_service as draft
from app.modules.production import schedule_excel_service
from app.modules.production import schedule_validation_service as validation
from tests.modules.production.test_schedule_validation_service import (
    _fa_block_rows,
)

NOW = datetime(2026, 11, 20, 12, 0)
PREV_TITLE = "2026年10月27日～2026年11月26日103车间FA450T罐排产"
DRAFT_START = date(2026, 11, 27)
DRAFT_END = date(2026, 12, 26)
TANKS = ["302A", "303A", "304A"]
CONSTRAINTS = {
    "standard_cycle_hours": 61.0,
    "cycle_tolerance_hours": 4.0,
    "max_cycle_hours": 72.0,
    "turnaround_hours": 8.0,
    "monthly_dump_target": None,
}


def _prev_days() -> dict[date, dict[str, Any]]:
    """上一期稳态排产：10-28 起每日移种（302A→303A→304A 轮转）。

    种子在前一日；放罐在移种后第 3 天（≤11-26 才有行）；
    11-26 晚备一粒种子（FA26431，等草稿首日 11-27 进罐）。
    期末在制：FA26428/29/30（11-24/25/26 移种，放罐落 11-27/28/29）。
    """
    days: dict[date, dict[str, Any]] = {}

    def ensure(day: date) -> dict[str, Any]:
        return days.setdefault(
            day, {"seed": None, "ferm": None, "dump": None, "note": ""}
        )

    for idx in range(30):  # 10-28 .. 11-26
        ferm_day = date(2026, 10, 28) + timedelta(days=idx)
        batch = f"FA{26401 + idx}"
        tank = TANKS[idx % 3]
        ensure(ferm_day - timedelta(days=1))["seed"] = batch
        ensure(ferm_day)["ferm"] = (batch, tank)
        dump_day = ferm_day + timedelta(days=3)
        if dump_day <= date(2026, 11, 26):
            ensure(dump_day)["dump"] = (batch, tank)
    # 上期末备好的草稿首批种子（11-26 接种、11-27 进罐）
    ensure(date(2026, 11, 26))["seed"] = "FA26431"
    # 种子罐 201A/202A 逐日交替（与现行 FA 表惯例一致），最后一粒落在 202A
    seed_days = sorted(d for d, e in days.items() if e["seed"])
    for index, seed_day in enumerate(seed_days):
        days[seed_day]["seed_tank"] = ["201A", "202A"][index % 2]
    return days


PREV_ROWS = _fa_block_rows(PREV_TITLE, _prev_days())


def _generate(
    *,
    skip_dates: set[date] | None = None,
    tank_blocks: list[draft.TankBlock] | None = None,
    batch_start_no: int | None = None,
    constraints: dict[str, Any] | None = CONSTRAINTS,
    prev_rows: list[list[Any]] | None = PREV_ROWS,
) -> tuple[draft.DraftResult, dict[str, Any]]:
    params = draft.DraftParams(
        period_start=DRAFT_START,
        period_end=DRAFT_END,
        batch_start_no=batch_start_no,
        skip_dates=skip_dates or set(),
        tank_blocks=tank_blocks or [],
    )
    result = draft.generate_draft(
        prev_rows or [], params, constraints=constraints
    )
    report = draft.validate_draft(
        result, prev_rows or [], constraints=constraints, now=NOW
    )
    return result, report


def _warns(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for i in report["issues"] if i["level"] == "warn"]


def _transfer_days(result: draft.DraftResult) -> dict[date, tuple[str, str]]:
    return {
        d.date: d.transfer for d in result.days if d.transfer
    }


def _dump_days(result: draft.DraftResult) -> dict[date, list[tuple[str, str]]]:
    return {d.date: d.dumps for d in result.days if d.dumps}


# ═══════════════════ 与上月接续 ═══════════════════


def test_next_accounting_period() -> None:
    assert draft.next_accounting_period(date(2026, 11, 20)) == (
        date(2026, 11, 27),
        date(2026, 12, 26),
    )
    assert draft.next_accounting_period(date(2026, 12, 10)) == (
        date(2026, 12, 27),
        date(2027, 1, 26),
    )


def test_continuity_from_previous_period() -> None:
    result, report = _generate()
    transfers = _transfer_days(result)
    dumps = _dump_days(result)
    # 上期末在制批次的放罐落进草稿（11-27/28/29，同罐）
    assert dumps[date(2026, 11, 27)] == [("FA26428", "302A")]
    assert dumps[date(2026, 11, 28)] == [("FA26429", "303A")]
    assert dumps[date(2026, 11, 29)] == [("FA26430", "304A")]
    # 上期末备好的种子 11-27 进 302A（当日唯一空闲：在制放罐 + 周转后）
    assert transfers[date(2026, 11, 27)] == ("FA26431", "302A")
    assert transfers[date(2026, 11, 28)] == ("FA26432", "303A")
    assert transfers[date(2026, 11, 29)] == ("FA26433", "304A")
    # 轮转无缝：首月每日一移种，批号自动续号（水位 26431）
    assert result.summary["transfer_count"] == 30
    assert result.summary["dump_count"] == 30
    assert result.summary["idle_tank_days"] == 0
    assert transfers[date(2026, 12, 1)][0] == "FA26435"
    # 周期末（12-26）照常接种：该粒种子服务于下一周期首日（12-27）
    last_day = by_day_last(result)
    assert last_day.seed_batch is not None
    assert _warns(report) == []


def by_day_last(result: draft.DraftResult) -> draft.DraftDay:
    return result.days[-1]


def test_seed_tank_rotation_continues_from_archive() -> None:
    """种子罐 201A/202A 接着上期最后一粒续排交替。

    夹具共 31 粒种子（10-27~11-26），从 201A 起逐日交替，最后一粒
    （11-26、FA26431）落在 201A → 草稿首粒（11-27）接 202A。
    """
    result, _ = _generate()
    seeded = [(d.date, d.seed_tank) for d in result.days if d.seed_batch]
    assert seeded[0] == (date(2026, 11, 27), "202A")
    assert seeded[1] == (date(2026, 11, 28), "201A")
    tanks = [t for _d, t in seeded]
    assert all(
        tanks[i] != tanks[i + 1] for i in range(len(tanks) - 1)
    ), "种子罐应逐日交替"
    # 排产表行：种子罐号行与预览一致
    parsed = board.parse_block(
        result.rows,
        {"start_row": 0, "start": DRAFT_START, "end": DRAFT_END, "label": ""},
    )
    cell_tanks = {
        d["date"]: d["seed_tank"] for d in parsed["days"] if d["seed_tank"]
    }
    assert cell_tanks[date(2026, 11, 27)] == "202A"
    assert cell_tanks[date(2026, 11, 28)] == "201A"


def test_batch_numbering_default_and_override() -> None:
    result, _ = _generate()
    transfers = _transfer_days(result)
    assert transfers[date(2026, 11, 27)][0] == "FA26431"  # 备好的种子
    assert transfers[date(2026, 11, 28)][0] == "FA26432"  # 水位 26431+1
    result2, _ = _generate(batch_start_no=26500)
    transfers2 = _transfer_days(result2)
    assert transfers2[date(2026, 11, 27)][0] == "FA26431"  # 备好种子优先
    assert transfers2[date(2026, 11, 28)][0] == "FA26500"


# ═══════════════════ 按天跳过 ═══════════════════


def test_skip_day_propagates_hole() -> None:
    result, report = _generate(skip_dates={date(2026, 12, 5)})
    transfers = _transfer_days(result)
    dumps = _dump_days(result)
    by_day = {d.date: d for d in result.days}
    # 跳过日不移种、前一日不接种（无废种留痕）
    assert date(2026, 12, 5) not in transfers
    assert by_day[date(2026, 12, 4)].seed_batch is None
    assert "次日跳过" in by_day[date(2026, 12, 4)].seed_note
    # 洞后置 3 天显形：12-08 无放罐；12-06 起节奏恢复
    assert date(2026, 12, 8) not in dumps
    assert transfers[date(2026, 12, 6)] is not None
    # 摘要：少一批、出现空拍；校验零 warn（备注标注跳过成因）
    assert result.summary["transfer_count"] == 29
    assert result.summary["dump_count"] == 29
    assert result.summary["idle_tank_days"] >= 1
    assert _warns(report) == []


def test_skip_day_note_written_to_rows() -> None:
    """跳过成因写进备注行，一期校验器据此不把空档当漏排提示。"""
    result, _ = _generate(skip_dates={date(2026, 12, 5)})
    parsed = board.parse_block(
        result.rows,
        {
            "start_row": 0,
            "start": DRAFT_START,
            "end": DRAFT_END,
            "label": "",
        },
    )
    notes = {d["date"]: d["note"] for d in parsed["days"]}
    assert "跳过" in notes[date(2026, 12, 5)]
    assert "不接种" in notes[date(2026, 12, 4)]


# ═══════════════════ 罐占用窗口 ═══════════════════


def test_tank_block_window_avoided() -> None:
    block = draft.TankBlock(
        tank_no="302A", from_date=date(2026, 12, 1), to_date=date(2026, 12, 5)
    )
    result, report = _generate(tank_blocks=[block])
    transfers = _transfer_days(result)
    dumps = _dump_days(result)
    # 窗口内 302A 不接活，窗口后恢复
    in_window = {
        d: t
        for d, t in transfers.items()
        if date(2026, 12, 1) <= d <= date(2026, 12, 5)
    }
    assert all(t[1] != "302A" for t in in_window.values())
    after = [t for d, t in transfers.items() if d >= date(2026, 12, 6)]
    assert any(t[1] == "302A" for t in after)
    # 代价：窗口内有一日三罐全不可用 → 少一批，洞后置 3 天显形；
    # 占用期间罐不算空拍（空拍=空闲却未接），故 idle_tank_days 为 0
    assert result.summary["transfer_count"] == 29
    assert date(2026, 12, 6) not in dumps
    assert result.summary["idle_tank_days"] == 0
    assert _warns(report) == []


def test_tank_block_and_skip_combined() -> None:
    block = draft.TankBlock(
        tank_no="303A", from_date=date(2026, 12, 10), to_date=date(2026, 12, 12)
    )
    result, report = _generate(
        skip_dates={date(2026, 12, 5)}, tank_blocks=[block]
    )
    transfers = _transfer_days(result)
    window = {
        d: t
        for d, t in transfers.items()
        if date(2026, 12, 10) <= d <= date(2026, 12, 12)
    }
    assert all(t[1] != "303A" for t in window.values())
    assert date(2026, 12, 5) not in transfers
    assert _warns(report) == []


# ═══════════════════ 排产表格式 ═══════════════════


def test_rows_match_current_fa_layout() -> None:
    result, _ = _generate()
    rows = result.rows
    # 标题可被现行周期块识别（与 _TITLE_RE 同口径）
    assert board.parse_period_title(str(rows[0][0])) == (DRAFT_START, DRAFT_END)
    # 行布局：日期行标签在第二格，业务行标签在首格，数据从第 3 列起
    assert rows[1][1] == "日期"
    assert [rows[i][0] for i in (3, 5, 6, 8, 9, 11, 12)] == [
        "种子罐",
        "接种时间",
        "发酵罐",
        "移种时间",
        "放罐",
        "放罐时间",
        "备注",
    ]
    # 一天一列：27..26 共 30 列；时间为文本（非时间对象）
    dates = rows[1][2:]
    assert len(dates) == 30
    assert dates[:4] == [27, 28, 29, 30] and dates[-1] == 26
    times = [v for v in rows[8][2:] if v]
    assert set(times) == {"21:00"}
    assert all(isinstance(v, str) for v in times)
    # 备注行第二格为月度汇总
    assert rows[12][1] == "11月共放罐30批"


def test_workbook_round_trip() -> None:
    """生成 xlsx → 现行上传解析器读回 → 事件与预览完全一致。"""
    result, _ = _generate(skip_dates={date(2026, 12, 5)})
    buffer = draft.build_draft_workbook(result)
    parsed = schedule_excel_service.parse_workbook_bytes(buffer.getvalue())
    rows = parsed["rows"]
    # 周期块可识别
    assert board.find_period_block(
        rows, datetime.combine(DRAFT_START + timedelta(days=3), board_time())
    ) is not None
    # 移种/放罐事件一致
    transfers = _transfer_days(result)
    dumps = _dump_days(result)
    for event in board.collect_ferm_events(rows):
        assert transfers[event["start"].date()] == (
            event["batch_no"],
            event["tank_no"],
        )
    assert len(board.collect_ferm_events(rows)) == result.summary["transfer_count"]
    dump_dates = board.collect_dump_dates(rows)
    for day, batches in dumps.items():
        for batch, _tank in batches:
            assert dump_dates[batch] == day
    # 种子罐号随表往返
    first_block = board.parse_block(
        rows,
        {"start_row": 0, "start": DRAFT_START, "end": DRAFT_END, "label": ""},
    )
    seed_tank_cells = [d["seed_tank"] for d in first_block["days"] if d["seed_tank"]]
    assert seed_tank_cells[:2] == ["202A", "201A"]
    # round-trip 后再跑一期校验，依旧零 warn（上传链路兼容）
    report = validation.validate_schedule_rows(
        rows,
        previous_rows=PREV_ROWS,
        constraints=CONSTRAINTS,
        now=NOW,
    )
    assert [i for i in report["issues"] if i["level"] == "warn"] == []


def board_time():
    from datetime import time

    return time(12, 0)


def test_no_seed_wasted_in_planned_skips() -> None:
    """所有未接种日均有成因（跳过/无罐/周期末），不出现计划性废种。"""
    result, _ = _generate(skip_dates={date(2026, 12, 5), date(2026, 12, 6)})
    for entry in result.days:
        if entry.seed_batch is None:
            assert entry.seed_note, f"{entry.date} 未接种但无成因说明"
            assert "废种" not in (entry.transfer_note or "")


def test_two_consecutive_skips_still_zero_warn() -> None:
    result, report = _generate(
        skip_dates={date(2026, 12, 5), date(2026, 12, 6)}
    )
    assert result.summary["transfer_count"] == 28
    assert _warns(report) == []


# ═══════════════════ 跨月对齐与多周期分块 ═══════════════════


def test_period_alignment_and_two_blocks() -> None:
    """起始/截止对齐所在扎帐周期；跨两月时按周期分块输出。

    上期存档 = 9/27~10/26 满排（移种到 10/26，放罐到 10/26，尾巴
    10/24~26 移种的批次放罐落 10/27~29，10/26 晚备好种子 FA26331）。
    草稿选 10/20~11/15 → 对齐 9/27~11/26 两个月：重叠期 9/27~10/26
    全部按在制占位无新移种；新批次从 10/30 前最后一个空罐日（10/27）
    接续，批号跳过上期备好的 FA26331 从 FA26332 起。
    """
    prev: dict[date, dict[str, Any]] = {}

    def ensure(day: date) -> dict[str, Any]:
        return prev.setdefault(
            day, {"seed": None, "ferm": None, "dump": None, "note": ""}
        )

    for idx in range(30):  # 9/27 .. 10/26 每日移种
        ferm_day = date(2026, 9, 27) + timedelta(days=idx)
        batch = f"FA{26301 + idx}"
        tank = TANKS[idx % 3]
        ensure(ferm_day - timedelta(days=1))["seed"] = batch
        ensure(ferm_day)["ferm"] = (batch, tank)
        dump_day = ferm_day + timedelta(days=3)
        if dump_day <= date(2026, 10, 26):
            ensure(dump_day)["dump"] = (batch, tank)
    # 10/26 晚备好下一周期首日（10/27）的种子
    ensure(date(2026, 10, 26))["seed"] = "FA26331"
    prev_rows = _fa_block_rows(
        "2026年9月27日～2026年10月26日103车间FA450T罐排产", prev
    )
    params = draft.DraftParams(
        period_start=date(2026, 9, 27),
        period_end=date(2026, 11, 26),
        skip_dates=set(),
        tank_blocks=[],
    )
    result = draft.generate_draft(prev_rows, params, constraints=CONSTRAINTS)
    report = draft.validate_draft(
        result, prev_rows, constraints=CONSTRAINTS, now=datetime(2026, 9, 20)
    )
    # 两个周期块：标题各按 27~26
    titles = [
        str(r[0])
        for r in result.rows
        if r and board.parse_period_title(str(r[0]))
    ]
    assert titles == [
        "2026年9月27日～2026年10月26日103车间FA450T罐排产",
        "2026年10月27日～2026年11月26日103车间FA450T罐排产",
    ]
    transfers = _transfer_days(result)
    dumps = _dump_days(result)
    # 重叠期 9/27~10/26 无新移种（上期在制占满），10/27 起接续
    assert all(d >= date(2026, 10, 27) for d in transfers)
    assert transfers[date(2026, 10, 27)] == ("FA26332", "302A")
    # 上期批次的放罐落进草稿：首日 9/30（上期 9/27 移种批）与尾巴 10/27~29
    assert dumps[date(2026, 9, 30)] == [("FA26301", "302A")]
    assert dumps[date(2026, 10, 27)] == [("FA26328", "302A")]
    assert dumps[date(2026, 10, 29)] == [("FA26330", "304A")]
    # 黄金断言：跨月两块依旧零 warn
    assert [i for i in report["issues"] if i["level"] == "warn"] == []


def test_two_period_round_trip() -> None:
    """跨月草稿 Excel → 现行解析器读回 → 两个周期块均可识别。"""
    prev: dict[date, dict[str, Any]] = {}
    for idx in range(3):
        ferm_day = date(2026, 10, 24) + timedelta(days=idx)
        batch = f"FA2640{idx + 1}"
        tank = TANKS[idx % 3]
        prev.setdefault(
            ferm_day, {"seed": None, "ferm": None, "dump": None, "note": ""}
        )["ferm"] = (batch, tank)
    prev_rows = _fa_block_rows(
        "2026年9月27日～2026年10月26日103车间FA450T罐排产", prev
    )
    params = draft.DraftParams(
        period_start=date(2026, 10, 27), period_end=date(2026, 12, 26)
    )
    result = draft.generate_draft(prev_rows, params, constraints=CONSTRAINTS)
    buffer = draft.build_draft_workbook(result)
    parsed = schedule_excel_service.parse_workbook_bytes(buffer.getvalue())
    from datetime import time as dt_time

    first = board.find_period_block(
        parsed["rows"], datetime.combine(date(2026, 11, 10), dt_time(12, 0))
    )
    second = board.find_period_block(
        parsed["rows"], datetime.combine(date(2026, 12, 10), dt_time(12, 0))
    )
    assert first is not None and second is not None
    assert first["start"] == date(2026, 10, 27)
    assert second["start"] == date(2026, 11, 27)
    assert len(board.collect_ferm_events(parsed["rows"])) == (
        result.summary["transfer_count"]
    )


# ═══════════════════ 生成历史记录 ═══════════════════


@pytest.mark.asyncio
async def test_upsert_draft_record_dedupes_same_params(db_session) -> None:
    """同参数重复生成去重更新；导出附文件并记录时间；软删后可重建。"""
    params = draft.DraftParams(
        period_start=DRAFT_START,
        period_end=DRAFT_END,
        skip_dates={date(2026, 12, 5)},
    )
    result = draft.generate_draft(PREV_ROWS, params, constraints=CONSTRAINTS)
    report = draft.validate_draft(result, PREV_ROWS, constraints=CONSTRAINTS, now=NOW)

    first = await draft.upsert_draft_record(
        db_session,
        product_code="FA",
        params=params,
        result=result,
        validation_report=report,
    )
    again = await draft.upsert_draft_record(
        db_session,
        product_code="FA",
        params=params,
        result=result,
        validation_report=report,
    )
    assert again.id == first.id  # 同参数去重，不新增
    # 不同参数（去掉跳过日）→ 新记录
    params2 = draft.DraftParams(period_start=DRAFT_START, period_end=DRAFT_END)
    result2 = draft.generate_draft(PREV_ROWS, params2, constraints=CONSTRAINTS)
    report2 = draft.validate_draft(result2, PREV_ROWS, constraints=CONSTRAINTS, now=NOW)
    second = await draft.upsert_draft_record(
        db_session,
        product_code="FA",
        params=params2,
        result=result2,
        validation_report=report2,
        workbook_bytes=b"PK-fake",
        file_name="草稿.xlsx",
    )
    assert second.id != first.id
    assert second.file_name == "草稿.xlsx"
    assert second.original_path and second.downloaded_at is not None
    assert first.downloaded_at is None  # 仅预览的记录无导出信息
    # 快照字段完整（详情可回放当时方案）
    detail = draft.serialize_draft_record_detail(second)
    assert detail["days"] and detail["summary"]["period"]["start"] == "2026-11-27"
    assert detail["validation"]["summary"] is not None
    # 软删
    await draft.soft_delete_draft_record(db_session, first)
    assert await draft.get_draft_record(db_session, first.id) is None
    await db_session.delete(second)
    await db_session.commit()


@pytest.mark.asyncio
async def test_list_draft_records_orders_by_recency(db_session) -> None:
    params = draft.DraftParams(period_start=DRAFT_START, period_end=DRAFT_END)
    result = draft.generate_draft(PREV_ROWS, params, constraints=CONSTRAINTS)
    report = draft.validate_draft(result, PREV_ROWS, constraints=CONSTRAINTS, now=NOW)
    record = await draft.upsert_draft_record(
        db_session, product_code="FA", params=params, result=result,
        validation_report=report,
    )
    items, total = await draft.list_draft_records(
        db_session, product_code="FA", page=1, page_size=10
    )
    assert total >= 1
    assert any(item.id == record.id for item, _name in items)
    await draft.soft_delete_draft_record(db_session, record)
    items2, total2 = await draft.list_draft_records(
        db_session, product_code="FA", page=1, page_size=10
    )
    assert all(item.id != record.id for item, _name in items2)
