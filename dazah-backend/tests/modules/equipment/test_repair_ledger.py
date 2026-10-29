"""报修台账（平台 → 飞书多维表格）同步单测。"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.modules.equipment.feishu.repair_ledger as rl
from app.modules.equipment.feishu.repair_ledger import (
    _fields_payload,
    schedule_ledger_sync,
)


def _wo(**kw):
    base = dict(
        work_order_no="WO-1",
        equipment_id="e1",
        status="执行中",
        priority="紧急",
        fault_description="泄漏",
        created_at=datetime(2026, 10, 27, 8, 0, tzinfo=UTC),
        reported_at=datetime(2026, 10, 27, 8, 0, tzinfo=UTC),
        started_at=datetime(2026, 10, 27, 8, 2, tzinfo=UTC),
        completed_at=datetime(2026, 10, 27, 8, 47, tzinfo=UTC),
        reporter_id="u1",
        assignee_id="u2",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _eq():
    return SimpleNamespace(
        name="离心泵A", equipment_no="LB-1", workshop_code="201-1"
    )


def test_fields_payload_full_lifecycle():
    fields = _fields_payload(_wo(), _eq(), "秦佳豪", "李维修")
    assert fields["工单号"] == "WO-1"
    assert fields["车间"] == "201-1"
    assert fields["状态"] == "执行中"
    assert fields["修复耗时分钟"] == 47
    assert fields["接单时间"] == int(
        datetime(2026, 10, 27, 8, 2, tzinfo=UTC).timestamp() * 1000
    )


def test_fields_payload_open_order_has_no_duration():
    fields = _fields_payload(_wo(completed_at=None), _eq(), "秦佳豪", "")
    assert fields["修复耗时分钟"] is None
    assert fields["维修人"] == ""


@pytest.mark.asyncio
async def test_schedule_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(rl.settings, "REPAIR_LEDGER_APP_TOKEN", "", raising=False)
    monkeypatch.setattr(
        rl, "_upsert_ledger", AsyncMock(side_effect=AssertionError("不应调用"))
    )
    schedule_ledger_sync("WO-1")
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_upsert_creates_when_not_found(monkeypatch):
    monkeypatch.setattr(
        rl.settings, "REPAIR_LEDGER_APP_TOKEN", "bapp", raising=False
    )
    monkeypatch.setattr(
        rl.settings, "REPAIR_LEDGER_TABLE_ID", "tbl1", raising=False
    )
    # 本用例只验证记录 upsert；车间汇总由独立链路覆盖
    monkeypatch.setattr(
        rl.settings, "REPAIR_LEDGER_SUMMARY_TABLE_ID", "", raising=False
    )
    monkeypatch.setattr(rl, "_ledger_token", AsyncMock(return_value="tk"))

    wo = _wo()
    eq = _eq()
    users = SimpleNamespace(all=lambda: [("u1", "秦佳豪"), ("u2", "李维修")])

    class _Q:
        def __init__(self, result):
            self._r = result

        def scalars(self):
            return SimpleNamespace(first=Mock(return_value=self._r))

    wo_result = _Q(wo)
    eq_result = _Q(eq)
    db = SimpleNamespace(execute=AsyncMock(side_effect=[wo_result, eq_result, users]))

    class _DbCtx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(rl, "async_session_factory", Mock(return_value=_DbCtx()))
    monkeypatch.setattr(rl.asyncio, "sleep", AsyncMock())

    post = AsyncMock(return_value=Mock(status_code=200,
                                       json=Mock(return_value={"code": 0})))
    get = AsyncMock(return_value=Mock(status_code=200, json=Mock(
        return_value={"code": 0, "data": {"items": []}})))
    client = Mock(post=post, get=get)
    put = AsyncMock(return_value=Mock(status_code=200,
                                      json=Mock(return_value={"code": 0})))
    client.put = put
    cls = Mock()
    cls.return_value.__aenter__ = AsyncMock(return_value=client)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(rl.httpx, "AsyncClient", cls)

    await rl._upsert_ledger("WO-1")

    # 搜不到已有记录 → 走创建
    assert client.post.call_count == 2  # search + create
    create_body = client.post.call_args_list[-1].kwargs["json"]["fields"]
    assert create_body["工单号"] == "WO-1"
    assert create_body["维修人"] == "李维修"


@pytest.mark.asyncio
async def test_summary_sync_targets_summary_table(monkeypatch):
    """车间汇总按「车间」字段在汇总表 upsert，不得误查主台账表。"""
    monkeypatch.setattr(
        rl.settings, "REPAIR_LEDGER_APP_TOKEN", "bapp", raising=False
    )
    monkeypatch.setattr(
        rl.settings, "REPAIR_LEDGER_SUMMARY_TABLE_ID", "tblSum", raising=False
    )

    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(all=lambda: [(_wo(), _eq())])
        )
    )

    class _DbCtx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(rl, "async_session_factory", Mock(return_value=_DbCtx()))

    search_resp = Mock(
        status_code=200,
        json=Mock(
            return_value={
                "code": 0,
                "data": {
                    "items": [{"record_id": "rec9", "fields": {"车间": "201-1"}}]
                },
            }
        ),
    )
    client = Mock(
        post=AsyncMock(return_value=search_resp),
        put=AsyncMock(
            return_value=Mock(status_code=200, json=Mock(return_value={"code": 0}))
        ),
    )

    await rl._refresh_workshop_summary(client, "tk", "201-1")

    # 搜索走汇总表且按「车间」字段过滤
    search_call = client.post.await_args_list[0]
    assert "tblSum" in search_call.args[0]
    assert search_call.kwargs["json"]["field_names"] == ["车间"]
    # 命中已有行 → 更新汇总表该记录
    put_url = client.put.await_args_list[0].args[0]
    assert "tblSum" in put_url and put_url.endswith("/rec9")
    put_fields = client.put.await_args_list[0].kwargs["json"]["fields"]
    assert put_fields["车间"] == "201-1"
    assert put_fields["工单总数"] == 1
    assert put_fields["平均修复分钟"] == 47
