"""生产汇总聚合（build_production_summary）单测：五产线结构与工段权限过滤。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.production import fermentation_board_service as board
from tests.unit.test_fermentation_board_service import _dr_rows, _mp_rows

EXPECTED_PRODUCTS = ["MC", "DR", "FA", "LV", "MV"]


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
