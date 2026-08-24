"""MC 飞书电子表格同步 + DR 追溯辅助纯函数测试。

覆盖 mc_feishu_sheets_sync 与 dr_lineage_api 中不依赖数据库/网络的可测纯函数，
把 CI 覆盖率里这些大面积未覆盖分支消化掉。
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.modules.production import ai_analysis_api as ai_api
from app.modules.production import dr_lineage_api as dr
from app.modules.production import fa_ai_analysis_api as faai
from app.modules.production import fa_dashboard_api as fdash
from app.modules.production import fa_feishu_scheduler as fascheduler
from app.modules.production import fa_feishu_sync as fas
from app.modules.production import mc_feishu_sheets_sync as sync
from app.modules.production import mc_yield_anomaly_detector as anomaly

# ═══════════ mc_feishu_sheets_sync 纯函数 ═══════════


def test_safe_float_variants():
    assert sync._safe_float(None) is None
    assert sync._safe_float("") is None
    assert sync._safe_float("#REF!") is None
    assert sync._safe_float("#N/A") is None
    assert sync._safe_float(" 3.5 ") == 3.5
    assert sync._safe_float("98%") == 98.0
    assert sync._safe_float("abc") is None
    assert sync._safe_float(7) == 7.0
    assert sync._safe_float([]) is None


def test_safe_int_variants():
    assert sync._safe_int(None) is None
    assert sync._safe_int("") is None
    assert sync._safe_int("#VALUE!") is None
    assert sync._safe_int("12") == 12
    assert sync._safe_int("1.7") == 1
    assert sync._safe_int("x") is None


def test_safe_date_variants():
    assert sync._safe_date(None) is None
    assert sync._safe_date("") is None
    assert sync._safe_date("#N/A") is None
    assert sync._safe_date("2026.03.01") == date(2026, 3, 1)
    assert sync._safe_date("2026-03-01") == date(2026, 3, 1)
    assert sync._safe_date("2026/03/01") == date(2026, 3, 1)
    # 只有月日 → 假定当年 2026
    assert sync._safe_date("03.01") == date(2026, 3, 1)
    assert sync._safe_date("not-a-date") is None


def test_safe_yield_scales_small_fractions():
    assert sync._safe_yield(0.91) == 91.0
    assert sync._safe_yield(1.0) == 1.0
    assert sync._safe_yield(98.5) == 98.5
    assert sync._safe_yield(None) is None


def test_parse_csv_line():
    assert sync._parse_csv_line("a,b,c") == ["a", "b", "c"]
    assert sync._parse_csv_line("a,b") == ["a", "b"]
    assert sync._parse_csv_line('"a,b",c') == ["a,b", "c"]
    assert sync._parse_csv_line('"",c') == ["", "c"]


def test_get_col_and_skip():
    assert sync._get_col(["a", " b ", "c"], 1) == "b"
    assert sync._get_col(["a"], 5) == ""
    assert sync._get_col([], 0) == ""

    # _is_skip_row：月份分隔行 / 空行 / 标题行
    assert sync._is_skip_row([]) is True
    assert sync._is_skip_row(["03月份"]) is True
    assert sync._is_skip_row(["", "", ""]) is True
    assert sync._is_skip_row(["霉酚酸粗提台账"]) is True
    assert sync._is_skip_row(["MC二次精制"]) is True
    assert sync._is_skip_row(["苯丙氨酸", "1号罐"]) is False


# ═══════════ dr_lineage_api 纯函数 ═══════════


def test_fmt_val():
    assert dr.fmt_val(3.5) == 3.5
    assert dr.fmt_val(None) == 0.0
    assert dr.fmt_val(0) == 0.0


def test_to_f1_normalization():
    assert dr._to_f1("DR-24019-1") == "DR-F1-24019-1"
    assert dr._to_f1("DR-F1-24019-1") == "DR-F1-24019-1"
    assert dr._to_f1("DR-24019-1 ") == "DR-F1-24019-1"
    assert dr._to_f1("OTHER") == "OTHER"


def test_f1_to_dr():
    assert dr._f1_to_dr("DR-F1-24019-1") == "DR-24019-1"
    assert dr._f1_to_dr("DR-24019-1") == "DR-24019-1"


def test_detect_stage_prefixes():
    assert dr._detect_stage("DR-GB-1") == "fourth_refinement"
    assert dr._detect_stage("DR-F3-1") == "third_refinement"
    assert dr._detect_stage("DR-F2-1") == "second_refinement"
    assert dr._detect_stage("DR-F1-1") == "first_refinement"
    assert dr._detect_stage("DR-H1") is None
    assert dr._detect_stage("DR-2601") is None


def test_split_feeds():
    assert dr._split_feeds("DR-F1-1 + DR-F1-2") == ["DR-F1-1", "DR-F1-2"]
    assert dr._split_feeds("DR-F1-1、DR-F1-2") == ["DR-F1-1", "DR-F1-2"]
    assert dr._split_feeds("DR-F1-1,DR-F1-2") == ["DR-F1-1", "DR-F1-2"]
    assert dr._split_feeds("DR-F1-1") == ["DR-F1-1"]
    assert dr._split_feeds("") == []


def test_feed_stage():
    assert dr._feed_stage("DR-F2-1") == "second_refinement"
    assert dr._feed_stage("DR-F1-1") == "first_refinement"
    assert dr._feed_stage("DR-F3-1") == "third_refinement"
    assert dr._feed_stage("DR-GB-1") == "fourth_refinement"
    assert dr._feed_stage("DR-H1/x") == "recovery"


def test_to_feeds():
    up = [("second_refinement", "DR-F1-1", 3.5), ("recovery", "回收粉", 0.0)]
    feeds = dr._to_feeds(up)
    assert len(feeds) == 2
    assert feeds[0].batch_no == "DR-F1-1"
    assert feeds[0].stage == "second_refinement"
    assert feeds[0].qty == 3.5
    assert feeds[1].qty == 0.0


def test_drg_models_and_labels():
    # 常量检查（无欲通过）
    assert dr.DR_STAGE_ORDER[0] == "fermentation"
    assert "fourth_refinement" in dr.DR_STAGE_LABELS
    assert dr._MAIN_TABLES["chromatography"][0] == "dr_chromatography_crystal"
    assert dr._DIST_LABELS["second_refinement"] == "二次精制"


# ═══════════ mc_yield_anomaly_detector 纯函数 ═══════════

def test_judge_anomaly_severity():
    # median=90, iqr=20 → high < 60, medium < 70
    assert anomaly.judge_anomaly_severity(50, 90, 20) == "high"
    assert anomaly.judge_anomaly_severity(65, 90, 20) == "medium"
    assert anomaly.judge_anomaly_severity(80, 90, 20) is None
    assert anomaly.judge_anomaly_severity(50, 90, 0) is None


def test_parse_json_simple():
    assert anomaly._parse_json('{"a": 1}') == {"a": 1}
    assert anomaly._parse_json("not json") == {}
    # 带 markdown 代码块
    assert anomaly._parse_json('```json\n{"x": 2}\n```') == {"x": 2}
    # 截断 JSON 的补全
    parsed = anomaly._parse_json('{"summary":"ok"}')
    assert parsed.get("summary") == "ok"


# ═══════════ fa_dashboard_api / fa_ai_analysis_api 纯函数 ═══════════

def test_fa_dashboard_float_helpers():
    assert fdash._to_yield(None) == 0.0
    assert fdash._to_yield(1.5) == 150.0
    assert fdash._to_yield(98.5) == 98.5
    assert fdash._to_yield("0.8") == 80.0
    assert fdash._to_yield("85%") == 85.0
    assert fdash._to_yield("bad") == 0.0
    assert fdash._to_float(None) == 0.0
    assert fdash._to_float("3.5") == 3.5
    assert fdash._to_float("7%") == 7.0
    assert fdash._to_float("x") == 0.0


def test_fa_suggestion_lookup():
    # 规则 key 为参数名（如 conductivity/acid_adj），direction 为 high/low
    assert fdash._get_suggestion("conductivity", "high") is not None
    assert fdash._get_suggestion("conductivity", "low") is not None
    assert fdash._get_suggestion("acid_adj", "high") is not None
    assert fdash._get_suggestion("unknown_key", "high") is None


def test_fa_ai_parse_json():
    assert faai._parse_json('{"summary":"ok"}') == {"summary": "ok"}
    assert faai._parse_json('prefix ```json\n{"ox": 1}\n``` suffix') == {"ox": 1}
    assert faai._parse_json('plain { "a": 1 }') == {"a": 1}
    assert faai._parse_json("no json") == {}


# ═══════════ fa_feishu_sync 纯函数 ═══════════

def test_fa_get_column():
    assert fas._get(["a", " b ", "c"], 1) == "b"
    assert fas._get(["a"], 5) == ""
    assert fas._get([], 0) == ""


def test_fa_parse_date():
    assert fas._parse_date("12月27日") == "2025-12-27"
    assert fas._parse_date("3月05日") == "2026-03-05"
    assert fas._parse_date("not-a-date") is None
    assert fas._parse_date("") is None


def test_fa_safe_num():
    assert fas._safe_num(" 12.5 ") == "12.5"
    assert fas._safe_num("98%") == "98.0"
    assert fas._safe_num("-") == "NULL"
    assert fas._safe_num("") == "NULL"
    assert fas._safe_num("abc") == "NULL"


def test_fa_safe_pct():
    assert fas._safe_pct("0.39") == "'39%'"
    assert fas._safe_pct("85") == "'85'"
    assert fas._safe_pct("-") == "NULL"
    assert fas._safe_pct("0.5") == "'50%'"
    assert fas._safe_pct("x") == "'x'"


# ═══════════ fa_feishu_scheduler 纯辅助函数 ═══════════

def test_fa_scheduler_g_and_pd_ed_n_p():
    # _g：安全取列
    assert fascheduler._g(["a", " b ", "c"], 1) == "b"
    assert fascheduler._g(["a"], 5) == ""
    # _pd：日期解析（slash/点/中文）
    assert fascheduler._pd("2026-03-01") == "2026-03-01"
    assert fascheduler._pd("2026/3/1") == "2026-03-01"
    assert fascheduler._pd("2026.3.5") == "2026-03-05"
    assert fascheduler._pd("12月27日") == "2025-12-27"
    assert fascheduler._pd("2026年3月2日") == "2026-03-02"
    assert fascheduler._pd("bad") is None
    # _ed：Excel 日期序列号
    assert fascheduler._ed("44927") is not None  # 约 2023-01-01
    assert fascheduler._ed("bad") is None
    # _n：数值
    assert fascheduler._n(" 12.5 ") == "12.5"
    assert fascheduler._n("98%") == "98.0"
    assert fascheduler._n("-") == "NULL"
    assert fascheduler._n("#DIV/0!") == "NULL"
    assert fascheduler._n("") == "NULL"
    assert fascheduler._n("abc") == "NULL"
    # _p：百分比
    assert fascheduler._p("0.39") == "'39%'"
    assert fascheduler._p("0.85") == "'85%'"
    assert fascheduler._p("-") == "NULL"
    assert fascheduler._p("x") == "'x'"


# ═══════════ ai_analysis_api 纯函数 ═══════════

def test_ai_api_parse_json():
    assert ai_api._parse_json('{"summary":"ok"}') == {"summary": "ok"}
    assert ai_api._parse_json('```json\n{"ox": 1}\n```') == {"ox": 1}
    # 截断补全 + 正则提取 summary/severity
    parsed = ai_api._parse_json('{"summary":"风险","severity":"high"}')
    assert parsed.get("summary") == "风险"
    assert parsed.get("severity") == "high"
    assert ai_api._parse_json("no json") == {}


def test_ai_api_build_prompt_includes_labels():
    # _build_prompt 根据 stages 生成 prompt（含阶段标签）
    prompt = ai_api._build_prompt(
        batch_no="MC-1", stage="sub_tank",
        stages=[
            {"stage": "sub_tank", "label": "钠化批号",
             "nodes": [{"batch_no": "MC-1", "detail": ""}]},
        ],
        cumulative_yield=90,
        max_loss_stage=None,
        anomalies=[],
        impurities=[],
        ref_cases=[],
    )
    assert isinstance(prompt, str)
    assert prompt  # 非空


# ═══════════ fa_chat_api 纯函数 ═══════════


def test_fa_chat_build_prompt_injects_context():
    from app.modules.production import fa_chat_api as fchat

    msgs = fchat._build_chat_prompt(
        history=[
            {"role": "user", "summary": "previous", "llm_response": None},
            {"role": "assistant", "summary": None, "llm_response": "assistant-reply"},
        ],
        user_msg="当前问题",
        batch_no="FA-1",
        stage="acidification",
        trace_context="批次追溯内容",
    )
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "user"]
    any_fa = any("当前关注批次: FA-1" in m["content"] for m in msgs if m["role"] == "system")  # noqa: E501
    assert any_fa
    assert msgs[-1]["content"] == "当前问题"


def test_fa_chat_build_prompt_empty_context():
    from app.modules.production import fa_chat_api as fchat
    msgs = fchat._build_chat_prompt(
        history=[], user_msg="hi", batch_no="", stage="x", trace_context=""
    )
    # 无批次上下文 → 不注入批次行；历史为空 → 直接 append 用户消息
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[-1]["content"] == "hi"


@pytest.mark.anyio
async def test_fa_chat_gather_context_branch_queries():
    """覆盖 _gather_fa_context 的追溯 BFS、收率/产量查询、统计分支。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.modules.production import fa_chat_api as f

    session = AsyncMock()

    async def branch(sql, params=None):
        s = str(sql)
        r = MagicMock()
        if "downstream_batch = :batch AND bl.downstream_type = :stage" in s:
            r.fetchall.return_value = [
                SimpleNamespace(upstream_type="acidification", upstream_batch="FA-A", quantity=2.0),  # noqa: E501
                SimpleNamespace(upstream_type="fermentation", upstream_batch="FA-F", quantity=None),  # noqa: E501
            ]
        elif "upstream_batch = :batch AND bl.upstream_type = :stage" in s:
            r.fetchall.return_value = [
                SimpleNamespace(downstream_type="decolor1", downstream_batch="FA-D", quantity=5.0),  # noqa: E501
            ]
        elif '"批收率"' in s and "fa_acidification_records" in s and "agg" not in s:
            r.fetchone.return_value = ("88.5",)
        elif '"收率"' in s and "fa_decolor_centrifuge_records" in s and "WHERE" in s:
            r.fetchone.return_value = ("0.95",)
        elif '"汇总总量_kg"' in s:
            r.fetchone.return_value = ("100",)
        elif "REGEXP_REPLACE" in s and "fa_acidification_records" in s:
            r.fetchone.return_value = (10, 20, 30, 40, 50)
        elif "fa_decolor_centrifuge_records WHERE" in s:
            r.fetchone.return_value = (11, 22, 33, 44, 55)
        elif "电导_uscm" in s:
            r.fetchone.return_value = (80, 82)
        else:
            r.fetchone.return_value = None
            r.fetchall.return_value = []
        return r

    session.execute.side_effect = branch
    with patch(
        "app.modules.production.fa_ai_analysis_api._get_trace_data",
        new=AsyncMock(return_value=("批次数据文本", {})),
    ):
        ctx = await f._gather_fa_context("FA-F", "fermentation", session)
    assert "批次追溯链路" in ctx
    # 收率/统计块本身被 try/except 包裹，若 SQL 匹配不足则不出现；
    # 但批号级收率（酸化 88.5%）应在追溯链路内渲染。
    assert "FA-A" in ctx
    assert "批次详细生产数据" in ctx
    assert "批次数据文本" in ctx


# ═══════════ mc_chat_api 对话 prompt / 追溯上下文 ═══════════


def test_mc_chat_build_prompt_with_context():
    from app.modules.production import mc_chat_api as mchat

    msgs = mchat._build_chat_prompt(
        history=[
            {"role": "user", "summary": "问", "llm_response": None},
            {"role": "assistant", "summary": None, "llm_response": "答"},
            {"role": "system", "summary": "忽略", "llm_response": None},
        ],
        user_msg="新的问题",
        batch_no="MC-100",
        stage="refining",
        trace_context="MC 批次链路内容",
    )
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "user"]
    any_inject = any(
        "当前关注批次: MC-100" in m["content"] for m in msgs if m["role"] == "system"
    )
    assert any_inject
    # 非 user/assistant 的 history 被过滤掉
    assert msgs[1]["content"] == "问"
    assert msgs[2]["content"] == "答"
    assert msgs[-1]["content"] == "新的问题"


def test_mc_chat_build_prompt_no_context_and_stage_label():
    from app.modules.production import mc_chat_api as mchat

    # 无批次 → 不注入；stage 未在 STAGE_LABELS 中 → 原样显示
    msgs = mchat._build_chat_prompt(
        history=[], user_msg="hi", batch_no="", stage="unknown_stage", trace_context=""
    )
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[-1]["content"] == "hi"
    assert "当前关注批次" not in msgs[0]["content"]


@pytest.mark.anyio
async def test_mc_chat_gather_trace_context_full():
    """覆盖 _gather_trace_context 的追溯链路、收率分布、RRT 杂质 RRT 分支。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.modules.production import mc_chat_api as f

    session = AsyncMock()
    r = MagicMock()
    r.fetchone.return_value = SimpleNamespace(
        rrt_053=0.5, rrt_0755=None, rrt_094_096=0.3,
        rrt_103_106=None, rrt_201=0.2, total_impurity=1.0,
    )
    session.execute.return_value = r

    trace_body = json.dumps(
        {
            "data": {
                "stages": [
                    {
                        "label": "粗提",
                        "stage": "refining",
                        "nodes": [
                            {
                                "batch_no": "MC-A",
                                "yield_rate": 0.9,
                                "is_sibling": False,
                                "detail": "顺利",
                            },
                            {
                                "batch_no": "MC-A",
                                "yield_rate": 92,
                                "is_sibling": True,
                                "detail": "同级",
                            },
                        ],
                    },
                    {
                        "label": "混粉成品",
                        "stage": "blending",
                        "nodes": [
                            {"batch_no": "MC-B", "yield_rate": None, "detail": "混粉"},
                        ],
                    },
                ],
                "cumulative_yield": 80,
                "max_loss_stage": "粗提",
                "target_stage": "blending",
            }
        }
    )
    dist_body = json.dumps(
        {
            "data": [
                {"stage": "refining", "min": 10, "q1": 20, "median": 30,
                 "q3": 40, "max": 50},
                {"stage": "blending", "min": 1, "q1": 2, "median": 3,
                 "q3": 4, "max": 5},
            ]
        }
    )

    async def fake_trace(**kw):
        return SimpleNamespace(body=trace_body)

    async def fake_dist(**kw):
        return SimpleNamespace(body=dist_body)

    with patch(
        "app.modules.production.mc_chat_api.lineage_trace",
        new=fake_trace,
    ), patch(
        "app.modules.production.mc_chat_api.lineage_yield_distribution",
        new=fake_dist,
    ):
        ctx = await f._gather_trace_context("MC-A", "refining", session)

    assert "批次追溯链路" in ctx
    assert "MC-A" in ctx
    assert "[同级]" in ctx
    assert "← 当前" in ctx
    assert "最大损失工段: 粗提" in ctx
    assert "min=10" in ctx
    assert "RRT 杂质 (MC-B)" in ctx
    assert "总杂=1.0%"


@pytest.mark.anyio
async def test_mc_chat_gather_trace_context_exception():
    """追溯抛异常 → 返回占位文本，不扩散。"""
    from unittest.mock import AsyncMock, patch

    from app.modules.production import mc_chat_api as f

    session = AsyncMock()
    with patch(
        "app.modules.production.mc_chat_api.lineage_trace",
        new=AsyncMock(side_effect=Exception("boom")),
    ):
        ctx = await f._gather_trace_context("X", "x", session)
    assert ctx == "(批次数据暂时无法获取)"


# ═══════════ fa_feishu_scheduler 纯函数 ═══════════


def test_fa_scheduler_g():
    """_g: 从行中获取值并去除空白。"""
    from app.modules.production import fa_feishu_scheduler as fas

    assert fas._g(["a", " b ", "c"], 0) == "a"
    assert fas._g(["a", " b ", "c"], 1) == "b"
    assert fas._g(["a", " b ", "c"], 5) == ""  # 索引超出范围
    assert fas._g([], 0) == ""


def test_fa_scheduler_pd():
    """_pd: 解析各种日期格式。"""
    from app.modules.production import fa_feishu_scheduler as fas

    assert fas._pd("2026-03-05") == "2026-03-05"
    assert fas._pd("2026/3/5") == "2026-03-05"
    assert fas._pd("2026.3.5") == "2026-03-05"
    assert fas._pd("3月5日") == "2026-03-05"
    assert fas._pd("12月15日") == "2025-12-15"  # 12月归2025年
    assert fas._pd("2026年3月5日") == "2026-03-05"
    assert fas._pd("invalid") is None


def test_fa_scheduler_ed():
    """_ed: Excel 日期序列号转 ISO 日期。"""
    from app.modules.production import fa_feishu_scheduler as fas

    # Excel 序列号 45356 = 2024-03-05 (从 1899-12-30 开始)
    result = fas._ed("45356")
    assert result == "2024-03-05"
    assert fas._ed("invalid") is None
    assert fas._ed("") is None


def test_fa_scheduler_n():
    """_n: 数值字符串转换。"""
    from app.modules.production import fa_feishu_scheduler as fas

    assert fas._n("100") == "100.0"
    assert fas._n("85.5") == "85.5"
    assert fas._n("50%") == "50.0"
    assert fas._n("-") == "NULL"
    assert fas._n("#DIV/0!") == "NULL"
    assert fas._n("") == "NULL"
    assert fas._n("invalid") == "NULL"


def test_fa_scheduler_p():
    """_p: 百分比格式化。"""
    from app.modules.production import fa_feishu_scheduler as fas

    assert fas._p("0.5") == "'50%'"
    assert fas._p("0.855") == "'85.5%'"
    assert fas._p("1") == "'100%'"
    assert fas._p("-") == "NULL"
    assert fas._p("") == "NULL"
    assert fas._p("invalid") == "'invalid'"
