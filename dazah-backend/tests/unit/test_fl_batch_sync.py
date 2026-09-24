"""FL 氟苯尼考批次同步：字段解析与按月分表同步流程单测。

飞书客户端全程 mock（list_tables / list_records），不访问真实外部服务。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.production import fl_batch_sync as fl_sync
from app.modules.production.fl_models import FlBatch

# 2026-09-19 12:00 北京时间对应的毫秒时间戳
MS_2026_09_19 = 1_789_790_400_000


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        app_id="app-id",
        encrypted_app_secret="encrypted-secret",
        bitable_app_token="token",
        table_id="",
        sync_target="fl_batch",
        product_name="2%氟苯尼考预混剂",
    )


def _session(existing: FlBatch | None = None) -> AsyncMock:
    """mock session：execute 返回同步的 scalar_one_or_none 结果。"""
    session = AsyncMock()
    session.add = MagicMock()  # 真实 session.add 为同步方法
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing)
    session.execute = AsyncMock(return_value=result)
    return session


def _fields(batch_no: str | None = "FL-2609001", **extra: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "生产批号": batch_no,
        "指令日期": MS_2026_09_19,
        "领料日期": "2026.09.20",
        "投料日期": MS_2026_09_19 + 86_400_000,
        "投料时间": "8:00~10:00",
        "混合日期｜生产日期": "2026-09-20",
        "混合时间": "10:00~12:00",
        "规格": [{"text": "10kg/袋"}, {"text": "2袋/箱"}],
        "包装重量": "1980±10",
        "包装日期": "2026/09/20",
        "包装时间": "14:00~16:00",
        "请检日期": MS_2026_09_19 + 86_400_000,
        "入库日期": "2026-09-20",
    }
    fields.update(extra)
    if batch_no is None:
        fields.pop("生产批号")
    return fields


# ── 字段解析 ──


def test_parse_batch_no_valid() -> None:
    assert fl_sync.parse_batch_no("FL-2609001") == (2026, 9, 1)
    assert fl_sync.parse_batch_no("FL2609013") == (2026, 9, 13)
    assert fl_sync.parse_batch_no("FL-2701001") == (2027, 1, 1)


def test_parse_batch_no_invalid() -> None:
    assert fl_sync.parse_batch_no("FA26234") is None
    assert fl_sync.parse_batch_no("FL-2613001") is None  # 月份越界
    assert fl_sync.parse_batch_no("") is None


def test_extract_date_variants() -> None:
    extract = fl_sync._extract_date
    assert extract(MS_2026_09_19) == date(2026, 9, 19)
    assert extract("2026-09-20") == date(2026, 9, 20)
    assert extract("2026.09.21 08:00") == date(2026, 9, 21)
    assert extract("2026/09/22") == date(2026, 9, 22)
    assert extract({"text": "2026-09-23"}) == date(2026, 9, 23)
    assert extract(None) is None
    assert extract("待定") is None


def test_extract_weight_kg_variants() -> None:
    extract = fl_sync._extract_weight_kg
    assert extract(1980) == 1980.0
    assert extract("1980±10") == 1980.0
    assert extract("1,980.5") == 1980.5
    assert extract("±10") is None
    assert extract(None) is None


def test_map_record_field_name_compatibility() -> None:
    """请检/入库列名的月表差异按候选兼容；多选规格合并展示。"""
    mapped = fl_sync.map_record(
        {
            "成品清检日期": "2026-09-21",
            "成品入库": "2026-09-22",
            "规格": ["10kg/袋", "2袋/箱"],
        }
    )
    assert mapped["inspection_date"] == date(2026, 9, 21)
    assert mapped["inbound_date"] == date(2026, 9, 22)
    assert mapped["spec"] == "10kg/袋、2袋/箱"


# ── 同步流程 ──


@pytest.mark.anyio
async def test_sync_discovers_month_tables_and_creates() -> None:
    session = _session(existing=None)
    with patch.object(fl_sync, "decrypt_secret", return_value="secret"):
        with patch.object(
            fl_sync.ProductionFeishuClient,
            "list_tables",
            new=AsyncMock(
                return_value=[
                    {"table_id": "t9", "name": "9月排产"},
                    {"table_id": "tx", "name": "说明表"},
                ]
            ),
        ):
            with patch.object(
                fl_sync.ProductionFeishuClient,
                "list_records",
                new=AsyncMock(
                    return_value={"items": [{"fields": _fields()}], "has_more": False}
                ),
            ):
                summary = await fl_sync.sync_fl_batches(_config(), session)

    assert summary["created"] == 1
    assert summary["updated"] == 0
    assert summary["tables"] == ["9月排产"]
    assert summary["skipped_tables"] == ["说明表"]
    added = session.add.call_args[0][0]
    assert isinstance(added, FlBatch)
    assert added.batch_no == "FL-2609001"
    assert added.data_month == "2026-09"
    assert added.source_table == "9月排产"
    assert added.order_date == date(2026, 9, 19)
    assert added.pick_date == date(2026, 9, 20)
    assert added.charge_date == date(2026, 9, 20)
    assert added.pack_weight_kg == 1980.0
    assert added.spec == "10kg/袋、2袋/箱"


@pytest.mark.anyio
async def test_sync_updates_existing_and_keeps_blank_history() -> None:
    existing = FlBatch(
        batch_no="FL-2609001", pack_weight_kg=1900.0, spec="旧规格"
    )
    session = _session(existing=existing)
    with patch.object(fl_sync, "decrypt_secret", return_value="secret"):
        with patch.object(
            fl_sync.ProductionFeishuClient,
            "list_tables",
            new=AsyncMock(return_value=[{"table_id": "t9", "name": "9月排产"}]),
        ):
            with patch.object(
                fl_sync.ProductionFeishuClient,
                "list_records",
                new=AsyncMock(
                    return_value={
                        "items": [
                            # 空行（无批号）跳过
                            {"fields": _fields(batch_no=None)},
                            # 既有批次：飞书侧非空字段覆盖，包装重量缺失保留旧值
                            {"fields": _fields(包装重量=None)},
                        ],
                        "has_more": False,
                    }
                ),
            ):
                summary = await fl_sync.sync_fl_batches(_config(), session)

    assert summary["created"] == 0
    assert summary["updated"] == 1
    assert summary["skipped_empty"] == 1
    assert existing.pack_weight_kg == 1900.0  # 空字段不回写
    assert existing.spec == "10kg/袋、2袋/箱"
    assert session.add.call_count == 0


@pytest.mark.anyio
async def test_sync_flags_month_mismatch_and_invalid_batch_no() -> None:
    session = _session(existing=None)
    with patch.object(fl_sync, "decrypt_secret", return_value="secret"):
        with patch.object(
            fl_sync.ProductionFeishuClient,
            "list_tables",
            new=AsyncMock(return_value=[{"table_id": "t9", "name": "9月排产"}]),
        ):
            with patch.object(
                fl_sync.ProductionFeishuClient,
                "list_records",
                new=AsyncMock(
                    return_value={
                        "items": [
                            {"fields": _fields(batch_no="FL-2608001")},
                            {"fields": _fields(batch_no="补料批")},
                        ],
                        "has_more": False,
                    }
                ),
            ):
                summary = await fl_sync.sync_fl_batches(_config(), session)

    assert summary["created"] == 0
    assert summary["anomaly_count"] == 2
    reasons = {item["batch_no"] for item in summary["anomalies"]}
    assert reasons == {"FL-2608001", "补料批"}
    assert session.add.call_count == 0


@pytest.mark.anyio
async def test_sync_paginates_records() -> None:
    session = _session(existing=None)
    pages = [
        {"items": [{"fields": _fields()}], "has_more": True, "page_token": "p2"},
        {
            "items": [{"fields": _fields(batch_no="FL-2609002")}],
            "has_more": False,
        },
    ]
    with patch.object(fl_sync, "decrypt_secret", return_value="secret"):
        with patch.object(
            fl_sync.ProductionFeishuClient,
            "list_tables",
            new=AsyncMock(return_value=[{"table_id": "t9", "name": "9月排产"}]),
        ):
            with patch.object(
                fl_sync.ProductionFeishuClient,
                "list_records",
                new=AsyncMock(side_effect=pages),
            ):
                summary = await fl_sync.sync_fl_batches(_config(), session)

    assert summary["created"] == 2
