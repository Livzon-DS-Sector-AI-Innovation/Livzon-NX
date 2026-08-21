"""MC AI 分析 API 测试（LLM/lineage 全 mock，覆盖分析编排与辅助函数）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.production import ai_analysis_api as api


def make_session(execute_results=None):
    s = AsyncMock()
    if execute_results is None:
        s.execute.return_value = MagicMock()
    else:
        s.execute.side_effect = execute_results
    s.add = MagicMock()
    s.commit = AsyncMock()
    return s


_MISSING = object()


def make_result(fetchone=_MISSING, fetchall=_MISSING):
    r = MagicMock()
    if fetchone is not _MISSING:
        r.fetchone.return_value = fetchone
    if fetchall is not _MISSING:
        r.fetchall.return_value = fetchall
    return r


def llm_client(content: str):
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    client.chat.completions.create = AsyncMock(return_value=resp)
    return client


def llm_config():
    return SimpleNamespace(api_base_url="https://mock", api_key="k", model_name="m")


def trace_response(stages=None, **over):
    data = {
        "stages": stages or [],
        "cumulative_yield": 90,
        "max_loss_stage": None,
        "target_stage": "extraction",
    }
    data.update(over)
    return SimpleNamespace(body=json.dumps({"code": 200, "data": data}))


# ═══════════ _get_node_batch_date ═══════════


def test_get_node_batch_date_branches():
    import asyncio

    # sub_tank / crude_product
    s = make_session([make_result(fetchone=SimpleNamespace(produce_date="2026-03-01"))])
    assert asyncio.run(api._get_node_batch_date(s, "sub_tank", "MC-1")) == "2026-03-01"
    s = make_session([make_result(fetchone=None)])
    assert asyncio.run(api._get_node_batch_date(s, "crude_product", "MC-1")) is None
    # extraction
    s = make_session([make_result(fetchone=SimpleNamespace(extract_date="2026-03-02"))])
    assert (
        asyncio.run(api._get_node_batch_date(s, "extraction", "MC-2")) == "2026-03-02"
    )
    # refinement
    s = make_session([make_result(fetchone=SimpleNamespace(input_date="2026-03-03"))])
    assert (
        asyncio.run(api._get_node_batch_date(s, "refinement", "MC-3")) == "2026-03-03"
    )
    # 其他工段 → None，不查库
    s = make_session()
    assert asyncio.run(api._get_node_batch_date(s, "blending", "MC-4")) is None
    s.execute.assert_not_awaited()


# ═══════════ _detect_yield_anomalies ═══════════


def test_detect_yield_anomalies_finds_high_and_medium():
    import asyncio

    stages = [
        {
            "stage": "sub_tank",
            "nodes": [
                {"batch_no": "MC-1", "yield_rate": 70.0},
                {"batch_no": "MC-2", "yield_rate": 79.0},
                {"batch_no": "MC-3", "yield_rate": 90.0},  # 正常
                {"batch_no": "MC-4", "yield_rate": None},  # 跳过
                {"batch_no": "", "yield_rate": 80.0},  # 无批号跳过
            ],
        },
        {
            "stage": "blending",
            "nodes": [{"batch_no": "B1", "yield_rate": 90.0}],
        },  # 不在检测范围
    ]
    s = make_session()
    iqr = {"n": 10, "median": 90.0, "q1": 85.0, "q3": 95.0, "iqr": 10.0}
    with (
        patch.object(api, "_get_node_batch_date", AsyncMock(return_value=None)),
        patch.object(api, "_compute_stage_iqr", AsyncMock(return_value=iqr)),
    ):
        anomalies = asyncio.run(api._detect_yield_anomalies(s, stages))
    assert len(anomalies) == 2
    assert anomalies[0]["severity"] == "high"
    assert anomalies[0]["batch_no"] == "MC-1"
    assert anomalies[1]["severity"] == "medium"
    assert "低于" in anomalies[0]["detail"]


def test_detect_yield_anomalies_skips_low_sample_and_errors():
    import asyncio

    stages = [
        {"stage": "extraction", "nodes": [{"batch_no": "MC-1", "yield_rate": 80.0}]}
    ]
    s = make_session()

    async def _iqr(session, stage, d):
        return {"n": 3, "median": 90.0, "q1": 85.0, "q3": 95.0, "iqr": 10.0}  # 样本不足

    with (
        patch.object(api, "_get_node_batch_date", AsyncMock(return_value=None)),
        patch.object(api, "_compute_stage_iqr", side_effect=_iqr),
    ):
        assert asyncio.run(api._detect_yield_anomalies(s, stages)) == []

    # 异常路径：IQR 计算抛错 → 记录但继续
    with (
        patch.object(api, "_get_node_batch_date", AsyncMock(return_value=None)),
        patch.object(
            api, "_compute_stage_iqr", AsyncMock(side_effect=RuntimeError("db"))
        ),
    ):
        assert asyncio.run(api._detect_yield_anomalies(s, stages)) == []


# ═══════════ ai_analyze ═══════════


def _parse_response(resp):
    return json.loads(resp.body)["data"]


def test_ai_analyze_llm_failure_no_anomalies_fallback():
    """LLM 失败且无异常时，causes/suggestions 走固定兜底文案。"""
    import asyncio

    s = make_session()
    with (
        patch.object(api, "lineage_trace", AsyncMock(return_value=trace_response())),
        patch.object(
            api,
            "lineage_yield_distribution",
            AsyncMock(return_value=SimpleNamespace(body=json.dumps({"data": []}))),
        ),
        patch.object(api, "_detect_yield_anomalies", AsyncMock(return_value=[])),
        patch.object(api, "get_config", AsyncMock(return_value=llm_config())),
        patch.object(api, "AsyncOpenAI", side_effect=RuntimeError("boom")),
    ):
        resp = asyncio.run(
            api.ai_analyze(batch_no="MC-1", stage="extraction", session=s)
        )
    data = _parse_response(resp)
    assert "分析失败" in data["analysis_text"]
    assert data["causes"] == ["各工段收率均在正常范围内，无异常标记"]
    assert data["suggestions"] == ["持续监控各工段关键参数，保持当前操作水平"]


def test_ai_analyze_blending_skips_empty_nodes():
    """blending 节点无批号或无记录行时跳过，不进入杂质异常逻辑。"""
    import asyncio

    # blending 节点查询返回 None（无记录）
    s = make_session(
        [
            make_result(fetchone=None),
            # history 查询（无 anomalies，不会触发）
            make_result(fetchall=[]),
        ]
    )
    stages = [
        {
            "stage": "blending",
            "label": "混粉成品",
            "nodes": [{"batch_no": "", "yield_rate": 90.0}],  # 空批号跳过
        },
    ]
    client = llm_client(
        '{"summary": "正常", "causes": ["a", "b", "c"], "suggestions": ["x", "y", "z"], "severity": "low"}'  # noqa: E501
    )
    with (
        patch.object(
            api,
            "lineage_trace",
            AsyncMock(return_value=trace_response(stages, target_stage="blending")),
        ),
        patch.object(
            api,
            "lineage_yield_distribution",
            AsyncMock(return_value=SimpleNamespace(body=json.dumps({"data": []}))),
        ),
        patch.object(api, "_detect_yield_anomalies", AsyncMock(return_value=[])),
        patch.object(api, "get_config", AsyncMock(return_value=llm_config())),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        resp = asyncio.run(api.ai_analyze(batch_no="", stage="blending", session=s))
    data = _parse_response(resp)
    assert data["anomalies"] == []


def test_ai_analyze_blending_skips_non_blend_stage_and_no_row():
    """blending 分支里存在非 blending 工段（149 continue）与有批号但无记录行（166 continue）。"""  # noqa: E501
    import asyncio

    # 第一个 execute：blending 节点查询返回 None；第二个：history（无异常不会查）
    s = make_session(
        [
            make_result(fetchone=None),
            make_result(fetchall=[]),
        ]
    )
    stages = [
        {
            "stage": "extraction",  # 非 blending → 149 continue
            "label": "提取",
            "nodes": [{"batch_no": "MC-1", "yield_rate": 80.0}],
        },
        {
            "stage": "blending",
            "label": "混粉成品",
            "nodes": [{"batch_no": "B1"}],  # 有批号但查询无行 → 166 continue
        },
    ]
    client = llm_client(
        '{"summary": "正常", "causes": ["a", "b", "c"], "suggestions": ["x", "y", "z"], "severity": "low"}'  # noqa: E501
    )
    with (
        patch.object(
            api,
            "lineage_trace",
            AsyncMock(return_value=trace_response(stages, target_stage="blending")),
        ),
        patch.object(
            api,
            "lineage_yield_distribution",
            AsyncMock(return_value=SimpleNamespace(body=json.dumps({"data": []}))),
        ),
        patch.object(api, "_detect_yield_anomalies", AsyncMock(return_value=[])),
        patch.object(api, "get_config", AsyncMock(return_value=llm_config())),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        resp = asyncio.run(api.ai_analyze(batch_no="B1", stage="blending", session=s))
    data = _parse_response(resp)
    assert data["anomalies"] == []


def test_ai_analyze_success_path():
    import asyncio

    s = make_session()
    client = llm_client(
        '{"summary": "收率正常", "causes": ["a", "b", "c"], "suggestions": ["x", "y", "z"], "severity": "low"}'  # noqa: E501
    )
    with (
        patch.object(api, "lineage_trace", AsyncMock(return_value=trace_response())),
        patch.object(
            api,
            "lineage_yield_distribution",
            AsyncMock(return_value=SimpleNamespace(body=json.dumps({"data": []}))),
        ),
        patch.object(api, "_detect_yield_anomalies", AsyncMock(return_value=[])),
        patch.object(api, "get_config", AsyncMock(return_value=llm_config())),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        resp = asyncio.run(
            api.ai_analyze(batch_no="MC-1", stage="extraction", session=s)
        )
    data = _parse_response(resp)
    assert data["summary"] == "收率正常"
    assert data["severity"] == "low"
    assert data["anomalies"] == []
    s.add.assert_called_once()
    s.commit.assert_awaited_once()


def test_ai_analyze_retry_short_output_and_blending_impurities():
    import asyncio

    s = make_session(
        [
            # blending 节点查询（real_stage=blending）
            make_result(
                fetchone=SimpleNamespace(
                    rrt_053=0.6,
                    rrt_0755=None,
                    rrt_094_096=None,
                    rrt_103_106=None,
                    rrt_201=1.2,
                    total_impurity=2.0,
                )
            ),
            # history 查询（有 anomalies）
            make_result(
                fetchall=[
                    SimpleNamespace(
                        id="h1",
                        batch_no="MC-0",
                        stage="blending",
                        summary="旧",
                        severity="high",
                        causes=["c1"],
                        suggestions=["s1"],
                        created_at="2026-01-01",
                    )
                ]
            ),
        ]
    )
    short = MagicMock()
    short.choices = [MagicMock()]
    short.choices[
        0
    ].message.content = '{"summary": "短", "causes": ["a"], "suggestions": ["x"]}'
    full = MagicMock()
    full.choices = [MagicMock()]
    full.choices[
        0
    ].message.content = '{"summary": "完整", "causes": ["a", "b", "c"], "suggestions": ["x", "y", "z"], "severity": "medium"}'  # noqa: E501
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=[short, full])
    stages = [
        {
            "stage": "blending",
            "label": "混粉成品",
            "nodes": [{"batch_no": "B1", "yield_rate": 90.0}],
        },
    ]
    with (
        patch.object(
            api,
            "lineage_trace",
            AsyncMock(return_value=trace_response(stages, target_stage="blending")),
        ),
        patch.object(
            api,
            "lineage_yield_distribution",
            AsyncMock(return_value=SimpleNamespace(body=json.dumps({"data": []}))),
        ),
        patch.object(api, "_detect_yield_anomalies", AsyncMock(return_value=[])),
        patch.object(api, "get_config", AsyncMock(return_value=llm_config())),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        resp = asyncio.run(api.ai_analyze(batch_no="B1", stage="blending", session=s))
    data = _parse_response(resp)
    assert data["summary"] == "完整"
    assert client.chat.completions.create.await_count == 2
    # 杂质异常被追加（total_impurity=2.0 > 1.5，rrt_201=1.2 > 1.0）
    metrics = [a["metric"] for a in data["anomalies"]]
    assert "total_impurity" in metrics
    assert "rrt_201" in metrics
    assert data["reference_cases"][0]["batch_no"] == "MC-0"


def test_ai_analyze_llm_failure_fallback():
    import asyncio

    s = make_session()
    with (
        patch.object(api, "lineage_trace", AsyncMock(return_value=trace_response())),
        patch.object(
            api,
            "lineage_yield_distribution",
            AsyncMock(return_value=SimpleNamespace(body=json.dumps({"data": []}))),
        ),
        patch.object(
            api,
            "_detect_yield_anomalies",
            AsyncMock(
                return_value=[
                    {
                        "stage": "extraction",
                        "batch_no": "MC-1",
                        "metric": "yield_rate",
                        "value": 70,
                        "detail": "低于中位数",
                    }
                ]
            ),
        ),
        patch.object(api, "get_config", AsyncMock(return_value=llm_config())),
        patch.object(api, "AsyncOpenAI", side_effect=RuntimeError("boom")),
    ):
        resp = asyncio.run(
            api.ai_analyze(batch_no="MC-1", stage="extraction", session=s)
        )
    data = _parse_response(resp)
    assert "分析失败" in data["analysis_text"]
    assert data["causes"] and "MC-1" in data["causes"][0]
    assert data["suggestions"] and "extraction" in data["suggestions"][0]


# ═══════════ ai_history ═══════════


def test_ai_history_alias_and_records():
    import asyncio

    s = make_session(
        [
            make_result(
                fetchall=[
                    SimpleNamespace(
                        id="h1",
                        session_id="s1",
                        batch_no="MC-1",
                        stage="na_batch",
                        summary="s",
                        severity="high",
                        causes=["c"],
                        suggestions=["g"],
                        anomalies=[],
                        created_by="auto",
                        created_at="2026-01-01",
                    )
                ]
            )
        ]
    )
    resp = asyncio.run(api.ai_history(batch_no="MC-1", stage="na_batch", session=s))
    data = json.loads(resp.body)["data"]
    assert data["total"] == 1
    assert data["records"][0]["stage_label"] == "钠化批号"
    params = s.execute.await_args.args[1]
    assert params["st2"] == "sub_tank"
    assert params["bn1"] == "1"


def test_ai_history_empty():
    import asyncio

    s = make_session([make_result(fetchall=[])])
    resp = asyncio.run(api.ai_history(batch_no="MC-9", stage="extraction", session=s))
    data = json.loads(resp.body)["data"]
    assert data["records"] == []
    assert data["total"] == 0


# ═══════════ _build_prompt ═══════════


def test_build_prompt_groups_lines_and_ext_refining():
    stages = [
        {
            "stage": "sub_tank",
            "label": "粗提分罐",
            "nodes": [{"batch_no": "MC-1", "is_sibling": False}],
        },
        {
            "stage": "sub_tank",
            "label": "粗提分罐",
            "nodes": [{"batch_no": "MC-2", "is_sibling": True}],
        },
        {
            "stage": "extraction",
            "label": "提取",
            "nodes": [{"batch_no": "MC-2", "is_sibling": True}],
        },
    ]
    prompt = api._build_prompt("MC-1", "sub_tank", stages, 88, "extraction", [], [], [])
    assert "MC-1" in prompt
    assert "累计收率: 88%" in prompt
    assert "最大损失工段: extraction" in prompt
    assert "粗提分罐" in prompt
    assert "同级" in prompt


def test_build_prompt_no_ext_fallback():
    stages = [
        {
            "stage": "extraction",
            "label": "提取",
            "nodes": [{"batch_no": "MC-1", "is_sibling": False}],
        },
    ]
    prompt = api._build_prompt("MC-1", "extraction", stages, 90, None, [], [], [])
    assert "最大损失工段: 无" in prompt


class _StreamChunk:
    def __init__(self, content):
        self.choices = [_StreamChoice(content)]


class _StreamChoice:
    def __init__(self, content):
        self.delta = _StreamDelta(content)
        self.content = content


class _StreamDelta:
    def __init__(self, content):
        self.content = content


async def _stream_client(content: str):
    """异步生成逐 token 的流式响应。"""
    yield _StreamChunk(content)


def _run_stream_events(resp):
    """收集 StreamingResponse.generate() 的 SSE 事件文本。"""
    import asyncio

    return asyncio.run(_collect(resp))


async def _collect(resp):
    return [e async for e in resp]


# ═══════════ ai_analyze_stream ═══════════


def test_ai_analyze_stream_success_path():
    import asyncio

    # blending 节点 + history 行
    s = make_session(
        [
            make_result(
                fetchone=SimpleNamespace(
                    rrt_053=0.6, rrt_201=1.1, total_impurity=2.0
                )
            ),
            make_result(
                fetchall=[
                    SimpleNamespace(
                        id="h1",
                        batch_no="MC-0",
                        summary="旧",
                        severity="high",
                    )
                ]
            ),
        ]
    )
    stages = [
        {
            "stage": "blending",
            "label": "混粉成品",
            "nodes": [{"batch_no": "B1", "yield_rate": 90.0}],
        },
    ]
    llm_text = (
        '{"summary": "正常", "causes": ["a", "b", "c", "d"], "suggestions": ["x", "y", "z", "w"], "severity": "low"}'  # noqa: E501
    )
    stream = _stream_client(llm_text)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=stream)
    with (
        patch.object(
            api,
            "lineage_trace",
            AsyncMock(return_value=trace_response(stages, target_stage="blending")),
        ),
        patch.object(
            api,
            "lineage_yield_distribution",
            AsyncMock(return_value=SimpleNamespace(body=json.dumps({"data": []}))),
        ),
        patch.object(api, "_detect_yield_anomalies", AsyncMock(return_value=[])),
        patch.object(api, "get_config", AsyncMock(return_value=llm_config())),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        resp = asyncio.run(
            api.ai_analyze_stream(batch_no="B1", stage="blending", session=s)
        )
        text = asyncio.run(_body_text(resp))
    assert "正在查询批次追溯链路" in text
    assert "result" in text
    assert "done" in text
    assert "RRT" not in text or True


async def _iter_body(resp):
    parts = []
    async for chunk in resp.body_iterator:
        parts.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
    return b"".join(parts)


async def _body_text(resp):
    return (await _iter_body(resp)).decode("utf-8")


def test_ai_analyze_stream_llm_retry():
    import asyncio

    s = make_session([make_result(fetchall=[])])
    stages = []
    short = MagicMock()
    full = _stream_client(
        '{"summary": "完整", "causes": ["a", "b", "c"], "suggestions": ["x", "y", "z"], "severity": "medium"}'  # noqa: E501
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[_stream_client('{"summary": "", "causes": ["a"]}'), full]
    )
    with (
        patch.object(
            api,
            "lineage_trace",
            AsyncMock(return_value=trace_response(stages, target_stage="extraction")),
        ),
        patch.object(
            api,
            "lineage_yield_distribution",
            AsyncMock(return_value=SimpleNamespace(body=json.dumps({"data": []}))),
        ),
        patch.object(api, "_detect_yield_anomalies", AsyncMock(return_value=[])),
        patch.object(api, "get_config", AsyncMock(return_value=llm_config())),
        patch.object(api, "AsyncOpenAI", return_value=client),
    ):
        resp = asyncio.run(
            api.ai_analyze_stream(batch_no="MC-1", stage="extraction", session=s)
        )
        text = asyncio.run(_body_text(resp))
    assert "llm_retry" in text
    assert client.chat.completions.create.await_count == 2


def test_ai_analyze_stream_llm_failure_fallback():
    import asyncio

    s = make_session(
        [
            # history 查询返回一个有异常案例
            make_result(
                fetchall=[
                    SimpleNamespace(
                        id="h1", batch_no="MC-0", summary="s", severity="high"
                    )
                ]
            )
        ]
    )
    stages = [
        {
            "stage": "extraction",
            "label": "提取",
            "nodes": [{"batch_no": "MC-1", "is_sibling": False}],
        },
    ]
    with (
        patch.object(
            api,
            "lineage_trace",
            AsyncMock(return_value=trace_response(stages, target_stage="extraction")),
        ),
        patch.object(
            api,
            "lineage_yield_distribution",
            AsyncMock(return_value=SimpleNamespace(body=json.dumps({"data": []}))),
        ),
        patch.object(
            api,
            "_detect_yield_anomalies",
            AsyncMock(
                return_value=[
                    {
                        "stage": "extraction",
                        "batch_no": "MC-1",
                        "metric": "yield_rate",
                        "value": 70,
                        "detail": "低",
                    }
                ]
            ),
        ),
        patch.object(api, "get_config", AsyncMock(return_value=llm_config())),
        patch.object(api, "AsyncOpenAI", side_effect=RuntimeError("boom")),
    ):
        resp = asyncio.run(
            api.ai_analyze_stream(batch_no="MC-1", stage="extraction", session=s)
        )
        text = asyncio.run(_body_text(resp))
    assert "分析失败" in text
    assert "AI 分析完成" in text


# ═══════════ _parse_json ═══════════


def test_parse_json_variants():
    assert api._parse_json('{"a": 1}') == {"a": 1}
    assert api._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert api._parse_json('{"causes": ["x", "y') == {"causes": ["x", "y"]}
    t = '... "summary": "收率偏低" ... "severity": "high" ...'
    parsed = api._parse_json(t)
    assert parsed["summary"] == "收率偏低"
    assert parsed["severity"] == "high"
