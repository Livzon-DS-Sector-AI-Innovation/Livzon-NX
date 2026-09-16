"""维护保养记录「完成即生成下一期任务」：spawn 触发/防重复/复制字段 + 展示 enrich。"""

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


class _Client:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.completed: list[tuple[str, dict[str, Any]]] = []
        self.searched: list[str] = []
        self.search_results: dict[str, list[dict[str, Any]]] = {}

    async def search_records(self, table_id, *, filter_str=None, **kwargs):
        code = filter_str.split('"')[1]
        self.searched.append(code)
        return self.search_results.get(code, [])

    async def update_record(self, table_id, record_id, fields, **kwargs):
        self.completed.append((record_id, fields))
        return {"record_id": record_id}

    async def create_record(self, table_id, fields, *, user_id_type="open_id"):
        self.created.append(fields)
        return {"record_id": f"rec-new-{len(self.created)}"}


async def test_add_months_clamps_to_month_end() -> None:
    assert schedule.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert schedule.add_months(date(2026, 3, 15), 3) == date(2026, 6, 15)
    assert schedule.add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)


async def test_spawn_creates_next_task_with_copied_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cycle(
        monkeypatch,
        [{"仪器编号": "QC-1-2-010", "维护内容": "清洗单向阀", "周期（月）": 3}],
    )
    client = _Client()
    fields = {
        "生成日期": 1_700_000_000_000,
        # 回读形态：文本是富文本段、人员带多余键，复制时须转可写入形态
        "设备名称": [{"text": "高效液相色谱仪", "type": "text"}],
        "设备编号": [{"text": "QC-1-2-010", "type": "text"}],
        "通知人": [
            {"id": "ou_notify", "name": "张三", "avatar_url": "https://x"}
        ],
        "维护人": [{"id": "ou_owner"}],
        "复核人": [{"id": "ou_checker"}],
        "维保类型": "1",
        "维护内容": [{"text": "清洗单向阀", "type": "text"}],
        "是否完成": "否",
        "维护日期": int(_ms(date(2026, 7, 29))),
        "下次维保时间": int(_ms(date(2026, 7, 29))),
    }

    created = await schedule.spawn_next_for_fields(
        None, client, "tblM", "rec-src", fields
    )

    assert created == ("rec-new-1", schedule._to_ms(date(2026, 10, 29)))
    # 填了维护日期：原记录自动置完成
    assert client.completed == [("rec-src", {"是否完成": "是"})]
    assert len(client.created) == 1
    new_fields = client.created[0]
    # 复制设备信息与通知人；是否完成=否；下次维保时间=维护日期+3个月
    assert new_fields["设备名称"] == "高效液相色谱仪"
    assert new_fields["设备编号"] == "QC-1-2-010"
    assert new_fields["通知人"] == [{"id": "ou_notify"}]
    assert new_fields["维保类型"] == "1"
    assert new_fields["是否完成"] == "否"
    # 维护内容随链复制（链的粒度=编号+维护内容）
    assert new_fields["维护内容"] == "清洗单向阀"
    assert new_fields["下次维保时间"] == schedule._to_ms(date(2026, 10, 29))
    assert "生成日期" in new_fields
    # 不复制完成状态与维护日期（新任务未完成）；维护人/复核人留空待实际维护
    assert "维护日期" not in new_fields
    assert "维护人" not in new_fields
    assert "复核人" not in new_fields


async def test_spawn_skips_when_successor_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cycle(
        monkeypatch,
        [{"仪器编号": "QC-1-2-010", "维护内容": "清洗单向阀", "周期（月）": 3}],
    )
    client = _Client()
    expected_ms = schedule._to_ms(date(2026, 10, 29))
    client.search_results["QC-1-2-010"] = [
        {
            "record_id": "rec-existing",
            "fields": {
                "设备编号": "QC-1-2-010",
                "维护内容": [{"text": "清洗单向阀", "type": "text"}],
                "是否完成": "否",
                "下次维保时间": expected_ms,
            },
        }
    ]
    fields = {
        "设备编号": "QC-1-2-010",
        "维护内容": "清洗单向阀",
        "维护日期": int(_ms(date(2026, 7, 29))),
    }

    created = await schedule.spawn_next_for_fields(
        None, client, "tblM", "rec-src", fields
    )
    assert created is None
    # 无「是否完成」的源记录同样被自动置完成（填了维护日期即完成）
    assert client.completed == [("rec-src", {"是否完成": "是"})]
    assert client.created == []


async def test_spawn_requires_done_date_and_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cycle(
        monkeypatch,
        [{"仪器编号": "QC-1-2-010", "维护内容": "清洗单向阀", "周期（月）": 3}],
    )
    client = _Client()

    # 无维护日期：不生成
    assert (
        await schedule.spawn_next_for_fields(
            None, client, "tblM", "rec-nodate", {"设备编号": "QC-1-2-010"}
        )
        is None
    )
    # 周期表无此编号：不生成
    assert (
        await schedule.spawn_next_for_fields(
            None,
            client,
            "tblM",
            "rec-nocycle",
            {
                "设备编号": "QC-9-9-999",
                "维护日期": int(_ms(date(2026, 7, 29))),
            },
        )
        is None
    )
    assert client.created == []


async def test_maybe_spawn_batch_dedup_within_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同批同编号同维护内容（同链）多条已完成记录：只生成一条下一期任务。"""
    _install_cycle(
        monkeypatch,
        [
            {"仪器编号": "QC-1-2-010", "维护内容": "清洗单向阀", "周期（月）": 3},
            {"仪器编号": "QC-1-2-010", "维护内容": "更换光源灯", "周期（月）": 6},
        ],
    )
    client = _Client()
    records = [
        {
            "record_id": "rec-a",
            "fields": {
                "设备编号": "QC-1-2-010",
                "维护内容": "清洗单向阀",
                "维护日期": int(_ms(date(2026, 7, 29))),
            },
        },
        {
            "record_id": "rec-b",
            "fields": {
                "设备编号": "QC-1-2-010",
                "维护内容": "清洗单向阀",
                "维护日期": int(_ms(date(2026, 7, 28))),
            },
        },
        # 未完成（无维护日期）的行不触发
        {"record_id": "rec-c", "fields": {"设备编号": "QC-1-2-010"}},
    ]

    spawned = await schedule.maybe_spawn_next_maintenance(
        None, client, "tblM", records
    )
    assert spawned == 1
    assert len(client.created) == 1


async def test_maybe_spawn_different_chains_both_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同编号不同维护内容（不同链、不同周期）：各自生成，互不拦截。"""
    _install_cycle(
        monkeypatch,
        [
            {"仪器编号": "QC-1-2-010", "维护内容": "清洗单向阀", "周期（月）": 3},
            {"仪器编号": "QC-1-2-010", "维护内容": "更换光源灯", "周期（月）": 6},
        ],
    )
    client = _Client()
    records = [
        {
            "record_id": "rec-clean",
            "fields": {
                "设备编号": "QC-1-2-010",
                "维护内容": "清洗单向阀",
                "维护日期": int(_ms(date(2026, 7, 29))),
            },
        },
        {
            "record_id": "rec-lamp",
            "fields": {
                "设备编号": "QC-1-2-010",
                "维护内容": "更换光源灯",
                "维护日期": int(_ms(date(2026, 7, 29))),
            },
        },
    ]

    spawned = await schedule.maybe_spawn_next_maintenance(
        None, client, "tblM", records
    )
    assert spawned == 2
    next_dates = sorted(row["下次维保时间"] for row in client.created)
    assert next_dates == [
        schedule._to_ms(date(2026, 10, 29)),  # 清洗链：+3 个月
        schedule._to_ms(date(2027, 1, 29)),  # 换灯链：+6 个月
    ]


async def test_maybe_spawn_tolerates_single_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cycle(
        monkeypatch,
        [{"仪器编号": "QC-1-2-010", "维护内容": "清洗单向阀", "周期（月）": 3}],
    )

    class _FlakyClient(_Client):
        calls = 0

        async def create_record(self, table_id, fields, *, user_id_type="open_id"):
            _FlakyClient.calls += 1
            if _FlakyClient.calls == 1:
                raise RuntimeError("feishu down")
            return await super().create_record(table_id, fields)

    client = _FlakyClient()
    records = [
        {
            "record_id": "rec-a",
            "fields": {
                "设备编号": "QC-1-2-010",
                "维护内容": "清洗单向阀",
                "维护日期": int(_ms(date(2026, 7, 29))),
            },
        },
        {
            "record_id": "rec-b",
            "fields": {
                "设备编号": "QC-1-2-010",
                "维护内容": "清洗单向阀",
                "维护日期": int(_ms(date(2026, 7, 25))),
            },
        },
    ]

    spawned = await schedule.maybe_spawn_next_maintenance(
        None, client, "tblM", records
    )
    # 第一条失败被吞，第二条成功
    assert _FlakyClient.calls == 2
    assert spawned == 1


async def test_enrich_fills_display_only_for_empty_next_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cycle(
        monkeypatch,
        [
            {
                "仪器编号": "QC-1-2-010、QC-1-2-011",
                "维护内容": "清洗单向阀",
                "周期（月）": 3,
            }
        ],
    )
    items = [
        {
            "record_id": "m1",
            "设备编号": "QC-1-2-011",
            "维护内容": "清洗单向阀",
            "维护日期": _ms(date(2026, 1, 31)),
            "下次维保时间": None,
        },
        {
            "record_id": "m2",
            "设备编号": "QC-1-2-010",
            "维护内容": "清洗单向阀",
            "下次维保时间": "2026-12-31",  # 已有值不覆盖
        },
        {"record_id": "m3", "设备编号": "QC-9-9-999"},
    ]

    enriched = await schedule.enrich_maintenance_schedule(None, items)

    assert enriched[0]["下次维保时间"] == "2026-04-30"
    assert enriched[1]["下次维保时间"] == "2026-12-31"
    assert not enriched[2].get("下次维保时间")


async def test_enrich_no_cycles_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_cycle(monkeypatch, [])
    items: list[dict[str, Any]] = [{"record_id": "m1", "设备编号": "QC-1-2-010"}]
    enriched = await schedule.enrich_maintenance_schedule(None, items)
    assert enriched == items


async def test_next_maintenance_date_supports_fractional_months() -> None:
    """小数周期（0.5=每半月）按 30 天/月折算，不退化成同一天。"""
    assert schedule.next_maintenance_date(date(2026, 9, 16), 0.5) == date(
        2026, 10, 1
    )
    assert schedule.next_maintenance_date(date(2026, 9, 16), 3) == date(2026, 12, 16)
