"""FA 加减看板 / 黄金批次 / 批次对比诊断 端点测试（SQL 全 mock）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.production import fa_dashboard_api as fd

# ═══════════ get_fa_dashboard / summary ═══════════


@pytest.mark.anyio
async def test_get_fa_dashboard_summary_full() -> Any:
    """汇总端点全流程：各工段计数、产量、平均收率、达标率、流程监控、趋势。"""
    s = AsyncMock()

    def branch(sql: Any, params: Any=None) -> Any:
        ssql = str(sql)
        r = MagicMock()
        if "SELECT COUNT(1) FROM production.fa_fermentation_batches" in ssql:
            r.scalar.return_value = 3
        elif "SELECT COUNT(1) FROM production.fa_" in ssql:
            r.scalar.return_value = 2
        elif 'COALESCE(SUM("汇总总量_kg")' in ssql:
            r.scalar.return_value = 1000.0
        elif "COALESCE(AVG(" in ssql:
            r.scalar.return_value = 85.5
        elif "COUNT(CASE WHEN" in ssql:
            row = SimpleNamespace(total=6, passed=5)
            r.one.return_value = row
        elif "EXTRACT(MONTH FROM" in ssql:
            rows = [
                SimpleNamespace(m=1, kg=10.0),
                SimpleNamespace(m=5, kg=20.0),
                SimpleNamespace(m=13, kg=99.0),
            ]
            r.__iter__ = lambda _self: iter(rows)
        else:
            r.scalar.return_value = 0
        return r

    s.execute.side_effect = branch
    resp = await fd.get_fa_dashboard(month="2026-05", session=s)
    data = json.loads(resp.body)["data"]
    assert data["_month"] == "2026-05"
    assert data["monthly_output_kg"] == 1000.0
    assert data["avg_yield"] == 85.5
    assert data["pass_rate"] == round(5 / 6 * 100, 1)
    assert data["monthly_batches"] == 3
    assert data["ba_stock_kg"] == 0
    assert len(data["stages"]) == 8
    assert len(data["monthly_trend"]) == 12
    assert data["status_distribution"][0]["count"] == 3


@pytest.mark.anyio
async def test_get_fa_dashboard_dec_boundary_and_empty() -> Any:
    """12 月边界 end_date 跨年；无数据 → 达标率/产量为 0。"""
    s = AsyncMock()

    def branch(sql: Any, params: Any=None) -> Any:
        ssql = str(sql)
        r = MagicMock()
        if "SELECT COUNT(1) FROM production.fa_fermentation_batches" in ssql:
            r.scalar.return_value = 0
        elif "SELECT COUNT(1) FROM production.fa_" in ssql:
            r.scalar.return_value = 1
        elif 'COALESCE(SUM("汇总总量_kg")' in ssql:
            r.scalar.return_value = 0.0
        elif "COALESCE(AVG(" in ssql:
            r.scalar.return_value = 0.0
        elif "COUNT(CASE WHEN" in ssql:
            row = SimpleNamespace(total=0, passed=0)
            r.one.return_value = row
        else:
            r.scalar.return_value = 0
        return r

    s.execute.side_effect = branch
    resp = await fd.get_fa_dashboard(month="2026-12", session=s)
    data = json.loads(resp.body)["data"]
    assert data["pass_rate"] == 0
    assert data["monthly_output_kg"] == 0
    assert data["monthly_batches"] == 0
    # 12 月 end_date 跨年分派正常
    assert all(x["output_kg"] == 0 for x in data["monthly_trend"])


@pytest.mark.anyio
async def test_get_fa_dashboard_exception_paths() -> Any:
    """所有子查询抛异常 → 汇总端点仍返回全部 0 的响应，不扩散。"""
    s = AsyncMock()
    s.execute.side_effect = Exception("boom")
    resp = await fd.get_fa_dashboard(month="2026-05", session=s)
    data = json.loads(resp.body)["data"]
    assert data["monthly_output_kg"] == 0
    assert data["avg_yield"] == 0
    assert data["pass_rate"] == 0
    assert all(flow["in_progress"] == 0 for flow in data["flow"])
    assert data["rrt_pass_rates"] == []
    assert data["ba_stock_kg"] == 0

# ═══════════ fa_yield_chain ═══════════


@pytest.mark.anyio
async def test_fa_yield_chain_full() -> Any:
    """收率全链路：一个批次完全走通酸化/离心/脱色，生成阶段汇总与整体累计。"""
    s = AsyncMock()

    def branch(sql: Any, params: Any=None) -> Any:
        ssql = str(sql)
        r = MagicMock()
        if "FROM production.fa_fermentation_batches fb" in ssql:
            r.fetchall.return_value = [
                SimpleNamespace(
                    batch_no="FA-EX-1", date="2026-05-01", total_kg=100.0,
                    conductivity="1.5", yield_rate="0.9",
                ),
                SimpleNamespace(
                    batch_no="FA-EX-2", date="2026-05-02", total_kg=90.0,
                    conductivity=None, yield_rate="bad",
                ),
            ]
        elif "fa_acidification_records" in ssql:
            r.fetchone.return_value = ("FA-EX-1", "50", "0.85")
        elif "fa_decolor_centrifuge_records" in ssql:
            r.fetchall.return_value = [
                ("FA-EX-1-1", "95", "0.9"),
                ("FA-EX-1-2", "96", "0.85"),
                ("FA-EX-1-3", "97", "0.0"),
            ]
        elif "fa_decolor1_records" in ssql:
            r.fetchone.return_value = ("FA-EX-1", "96", "12.5")
        else:
            r.fetchone.return_value = None
            r.fetchall.return_value = []
        return r

    s.execute.side_effect = branch  # noqa: F841
    resp = await fd.fa_yield_chain(month="2026-05", session=s)
    data = json.loads(resp.body)["data"]
    assert len(data["batches"]) == 2
    first = data["batches"][0]
    assert first["fermentation_batch"] == "FA-EX-1"
    assert first["acid_batch"] == "FA-EX-1"
    assert first["centrifuge_avg_yield"] is not None
    assert first["cumulative_yield"] is not None
    assert len(data["stages"]) == 3  # fermentation/acidification/decolor_centrifuge
    assert data["summary"]["total_batches"] == 2
    assert data["summary"]["avg_cumulative_yield"] > 0
    assert data["summary"]["max_loss_stage"] in ("酸化过滤", "脱色离心")


@pytest.mark.anyio
async def test_fa_yield_chain_empty() -> Any:
    """无发酵批次 → 立即空响应。"""
    s = AsyncMock()
    s.execute.side_effect = lambda sql, params: MagicMock(fetchall=lambda: [])
    resp = await fd.fa_yield_chain(month=cast(str, None), session=s)
    data = json.loads(resp.body)["data"]
    assert data["batches"] == []
    assert data["stages"] == []
    assert data["summary"] == {}


# ═══════════ fa_golden_batches ═══════════


@pytest.mark.anyio
async def test_fa_golden_batches_quality_score() -> Any:
    """quality 评分：批量条目含 x2 离心数据、酸化/脱色字段，参考区间生成。"""
    s = AsyncMock()

    def branch(sql: Any, params: Any) -> Any:
        ssql = str(sql)
        r = MagicMock()
        if "FROM production.fa_fermentation_batches fb" in ssql:
            r.fetchall.return_value = [
                SimpleNamespace(
                    batch_no="FA-EX-1", total_kg=100.0, conductivity=1.5,
                    acid_adj=3.0, filter_speed=60.0,
                ),
                SimpleNamespace(
                    batch_no="FA-EX-2", total_kg=90.0, conductivity=None,
                    acid_adj=None, filter_speed=None,
                ),
            ]
        elif "fa_acidification_records" in ssql:
            r.fetchone.return_value = ("5.0", "6.5", "2.0", "80.0", "90")
        elif "fa_decolor_centrifuge_records" in ssql:
            r.fetchall.return_value = [
                ("0.90",), ("0.88",), ("0.95",), ("0.92",), ("0.9",),
            ]
        elif "fa_decolor1_records" in ssql:
            r.fetchone.return_value = ("1.0", "12.0")
        else:
            r.fetchall.return_value = []
            r.fetchone.return_value = None
        return r

    s.execute.side_effect = branch
    resp = await fd.fa_golden_batches(limit=5, score="quality", session=s)
    data = json.loads(resp.body)["data"]
    assert len(data["batches"]) == 2  # 每条含 >=3 份离心数据
    assert isinstance(data["reference"], dict)
    assert "_quality_score" in data["batches"][0]
    first_params = data["batches"][0]
    assert "conductivity" in first_params
    assert "centrifuge_avg" in first_params


# ═══════════ fa_batch_params（批次对比诊断） ═══════════


@pytest.mark.anyio
async def test_fa_batch_params_full() -> Any:
    """批次对比诊断：命中发酵批次、构建参数、生成偏离建议，并保存 ai_analysis。"""
    s = AsyncMock()

    def acidexec(sql: Any, params: Any=None) -> Any:
        rm = MagicMock()
        ssql = str(sql)
        if "fa_fermentation_batches" in ssql and "WHERE" in ssql:
            if "发酵罐号" in ssql:
                rm.fetchone.return_value = SimpleNamespace(
                    batch_no="FA-EX-1", total_kg=100.0, conductivity=1.5,
                    acid_adj=3.0, filter_speed=60.0,
                )
            else:
                # 黄金参考的 ferment_all
                rm.fetchall.return_value = [
                    SimpleNamespace(batch_no="FA-EX-1", total_kg=100.0,
                                    conductivity=1.0, acid_adj=2.0, filter_speed=50.0),
                    SimpleNamespace(batch_no="FA-EX-2", total_kg=110.0,
                                    conductivity=2.0, acid_adj=5.0, filter_speed=80.0),
                ]
        elif "fa_acidification_records" in ssql:
            rm.fetchone.return_value = ("8.0", "6.0", "5.0", "90")
        elif "fa_decolor_centrifuge_records" in ssql:
            rm.fetchall.return_value = [
                ("0.9",), ("0.88",), ("0.95",), ("0.92",), ("0.9",),
            ]
        elif "fa_decolor1_records" in ssql:
            rm.fetchone.return_value = ("2.0", "11.0")
        else:
            rm.fetchone.return_value = None
            rm.fetchall.return_value = []
        return rm

    s.execute.side_effect = acidexec
    s.add = MagicMock()
    resp = await fd.fa_batch_params(batch_no="FA-EX-1", score="stability", session=s)
    data = json.loads(resp.body)["data"]
    assert data["batch_no"] == "FA-EX-1"
    # 四个阶段均有 stage 键
    assert set(data["stages"].keys()) == {"发酵放罐", "酸化过滤", "一次脱色", "脱色离心"}  # noqa: E501
    # 电导偏差偏离会生成 suggestion 且 severity 非 normal
    cond = data["stages"]["发酵放罐"][0]
    assert cond["label"] in ("电导(us/cm)", "调酸量(L)", "滤速(ml/10min)")
    assert "deviation" in cond
    assert "direction" in cond
    assert "severity" in cond
    assert s.add.called
    assert s.commit.called


@pytest.mark.anyio
async def test_fa_batch_params_not_found_and_quality() -> Any:
    """批次不存在 → error_response；quality 评分走 quality 分支。"""
    s = AsyncMock()

    def ac_query(sql: Any, params: Any=None) -> Any:
        ssql = str(sql)
        rm = MagicMock()
        if "fe_fermentation_batches" in ssql and "发酵罐号" in ssql:
            rm.fetchone.return_value = None
        else:
            rm.fetchone.return_value = None
            rm.fetchall.return_value = []
        return rm

    s.execute.side_effect = ac_query
    resp = await fd.fa_batch_params(batch_no="NOPE", score="quality", session=s)
    assert "未找到批次数据" in json.loads(resp.body)["message"]

    # 找到批次但 score=quality 走 quality 分支（用简单场景）
    s2 = AsyncMock()

    def ac_query2(sql: Any, params: Any=None) -> Any:
        ssql = str(sql)
        rm = MagicMock()
        if "fa_fermentation_batches" in ssql and "发酵罐号" in ssql:
            rm.fetchone.return_value = SimpleNamespace(
                batch_no="FA-EX-1", total_kg=100.0, conductivity=1.5,
                acid_adj=3.0, filter_speed=60.0,
            )
        elif "fa_fermentation_batches" in ssql:
            rm.fetchall.return_value = [
                SimpleNamespace(batch_no="G1", total_kg=100.0, conductivity=1.0,
                                acid_adj=2.0, filter_speed=50.0),
            ]
        elif "fa_acidification_records" in ssql:
            rm.fetchone.return_value = ("7.0", "6.0", "3.0", "82")
        elif "fa_decolor_centrifuge_records" in ssql:
            rm.fetchall.return_value = [
                ("0.9",), ("0.88",), ("0.95",), ("0.92",), ("0.9",),
            ]
        elif "fa_decolor1_records" in ssql:
            rm.fetchone.return_value = ("1.0", "12.0")
        else:
            rm.fetchone.return_value = None
            rm.fetchall.return_value = []
        return rm

    s2.execute.side_effect = ac_query2
    s2.add = MagicMock()
    resp2 = await fd.fa_batch_params(batch_no="FA-EX-1", score="quality", session=s2)
    data2 = json.loads(resp2.body)["data"]
    assert data2["batch_no"] == "FA-EX-1"
