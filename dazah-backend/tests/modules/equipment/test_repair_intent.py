"""报修 LLM 意图解析层单测：抽取、归一化、失败兜底与建单集成。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.modules.equipment.service.work_order_feishu as wof
from app.core.llm import LLMError
from app.modules.equipment.feishu import repair_intent
from app.modules.equipment.feishu.repair_intent import parse_repair_intent


@pytest.mark.asyncio
async def test_parse_extracts_and_normalizes_fields(monkeypatch):
    monkeypatch.setattr(
        repair_intent.llm_client,
        "chat_json",
        AsyncMock(
            return_value={
                "workshop": "201一车间",
                "equipment": "下卸料离心机 1",
                "fault": "泄漏",
                "urgency": "紧急",
            }
        ),
    )
    intent = await parse_repair_intent("报修 201车间那个离心机1又漏了赶紧来")
    assert intent == {
        "workshop": "201一车间",
        "equipment": "下卸料离心机 1",
        "fault": "泄漏",
        "urgency": "紧急",
    }


@pytest.mark.asyncio
async def test_parse_falls_back_on_llm_error(monkeypatch):
    monkeypatch.setattr(
        repair_intent.llm_client,
        "chat_json",
        AsyncMock(side_effect=LLMError("bad output", "raw")),
    )
    assert await parse_repair_intent("报修 离心泵 漏了") is None


@pytest.mark.asyncio
async def test_parse_falls_back_on_any_failure(monkeypatch):
    monkeypatch.setattr(
        repair_intent.llm_client,
        "chat_json",
        AsyncMock(side_effect=TimeoutError()),
    )
    assert await parse_repair_intent("报修 离心泵 漏了") is None


@pytest.mark.asyncio
async def test_parse_empty_body_returns_none(monkeypatch):
    called = AsyncMock()
    monkeypatch.setattr(repair_intent.llm_client, "chat_json", called)
    assert await parse_repair_intent("报修") is None
    called.assert_not_awaited()


@pytest.mark.asyncio
async def test_parse_all_empty_fields_returns_none(monkeypatch):
    monkeypatch.setattr(
        repair_intent.llm_client,
        "chat_json",
        AsyncMock(
            return_value={
                "workshop": "",
                "equipment": "",
                "fault": "",
                "urgency": "普通",
            }
        ),
    )
    assert await parse_repair_intent("报修 你好") is None


def _bot_env(monkeypatch, db, intent):
    eq = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        name="离心泵A",
        equipment_no="LB-1",
        status="在用",
        workshop_code="201-1",
    )
    from tests.modules.equipment.test_work_order_feishu_bot import _factory

    monkeypatch.setattr(wof, "async_session_factory", _factory(db), raising=False)
    user = SimpleNamespace(id="u1", name="秦佳豪", username="q")
    monkeypatch.setattr(
        wof, "_find_user_by_feishu", AsyncMock(return_value=user)
    )
    workshop = SimpleNamespace(code="201-1", name="201一车间")
    monkeypatch.setattr(
        wof, "_match_workshops", AsyncMock(return_value=[workshop])
    )
    monkeypatch.setattr(
        wof, "_match_equipments", AsyncMock(return_value=[eq])
    )
    from tests.modules.equipment.test_work_order_feishu_bot import _Result

    lead_ws = SimpleNamespace(code="201-1", name="201一车间")
    db.execute = AsyncMock(side_effect=[_Result([lead_ws]), _Result([])])
    monkeypatch.setattr(
        wof, "_sample_ledger_names", AsyncMock(return_value=[]), raising=False
    )
    wo = SimpleNamespace(
        id="w1", work_order_no="WO-9", status="待处理", priority="高",
        equipment=eq,
    )
    monkeypatch.setattr(
        wof, "create_work_order", AsyncMock(return_value=wo), raising=False
    )
    monkeypatch.setattr(wof, "dispatch_repair_card", AsyncMock(), raising=False)
    monkeypatch.setattr(wof, "send_user_card", AsyncMock())
    # create_repair_by_text 在函数内 import，须打到源模块
    import app.modules.equipment.feishu.repair_intent as ri

    monkeypatch.setattr(
        ri, "parse_repair_intent", AsyncMock(return_value=intent), raising=False
    )
    return wo


@pytest.mark.asyncio
async def test_create_repair_uses_llm_enrichment_for_matching(monkeypatch):
    from tests.modules.equipment.test_work_order_feishu_bot import _db_mock

    db = _db_mock()
    intent = {
        "workshop": "201一车间",
        "equipment": "离心泵A",
        "fault": "泄漏",
        "urgency": "紧急",
    }
    _bot_env(monkeypatch, db, intent)

    await wof.create_repair_by_text(
        user_id="",
        open_id="ou_1",
        # 口语化消息：无「紧急」关键词、车间写法不规范，依赖 LLM 归一化
        text="报修 201车间那台离心泵又漏了快来人",
    )

    # 匹配文本包含 LLM 归一化后的车间与设备全名
    called_body = wof._match_workshops.await_args.args[1]  # type: ignore[attr-defined]
    assert "201一车间" in called_body and "离心泵A" in called_body
    matched_body = wof._match_equipments.await_args.kwargs["body"]  # type: ignore[attr-defined]
    assert "离心泵A" in matched_body
    # LLM 判定紧急 → 优先级紧急（原文没有紧急关键词）
    order = wof.create_work_order.await_args.args[1]  # type: ignore[attr-defined]
    assert order.priority == "紧急"


@pytest.mark.asyncio
async def test_create_repair_rules_still_work_without_llm(monkeypatch):
    from tests.modules.equipment.test_work_order_feishu_bot import _db_mock

    db = _db_mock()
    _bot_env(monkeypatch, db, intent=None)

    await wof.create_repair_by_text(
        user_id="", open_id="ou_1", text="报修 201一车间 离心泵A 漏了"
    )

    wof.create_work_order.assert_awaited_once()  # type: ignore[attr-defined]
    order = wof.create_work_order.await_args.args[1]  # type: ignore[attr-defined]
    assert order.priority == "高"
