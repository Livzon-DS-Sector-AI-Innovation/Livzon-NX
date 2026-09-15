"""成品检测趋势异常确定性规则引擎单测（v3：历史做基线，本月对基线比）。"""

from __future__ import annotations

from app.modules.quality.service.trend_anomaly_rules import (
    RULE_MONTH_LEVEL,
    RULE_MONTH_OVER_MONTH,
    RULE_MONTH_SLOPE,
    RULE_SLOPE_CHANGE,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    detect_trend_anomalies,
    parse_batch_month,
)


def _points(values: list[float], ym: str = "2601") -> list[dict]:
    return [
        {"batch_no": f"MC{ym}{i:03d}", "value": v}
        for i, v in enumerate(values)
    ]


def _rules(anomalies) -> set[str]:
    return {a.rule_type for a in anomalies}


# ─── 批号日期解析 ────────────────────────────────────────────────


def test_parse_batch_month_yyyymmdd():
    assert parse_batch_month("MC20260815") == 202608


def test_parse_batch_month_yymm_in_batch():
    assert parse_batch_month("LFT260801") == 202608


def test_parse_batch_month_yymm_with_serial():
    # 业务批号口径：年月+流水号（USMC-M-2607007T = 2026-07 第 7 批）
    assert parse_batch_month("USMC-M-2607007T") == 202607
    assert parse_batch_month("USMC-M-260801-U") == 202608
    assert parse_batch_month("MC2606015S") == 202606


def test_parse_batch_month_none_when_no_date():
    assert parse_batch_month("ABCXYZ") is None
    assert parse_batch_month("") is None
    assert parse_batch_month("1234567") is None  # 流水号误读防护


# ─── 当月 vs 历史（水位） ────────────────────────────────────────


def test_month_level_up_detected():
    # 历史（2605/2606）~0.335，本月（2607）整体抬到 ~0.455 —— 霉酚酸总杂质形态
    history = [0.31, 0.33, 0.35, 0.32, 0.34, 0.30, 0.36, 0.33, 0.35, 0.32]
    history += [0.34, 0.32, 0.35, 0.33, 0.31, 0.36, 0.33, 0.34, 0.32, 0.35]
    current = [0.44, 0.47, 0.45, 0.46, 0.44, 0.47]
    points = (
        _points(history, ym="2605")[:10]
        + _points(history[10:], ym="2606")
        + _points(current, ym="2607")
    )
    anomalies = detect_trend_anomalies(points)
    assert RULE_MONTH_LEVEL in _rules(anomalies)
    level = next(a for a in anomalies if a.rule_type == RULE_MONTH_LEVEL)
    assert level.evidence["delta"] > 0
    assert level.evidence["current_points"] == 6
    assert level.severity in {SEVERITY_MEDIUM, SEVERITY_HIGH}


def test_month_level_stable_not_flagged():
    # 三个月都在 ~0.33：本月与历史一致 → 不报
    points = (
        _points([0.32, 0.35, 0.31, 0.34, 0.30, 0.33], ym="2605")
        + _points([0.33, 0.30, 0.34, 0.32, 0.35, 0.31], ym="2606")
        + _points([0.32, 0.35, 0.31, 0.34, 0.30, 0.33], ym="2607")
    )
    anomalies = detect_trend_anomalies(points)
    assert RULE_MONTH_LEVEL not in _rules(anomalies)


# ─── 当月内趋势（本月斜率） ──────────────────────────────────────


def test_month_slope_detected():
    # 历史平稳，本月持续走高（0.33 → 0.43）
    history = [0.33, 0.32, 0.34, 0.33, 0.35, 0.32, 0.34, 0.33, 0.32, 0.34]
    history += [0.33, 0.34, 0.32, 0.33, 0.35, 0.33, 0.34, 0.32, 0.33, 0.34]
    current = [0.33, 0.35, 0.37, 0.39, 0.41, 0.43]
    points = (
        _points(history[:10], ym="2605")
        + _points(history[10:], ym="2606")
        + _points(current, ym="2607")
    )
    anomalies = detect_trend_anomalies(points)
    assert RULE_MONTH_SLOPE in _rules(anomalies)
    slope = next(a for a in anomalies if a.rule_type == RULE_MONTH_SLOPE)
    assert slope.evidence["month_move"] > 0


def test_month_slope_wiggle_not_flagged():
    # 本月上下摆动无方向 → 不报
    points = (
        _points([0.33] * 12, ym="2605")
        + _points([0.33] * 12, ym="2606")
        + _points([0.34, 0.31, 0.35, 0.30, 0.34, 0.32], ym="2607")
    )
    anomalies = detect_trend_anomalies(points)
    assert RULE_MONTH_SLOPE not in _rules(anomalies)


# ─── 斜率较历史变化 ──────────────────────────────────────────────


def test_slope_change_detected():
    # 历史平稳、本月抬头 —— 当月斜率较历史显著变化
    history = [0.33, 0.32, 0.34, 0.33, 0.35, 0.32, 0.34, 0.33, 0.32, 0.34]
    history += [0.33, 0.34, 0.32, 0.33, 0.35, 0.33, 0.34, 0.32, 0.33, 0.34]
    current = [0.33, 0.35, 0.37, 0.39, 0.41, 0.43]
    points = (
        _points(history[:10], ym="2605")
        + _points(history[10:], ym="2606")
        + _points(current, ym="2607")
    )
    anomalies = detect_trend_anomalies(points)
    assert RULE_SLOPE_CHANGE in _rules(anomalies)
    change = next(a for a in anomalies if a.rule_type == RULE_SLOPE_CHANGE)
    assert change.evidence["slope_delta"] > 0


# ─── 月度整体趋势 ────────────────────────────────────────────────


def test_month_over_month_sustained_rise_detected():
    # 连续 3 个月上升（0.33 → 0.35 → 0.37 → 0.40）
    points = (
        _points([0.33, 0.33], ym="2605")
        + _points([0.35, 0.35], ym="2606")
        + _points([0.37, 0.37], ym="2607")
        + _points([0.40, 0.40], ym="2608")
    )
    anomalies = detect_trend_anomalies(points)
    assert RULE_MONTH_OVER_MONTH in _rules(anomalies)
    mom = next(a for a in anomalies if a.rule_type == RULE_MONTH_OVER_MONTH)
    assert mom.evidence["consecutive_months"] >= 3


# ─── 历史异常不报（核心口径） ────────────────────────────────────


def test_historical_step_not_reported():
    # 台阶发生在历史上（2601-2602 为 0.20，之后至今都是 0.33）：
    # 本月与近期水平一致 → 不得产出任何趋势异常
    points = (
        _points([0.20, 0.21, 0.19, 0.20, 0.22, 0.20], ym="2601")
        + _points([0.20, 0.19, 0.21, 0.20, 0.20, 0.22], ym="2602")
        + _points([0.33, 0.32, 0.34, 0.33, 0.35, 0.32], ym="2603")
        + _points([0.33, 0.34, 0.32, 0.33, 0.35, 0.33], ym="2604")
        + _points([0.34, 0.32, 0.33, 0.35, 0.32, 0.33], ym="2605")
        + _points([0.33, 0.34, 0.32, 0.33], ym="2606")
        + _points([0.33, 0.35, 0.32, 0.34, 0.31, 0.33], ym="2607")
    )
    anomalies = detect_trend_anomalies(points)
    assert anomalies == [], f"历史台阶不应上报: {[a.description for a in anomalies]}"


# ─── 输出契约 ────────────────────────────────────────────────────


def test_anomalies_sorted_by_severity_and_serializable():
    history = [0.33, 0.32, 0.34, 0.33, 0.35, 0.32, 0.34, 0.33, 0.32, 0.34]
    history += [0.33, 0.34, 0.32, 0.33, 0.35, 0.33, 0.34, 0.32, 0.33, 0.34]
    current = [0.33, 0.35, 0.37, 0.39, 0.41, 0.43]
    points = (
        _points(history[:10], ym="2605")
        + _points(history[10:], ym="2606")
        + _points(current, ym="2607")
    )
    anomalies = detect_trend_anomalies(points)
    assert anomalies
    order = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, "low": 2}
    ranks = [order[a.severity] for a in anomalies]
    assert ranks == sorted(ranks)
    for anomaly in anomalies:
        assert set(anomaly.to_dict()) == {
            "rule_type",
            "severity",
            "start_batch",
            "end_batch",
            "description",
            "evidence",
            "affected_batches",
        }


def test_insufficient_samples_returns_empty():
    assert detect_trend_anomalies([]) == []
    assert detect_trend_anomalies(_points([1.0, 2.0])) == []


# ─── 粗筛业务约束（AI 终审前）：方向 / 全历史波动带 / 相对幅度 ───

_UPPER_ONLY = [{"label": "标准上限", "value": 2.0}]
_RANGE_SPEC = [
    {"label": "标准下限", "value": 97.0},
    {"label": "标准上限", "value": 103.0},
]


def test_spec_direction_classification():
    from app.modules.quality.service.trend_anomaly_rules import spec_direction

    assert spec_direction(_UPPER_ONLY) == "up_only"
    assert spec_direction([{"label": "标准下限", "value": 90.0}]) == "down_only"
    assert spec_direction(_RANGE_SPEC) == "both"
    assert spec_direction(None) == "both"
    # 警戒/纠偏限度（纯化水微生物限度）按上限语义
    assert (
        spec_direction(
            [{"label": "警戒限度", "value": 50.0}, {"label": "纠偏限度", "value": 80.0}]
        )
        == "up_only"
    )


def test_up_only_indicator_decline_is_improvement_not_flagged():
    # 单边上限指标（杂质 ≤2.0%）：本月由 ~0.35 降到 ~0.26 —— 改善，不提名
    history = [0.34, 0.36, 0.35, 0.33, 0.37, 0.35, 0.34, 0.36, 0.33, 0.35]
    history += [0.35, 0.34, 0.36, 0.35, 0.33, 0.37, 0.34, 0.35, 0.36, 0.34]
    current = [0.28, 0.26, 0.27, 0.25, 0.26, 0.24]
    points = (
        _points(history[:10], ym="2606")
        + _points(history[10:], ym="2607")
        + _points(current, ym="2608")
    )
    anomalies = detect_trend_anomalies(points, spec_lines=_UPPER_ONLY)
    assert anomalies == [], f"下落=改善不应提名: {[a.description for a in anomalies]}"
    # 对照：同一组数据按双向（无方向信息）才会提名下移
    baseline = detect_trend_anomalies(points)
    assert RULE_MONTH_LEVEL in _rules(baseline)


def test_all_history_band_blocks_recovery_from_low_baseline():
    # 基线恰处低谷（2607 掉到 ~1.05），本月回升到常态 ~1.30 —— 属正常波动
    points = (
        _points([1.24, 1.26, 1.22, 1.25, 1.23, 1.27], ym="2603")
        + _points([1.25, 1.23, 1.26, 1.24, 1.22, 1.25], ym="2604")
        + _points([1.23, 1.25, 1.24, 1.26, 1.22, 1.24], ym="2605")
        + _points([1.25, 1.24, 1.26, 1.23, 1.25, 1.24], ym="2606")
        + _points([1.05, 1.06, 1.04, 1.05, 1.07, 1.04], ym="2607")
        + _points([1.30, 1.29, 1.31, 1.30, 1.28, 1.31], ym="2608")
    )
    anomalies = detect_trend_anomalies(
        points, spec_lines=[{"label": "标准上限", "value": 3.0}]
    )
    assert RULE_MONTH_LEVEL not in _rules(anomalies), (
        f"回归常态不应提名: {[a.description for a in anomalies]}"
    )


def test_relative_amplitude_blocks_tiny_drift_on_flat_data():
    # 数据极平（~0.100，σ≈0.002）：本月偏 +0.005（2.5σ 统计显著）但仅 5% 幅度
    history = [0.100, 0.102, 0.099, 0.101, 0.098, 0.102, 0.100, 0.101, 0.099, 0.100]
    history += [0.101, 0.099, 0.100, 0.102, 0.098, 0.101, 0.100, 0.099, 0.101, 0.100]
    current = [0.105, 0.105, 0.105, 0.105, 0.105, 0.105]
    points = (
        _points(history[:10], ym="2606")
        + _points(history[10:], ym="2607")
        + _points(current, ym="2608")
    )
    anomalies = detect_trend_anomalies(
        points, spec_lines=[{"label": "标准上限", "value": 0.5}]
    )
    assert anomalies == [], f"微小漂移不应提名: {[a.description for a in anomalies]}"


def test_material_rise_toward_limit_still_flagged():
    # 真异常：单边上限指标本月大幅抬升（0.33 → 0.60），离开全历史带 → 仍提名
    history = [0.33, 0.32, 0.34, 0.33, 0.35, 0.32, 0.34, 0.33, 0.32, 0.34]
    history += [0.33, 0.34, 0.32, 0.33, 0.35, 0.33, 0.34, 0.32, 0.33, 0.34]
    current = [0.55, 0.58, 0.60, 0.62, 0.61, 0.63]
    points = (
        _points(history[:10], ym="2606")
        + _points(history[10:], ym="2607")
        + _points(current, ym="2608")
    )
    anomalies = detect_trend_anomalies(points, spec_lines=_UPPER_ONLY)
    assert RULE_MONTH_LEVEL in _rules(anomalies)
    level = next(a for a in anomalies if a.rule_type == RULE_MONTH_LEVEL)
    assert level.evidence["direction_mode"] == "up_only"


def test_range_spec_still_flags_downward_drift():
    # 双边限度（含量 97~103%）：本月由 ~100.5 掉到 ~97.5 —— 朝下限方向，仍提名
    history = [100.4, 100.6, 100.5, 100.3, 100.7, 100.5, 100.4, 100.6, 100.3, 100.5]
    history += [100.5, 100.4, 100.6, 100.5, 100.3, 100.7, 100.4, 100.5, 100.6, 100.4]
    current = [98.0, 97.6, 97.8, 97.4, 97.5, 97.3]
    points = (
        _points(history[:10], ym="2606")
        + _points(history[10:], ym="2607")
        + _points(current, ym="2608")
    )
    anomalies = detect_trend_anomalies(points, spec_lines=_RANGE_SPEC)
    assert RULE_MONTH_LEVEL in _rules(anomalies)
    level = next(a for a in anomalies if a.rule_type == RULE_MONTH_LEVEL)
    assert level.evidence["delta"] < 0  # 下移
    assert level.evidence["direction_mode"] == "both"
