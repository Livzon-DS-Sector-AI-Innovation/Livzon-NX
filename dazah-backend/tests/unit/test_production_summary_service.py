"""生产汇总聚合（build_production_summary）单测：五产线结构与工段权限过滤。"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.production import fermentation_board_service as board
from tests.unit.test_fermentation_board_service import _dr_rows, _mp_rows

EXPECTED_PRODUCTS = ["MC", "DR", "FA", "LV", "MV", "TY", "FL"]


def _empty_db() -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _patch_board_io(monkeypatch: Any) -> None:
    """隔离外部读写：存档/仓储/日报/批次实绩全部不触碰真实查询。"""
    monkeypatch.setattr(board, "load_archive_covering", AsyncMock(return_value=None))
    monkeypatch.setattr(
        board, "get_warehouse_finished_inbound_kg", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        board, "sum_extraction_daily_reports", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(board, "list_batch_actuals", AsyncMock(return_value=[]))
    monkeypatch.setattr(board, "get_month_setting", AsyncMock(return_value=None))


@pytest.mark.anyio
async def test_summary_lists_five_products_in_fixed_order(monkeypatch: Any) -> None:
    _patch_board_io(monkeypatch)
    payload = await board.build_production_summary(
        _empty_db(), ref_date=date(2026, 9, 16), has_ferm=True, has_extract=True
    )
    assert [row["product_code"] for row in payload["rows"]] == EXPECTED_PRODUCTS
    assert payload["period"] is None or "start" in payload["period"]


@pytest.mark.anyio
async def test_summary_uncovered_new_products_keep_extract_metrics(
    monkeypatch: Any,
) -> None:
    """TY/FL 无排产存档：发酵段空值兜底，提炼段按统一扎帐周期出数。"""
    plan_rows = [
        SimpleNamespace(
            is_deleted=False,
            workshop="203-3车间",
            product_name="L-色氨酸",
            planned_yield=69000.0,
        ),
        SimpleNamespace(
            is_deleted=False,
            workshop="102-2车间",
            product_name="2%氟苯尼考预混剂",
            planned_yield=60000.0,
        ),
    ]
    plan_result = MagicMock()
    plan_result.scalars.return_value.all.return_value = plan_rows
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    state = {"plan_fetched": False}

    async def _execute(*_args: Any, **_kwargs: Any) -> Any:
        # 第 1 次为生产计划查询，其余（如下周期提醒）一律空结果
        if not state["plan_fetched"]:
            state["plan_fetched"] = True
            return plan_result
        return empty_result

    db = MagicMock()
    db.execute = _execute

    captured: dict[str, tuple[date, date]] = {}

    async def _inbound(
        db: Any,
        *,
        product_code: str,
        period_start: date,
        period_end: date,
    ) -> float | None:
        captured[product_code] = (period_start, period_end)
        return {"TY": 0.0, "FL": 9900.0}.get(product_code)

    _patch_board_io(monkeypatch)
    monkeypatch.setattr(board, "get_warehouse_finished_inbound_kg", _inbound)

    payload = await board.build_production_summary(
        db, ref_date=date(2026, 9, 15), has_ferm=True, has_extract=True
    )
    by_code = {row["product_code"]: row for row in payload["rows"]}
    ty = by_code["TY"]
    fl = by_code["FL"]
    # 无存档：发酵段空值兜底
    assert ty["covered"] is False
    assert ty["ferment"]["planned_batches"] is None
    assert ty["ferment"]["done_yield_kg"] is None
    # 提炼段与计划同按扎帐周期（8/27～9/26），计划产量取自产销计划行
    assert ty["extract"]["planned_yield_kg"] == 69000.0
    assert ty["extract"]["finished_inbound_kg"] == 0.0
    assert ty["extract"]["completion_rate"] == 0.0
    assert fl["extract"]["finished_inbound_kg"] == 9900.0
    assert fl["extract"]["completion_rate"] == 16.5
    # 入库统计区间为统一扎帐周期（27日～26日），而非自然月
    for code in ("TY", "FL"):
        assert captured[code] == (date(2026, 8, 27), date(2026, 9, 26))


@pytest.mark.anyio
async def test_summary_hides_stage_fields_without_permissions(
    monkeypatch: Any,
) -> None:
    _patch_board_io(monkeypatch)
    payload = await board.build_production_summary(
        _empty_db(), ref_date=date(2026, 9, 16), has_ferm=False, has_extract=False
    )
    row = payload["rows"][0]
    # 无工段权限：指标保持 None，告警不出接口
    assert row["ferment"]["planned_batches"] is None
    assert row["extract"]["planned_yield_kg"] is None
    assert row["alerts"] == []


@pytest.mark.anyio
async def test_summary_none_fields_when_no_archive_covers_period(
    monkeypatch: Any,
) -> None:
    _patch_board_io(monkeypatch)
    payload = await board.build_production_summary(
        _empty_db(), ref_date=date(2026, 9, 16), has_ferm=True, has_extract=True
    )
    row = payload["rows"][0]
    # 无覆盖存档：各段指标为 None，但结构完整
    assert row["ferment"]["planned_capacity_kg"] is None
    assert row["extract"]["finished_inbound_kg"] is None
    assert SimpleNamespace(**row["ferment"]) is not None


@pytest.mark.anyio
async def test_summary_fills_ferment_metrics_from_mc_archive(
    monkeypatch: Any,
) -> None:
    _patch_board_io(monkeypatch)
    archive = SimpleNamespace(rows=_mp_rows(), product_code="MC")

    async def _covering(db: Any, ref_date: Any, code: str) -> Any:
        return archive if code == "MC" else None

    monkeypatch.setattr(
        board,
        "load_archive_covering",
        AsyncMock(side_effect=_covering),
    )
    monkeypatch.setattr(
        board,
        "get_month_setting",
        AsyncMock(return_value=SimpleNamespace(planned_capacity_kg=930000.0)),
    )
    payload = await board.build_production_summary(
        _empty_db(), ref_date=date(2026, 9, 15), has_ferm=True, has_extract=True
    )
    mc = next(r for r in payload["rows"] if r["product_code"] == "MC")
    assert mc["ferment"]["planned_batches"] is not None
    assert mc["ferment"]["planned_capacity_kg"] == 930000.0
    assert payload["period"] is not None
    assert "8月27日" in payload["period"]["start"] + payload["period"]["label"]


@pytest.mark.anyio
async def test_summary_fills_metrics_for_dr_archive(monkeypatch: Any) -> None:
    _patch_board_io(monkeypatch)
    archive = SimpleNamespace(rows=_dr_rows(), product_code="DR")

    async def _covering(db: Any, ref_date: Any, code: str) -> Any:
        return archive if code == "DR" else None

    monkeypatch.setattr(
        board,
        "load_archive_covering",
        AsyncMock(side_effect=_covering),
    )
    payload = await board.build_production_summary(
        _empty_db(), ref_date=date(2026, 9, 15), has_ferm=True, has_extract=True
    )
    dr = next(r for r in payload["rows"] if r["product_code"] == "DR")
    assert dr["ferment"]["planned_batches"] is not None
    assert dr["ferment"]["planned_capacity_kg"] is None


_FA_TITLE = "2026年08月27日～2026年09月26日103车间FA450T罐排产"


def _fa_rows() -> list[list]:
    """FA 块：8/27 与 9/16（所选月 15 日之后）各一个计划放罐批次。"""
    return [
        [_FA_TITLE, "", "", "", "", ""],
        ["", "日期", 27, 28, 16, ""],
        ["时间", "罐号", "", "", "", ""],
        ["种子罐", "", "", "", "", ""],
        ["罐号", "", "", "", "", ""],
        ["接种时间", "", "", "", "", ""],
        ["发酵罐", "", "", "", "", ""],
        ["罐号", "", "", "", "", ""],
        ["移种时间", "", "", "", "", ""],
        ["放罐", "", "FA-EARLY", "", "FA-LATE", ""],
        ["罐号", "", "302A", "", "302A", ""],
        ["放罐时间", "", "10:00", "", "10:00", ""],
        ["备注", "", "", "", "", ""],
    ]


@pytest.mark.anyio
async def test_summary_counts_dumps_recorded_after_month_anchor(
    monkeypatch: Any,
) -> None:
    """回归：15 日后放罐且已录产量的批次必须计入当月汇总已完成产能。

    看板 KPI 曾按所选月 15 日构建 now，16 日起放罐的批次在汇总中
    永久缺席（单产品看板按真实时间正常统计）；现 KPI 与单板一致，
    按 alert_now 真实时间门控，15 日锚点只定位周期块。
    """
    _patch_board_io(monkeypatch)
    archive = SimpleNamespace(rows=_fa_rows(), product_code="FA")

    async def _covering(db: Any, ref_date: Any, code: str) -> Any:
        return archive if code == "FA" else None

    monkeypatch.setattr(
        board,
        "load_archive_covering",
        AsyncMock(side_effect=_covering),
    )
    actuals = [
        SimpleNamespace(
            id="1",
            batch_no="FA-EARLY",
            dump_date=date(2026, 8, 27),
            yield_kg=100.0,
            extract_kg=None,
            remark=None,
        ),
        SimpleNamespace(
            id="2",
            batch_no="FA-LATE",
            dump_date=date(2026, 9, 16),
            yield_kg=200.0,
            extract_kg=None,
            remark=None,
        ),
    ]
    monkeypatch.setattr(
        board, "list_batch_actuals", AsyncMock(return_value=actuals)
    )
    monkeypatch.setattr(
        board,
        "get_month_setting",
        AsyncMock(return_value=SimpleNamespace(planned_capacity_kg=945500.0)),
    )
    payload = await board.build_production_summary(
        _empty_db(),
        ref_date=date(2026, 9, 15),
        has_ferm=True,
        has_extract=True,
        today=date(2026, 9, 18),
        alert_now=datetime(2026, 9, 18, 12, 0),
    )
    fa = next(r for r in payload["rows"] if r["product_code"] == "FA")
    # 两批均已过放罐窗口且已录产量：15 日后放罐的 FA-LATE 不再被冻结漏计
    assert fa["ferment"]["done_yield_kg"] == 300.0
    assert fa["ferment"]["planned_batches"] == 2
    # 产能达成率跟随已完成产能（945500 为月计划产能设置）
    assert fa["ferment"]["capacity_rate"] == round(300.0 / 945500.0 * 100, 1)
