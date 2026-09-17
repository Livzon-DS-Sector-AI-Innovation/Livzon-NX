"""实时兜底读取 _list_feishu_dynamic：列跟随飞书真实字段（镜像未就绪时使用）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.exceptions import AppException
from app.modules.quality.service import inspection_helpers as helpers

pytestmark = pytest.mark.anyio

_TZ_SH = timezone(timedelta(hours=8))


def _records() -> list[dict[str, Any]]:
    return [
        {
            "record_id": "rec1",
            "fields": {
                "设备名称": "高效液相色谱仪",
                "入厂日期": 1_768_838_400_000,
                "使用负责人": [{"id": "ou1", "name": "李慧"}],
                "附件": [
                    {
                        "name": "校准证书.pdf",
                        "file_token": "tok1",
                        "url": "https://feishu/example.pdf",
                    }
                ],
            },
            "last_modified_time": 1_700_000_000_000,
        },
        {
            "record_id": "rec2",
            "fields": {"设备名称": "TOC分析仪", "设备状态": "完好"},
            "last_modified_time": 1_700_000_000_100,
        },
        {
            "record_id": "rec_empty",
            "fields": {},
            "last_modified_time": 1_700_000_000_200,
        },
    ]


def _install(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(_db: Any, entity_code: str, *, direction: str):
        return SimpleNamespace(), SimpleNamespace(field_mappings={})

    async def fake_search(
        _db: Any,
        entity_code: str,
        *,
        filters: dict[str, Any] | None = None,
        field_names: list[str] | None = None,
        user_id_type: str = "open_id",
    ) -> list[dict[str, Any]]:
        return _records()

    monkeypatch.setattr(helpers, "_resolve_runtime_entity", fake_resolve)
    monkeypatch.setattr(helpers, "_search_entity_records", fake_search)


async def test_dynamic_list_maps_all_real_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)

    result = await helpers._list_feishu_dynamic(
        SimpleNamespace(), "qc_instr_equipment", page=1, page_size=20
    )

    # 列 = 记录真实字段（首次出现顺序），全空占位行被过滤
    assert result["fields"] == [
        "设备名称", "入厂日期", "使用负责人", "附件", "设备状态"
    ]
    assert result["total"] == 2
    first = result["items"][0]
    assert first["record_id"] == "rec2"
    # 毫秒时间戳按数字字符串下发（前端按 uiType=DateTime 渲染日期）
    by_id = {item["record_id"]: item for item in result["items"]}
    assert by_id["rec1"]["入厂日期"] == "1768838400000"
    assert by_id["rec1"]["使用负责人"][0]["name"] == "李慧"
    assert by_id["rec1"]["附件"][0]["file_token"] == "tok1"


async def test_dynamic_list_keyword_and_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)

    hit = await helpers._list_feishu_dynamic(
        SimpleNamespace(), "qc_instr_equipment", keyword="液相色谱"
    )
    assert [it["record_id"] for it in hit["items"]] == ["rec1"]

    filtered = await helpers._list_feishu_dynamic(
        SimpleNamespace(),
        "qc_instr_equipment",
        filters={"设备状态": "完好"},
    )
    assert [it["record_id"] for it in filtered["items"]] == ["rec2"]


async def test_dynamic_list_month_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """month 过滤：毫秒时间戳（数字字符串）落在当月才保留，与镜像路径同口径。"""
    _install(monkeypatch)

    # rec1 入厂日期 1768838400000 = 2026-01-20（东八区）
    hit = await helpers._list_feishu_dynamic(
        SimpleNamespace(),
        "qc_instr_equipment",
        month="2026-01",
        month_field="入厂日期",
    )
    assert [it["record_id"] for it in hit["items"]] == ["rec1"]

    none = await helpers._list_feishu_dynamic(
        SimpleNamespace(),
        "qc_instr_equipment",
        month="2026-02",
        month_field="入厂日期",
    )
    assert none["total"] == 0

    # 无该字段值的行不落入任何月份
    all_month = await helpers._list_feishu_dynamic(
        SimpleNamespace(),
        "qc_instr_equipment",
        month="2026-01",
        month_field="生成日期",
    )
    assert all_month["total"] == 0


def test_resolve_month_range_ms_bounds_and_errors() -> None:
    start, end = helpers.resolve_month_range_ms("2026-09")
    assert datetime.fromtimestamp(start / 1000, tz=_TZ_SH) == datetime(
        2026, 9, 1, tzinfo=_TZ_SH
    )
    assert datetime.fromtimestamp(end / 1000, tz=_TZ_SH) == datetime(
        2026, 10, 1, tzinfo=_TZ_SH
    )
    # 十二月滚动次年一月
    _, end_dec = helpers.resolve_month_range_ms("2026-12")
    assert datetime.fromtimestamp(end_dec / 1000, tz=_TZ_SH) == datetime(
        2027, 1, 1, tzinfo=_TZ_SH
    )
    for bad in ("2026/09", "abc", "2026-13", "202609"):
        with pytest.raises(AppException):
            helpers.resolve_month_range_ms(bad)
