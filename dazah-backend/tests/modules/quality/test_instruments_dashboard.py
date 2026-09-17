"""仪器管理仪表盘聚合：概览统计、校验到期提醒（mock 镜像读取）。

口径：内部校验计划 2026-09 起表内新增「状态」公式列（未提醒/提醒中/已完成），
提供可靠完成标记，据此纳入到期提醒——已完成行不计；合同只统计总数、
不做到期提醒。
"""

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
    assert result["contracts"] == {"total": 0}
    assert captured["entity"] == "qc_instr_equipment"


def _ms(target: date) -> str:
    """日期 -> 飞书 DateTime 列的毫秒时间戳字符串（东八区当天零点）。"""
    stamp = datetime(target.year, target.month, target.day, tzinfo=_TZ_SH)
    return str(int(stamp.timestamp() * 1000))


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
        # 内部校验计划：状态=已完成的行不计；未完成行按计划校验时间归档
        "qc_instr_cal_plan": [
            {
                # 提醒中 + 3 天后到期 → 进临期提醒
                "record_id": "p1",
                "仪器、设备名称": "TOC",
                "仪器、设备编号": "QC-1-2-020",
                "状态": "提醒中",
                "计划校验时间": _ms(_today(3)),
                "剩余天数": "3",
            },
            {
                # 已完成：即使刚过期也绝不计入
                "record_id": "p2",
                "仪器、设备名称": "done-TOC",
                "仪器、设备编号": "QC-1-2-021",
                "状态": "已完成",
                "计划校验时间": _ms(_today(-1)),
            },
            {
                # 未提醒 + 已过期 200 天 → 进过期提醒
                "record_id": "p3",
                "仪器、设备名称": "past-TOC",
                "仪器、设备编号": "QC-1-2-022",
                "状态": "未提醒",
                "计划校验时间": _serial(_today(-200)),
            },
            {
                # 未提醒 + 远期 → 不进提醒
                "record_id": "p4",
                "仪器、设备名称": "future-TOC",
                "仪器、设备编号": "QC-1-2-023",
                "状态": "未提醒",
                "计划校验时间": _ms(_today(100)),
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
            # 未完成：5 天后到期 → 7 天内临期
            {
                "record_id": "m1",
                "是否完成": "否",
                "下次维保时间": _ms(_today(5)),
            },
            # 未完成：40 天后到期 → 不临期
            {
                "record_id": "m2",
                "是否完成": "否",
                "下次维保时间": _ms(_today(40)),
            },
            # 已完成：即使 2 天后到期也绝不计入临期
            {
                "record_id": "m3",
                "是否完成": "是",
                "下次维保时间": _ms(_today(2)),
            },
        ],
        "qc_instr_plans": [{"record_id": "cy1"}, {"record_id": "cy2"}],
        # 合同：历史合同临期/过期一律不再提醒，只统计总数
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
    # 未完成 2 条（已完成的 m3 不计入）；7 天内临期只有未完成的 m1
    assert result["maintenance"] == {
        "total": 3,
        "unfinished": 2,
        "due_soon_7d": 1,
        "cycle_count": 2,
    }
    assert result["contracts"] == {"total": 2}

    # 图表聚合：设备状态构成按数量降序
    assert result["equipment_status"] == [
        {"name": "完好", "value": 2},
        {"name": "维修", "value": 1},
    ]
    # 未来 6 个月校验分布：c1（+10 天）与 x1（+45 天）落在窗口内；
    # 过期 c2 与 400 天外的 c3 不计
    upcoming = result["calibration_upcoming"]
    assert len(upcoming) == 6
    assert sum(item["count"] for item in upcoming) == 2
    # 未完成维保到期分布：m1→7 天内，m2→31~90 天；已完成的 m3 不计
    buckets = {
        item["name"]: item["value"] for item in result["maintenance_due_buckets"]
    }
    assert buckets == {
        "已过期": 0,
        "7 天内": 1,
        "8~30 天": 0,
        "31~90 天": 1,
        "90 天以上": 0,
    }

    due = result["calibration_due"]
    # 临期提醒：内校计划 p1（3 天，提醒中）+ 内校汇总 c1（10 天），按天数升序
    assert [(item["days"], item["source"]) for item in due] == [
        (3, "内校计划"),
        (10, "内校汇总"),
    ]

    expired = result["calibration_expired"]
    # 过期提醒：计划表 p3（未提醒且过期 200 天）+ 内校汇总 c2（过期 5 天）
    assert [item["record_id"] for item in expired] == ["p3", "c2"]
    assert [item["days"] for item in expired] == [-200, -5]
    assert expired[0]["source"] == "内校计划"
    # 已完成的 p2 即使刚过期也绝不出现
    assert "p2" not in [item["record_id"] for item in expired + due]
