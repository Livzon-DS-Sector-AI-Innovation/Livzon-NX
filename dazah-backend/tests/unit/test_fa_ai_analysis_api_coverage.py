"""FA AI 分析 API 补充覆盖测试（endpoint 直接调用 + LLM mock）。

覆盖：
- fa_ai_analysis_api._parse_json 的花括号提取失败兜底
- _get_trace_data 统计分支（电导/收率/渣损失率 全量统计非空 / 空）
- fa_ai_analysis：非法工段 400、批次不存在 404、成功路径、LLM 异常兜底
- fa_ai_analysis_stream：成功流式、过短重试、LLM 失败兜底
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.modules.production import fa_ai_analysis_api as api


def _parse(resp):
    return json.loads(resp.body)["data"]


def _session():
    s = AsyncMock()
    res = MagicMock()
    res.fetchall.return_value = []
    res.fetchone.return_value = None
    res.scalar.return_value = 0
    s.execute.return_value = res
    s.add = MagicMock()
    s.commit = AsyncMock()
    return s


# ── 纯函数补充 ──


def test_parse_json_invalid_brace_fallback():
    # 外层 JSON 失败，尝试提取 { ... } 后仍失败 → {}
    assert api._parse_json('prefix {"causes": } suffix') == {}
    assert api._parse_json('{"unclosed') == {}


# ── _get_trace_data 统计分支 ──


def _trace_session(ferment=None, acid=None, dec=None, cent=None,
                   conductance=None, yield_stats=None, slag=None):
    s = AsyncMock()

    def exec(*args, **kw):
        stmt = args[0]
        sql = str(stmt)
        r = MagicMock()
        if "LEFT JOIN" in sql and "fa_fermentation_batches" in sql:
            r.fetchone.return_value = ferment
        elif "fa_acidification_records" in sql and "ORDER BY id" in sql:
            r.fetchall.return_value = acid or []
        elif "fa_decolor1_records" in sql:
            r.fetchone.return_value = dec
        elif "fa_decolor_centrifuge_records" in sql and "LIMIT 10" in sql:
            r.fetchall.return_value = cent or []
        elif "PERCENTILE_CONT" in sql:
            r.fetchone.return_value = conductance
        elif '"收率"' in sql:
            r.fetchone.return_value = yield_stats
        elif "渣损失率" in sql:
            r.fetchone.return_value = slag
        else:
            r.fetchone.return_value = None
            r.fetchall.return_value = []
        return r

    s.execute.side_effect = exec
    return s


@pytest.mark.anyio
async def test_get_trace_data_with_stats():
    s = _trace_session(
        ferment=("FA-EX21", "2026-05-10", 5000.0, 6200.0, 150.0, 12.0, 3.0,
                 "子批1(100kl/50gL/200kg)"),
        acid=[SimpleNamespace(acid=210.0, ph_acid=3.2, acid_vol=120.0, mf_vol=100.0,
                              mf_content=45.0, mf_qty=4500.0, slag_loss=0.08, balance=0.97)],  # noqa: E501
        dec=SimpleNamespace(批号="FA-EX21-D1", vol=150.0, content=45.0, carbon=5.0,
                           after_carbon=40.0, cond1=6200.0, cond2=5000.0, cond3=4800.0),
cent=[SimpleNamespace(批号="FA-EX21-C1", in_vol=120.0, yield_rate=0.88, before_c=30.0, after_c=28.0,  # noqa: E501
                               bl=("FA-C1",))],
        conductance=[1200, 900, 800, 100, 4000],
        yield_stats=[1.0, 0.5, 0.98],
        slag=("12.5",),
    )
    batch, stats = await api._get_trace_data(s, "FA-EX21", "fermentation")
    assert "发酵放罐: FA-EX21" in batch
    assert "膜滤: " in batch
    assert "电导全量统计" in stats
    assert "渣损失率全量均值: 12.5%" in stats


@pytest.mark.anyio
async def test_get_trace_data_no_stats():
    s = _trace_session(
        ferment=("FA-EX21", "2026-05-10", 500.0, 6200.0, 150.0, 12.0, 3.2,
                 "区(1)"),
        acid=[
            SimpleNamespace(acid=210.0, ph_acid=3.2, acid_vol=120.0, mf_vol=0.0,
                            mf_content=0.0, mf_qty=0.0, slag_loss=0.08, balance=0.97),
        ],
        dec=None,
        cent=None,
    )
    batch_data, stats_data = await api._get_trace_data(s, "FA-EX21", "fermentation")
    assert isinstance(batch_data, str) and batch_data.startswith("发酵放罐")
    assert stats_data == ""


# ── fa_ai_analysis 主端点 ──


@pytest.mark.anyio
async def test_ai_analysis_invalid_stage_400():
    s = _session()
    with pytest.raises(HTTPException) as exc:
        await api.fa_ai_analysis(batch_no="FA-1", stage="bad_stage", session=s)
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_ai_analysis_batch_not_found_404():
    s = _session()
    with (
        patch.object(api, "_get_trace_data", AsyncMock(return_value=("", "stats"))),
        pytest.raises(HTTPException) as exc,
    ):
        await api.fa_ai_analysis(batch_no="NOPE", stage="fermentation", session=s)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_ai_analysis_success():
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = (
        '{"summary": "批次正常", "causes": ["c1", "c2"], "suggestions": ["s1", "s2"], "severity": "low"}'  # noqa: E501
    )
    client.chat.completions.create = AsyncMock(return_value=resp)
    s = _session()
    with (
        patch.object(api, "_get_trace_data", AsyncMock(return_value=("批次数据文本", "统计"))),  # noqa: E501
        patch.object(api, "get_config", AsyncMock(return_value=SimpleNamespace(
            api_base_url="https://x", api_key="k", model_name="m"))),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        out = await api.fa_ai_analysis(batch_no="FA-1", stage="fermentation", session=s)
    data = _parse(out)
    assert data["summary"] == "批次正常"
    assert data["causes"] == ["c1", "c2"]
    assert data["anomalies"] == []
    assert data["severity"] == "low"
    assert data["analysis_text"]
    s.commit.assert_awaited()


@pytest.mark.anyio
async def test_ai_analysis_success_empty_content_and_dict_msg():
    """resp.content 为空字符串 → summary 用默认 '分析完成'；入库失败被吞掉。"""
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = None
    client.chat.completions.create = AsyncMock(return_value=resp)
    s = AsyncMock()
    s.execute.side_effect = RuntimeError("db down")  # 入库路径抛错
    s.commit = AsyncMock()
    with (
        patch.object(api, "_get_trace_data", AsyncMock(return_value=("批次", "统计"))),
        patch.object(api, "get_config", AsyncMock(return_value=SimpleNamespace(
            api_base_url=None, api_key=None, model_name=None))),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        data = _parse(await api.fa_ai_analysis(batch_no="FA-1", stage="fermentation", session=s))  # noqa: E501
    assert data["summary"] == "分析完成"
    assert data["severity"] == "low"


@pytest.mark.anyio
async def test_ai_analysis_llm_failure_fallback():
    s = _session()
    with (
        patch.object(api, "_get_trace_data", AsyncMock(return_value=("批次", "统计"))),
        patch.object(api, "get_config", AsyncMock(return_value=SimpleNamespace(
            api_base_url="https://x", api_key="k", model_name="m"))),
        patch.object(api, "AsyncOpenAI", side_effect=RuntimeError("boom")),
    ):
        data = _parse(await api.fa_ai_analysis(batch_no="FA-1", stage="fermentation", session=s))  # noqa: E501
    assert "AI 分析暂时不可用" in data["summary"]
    assert data["analysis_text"] == ""
    assert "异常" in data["causes"][0]


# ── fa_ai_analysis_stream ──


class _Delta:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, delta):
        self.delta = delta


class _Chunk:
    def __init__(self, content="", no_choices=False):
        if no_choices:
            self.choices = []
        else:
            self.choices = [_Choice(_Delta(content))]


async def _make_stream(*contents):
    for c in contents:
        yield _Chunk(c)


async def _body_text(resp):
    parts = []
    async for chunk in resp.body_iterator:
        if isinstance(chunk, bytes):
            parts.append(chunk)
        else:
            parts.append(chunk.encode("utf-8"))
    return b"".join(parts).decode("utf-8")


@pytest.mark.anyio
async def test_stream_success():
    s = _session()
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_stream("(1)", "(2)")
    )
    with (
        patch.object(api, "_get_trace_data", AsyncMock(return_value=("批次数据", "统计"))),  # noqa: E501
        patch.object(api, "get_config", AsyncMock(return_value=SimpleNamespace(
            api_base_url="https://x", api_key="k", model_name="m"))),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        resp = await api.fa_ai_analysis_stream(batch_no="FA-1", stage="fermentation", session=s)  # noqa: E501
        text = await _body_text(resp)
    assert "已收集" in text
    assert "result" in text
    assert '"done"' in text
    assert "(1)" in text


@pytest.mark.anyio
async def test_stream_no_batch_error_path():
    """批次数据为空 → error 事件并结束，不调用 LLM。"""
    s = _session()
    with (
        patch.object(api, "_get_trace_data", AsyncMock(return_value=("", ""))),
        patch.object(api, "get_config", AsyncMock(return_value=None)),
    ):
        resp = await api.fa_ai_analysis_stream(batch_no="NOPE", stage="fermentation", session=s)  # noqa: E501
        text = await _body_text(resp)
    assert "未找到批次数据" in text
    assert '"error"' in text


@pytest.mark.anyio
async def test_stream_batch_no_stats_path():
    """有批次但 stats 为空 → 走 else 分支完成统计，LLM 失败不影响。"""
    s = _session()
    with (
        patch.object(api, "_get_trace_data", AsyncMock(return_value=("批次", None))),
        patch.object(api, "get_config", AsyncMock(return_value=None)),
        patch.object(api, "AsyncOpenAI", side_effect=RuntimeError("boom")),
    ):
        resp = await api.fa_ai_analysis_stream(batch_no="FA-1", stage="fermentation", session=s)  # noqa: E501
        text = await _body_text(resp)
    assert "统计完成" in text


@pytest.mark.anyio
async def test_stream_retry():
    s = _session()
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            _make_stream('{"summary":"过短","causes":["a"],"suggestions":["b"]}'),  # 少于2条 → 触发重试  # noqa: E501
            _make_stream('{"summary":"完整","causes":["a","b","c"],"suggestions":["x","y","z"]}'),  # noqa: E501
        ]
    )
    with (
        patch.object(api, "_get_trace_data", AsyncMock(return_value=("批次数据", "统计"))),  # noqa: E501
        patch.object(api, "get_config", AsyncMock(return_value=SimpleNamespace(
            api_base_url="https://x", api_key="k", model_name="m"))),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        resp = await api.fa_ai_analysis_stream(batch_no="FA-1", stage="fermentation", session=s)  # noqa: E501
        text = await _body_text(resp)
    assert "llm_retry" in text
    assert client.chat.completions.create.await_count == 2


@pytest.mark.anyio
async def test_stream_llm_failure_fallback():
    s = _session()
    with (
        patch.object(api, "_get_trace_data", AsyncMock(return_value=("批次数据", "统计"))),  # noqa: E501
        patch.object(api, "get_config", AsyncMock(return_value=None)),
        patch.object(api, "AsyncOpenAI", side_effect=RuntimeError("boom")),
    ):
        resp = await api.fa_ai_analysis_stream(batch_no="FA-1", stage="fermentation", session=s)  # noqa: E501
        text = await _body_text(resp)
    assert "分析失败" in text
    assert '"done"' in text
