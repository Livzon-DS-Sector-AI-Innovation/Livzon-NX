"""FA 多轮对话 API 覆盖测试（依赖全部 mock，不联网）。

覆盖：
- fa_chat_send：缺 session_id / 空消息 / 会话不存在错误分支；SSE 成功流式；LLM 失败
- fa_chat_history：system/user 消息拼接
- _gather_fa_context：酸化/收率小数放大、产量、BFS 异常、统计异常、批次数据缺失占位
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.production import fa_chat_api as api


def _parse(resp: Any) -> Any:
    return json.loads(resp.body)


class _Delta:
    def __init__(self, content: Any) -> None:
        self.content = content


class _Choice:
    def __init__(self, delta: Any) -> None:
        self.delta = delta


class _Chunk:
    def __init__(self, content: Any = "", no_choices: Any = False) -> None:
        if no_choices:
            self.choices = []
        else:
            self.choices = [_Choice(_Delta(content))]


async def _make_stream(*contents: Any) -> AsyncIterator[Any]:
    for c in contents:
        yield _Chunk(c)


async def _body_text(resp: Any) -> Any:
    parts = []
    async for chunk in resp.body_iterator:
        parts.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
    return b"".join(parts).decode("utf-8")


class _Req:
    def __init__(self, body: Any) -> None:
        self._body = body

    async def json(self) -> Any:
        return self._body


# ═══════════ fa_chat_send 错误路径 ═══════════


@pytest.mark.anyio
async def test_fa_chat_send_missing_session_id() -> Any:
    out = await api.fa_chat_send(
        cast(Any, _Req({"message": "hi"})), session=AsyncMock()
    )
    assert _parse(out)["message"] == "缺少 session_id"


@pytest.mark.anyio
async def test_fa_chat_send_empty_message() -> Any:
    out = await api.fa_chat_send(
        cast(Any, _Req({"session_id": "s1", "message": "  "})), session=AsyncMock()
    )  # noqa: E501
    assert _parse(out)["message"] == "消息不能为空"


@pytest.mark.anyio
async def test_fa_chat_send_session_not_found() -> Any:
    s = AsyncMock()
    s.execute.return_value = MagicMock()
    s.execute.return_value.scalars.return_value.all.return_value = []
    out = await api.fa_chat_send(
        cast(Any, _Req({"session_id": "nope", "message": "hi"})), session=s
    )  # noqa: E501
    assert _parse(out)["message"] == "会话不存在"


# ═══════════ fa_chat_send SSE 成功路径 ═══════════


def _history_row(role: Any = "assistant", seq: Any = 0, **over: Any) -> Any:
    data = dict(
        id=f"id-{seq}",
        session_id="s1",
        batch_no="FA-1",
        stage="fermentation",
        message_seq=seq,
        role=role,
        summary="旧摘要" if role in ("assistant", "user") else None,
        llm_response="旧回复" if role != "system" else None,
        created_by="测试员",
        created_at=datetime(2026, 5, 1),
    )
    data.update(over)
    return SimpleNamespace(**data)


@pytest.mark.anyio
async def test_fa_chat_send_stream_success() -> Any:
    s = AsyncMock()
    s.execute.return_value = MagicMock()
    s.execute.return_value.scalars.return_value.all.return_value = [
        _history_row(seq=0, role="assistant"),
        _history_row(seq=1, role="user"),
    ]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_stream("你好", "，"))
    with (
        patch.object(api, "_gather_fa_context", AsyncMock(return_value="追溯上下文")),
        patch.object(
            api,
            "get_config",
            AsyncMock(
                return_value=SimpleNamespace(
                    api_base_url="https://x", api_key="k", model_name="m"
                )
            ),
        ),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        resp = await api.fa_chat_send(
            cast(Any, _Req({"session_id": "s1", "message": "亚硝酸怎么加"})), session=s
        )  # noqa: E501
        text = await _body_text(resp)
    assert "token" in text
    assert '"done"' in text
    # 用户消息 + AI 回复均入库
    assert s.add.called
    assert s.commit.await_count >= 2


@pytest.mark.anyio
async def test_fa_chat_send_stream_llm_failure() -> Any:
    s = AsyncMock()
    s.execute.return_value = MagicMock()
    s.execute.return_value.scalars.return_value.all.return_value = [
        _history_row(seq=0),
    ]
    with (
        patch.object(api, "_gather_fa_context", AsyncMock(return_value="上下文")),
        patch.object(
            api,
            "get_config",
            AsyncMock(
                return_value=SimpleNamespace(
                    api_base_url="https://x", api_key="k", model_name="m"
                )
            ),
        ),
        patch.object(api, "AsyncOpenAI", side_effect=RuntimeError("boom")),
    ):
        resp = await api.fa_chat_send(
            cast(Any, _Req({"session_id": "s1", "message": "hi"})), session=s
        )  # noqa: E501
        text = await _body_text(resp)
    assert "error" in text
    assert "boom" in text


@pytest.mark.anyio
async def test_fa_chat_send_save_ai_reply_failure() -> Any:
    """AI 回复写入失败 → 仅记录日志，流仍正常结束。"""
    s = AsyncMock()
    s.execute.return_value = MagicMock()
    s.execute.return_value.scalars.return_value.all.return_value = [
        _history_row(seq=0),
    ]
    # 第二次 commit（存 AI 回复）失败
    s.commit.side_effect = [None, RuntimeError("save failed")]
    client = MagicMock()
    with (
        patch.object(api, "_gather_fa_context", AsyncMock(return_value="上下文")),
        patch.object(
            api,
            "get_config",
            AsyncMock(
                return_value=SimpleNamespace(
                    api_base_url="https://x", api_key="k", model_name="m"
                )
            ),
        ),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        client.chat.completions.create = AsyncMock(return_value=_make_stream("回复"))
        resp = await api.fa_chat_send(
            cast(Any, _Req({"session_id": "s1", "message": "hi"})), session=s
        )  # noqa: E501
        text = await _body_text(resp)
    assert "done" in text


# ═══════════ fa_chat_history ═══════════


@pytest.mark.anyio
async def test_fa_chat_history_system_and_user() -> Any:
    s = AsyncMock()
    s.execute.return_value = MagicMock()
    s.execute.return_value.scalars.return_value.all.return_value = [
        _history_row(
            seq=0,
            role="system",
            summary="摘要",
            anomalies=[{"key": "x"}],
            causes=["c"],
            suggestions=["g"],
            severity="high",  # noqa: E501
            llm_response="正文",
        ),
        _history_row(seq=1, role="user"),
    ]
    resp = await api.fa_chat_history(session_id="s1", session=s)
    data = _parse(resp)["data"]
    assert data["session_id"] == "s1"
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "system"
    # system 角色 content 为结构化 dict
    assert isinstance(data["messages"][0]["content"], dict)
    assert data["messages"][0]["content"]["summary"] == "摘要"
    assert data["messages"][1]["role"] == "user"
    assert data["messages"][1]["content"] == "旧回复"


@pytest.mark.anyio
async def test_fa_chat_history_empty() -> Any:
    s = AsyncMock()
    s.execute.return_value = MagicMock()
    s.execute.return_value.scalars.return_value.all.return_value = []
    resp = await api.fa_chat_history(session_id="s1", session=s)
    data = _parse(resp)["data"]
    assert data["messages"] == []


# ═══════════ _gather_fa_context 分支 ═══════════


def _ctx_session() -> Any:
    """覆盖 BFS 各工段、收率<2 放大、产量、酸化统计、离心统计、电导统计。"""
    s = AsyncMock()

    def exec(*args: Any, **kw: Any) -> Any:
        sql = str(args[0])
        r = MagicMock()
        if "downstream_batch = :batch" in sql:
            r.fetchall.return_value = [
                SimpleNamespace(
                    upstream_type="fermentation", upstream_batch="FA-F", quantity=None
                ),
                SimpleNamespace(
                    upstream_type="acidification", upstream_batch="FA-A", quantity=2.0
                ),
                SimpleNamespace(
                    upstream_type="decolor_centrifuge",
                    upstream_batch="FA-C",
                    quantity=1.2,
                ),
            ]
        elif "upstream_batch = :batch" in sql:
            r.fetchall.return_value = [
                SimpleNamespace(
                    downstream_type="decolor1", downstream_batch="FA-D", quantity=5.0
                ),
                SimpleNamespace(
                    downstream_type="fermentation",
                    downstream_batch="FA-F2",  # noqa: E501
                    quantity=3.0,
                ),
            ]
        elif "REGEXP_REPLACE" in sql and "fa_acidification_records" in sql:
            r.fetchone.return_value = (10.0, 20.0, 30.0, 40.0, 88.0)
        elif "PERCENTILE_CONT" in sql and "decolor_centrifuge" in sql:
            r.fetchone.return_value = (11.0, 22.0, 33.0, 44.0, 55.0)
        elif '"批收率"' in sql and "LIMIT 1" in sql:
            r.fetchone.return_value = ("0.75",)  # < 2 → 放大100倍
        elif (
            '"收率"' in sql
            and "fa_decolor_centrifuge_records" in sql
            and "LIMIT 1" in sql
        ):  # noqa: E501
            r.fetchone.return_value = ("5.0",)  # ≥ 2 → 不放大
        elif '"汇总总量_kg"' in sql:
            r.fetchone.return_value = ("100",)
        elif '"电导_uscm"' in sql:
            r.fetchone.return_value = (80.0, 82.0)
        else:
            r.fetchone.return_value = None
            r.fetchall.return_value = []
        return r

    s.execute.side_effect = exec
    return s


@pytest.mark.anyio
async def test_gather_fa_context_yield_branches() -> Any:
    s = _ctx_session()
    with patch(
        "app.modules.production.fa_ai_analysis_api._get_trace_data",
        AsyncMock(return_value=("批次数据文本 lombok", "统计 文本")),
    ):
        ctx = await api._gather_fa_context("FA-F", "fermentation", session=s)
    assert "批次追溯链路" in ctx
    assert "收率75.0%" in ctx
    assert "收率5.0%" in ctx
    assert "产量100kg" in ctx
    assert "酸化收率: min=10.0" in ctx
    assert "电导(us/cm): 均值=80.0" in ctx


@pytest.mark.anyio
async def test_gather_fa_context_exception_paths() -> Any:
    """BFS 异常 → 记录；统计异常 → 记录；批次数据缺失 → 占位符。"""
    s = AsyncMock()
    s.execute.side_effect = Exception("boom")
    with patch(
        "app.modules.production.fa_ai_analysis_api._get_trace_data",
        AsyncMock(side_effect=RuntimeError("data down")),
    ):
        ctx = await api._gather_fa_context("FA-F", "fermentation", session=s)
    assert "(批次数据暂时无法获取)" in ctx
    # 无追溯链路、无统计（全部被 try/except 吞掉）
    assert "批次追溯链路" not in ctx
