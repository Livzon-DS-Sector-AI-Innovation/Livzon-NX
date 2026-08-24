"""MC 收率异常自动检测引擎测试（纯规则 + 可 mock 的 SQL 路径）。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.production import mc_yield_anomaly_detector as det


def make_result(fetchall=None, fetchone=None):
    r = MagicMock()
    if fetchall is not None:
        r.fetchall.return_value = fetchall
    if fetchone is not None:
        r.fetchone.return_value = fetchone
    return r


def make_session(execute_results=None):
    s = AsyncMock()
    if execute_results is None:
        s.execute.return_value = make_result(fetchall=[])
    else:
        s.execute.side_effect = execute_results
    s.add = MagicMock()
    s.commit = AsyncMock()
    return s


# ═══════════ _parse_json ═══════════


def test_parse_json_variants():
    assert det._parse_json('{"a": 1}') == {"a": 1}
    assert det._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert det._parse_json('```\n{"a": 1}\n```') == {"a": 1}
    assert det._parse_json('prefix {"a": 1} suffix') == {}
    # 截断修复：常见后缀补全
    assert det._parse_json('{"a": 1') == {"a": 1}
    assert det._parse_json('{"causes": ["x", "y') == {"causes": ["x", "y"]}


def test_parse_json_regex_fallback():
    t = '... "summary": "收率偏低" ... "severity": "high" ... "causes": ["a", "b", "c"] ...'  # noqa: E501
    parsed = det._parse_json(t)
    assert parsed["summary"] == "收率偏低"
    assert parsed["severity"] == "high"
    assert parsed["causes"] == ["causes", "a", "b", "c"]
    assert det._parse_json("完全不可解析") == {}


# ═══════════ judge_anomaly_severity ═══════════


def test_judge_anomaly_severity():
    assert det.judge_anomaly_severity(80, 90, 10) is None  # 正常
    assert det.judge_anomaly_severity(79, 90, 10) == "medium"  # < median - IQR
    assert det.judge_anomaly_severity(74, 90, 10) == "high"  # < median - 1.5*IQR
    assert det.judge_anomaly_severity(90, 90, 10) is None
    assert det.judge_anomaly_severity(85, 90, 5) is None  # 边界：= median - IQR
    assert det.judge_anomaly_severity(82, 90, 5) == "high"  # 边界：< median - 1.5*IQR
    assert det.judge_anomaly_severity(80, 90, 0) is None  # IQR<=0 跳过


# ═══════════ _build_auto_detect_prompt ═══════════


def _iqr_stats(**over):
    base = {
        "n": 12,
        "median": 90.0,
        "q1": 85.0,
        "q3": 95.0,
        "iqr": 10.0,
        "window_start": "2026-01-01",
        "window_end": "2026-03-31",
    }
    base.update(over)
    return base


def test_build_auto_detect_prompt_full():
    prompt = det._build_auto_detect_prompt(
        "MC-1",
        "sub_tank",
        80.0,
        "high",
        _iqr_stats(),
        {"count": 3, "avg": 88.0, "min": 86.0, "max": 90.0},
        [
            {"batch_no": "MC-2", "yield_rate": 91.0},
            {"batch_no": "MC-3", "yield_rate": 89.5},
        ],
        [
            {
                "downstream_type": "extraction",
                "downstream_batch": "MC-E1",
                "yield_rate": 78.0,
                "stage_mean": 85.0,
                "stage_n": 8,
            }
        ],
        [{"id": "a1", "batch_no": "MC-9", "summary": "前次异常", "severity": "high"}],
    )
    assert "粗提分罐" in prompt
    assert "MC-1" in prompt
    assert "high" in prompt
    assert "移动窗口: 2026-01-01 → 2026-03-31" in prompt
    assert "窗口内批次: 12 条" in prompt
    assert "同收率范围(±2%)历史批次" in prompt
    assert "同工段/设备近3月收率趋势" in prompt
    assert "下游工段收率对比" in prompt
    assert "MC-E1" in prompt
    assert "历史类似案例" in prompt
    assert "MC-9" in prompt
    assert "只返回JSON" in prompt


def test_build_auto_detect_prompt_empty_sections():
    prompt = det._build_auto_detect_prompt(
        "MC-1",
        "extraction",
        80.0,
        "medium",
        _iqr_stats(n=5),
        {"count": 0, "avg": 0, "min": 0, "max": 0},
        [],
        [],
        [],
    )
    assert "同收率范围" not in prompt
    assert "该批次暂无下游数据" in prompt
    assert "首次检测" in prompt
    assert "提取" in prompt


# ═══════════ SQL 查询函数 ═══════════


def test_compute_stage_iqr_extraction():
    import asyncio

    s = make_session(
        [make_result(fetchone=SimpleNamespace(n=10, q1=85.0, median=90.0, q3=95.0))]
    )

    async def _run():
        return await det._compute_stage_iqr(s, "extraction", date(2026, 3, 15))

    result = asyncio.run(_run())
    assert result["n"] == 10
    assert result["median"] == 90.0
    assert result["iqr"] == 10.0
    assert result["window_end"] == "2026-03-15"
    assert "2025-12" in result["window_start"]


def test_compute_stage_iqr_default_date_and_sub_tank():
    import asyncio

    s = make_session(
        [make_result(fetchone=SimpleNamespace(n=3, q1=0.0, median=0.0, q3=0.0))]
    )
    result = asyncio.run(det._compute_stage_iqr(s, "sub_tank", None))
    assert result["n"] == 3
    assert result["window_end"] == date.today().isoformat()


def test_compute_similar_range():
    import asyncio

    s = make_session(
        [
            make_result(
                fetchone=SimpleNamespace(cnt=5, avg_yr=87.5, min_yr=85.0, max_yr=90.0)
            )
        ]
    )
    result = asyncio.run(det._compute_similar_range(s, "extraction", 88.0))
    assert result == {"count": 5, "avg": 87.5, "min": 85.0, "max": 90.0}


def test_compute_equipment_trend_without_tank():
    import asyncio

    s = make_session(
        [
            make_result(
                fetchall=[
                    SimpleNamespace(batch_no="MC-1", yield_rate=90.0),
                    SimpleNamespace(batch_no="MC-2", yield_rate=88.0),
                ]
            )
        ]
    )
    result = asyncio.run(det._compute_equipment_trend(s, "extraction", "MC-1"))
    assert result == [
        {"batch_no": "MC-1", "yield_rate": 90.0},
        {"batch_no": "MC-2", "yield_rate": 88.0},
    ]


def test_compute_equipment_trend_refinement_tank_filter():
    import asyncio

    s = make_session(
        [
            make_result(
                fetchone=SimpleNamespace(
                    dissolution_tank="T1", crystallization_tank=None
                )
            ),
            make_result(fetchall=[SimpleNamespace(batch_no="MC-3", yield_rate=91.0)]),
        ]
    )
    result = asyncio.run(det._compute_equipment_trend(s, "refinement", "MC-3"))
    assert result == [{"batch_no": "MC-3", "yield_rate": 91.0}]
    # 验证 tank 参数被传入
    params = s.execute.call_args_list[1].args[1]
    assert params["tank"] == "T1"


def test_compute_downstream_comparison():
    import asyncio

    s = make_session(
        [
            make_result(
                fetchall=[
                    SimpleNamespace(
                        downstream_type="extraction",
                        downstream_batch="MC-E1",
                        ds_yield=78.0,
                    ),
                    SimpleNamespace(
                        downstream_type="unknown", downstream_batch="X", ds_yield=None
                    ),
                ]
            ),
            make_result(fetchone=SimpleNamespace(mean_yr=85.0, n=8)),
        ]
    )
    result = asyncio.run(det._compute_downstream_comparison(s, "sub_tank", "MC-1"))
    assert result[0] == {
        "downstream_type": "extraction",
        "downstream_batch": "MC-E1",
        "yield_rate": 78.0,
        "stage_mean": 85.0,
        "stage_n": 8,
    }
    assert result[1]["stage_mean"] == 0
    assert result[1]["stage_n"] == 0


def test_get_similar_cases():
    import asyncio

    s = make_session(
        [
            make_result(
                fetchall=[
                    SimpleNamespace(
                        id="abc",
                        batch_no="MC-9",
                        stage="extraction",
                        summary="s",
                        severity="high",
                    ),
                ]
            )
        ]
    )
    result = asyncio.run(det._get_similar_cases(s, "extraction", "high", limit=3))
    assert result == [
        {
            "id": "abc",
            "batch_no": "MC-9",
            "stage": "extraction",
            "summary": "s",
            "severity": "high",
        }
    ]


# ═══════════ _call_llm_and_save ═══════════


def _llm_config():
    return SimpleNamespace(api_base_url="https://mock", api_key="k", model_name="m")


def _chat_mock(content: str):
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    client.chat.completions.create = AsyncMock(return_value=resp)
    return client


def test_call_llm_and_save_success():
    import asyncio

    s = make_session()
    client = _chat_mock(
        '```json\n{"summary": "收率偏低", "causes": ["a", "b", "c"], "suggestions": ["x", "y", "z"], "severity": "high"}\n```'  # noqa: E501
    )
    with (
        patch.object(det, "get_config", AsyncMock(return_value=_llm_config())),
        patch.object(det, "AsyncOpenAI", return_value=client),
    ):
        analysis = asyncio.run(
            det._call_llm_and_save(
                s,
                "MC-1",
                "extraction",
                80.0,
                "high",
                _iqr_stats(),
                {"count": 0},
                [],
                [],
                [],
            )
        )
    assert analysis.summary == "收率偏低"
    assert analysis.causes == ["a", "b", "c"]
    assert analysis.severity == "high"
    assert analysis.created_by == "auto"
    s.add.assert_called_once()
    s.commit.assert_awaited_once()


def test_call_llm_and_save_retries_short_output():
    import asyncio

    s = make_session()
    short_resp = MagicMock()
    short_resp.choices = [MagicMock()]
    short_resp.choices[
        0
    ].message.content = '{"summary": "短", "causes": ["a"], "suggestions": ["x"]}'
    long_resp = MagicMock()
    long_resp.choices = [MagicMock()]
    long_resp.choices[
        0
    ].message.content = (
        '{"summary": "完整", "causes": ["a", "b", "c"], "suggestions": ["x", "y", "z"]}'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=[short_resp, long_resp])
    with (
        patch.object(det, "get_config", AsyncMock(return_value=_llm_config())),
        patch.object(det, "AsyncOpenAI", return_value=client),
    ):
        analysis = asyncio.run(
            det._call_llm_and_save(
                s,
                "MC-1",
                "refinement",
                80.0,
                "medium",
                _iqr_stats(),
                {"count": 0},
                [],
                [],
                [],
            )
        )
    assert analysis.summary == "完整"
    assert len(analysis.causes) == 3
    assert client.chat.completions.create.await_count == 2


def test_call_llm_and_save_failure_fallback():
    import asyncio

    s = make_session()
    with (
        patch.object(det, "get_config", AsyncMock(return_value=_llm_config())),
        patch.object(det, "AsyncOpenAI", side_effect=RuntimeError("boom")),
    ):
        analysis = asyncio.run(
            det._call_llm_and_save(
                s,
                "MC-1",
                "extraction",
                80.0,
                "high",
                _iqr_stats(),
                {"count": 0},
                [],
                [],
                [],
            )
        )
    assert "LLM调用失败" in analysis.summary
    assert any("人工复核" in x for x in analysis.suggestions)
    assert analysis.anomalies[0]["metric"] == "yield_rate"


# ═══════════ run_anomaly_detection 编排 ═══════════


def test_run_anomaly_detection_no_new_batches():
    import asyncio

    s = make_session([make_result(fetchall=[])])
    result = asyncio.run(det.run_anomaly_detection(s))
    assert result == {
        "scanned": 0,
        "detected": 0,
        "high": 0,
        "medium": 0,
        "skipped_normal": 0,
        "errors": 0,
        "details": [],
    }


def test_run_anomaly_detection_insufficient_sample():
    import asyncio

    s = make_session(
        [
            make_result(
                fetchall=[
                    SimpleNamespace(
                        stage="extraction",
                        batch_no="MC-1",
                        yield_rate=80.0,
                        batch_date=date(2026, 3, 1),
                    )
                ]
            ),
            make_result(fetchone=SimpleNamespace(n=2, q1=0.0, median=0.0, q3=0.0)),
        ]
    )
    result = asyncio.run(det.run_anomaly_detection(s))
    assert result["scanned"] == 1
    assert result["skipped_normal"] == 1
    assert result["detected"] == 0


def test_run_anomaly_detection_normal_skipped():
    import asyncio

    s = make_session(
        [
            make_result(
                fetchall=[
                    SimpleNamespace(
                        stage="extraction",
                        batch_no="MC-1",
                        yield_rate=90.0,
                        batch_date=date(2026, 3, 1),
                    )
                ]
            ),
            make_result(fetchone=SimpleNamespace(n=10, q1=85.0, median=90.0, q3=95.0)),
        ]
    )
    result = asyncio.run(det.run_anomaly_detection(s))
    assert result["scanned"] == 1
    assert result["skipped_normal"] == 1
    assert result["detected"] == 0


def test_run_anomaly_detection_full_path():
    import asyncio

    s = make_session()
    s.execute.return_value = make_result(fetchall=[])
    batch = {
        "stage": "extraction",
        "batch_no": "MC-1",
        "yield_rate": 70.0,
        "batch_date": date(2026, 3, 1),
    }
    with (
        patch.object(det, "scan_new_batches", AsyncMock(return_value=[batch])),
        patch.object(
            det,
            "_compute_stage_iqr",
            AsyncMock(return_value=_iqr_stats(n=10, median=90.0, iqr=10.0)),
        ),
        patch.object(
            det,
            "_compute_similar_range",
            AsyncMock(return_value={"count": 0, "avg": 0, "min": 0, "max": 0}),
        ),
        patch.object(det, "_compute_equipment_trend", AsyncMock(return_value=[])),
        patch.object(det, "_compute_downstream_comparison", AsyncMock(return_value=[])),
        patch.object(det, "_get_similar_cases", AsyncMock(return_value=[])),
        patch.object(det, "_call_llm_and_save", AsyncMock(return_value=MagicMock())),
    ):
        result = asyncio.run(det.run_anomaly_detection(s))
    assert result["scanned"] == 1
    assert result["detected"] == 1
    assert result["high"] == 1
    assert result["medium"] == 0
    assert result["details"] == [
        {
            "batch_no": "MC-1",
            "stage": "extraction",
            "severity": "high",
            "yield_rate": 70.0,
        }
    ]


def test_run_anomaly_detection_medium_and_error():
    import asyncio

    s = make_session()
    batches = [
        {
            "stage": "extraction",
            "batch_no": "MC-1",
            "yield_rate": 79.0,
            "batch_date": date(2026, 3, 1),
        },
        {
            "stage": "extraction",
            "batch_no": "MC-2",
            "yield_rate": 50.0,
            "batch_date": date(2026, 3, 1),
        },
    ]

    with (
        patch.object(det, "scan_new_batches", AsyncMock(return_value=batches)),
        patch.object(
            det,
            "_compute_stage_iqr",
            AsyncMock(return_value=_iqr_stats(n=10, median=90.0, iqr=10.0)),
        ),
        patch.object(
            det,
            "_compute_similar_range",
            AsyncMock(return_value={"count": 0, "avg": 0, "min": 0, "max": 0}),
        ),
        patch.object(det, "_compute_equipment_trend", AsyncMock(return_value=[])),
        patch.object(det, "_compute_downstream_comparison", AsyncMock(return_value=[])),
        patch.object(det, "_get_similar_cases", AsyncMock(return_value=[])),
        patch.object(
            det,
            "_call_llm_and_save",
            AsyncMock(side_effect=[MagicMock(), RuntimeError("llm down")]),
        ),
    ):
        result = asyncio.run(det.run_anomaly_detection(s))
    assert result["detected"] == 2
    assert result["medium"] == 1
    assert result["high"] == 1
    assert result["errors"] == 1
    assert len(result["details"]) == 1
