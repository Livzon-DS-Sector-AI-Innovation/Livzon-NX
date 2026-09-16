"""仪器管理仪表盘聚合：概览统计、校验/合同到期提醒（mock 镜像读取）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from app.modules.quality.service import instruments_dashboard as dashboard

pytestmark = pytest.mark.anyio

_TZ_SH = timezone(timedelta(hours=8))


def _serial(target: date) -> str:
    """日期 -> 飞书公式日期列的 Excel 序列号字符串。"""
    return str((target - date(1899, 12, 30)).days)


def _today(offset_days: int) -> date:
    return datetime.now(tz=_TZ_SH).date() + timedelta(days=offset_days)


def _page(items: list[dict[str, Any]], configured: bool = True) -> dict[str, Any]:
    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": 500,
        "configured": configured,
        "fields": [],
        "last_sync_time": "2026-09-14T00:00:00+00:00",
    }


def _install_mirror(
    monkeypatch: pytest.MonkeyPatch, pages: dict[str, list[Any]]
) -> None:
    async def fake_list(
        db: Any, entity_code: str, *, page: int = 1, page_size: int = 500
    ):
        return _page(pages.get(entity_code, []))

    monkeypatch.setattr(dashboard, "list_instrument_mirror", fake_list)


async def test_dashboard_configured_false_when_mirror_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_list(
        db: Any, entity_code: str, *, page: int = 1, page_size: int = 500
    ):
        captured["entity"] = entity_code
        return _page([], configured=False)

    monkeypatch.setattr(dashboard, "list_instrument_mirror", fake_list)
    result = await dashboard.get_instruments_dashboard(None)
    assert result["configured"] is False
    assert result["equipment"]["total"] == 0
    assert captured["entity"] == "qc_instr_equipment"


async def test_dashboard_aggregates_stats_and_due_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        "qc_instr_equipment": [
            {
                "record_id": "e1",
                "设备名称": "HPLC",
                "设备状态": "完好",
                "设备类型": "重点设备",
            },
            {
                "record_id": "e2",
                "设备名称": "GC",
                "设备状态": "维修",
                "设备类型": "主要设备",
            },
            {
                "record_id": "e3",
                "设备名称": "天平",
                "设备状态": "完好",
                "设备类型": "一般设备",
            },
        ],
        # 内校汇总：公式日期为 Excel 序列号；一条 10 天后到期、一条已过期 5 天
        "qc_instr_calibration": [
            {
                "record_id": "c1",
                "仪器、设备名称": "水浴锅",
                "仪器、设备编号": "QC-3-2-136",
                "校验有效期": _serial(_today(10)),
            },
            {
                "record_id": "c2",
                "仪器、设备名称": "旧烘箱",
                "仪器、设备编号": "QC-3-2-001",
                "校验有效期": _serial(_today(-5)),
            },
            {
                "record_id": "c3",
                "仪器、设备名称": "远期仪器",
                "仪器、设备编号": "QC-3-2-002",
                # 有效期为毫秒时间戳形态、远期
                "校验有效期": str(
                    int(datetime.now(tz=_TZ_SH).timestamp() * 1000)
                    + 400 * 24 * 3600 * 1000
                ),
            },
        ],
        # 内部校验计划：直接给公式「剩余天数」
        "qc_instr_cal_plan": [
            {
                "record_id": "p1",
                "仪器、设备名称": "TOC",
                "仪器、设备编号": "QC-1-2-020",
                "剩余天数": "3",
            },
        ],
        "qc_instr_cal_external": [
            {
                "record_id": "x1",
                "器具名称": "电位滴定仪",
                "器具编号": "1916001004291",
                "下次检定日期": _serial(_today(45)),
            },
        ],
        "qc_instr_maintenance": [
            {"record_id": "m1", "是否完成": "否"},
            {"record_id": "m2", "是否完成": "是"},
        ],
        "qc_instr_plans": [{"record_id": "cy1"}, {"record_id": "cy2"}],
        "qc_instr_contracts": [
            {
                "record_id": "k1",
                "设备维保合同": "合同A",
                "有效期": _serial(_today(20)),
            },
            {
                "record_id": "k2",
                "设备维保合同": "合同B",
                "有效期": _serial(_today(365)),
            },
        ],
    }
    _install_mirror(monkeypatch, pages)

    result = await dashboard.get_instruments_dashboard(None)

    assert result["configured"] is True
    assert result["equipment"] == {"total": 3, "ok": 2, "repairing": 1, "key_count": 1}
    assert result["maintenance"] == {"total": 2, "unfinished": 1, "cycle_count": 2}
    assert result["contracts"]["total"] == 2
    assert [item["record_id"] for item in result["contracts"]["expiring"]] == ["k1"]

    due = result["calibration_due"]
    # 剩余天数升序：TOC(3) -> 水浴锅(10)；远期与外部 45 天不进提醒
    assert [item["days"] for item in due] == [3, 10]
    assert due[0]["source"] == "内部校验计划"
    assert due[1]["source"] == "内校汇总"

    expired = result["calibration_expired"]
    assert [item["record_id"] for item in expired] == ["c2"]
    assert expired[0]["days"] == -5


async def test_dashboard_maintenance_contract_expires_included(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """合同到期提醒含已过期（负数），按剩余天数升序。"""
    pages = {
        "qc_instr_equipment": [{"record_id": "e1", "设备状态": "完好"}],
        "qc_instr_contracts": [
            {"record_id": "k1", "有效期": _serial(_today(-2))},
            {"record_id": "k2", "有效期": _serial(_today(15))},
        ],
    }
    _install_mirror(monkeypatch, pages)

    result = await dashboard.get_instruments_dashboard(None)
    assert [item["days"] for item in result["contracts"]["expiring"]] == [-2, 15]
    assert result["contracts"]["expiring"][0]["due_date"] == _today(-2).isoformat()
