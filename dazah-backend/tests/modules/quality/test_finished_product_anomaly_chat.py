"""成品异常 AI 聊天服务单元测试（mock LLM 与数据工具，不触库不连网）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.modules.quality.service.finished_product_anomaly_chat as chat_svc
from app.core.llm import LLMConfigError


def _item(record_id: str, desc: str, product: str) -> dict:
    return {
        "record_id": record_id,
        "不合格项目描述": desc,
        "数据来源": "IC",
        "涉及产品": [{"name": f"MC（{product}）"}],
    }


def _config() -> SimpleNamespace:
    return SimpleNamespace(model_name="q-test", enable_thinking=False)


class _FakeDB:
    pass


async def _fake_stream(self, *args, **kwargs):
    yield {"type": "content", "text": "最终回答：霉酚酸杂质异常最多。"}
    yield {"type": "done"}


def _collect(chunks: list[dict]) -> dict[str, str]:
    collected: dict[str, str] = {}
    for chunk in chunks:
        if chunk["type"] == "content":
            collected.setdefault("content", "")
            collected["content"] += chunk.get("text", "")
        if chunk["type"] == "status":
            collected.setdefault("status", "")
            collected["status"] += chunk.get("text", "")
    return collected


def _patch_data_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _items(db, year):
        return [_item("rec-1", "杂质RRT=1.98-2.01高于标准", "霉酚酸")]

    async def _cached(db, year, ids):
        return {
            "rec-1": {
                "content_hash": "x",
                "payload": {"product": "霉酚酸", "anomaly_type": "杂质异常"},
                "status": "completed",
                "created_at": None,
            }
        }

    monkeypatch.setattr(chat_svc, "_list_year_items", _items)
    monkeypatch.setattr(chat_svc, "_load_cached_classifications", _cached)


@pytest.mark.asyncio
async def test_tool_loop_calls_aggregation_then_streams_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_svc, "get_config", AsyncMock(return_value=_config()))
    agg_mock = AsyncMock(
        return_value={
            "products": [{"product": "霉酚酸", "count": 116}],
            "type_totals": [],
        }
    )
    monkeypatch.setattr(chat_svc, "get_dashboard_aggregation", agg_mock)
    # 第一轮要求调用聚合工具，第二轮直接结束工具循环
    chat_mock = AsyncMock(
        side_effect=[
            {
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "type": "function",
                        "function": {
                            "name": "fp_get_anomaly_aggregation",
                            "arguments": json.dumps({"year": 2026}),
                        },
                    }
                ],
                "content": "",
            },
            {"content": "根据统计，霉酚酸异常最多。"},
        ]
    )
    monkeypatch.setattr(type(chat_svc.llm_client), "chat_with_tools", chat_mock)
    monkeypatch.setattr(type(chat_svc.llm_client), "stream_chat", _fake_stream)

    chunks = [
        chunk
        async for chunk in chat_svc.run_anomaly_chat_loop(
            _FakeDB(),
            [{"role": "user", "content": "2026年哪个产品异常最多？"}],
            {"role": "system", "content": "system"},
        )
    ]
    collected = _collect(chunks)
    assert agg_mock.await_count == 1
    assert agg_mock.await_args.args[1] == 2026
    assert "正在查询成品异常统计" in collected["status"]
    assert "最终回答" in collected["content"]
    assert chunks[-1] == {"type": "done"}


@pytest.mark.asyncio
async def test_query_records_tool_filters_by_product_type_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_data_sources(monkeypatch)
    result = await chat_svc.execute_tool_call(
        _FakeDB(),
        "fp_query_anomaly_records",
        {
            "year": 2026,
            "product": "霉酚酸",
            "anomaly_type": "杂质异常",
            "keyword": "RRT",
        },
    )
    data = json.loads(result)
    assert data["total_matched"] == 1
    assert data["returned"][0]["id"] == "rec-1"
    assert data["returned"][0]["product"] == "霉酚酸"
    assert data["returned"][0]["anomaly_type"] == "杂质异常"


@pytest.mark.asyncio
async def test_query_records_tool_excludes_non_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_data_sources(monkeypatch)
    result = await chat_svc.execute_tool_call(
        _FakeDB(),
        "fp_query_anomaly_records",
        {"year": 2026, "product": "洛伐他汀"},
    )
    data = json.loads(result)
    assert data["total_matched"] == 0
    assert data["returned"] == []


@pytest.mark.asyncio
async def test_qwen_text_tool_calls_are_parsed_and_executed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_svc, "get_config", AsyncMock(return_value=_config()))
    agg_mock = AsyncMock(return_value={"products": [], "type_totals": []})
    monkeypatch.setattr(chat_svc, "get_dashboard_aggregation", agg_mock)
    chat_mock = AsyncMock(
        side_effect=[
            {
                "content": (
                    'call\n{"name": "fp_get_anomaly_aggregation", '
                    '"arguments": {}}'
                )
            },
            {"content": "根据统计完成回答。"},
        ]
    )
    monkeypatch.setattr(type(chat_svc.llm_client), "chat_with_tools", chat_mock)
    monkeypatch.setattr(type(chat_svc.llm_client), "stream_chat", _fake_stream)

    chunks = [
        chunk
        async for chunk in chat_svc.run_anomaly_chat_loop(
            _FakeDB(),
            [{"role": "user", "content": "统计"}],
            {"role": "system", "content": "s"},
        )
    ]
    agg_mock.assert_awaited_once()
    assert chunks[-1] == {"type": "done"}


@pytest.mark.asyncio
async def test_no_config_propagates_for_503_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_svc, "get_config", AsyncMock(side_effect=LLMConfigError("no config"))
    )
    with pytest.raises(LLMConfigError):
        async for _ in chat_svc.run_anomaly_chat_loop(
            _FakeDB(),
            [{"role": "user", "content": "你好"}],
            {"role": "system", "content": "s"},
        ):
            pass


def test_system_prompt_contains_persona_and_taxonomy() -> None:
    prompt = chat_svc.build_chat_system_prompt()
    assert "资深现场QA" in prompt
    assert "杂质异常" in prompt
    assert " Phenomenon" not in prompt
    assert "现象归纳" in prompt
    assert "USMC" in prompt
