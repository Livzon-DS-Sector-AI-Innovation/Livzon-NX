"""seed_cultures 飞书同步 coverage。

覆盖 seed_culture_sync 的字段解析 helper（日期/文本/数字）完整分支、
list_records 数据处理路径（数字时间戳、文本 ISO、dict/list 人员字段、
  缺 batch_no 跳过），以及 created 汇总断言。全部 mock，无真实网络/DB。
"""
from __future__ import annotations

import importlib
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        app_id="app-id",
        encrypted_app_secret="enc-secret",
        bitable_app_token="bitable",
        table_id="tbl-1",
        product_name="种子实验室",
    )


async def test_seed_culture_parsing_variants():
    mod = importlib.import_module("app.modules.production.seed_culture_sync")
    items = [
        # 人员字段 {"name": "张三"} + 数字时间戳日期 + 数值文本
        {
            "record_id": "r1",
            "fields": {
                "摇瓶批号": {"name": "B001"},
                "配置日期": 1735689600000,
                "调前PH": "7.2",
                "还原糖": {"name": "0.5"},
                "备注": {"text": None},
            },
        },
        # list[str] batch_no
        {"record_id": "r2", "fields": {"摇瓶批号": ["B002"], "配置日期": "2026-03-05"}},
        # list[dict] batch_no + 无效数值 → ValueError 分支
        {
            "record_id": "r3",
            "fields": {"摇瓶批号": [{"name": "B003"}], "调前PH": "not-a-number"},
        },
        # 纯文本 batch_no
        {"record_id": "r4", "fields": {"摇瓶批号": " B004 "}},
        # 缺少 batch_no → 跳过
        {"record_id": "r5", "fields": {}},
        # batch_no 明确为 None → 跳过
        {"record_id": "r6", "fields": {"摇瓶批号": None}},
        # 数值 batch_no（int）也视为非 text 分支
        {"record_id": "r7", "fields": {"摇瓶批号": 123}},
    ]
    session = AsyncMock()
    with patch.object(mod, "decrypt_secret", return_value="secret"):
        with patch.object(
            mod.ProductionFeishuClient,
            "list_records",
            new=AsyncMock(return_value={"items": items}),
        ):
            out = await mod.sync_seed_culture_to_table(_config(), session)
    assert out["created"] == 5  # r1~r4 + r7 有 batch_no；r5/r6 跳过
    session.execute.assert_awaited()


def test_seed_culture_pure_helpers():
    mod = importlib.import_module("app.modules.production.seed_culture_sync")
    assert mod._parse_date(None) is None
    assert mod._parse_date("2026-03-05") == date(2026, 3, 5)
    assert mod._parse_date("bad-date") is None
    assert mod._parse_date(1700000000000) == datetime.fromtimestamp(
        1700000000000 / 1000
    ).date()
    # 已是 date 对象 → 原样返回（_parse_date 兜底分支）
    assert mod._parse_date(date(2026, 3, 1)) == date(2026, 3, 1)
    assert mod._extract_text(None) is None
    assert mod._extract_text("  ab  ") == "ab"
    assert mod._extract_text({"name": "张三"}) == "张三"
    assert mod._extract_text({"text": "x"}) == "x"
    assert mod._extract_text(["str"]) == "str"
    assert mod._extract_text([{"name": "李四"}]) == "李四"
    assert mod._extract_text(123) == "123"
    assert mod._extract_number(7) == 7.0
    assert mod._extract_number(7.5) == 7.5
    assert mod._extract_number("2.5") == 2.5
    assert mod._extract_number("oops") is None
    assert mod._extract_number(None) is None
