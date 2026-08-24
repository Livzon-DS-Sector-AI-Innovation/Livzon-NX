"""生产飞书同步服务 + FA 仪表盘辅助 + 自动同步服务测试。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.production import auto_sync_service as auto
from app.modules.production import fa_dashboard_api as fa
from app.modules.production import production_feishu_service as pfs


def make_config(**over):
    cfg = {
        "app_id": "app-id",
        "encrypted_app_secret": "enc",
        "bitable_app_token": "tok",
        "table_id": "tbl1",
        "product_name": "苯丙氨酸",
        "id": "cfg-1",
    }
    cfg.update(over)
    return SimpleNamespace(**cfg)


def make_client(items, has_more=False, page_token=None, fields=None):
    c = MagicMock()
    c.list_records = AsyncMock(
        return_value={"items": items, "has_more": has_more, "page_token": page_token}
    )
    c.list_fields = AsyncMock(return_value=fields or [])
    return c


def make_session(scalar_result=None, scalars=None):
    s = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_result
    if scalars is not None:
        result.scalars.return_value.all.return_value = scalars
    s.execute = AsyncMock(return_value=result)
    s.add = MagicMock()
    s.flush = AsyncMock()
    s.commit = AsyncMock()
    return s


# ═══════════ production_feishu_service ═══════════


def test_feishu_extract_text_and_number():
    assert pfs._extract_text(None) is None
    assert pfs._extract_text(" 值 ") == "值"
    assert pfs._extract_text({"name": "甲"}) == "甲"
    assert pfs._extract_text([{"text": "乙"}]) == "乙"
    assert pfs._extract_text(["丙"]) == "丙"
    assert pfs._extract_text([]) is None
    assert pfs._extract_text(5) is None
    assert pfs._extract_number("12.5") == 12.5
    assert pfs._extract_number("bad") is None
    assert pfs._extract_number(None) is None


def test_sync_config_creates_and_updates():
    import asyncio

    existing = SimpleNamespace(batch_no="F1", fermenter="T1", entry_date=None)
    client = make_client(
        [
            {
                "fields": {
                    "批号": "F1",
                    "发酵罐": "T1",
                    "产品名称": "苯丙氨酸",
                    "进罐日期": "2026-03-01",
                    "放罐日期": "2026-03-10",
                    "罐产": "1200",
                    "状态": "已完成",
                }
            }
        ]
    )
    session = make_session(scalar_result=existing)
    with (
        patch(
            "app.modules.production.production_feishu_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.production_feishu_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(pfs.sync_config(make_config(), session))
    assert result["created"] == 0
    assert result["updated"] == 1
    assert existing.status == "completed"
    assert existing.tank_yield == 1200.0
    session.flush.assert_awaited()


def test_sync_config_skips_without_required_fields():
    import asyncio

    client = make_client([{"fields": {"发酵罐": "T1"}}])  # 无批号
    session = make_session(scalar_result=None)
    with (
        patch(
            "app.modules.production.production_feishu_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.production_feishu_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(pfs.sync_config(make_config(), session))
    assert result["created"] == 0
    assert result["updated"] == 0


def test_sync_config_pagination_and_defaults():
    import asyncio

    client = MagicMock()
    client.list_records = AsyncMock(
        side_effect=[
            {
                "items": [{"fields": {"批号": "F1", "发酵罐": "T1", "状态": "发酵中"}}],
                "has_more": True,
                "page_token": "p1",
            },
            {
                "items": [{"fields": {"批号": "F2", "发酵罐": "T2"}}],
                "has_more": False,
                "page_token": None,
            },
        ]
    )
    session = make_session(scalar_result=None)
    with (
        patch(
            "app.modules.production.production_feishu_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.production_feishu_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(pfs.sync_config(make_config(), session))
    assert result["created"] == 2
    added = session.add.call_args_list
    assert added[0].args[0].entry_date == date.today()  # 缺日期 → 今天
    assert added[0].args[0].status == "in_progress"
    assert client.list_records.await_args_list[1].kwargs["page_token"] == "p1"


def test_sync_all_active_success_and_error():
    import asyncio

    cfg1 = SimpleNamespace(product_name="苯丙氨酸")
    cfg2 = SimpleNamespace(product_name="丙氨酸")
    session = make_session(scalars=[cfg1, cfg2])

    async def _sync(config, session):
        if config.product_name == "丙氨酸":
            raise RuntimeError("sync boom")
        return {"created": 1, "updated": 0, "product": config.product_name}

    with patch.object(pfs, "sync_config", side_effect=_sync):
        summaries = asyncio.run(pfs.sync_all_active(session))
    assert summaries[0]["created"] == 1
    assert summaries[1]["error"] == "sync boom"
    session.commit.assert_awaited()


# ═══════════ fa_dashboard_api 辅助 ═══════════


def test_to_yield_variants():
    assert fa._to_yield(None) == 0.0
    assert fa._to_yield(0.85) == 85.0  # 小数转百分比
    assert fa._to_yield(88.5) == 88.5
    assert fa._to_yield("92%") == 92.0
    assert fa._to_yield("1,234.5") == 1234.5
    assert fa._to_yield("bad") == 0.0
    assert fa._to_yield(1.5) == 150.0  # 1.5 → 150%


def test_to_float_variants():
    assert fa._to_float(None) == 0.0
    assert fa._to_float(12.5) == 12.5
    assert fa._to_float("98%") == 98.0
    assert fa._to_float("bad") == 0.0


def test_get_suggestion():
    sug = fa._get_suggestion("fermentation_yield", "low")
    if sug is not None:
        assert set(sug) == {"happened", "remedy", "impact", "prevent"}
    assert fa._get_suggestion("unknown_key", "low") is None


# ═══════════ auto_sync_service ═══════════


def test_safe_col_name():
    assert auto._safe_col_name("batch_no") == "batch_no"
    assert auto._safe_col_name(" 车间 ") == "col_" + "车间".encode().hex()[:12]
    assert auto._safe_col_name("") == "col_"


def test_extract_value_variants():
    from datetime import datetime

    assert auto._extract_value(None, 1) is None
    assert (
        auto._extract_value(1700000000000, 5)
        == datetime.fromtimestamp(1700000000).date()
    )
    assert auto._extract_value(-1, 5) is None
    assert auto._extract_value({"type": 2, "value": [4.5]}, 2) == 4.5
    assert auto._extract_value(7.5, 3) == 7.5
    assert auto._extract_value([{"text": "3.2"}], 20) == 3.2
    assert auto._extract_value(" 文本 ", 1) == "文本"
    assert auto._extract_value([{"text": " 内容 "}], 1) == "内容"
    assert auto._extract_value([123], 1) == "123"
    assert auto._extract_value(False, 1) is None


def test_discover_and_save_mapping():
    import asyncio

    client = make_client(
        [],
        fields=[
            {"field_id": "f1", "field_name": "批号", "type": 1},
            {"field_id": "f2", "field_name": "产量", "type": 2},
            {"field_id": "f1", "field_name": "重复", "type": 1},  # 重复 f1 → f1_2
        ],
    )
    config = make_config(id="cfg-1234-abcd")
    session = make_session()
    with (
        patch(
            "app.modules.production.auto_sync_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.auto_sync_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(auto.discover_and_save_mapping(config, session))
    assert result["fields"] == 3
    assert config.sync_table_name == "feishu_sync_cfg_1234"
    session.commit.assert_awaited()


def test_auto_sync_config_upsert():
    import asyncio

    config = make_config(id="cfg-1234-abcd")
    config.field_mapping = {
        "f1": {"name": "批号", "type": 1, "db_column": "f_f1"},
        "批号": {"name": "批号", "type": 1, "db_column": "f_f1"},
    }
    config.sync_table_name = "feishu_sync_cfg_1234"
    client = MagicMock()
    client.list_records = AsyncMock(
        return_value={
            "items": [
                {"record_id": "r1", "fields": {"批号": "B1"}},
                {"record_id": "r2", "fields": {"批号": "B2"}},
                {
                    "record_id": "r3",
                    "fields": {"批号": "B3", "未知字段": "x"},
                },  # 未映射 → 忽略
            ],
            "has_more": False,
        }
    )
    s = AsyncMock()
    existing = MagicMock()
    existing.scalar_one_or_none.return_value = None
    s.execute = AsyncMock(return_value=existing)
    s.flush = AsyncMock()
    with (
        patch(
            "app.modules.production.auto_sync_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.auto_sync_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result = asyncio.run(auto.auto_sync_config(config, s))
    assert result["created"] == 3
    assert result["updated"] == 0
    assert result["table"] == "feishu_sync_cfg_1234"
    # 第二次走 UPDATE 分支
    s2 = AsyncMock()
    existing2 = MagicMock()
    existing2.scalar_one_or_none.return_value = "row-id"
    s2.execute = AsyncMock(return_value=existing2)
    s2.flush = AsyncMock()
    with (
        patch(
            "app.modules.production.auto_sync_service.decrypt_secret",
            return_value="secret",
        ),
        patch(
            "app.modules.production.auto_sync_service.ProductionFeishuClient",
            return_value=client,
        ),
    ):
        result2 = asyncio.run(auto.auto_sync_config(config, s2))
    assert result2["created"] == 0
    assert result2["updated"] == 3


def test_auto_sync_config_missing_mapping():
    import asyncio

    config = make_config()
    config.field_mapping = {"f1": {"name": "a", "type": 1, "db_column": "f_f1"}}
    config.sync_table_name = None
    s = make_session()
    result = asyncio.run(auto.auto_sync_config(config, s))
    assert result["error"] == "field_mapping or sync_table_name missing"
