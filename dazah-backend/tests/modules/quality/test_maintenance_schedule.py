"""维护保养记录「下次维保时间」自动计算（按维保周期表匹配）。"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.modules.quality.service import maintenance_schedule as schedule

pytestmark = pytest.mark.anyio


def _page(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": 500,
        "configured": True,
        "fields": [],
        "last_sync_time": None,
    }


def _ms(target: date) -> str:
    # 东八区当天零点的毫秒时间戳（普通 DateTime 列回读形态）
    from datetime import datetime, timedelta, timezone

    tz = timezone(timedelta(hours=8))
    stamp = datetime(target.year, target.month, target.day, tzinfo=tz).timestamp()
    return str(int(stamp * 1000))


def _install_cycle(
    monkeypatch: pytest.MonkeyPatch, cycles: list[dict[str, Any]]
) -> None:
    async def fake_load_page(db: Any, entity_code: str):
        assert entity_code == "qc_instr_plans"
        return _page(cycles)

    monkeypatch.setattr(schedule, "_load_page", fake_load_page)


async def test_add_months_clamps_to_month_end() -> None:
    assert schedule.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert schedule.add_months(date(2026, 3, 15), 3) == date(2026, 6, 15)
    assert schedule.add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)


async def test_enrich_fills_next_date_from_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 周期表：一格多编号（顿号分隔），周期 3 个月
    _install_cycle(
        monkeypatch,
        [
            {
                "仪器类别": "色谱类",
                "仪器编号": "QC-1-2-010、QC-1-2-011",
                "维护周期": "每3个月",
                "周期（月）": 3,
            },
        ],
    )
    items = [
        {
            "record_id": "m1",
            "仪器编号": "QC-1-2-011",
            "是否完成": "是",
            "完成日期": _ms(date(2026, 1, 31)),
            "下次维保时间": None,
        },
        {
            "record_id": "m2",
            "仪器编号": "QC-9-9-999",  # 周期表没有的编号
            "是否完成": "是",
            "完成日期": _ms(date(2026, 1, 31)),
        },
        {
            "record_id": "m3",
            "仪器编号": "QC-1-2-010",
            "是否完成": "否",
            "生成日期": _ms(date(2026, 6, 30)),
            # 已有值不覆盖
            "下次维保时间": "2026-12-31",
        },
    ]

    enriched = await schedule.enrich_maintenance_schedule(None, items)

    # 完成日期 2026-01-31 + 3 个月，1 月 31 日钳到 2 月 28 日
    assert enriched[0]["下次维保时间"] == "2026-04-30" or enriched[0][
        "下次维保时间"
    ] == "2026-04-30"
    assert enriched[0]["下次维保时间"] == str(schedule.add_months(date(2026, 1, 31), 3))
    # 周期表没有的编号：保持空
    assert not enriched[1].get("下次维保时间")
    # 已有值不覆盖
    assert enriched[2]["下次维保时间"] == "2026-12-31"


async def test_enrich_prefers_completion_date_over_generated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cycle(
        monkeypatch,
        [{"仪器编号": "QC-1-2-010", "周期（月）": 6}],
    )
    items = [
        {
            "record_id": "m1",
            "仪器编号": "QC-1-2-010",
            "生成日期": _ms(date(2026, 1, 1)),
            "完成日期": _ms(date(2026, 5, 20)),
        },
    ]
    enriched = await schedule.enrich_maintenance_schedule(None, items)
    assert enriched[0]["下次维保时间"] == "2026-11-20"


async def test_enrich_no_cycles_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_cycle(monkeypatch, [])
    items: list[dict[str, Any]] = [{"record_id": "m1", "仪器编号": "QC-1-2-010"}]
    enriched = await schedule.enrich_maintenance_schedule(None, items)
    assert enriched == items


async def test_backfill_writes_only_empty_dates_and_updates_local_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回写：只更新「下次维保时间」为空的行；写成功后同步本地 fields。"""
    _install_cycle(
        monkeypatch,
        [{"仪器编号": "QC-1-2-010", "周期（月）": 3}],
    )
    updates: list[tuple[str, dict[str, Any]]] = []

    class _Client:
        async def update_record(
            self, table_id, record_id, fields, *, user_id_type="open_id"
        ):
            updates.append((record_id, fields))
            return {}

    records = [
        {
            "record_id": "rec-empty",
            "fields": {
                "仪器编号": "QC-1-2-010",
                "完成日期": _ms(date(2026, 5, 20)),
                "下次维保时间": None,
            },
        },
        {
            "record_id": "rec-filled",
            "fields": {
                "仪器编号": "QC-1-2-010",
                "下次维保时间": 1_800_000_000_000,
            },
        },
        {
            "record_id": "rec-nocycle",
            "fields": {"仪器编号": "QC-9-9-999", "下次维保时间": None},
        },
    ]

    updated = await schedule.backfill_next_maintenance_dates(
        None, _Client(), "tblX", records
    )

    assert updated == 1
    assert len(updates) == 1
    record_id, fields = updates[0]
    assert record_id == "rec-empty"
    expected_ms = schedule._next_due_ms(schedule.add_months(date(2026, 5, 20), 3))
    assert fields["下次维保时间"] == expected_ms
    # 回写成功后本地 fields 同步更新（镜像与飞书一致）
    assert records[0]["fields"]["下次维保时间"] == expected_ms
    assert records[1]["fields"]["下次维保时间"] == 1_800_000_000_000  # 已填不动


async def test_backfill_swallows_single_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cycle(
        monkeypatch,
        [{"仪器编号": "QC-1-2-010", "周期（月）": 3}],
    )

    class _FailingClient:
        async def update_record(
            self, table_id, record_id, fields, *, user_id_type="open_id"
        ):
            raise RuntimeError("feishu down")

    records = [
        {
            "record_id": "rec-1",
            "fields": {
                "仪器编号": "QC-1-2-010",
                "完成日期": _ms(date(2026, 5, 20)),
            },
        },
        {
            "record_id": "rec-2",
            "fields": {
                "仪器编号": "QC-1-2-010",
                "完成日期": _ms(date(2026, 5, 21)),
            },
        },
    ]

    updated = await schedule.backfill_next_maintenance_dates(
        None, _FailingClient(), "tblX", records
    )
    assert updated == 0
    assert all(
        r["fields"].get("下次维保时间") in (None, "")
        for r in records
    )
