"""维保保存与同步交错时的重复生成、空内容和错周期回归。"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import date
from typing import Any

import pytest

from app.modules.quality.service import maintenance_schedule as schedule


class MemoryBitable:
    """保留真实写入结果，查询在网络让出前取得快照。"""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = deepcopy(records)
        self.created: list[dict[str, Any]] = []

    async def search_records(
        self, table_id: str, *, filter_str: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        code = filter_str.split('"')[1]
        result = deepcopy([
            row for row in self.records
            if schedule._record_code(row["fields"]) == code
        ])
        await asyncio.sleep(0)
        return result

    async def update_record(
        self, table_id: str, record_id: str, fields: dict[str, Any], **kwargs: Any
    ) -> dict[str, str]:
        for row in self.records:
            if row["record_id"] == record_id:
                row["fields"].update(deepcopy(fields))
        return {"record_id": record_id}

    async def create_record(
        self, table_id: str, fields: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        row = {
            "record_id": f"next-{len(self.created) + 1}",
            "fields": deepcopy(fields),
        }
        self.records.append(row)
        self.created.append(row)
        return deepcopy(row)


def source(code: str, content: str) -> dict[str, Any]:
    return {
        "record_id": f"source-{code}",
        "fields": {
            "设备编号": code,
            "设备名称": "高效液相色谱仪",
            "维护内容": content,
            "维护日期": schedule._to_ms(date(2026, 9, 16)),
            "下次维保时间": schedule._to_ms(date(2026, 10, 7)),
            "是否完成": "是",
            "维护人": [{"id": "ou_test_owner"}],
            "复核人": [{"id": "ou_test_reviewer"}],
            "通知人": [{"id": "ou_test_notify"}],
        },
    }


def install_plans(
    monkeypatch: pytest.MonkeyPatch, plans: list[dict[str, Any]]
) -> None:
    async def load_page(db: Any, entity_code: str) -> dict[str, Any]:
        assert entity_code == "qc_instr_plans"
        return {"items": plans}

    monkeypatch.setattr(schedule, "_load_page", load_page)
    monkeypatch.setattr(schedule, "_today", lambda: date(2026, 9, 16))


async def test_screenshot_sources_generate_only_two_correct_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_plans(monkeypatch, [
        {"仪器编号": "QC-1-2-010", "维护内容": "清洗溶剂滤头", "周期（月）": 3},
        {"仪器编号": "QC-1-2-009", "维护内容": "清洗单向阀", "周期（月）": 0.5},
        {
            "仪器编号": "QC-1-2-010、QC-1-2-009",
            "维护内容": "年度保养",
            "周期（月）": 12,
        },
    ])
    records = [source("QC-1-2-010", "清洗溶剂滤头"), source("QC-1-2-009", "清洗单向阀")]
    client = MemoryBitable(records)
    for row in records:
        await schedule.spawn_next_for_fields(
            None, client, "table-test", row["record_id"], row["fields"]
        )
    assert await schedule.maybe_spawn_next_maintenance(
        None, client, "table-test", deepcopy(client.records)
    ) == 0
    assert len(client.created) == 2
    for row, content, expected in zip(client.created, ["清洗溶剂滤头", "清洗单向阀"],
                                      [
                                          date(2026, 12, 16),
                                          date(2026, 10, 1),
                                      ],
                                      strict=True,
                                  ):
        fields = row["fields"]
        assert fields["维护内容"] == content
        assert fields["下次维保时间"] == schedule._to_ms(expected)
        assert fields["是否完成"] == "否"
        assert fields["通知人"] == [{"id": "ou_test_notify"}]
        assert not fields.get("维护人")
        assert not fields.get("复核人")
        assert not fields.get("维护日期")


async def test_save_overlapping_mirror_sync_creates_one_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_plans(monkeypatch, [
        {"仪器编号": "QC-1-2-010", "维护内容": "清洗溶剂滤头", "周期（月）": 3},
    ])
    row = source("QC-1-2-010", "清洗溶剂滤头")
    client = MemoryBitable([row])
    await asyncio.gather(
        schedule.spawn_next_for_fields(
            None, client, "table-test", row["record_id"], deepcopy(row["fields"])
        ),
        schedule.maybe_spawn_next_maintenance(
            None, client, "table-test", [deepcopy(row)]
        ),
    )
    assert len(client.created) == 1


async def test_unique_plan_supplies_missing_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_plans(monkeypatch, [
        {"仪器编号": "QC-1-2-010", "维护内容": "清洗溶剂滤头", "周期（月）": 3},
    ])
    row = source("QC-1-2-010", "")
    client = MemoryBitable([row])
    await schedule.spawn_next_for_fields(
        None, client, "table-test", row["record_id"], row["fields"]
    )
    assert len(client.created) == 1
    assert client.created[0]["fields"].get("维护内容") == "清洗溶剂滤头"
    assert await schedule.maybe_spawn_next_maintenance(
        None, client, "table-test", deepcopy(client.records)
    ) == 0
    assert len(client.created) == 1


@pytest.mark.parametrize("plans", [
    [{"维护内容": "", "周期（月）": 12}],
    [{"维护内容": "清洗溶剂滤头", "周期（月）": 3},
     {"维护内容": "清洗单向阀", "周期（月）": 3}],
])
async def test_missing_content_does_not_create_blank_or_ambiguous_task(
    monkeypatch: pytest.MonkeyPatch, plans: list[dict[str, Any]]
) -> None:
    install_plans(monkeypatch, [{"仪器编号": "QC-1-2-010", **p} for p in plans])
    row = source("QC-1-2-010", "")
    client = MemoryBitable([row])
    await schedule.spawn_next_for_fields(
        None, client, "table-test", row["record_id"], row["fields"]
    )
    assert client.created == []


async def test_conflicting_cycles_do_not_choose_arbitrary_next_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_plans(monkeypatch, [
        {"仪器编号": "QC-1-2-010", "维护内容": "清洗溶剂滤头", "周期（月）": months}
        for months in (12, 3)
    ])
    row = source("QC-1-2-010", "清洗溶剂滤头")
    client = MemoryBitable([row])
    await schedule.spawn_next_for_fields(
        None, client, "table-test", row["record_id"], row["fields"]
    )
    assert client.created == []
