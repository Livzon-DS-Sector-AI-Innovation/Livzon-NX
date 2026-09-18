"""成品检测趋势 AI 分析提示词构建。

风格对齐 validation_review_prompt：角色人设 + 确定性事实注入 + 严格 JSON 契约。
本模块只负责把「已算好的趋势规则事实」拼成给模型的输入，不做任何业务判断；
确定性判据（见 trend_anomaly_rules）先于模型执行，LLM 仅用于辅助解读。
"""

from __future__ import annotations

from statistics import fmean, pstdev
from typing import Any

from app.modules.quality.service.trend_anomaly_rules import (
    parse_batch_month,
    spec_direction,
    split_current_history,
)

# LLM 输出允许的严重度/规则白名单（超出即回退或丢弃，防编造）
SEVERITY_LEVELS = ("low", "medium", "high")
CONFIDENCE_LEVELS = ("low", "medium", "high")

_DIRECTION_LABELS: dict[str, str] = {
    "up_only": "越小越好（只给上限：下降=改善）",
    "down_only": "越大越好（只给下限：上升=改善）",
    "both": "双侧要求（上下限都要守，两个方向都可能超限）",
}

_RULE_LABELS: dict[str, str] = {
    "month_level": "当月较历史抬升/下移",
    "month_slope": "当月内趋势",
    "slope_change": "斜率较历史变化",
    "month_over_month": "月度整体趋势",
    # 旧口径（历史缓存行兼容展示）
    "continuous_move": "连续上升/下降",
    "slope_break": "斜率突变",
    "mean_shift": "均值台阶偏移",
    "level_step": "均值台阶突变",
}

# 注入模型的点序列上限（取末尾 N 点，控制 token；更早点由统计事实代表）
MAX_SERIES_POINTS_IN_PROMPT = 48
# 注入模型的月度均值上限（取最近 N 个月）
MAX_MONTHS_IN_PROMPT = 12
_MAX_NOTE_LEN = 400


def _rule_label(rule_type: str) -> str:
    return _RULE_LABELS.get(rule_type, rule_type)


def _fmt(value: float | None) -> str:
    return "-" if value is None else format(value, "g")


def _format_spec_lines(spec_lines: list[dict[str, Any]] | None) -> str:
    if not spec_lines:
        return "（无限度线）"
    return " / ".join(
        f"{line.get('label', '')} {float(line.get('value', 0)):g}"
        for line in spec_lines
        if line.get("value") is not None
    )


def _month_vs_history_stats(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    """「本月 vs 历史」统计（评估主轴）；样本不足时返回 None。"""
    batches = [str(p.get("batch_no") or "") for p in points]
    vals = [float(p["value"]) for p in points if p.get("value") is not None]
    usable = [
        (b, v)
        for b, p, v in zip(batches, points, vals, strict=False)
        if p.get("value") is not None
    ]
    if len(usable) < 6:
        return None
    current_idx, baseline_idx, time_basis = split_current_history(batches, vals)
    cur = [v for i, v in enumerate(vals) if i in set(current_idx)]
    hist = [v for i, v in enumerate(vals) if i in set(baseline_idx)]
    if not cur or not hist:
        return None
    month_key = parse_batch_month(batches[current_idx[-1]])
    month_label = (
        f"{month_key // 100}-{month_key % 100:02d}" if month_key else "最近批次"
    )
    return {
        "month_label": month_label,
        "time_basis": time_basis,
        "current_mean": fmean(cur),
        "current_count": len(cur),
        "history_mean": fmean(hist),
        "history_count": len(hist),
        "delta": fmean(cur) - fmean(hist),
    }


def _parse_limit_values(
    spec_lines: list[dict[str, Any]] | None,
) -> tuple[float | None, float | None]:
    """从 OOT/标准限度线取最紧的上限/下限（非"下限"标签按上限语义）。"""
    upper: float | None = None
    lower: float | None = None
    for line in spec_lines or []:
        label = str(line.get("label") or "")
        raw_value = line.get("value")
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if "下限" in label:
            lower = value if lower is None else max(lower, value)
        else:
            upper = value if upper is None else min(upper, value)
    return upper, lower


def _margin_text(
    value: float | None,
    upper: float | None,
    lower: float | None,
) -> str:
    """距最近限度的余量（绝对值 + 占该限度的百分比），供 AI 判断风险紧迫度。"""
    if value is None:
        return "（无当前水平数据）"
    candidates: list[tuple[str, float, float]] = []
    if upper is not None:
        candidates.append(("上限", upper, upper - value))
    if lower is not None:
        candidates.append(("下限", lower, value - lower))
    if not candidates:
        return "（无标准/OOT 限度线）"
    label, limit, margin = min(candidates, key=lambda item: abs(item[2]))
    ratio = (
        f"（余量约占该限度 {margin / abs(limit) * 100:.0f}%）"
        if abs(limit) > 0
        else ""
    )
    return f"距{label} {limit:g} 还差 {margin:g}{ratio}"


def _all_history_band_text(points: list[dict[str, Any]]) -> str | None:
    """全历史（除评估月）均值±2σ 波动带：AI 判断"是否仍在正常波动内"。"""
    batches = [str(p.get("batch_no") or "") for p in points]
    values = [float(p["value"]) for p in points if p.get("value") is not None]
    if len(values) < 6:
        return None
    current_idx, _baseline, _basis = split_current_history(batches, values)
    current_set = set(current_idx)
    history = [v for i, v in enumerate(values) if i not in current_set]
    if len(history) < 3:
        return None
    mean = fmean(history)
    sigma = pstdev(history)
    return (
        f"全历史波动带（除评估月）≈ {mean - 2 * sigma:g} ~ {mean + 2 * sigma:g}"
        f"（均值 {mean:g}）"
    )


def _format_month_vs_history(points: list[dict[str, Any]]) -> str | None:
    """「本月 vs 历史」评估主轴文本；样本不足时返回 None。"""
    stats = _month_vs_history_stats(points)
    if stats is None:
        return None
    compare = [
        f"评估月：{stats['month_label']}（口径 {stats['time_basis']}，"
        f"{stats['current_count']} 批）",
        f"本月均值：{stats['current_mean']:g}",
        f"历史均值：{stats['history_mean']:g}（{stats['history_count']} 批）",
        f"本月均值 − 历史均值：{stats['delta']:+g}",
    ]
    return "\n".join(compare)


def build_trend_ai_prompt(
    *,
    source_label: str,
    metric_label: str,
    points: list[dict[str, Any]],
    mean: float | None,
    std_dev: float | None,
    upper_control_limit: float | None,
    lower_control_limit: float | None,
    spec_lines: list[dict[str, Any]] | None,
    anomalies: list[dict[str, Any]],
) -> str:
    """组装趋势 AI 解读提示词。

    ``anomalies`` 为 ``detect_trend_anomalies`` 的确定性事实（已转 dict）。
    """
    parts: list[str] = []
    parts.append(
        "你是原料药工厂质量管理（QC）趋势分析专家。给定某检测指标按批号排列的"
        "历史检验结果、控制限与已算好的确定性趋势规则命中，请研判质量趋势风险，"
        "只做辅助分析，不替代放行/偏差/OOT 判定等责任决定。"
    )

    facts: list[str] = [
        f"产品系列：{source_label}",
        f"检测指标：{metric_label}",
        f"样本数：{len(points)}",
        f"均值：{_fmt(mean)}",
        f"标准差：{_fmt(std_dev)}",
        f"控制限（均值±3σ）：{_fmt(lower_control_limit)} ~ {_fmt(upper_control_limit)}",
        f"限度线（OOT/标准）：{_format_spec_lines(spec_lines)}",
    ]
    parts.append("【统计事实】\n" + "\n".join(facts))

    # 本月 vs 历史：评估口径的主轴（评估月=数据中最后一个有批号的月份）
    month_vs_history = _format_month_vs_history(points)
    if month_vs_history:
        parts.append("【本月 vs 历史（评估主轴）】\n" + month_vs_history)

    # 月度均值（按批号年月汇总）：月度趋势是整体评估的主线
    month_groups: dict[int, list[float]] = {}
    for point in points:
        raw = point.get("value")
        if raw is None:
            continue
        month = parse_batch_month(str(point.get("batch_no") or ""))
        if month is None:
            continue
        month_groups.setdefault(month, []).append(float(raw))
    if len(month_groups) >= 2:
        month_rows = [
            f"{month // 100}-{month % 100:02d}: 均值 {fmean(v):g}（{len(v)} 批）"
            for month, v in sorted(month_groups.items())[-MAX_MONTHS_IN_PROMPT:]
        ]
        header = "【月度均值（按批号年月汇总，整体评估主线）】"
        parts.append(header + "\n" + "\n".join(month_rows))

    if anomalies:
        rule_lines: list[str] = []
        for item in anomalies:
            evidence = item.get("evidence") or {}
            start = item.get("trend_start_batch") or item.get("start_batch") or "-"
            end = item.get("trend_end_batch") or item.get("end_batch") or "-"
            line = (
                f"- 规则[{_rule_label(str(item.get('rule_type')))}] "
                f"严重度[{item.get('severity')}] 批次[{start}~{end}] "
                f"事实：{item.get('description')}"
            )
            if evidence:
                line += f"；证据：{evidence}"
            rule_lines.append(line)
        parts.append("【已算好的确定性趋势判据命中】\n" + "\n".join(rule_lines))
    else:
        parts.append("【已算好的确定性趋势判据命中】\n（无趋势规则命中，仅按统计事实研判）")

    tail = points[-MAX_SERIES_POINTS_IN_PROMPT:]
    series_rows: list[str] = []
    for point in tail:
        raw_value = point.get("value")
        if raw_value is None:
            continue
        series_rows.append(
            f"{point.get('batch_no')}: {format(float(raw_value), 'g')}"
        )
    prefix = (
        f"（仅显示最近 {len(tail)} 批，共 {len(points)} 批）"
        if len(points) > len(tail)
        else ""
    )
    header = f"【批序检验结果（批号: 值，按生产批次先后）】{prefix}"
    parts.append(header + "\n" + "\n".join(series_rows))

    parts.append(
        "评估口径以「本月 vs 历史」为主轴，请回答四个问题：1) 本月均值较历史"
        "均值是否抬升/下移、幅度多大；2) 本月批次内部是否呈持续上升/下降"
        "（当月斜率）；3) 本月斜率较历史斜率是否发生变化（加速/反转）；"
        "4) 近几个月月度均值的整体走向如何、按此方向外推是否逼近控制限或"
        "OOT 限度线、预计还有多少批次。已命中的判据都经过「朝限度方向 + 幅度"
        "显著超噪声」过滤且全部锚定本月，请围绕它们展开；历史段里已经发生的"
        "波动属于既成事实，不要作为本次异常解读。逐批超出 均值±3σ/OOT 限度"
        "由系统即时告警并记录，无需逐点复述。若本月与历史基本一致且无持续方"
        "向，结论应简短明确「本月与历史水平相当、趋势平稳、风险可控」。"
    )

    parts.append(
        "只输出 JSON，不要任何多余文字，结构严格如下：\n"
        "{\n"
        '  "summary": "一句话总体趋势研判（<=60字）",\n'
        '  "trend_reading": "自然语言解读趋势与风险（<=300字）",\n'
        '  "signals": [\n'
        '    {"batch_no": "代表批次号", "rule_type": '
        '"month_level|month_slope|slope_change|month_over_month", '
        '"severity": "low|medium|high", "note": "该信号说明（<=120字）"}\n'
        "  ],\n"
        '  "outlook": {"direction": "up|down|flat", '
        '"batches_to_limit": "逼近限度线预计剩余批次数(整数,无法判断填null)", '
        '"risk": "风险说明(<=120字)"},\n'
        '  "recommendation": "建议动作（如关注/加严监测/结合偏差评估，<=150字）",\n'
        '  "confidence": "low|medium|high"\n'
        "}"
    )
    return "\n\n".join(parts)


def build_product_trend_ai_prompt(
    *,
    source_label: str,
    period: str,
    metrics: list[dict[str, Any]],
) -> str:
    """组装产品级（多指标合并一次分析）趋势 AI 提示词。

    ``metrics`` 每项需含 metric_label/points/mean/std_dev/upper_control_limit/
    lower_control_limit/spec_lines/anomalies（确定性命中，已转 dict）。
    一个产品只做一次模型调用、产出一版整体结论 + 逐指标结论，
    避免逐指标多次调用与逐指标推送触发飞书卡片限流。
    """
    parts: list[str] = []
    parts.append(
        "你是原料药工厂质量管理（QC）趋势分析专家。给定同一产品的多个检测"
        "指标的统计事实与已算好的确定性趋势判据命中，请对整个产品做一次"
        "汇总趋势研判，并逐指标给出简短结论；只做辅助分析，不替代放行/"
        "偏差/OOT 判定等责任决定。"
    )
    parts.append(f"【产品系列】{source_label}\n【分析周期】{period}")

    blocks: list[str] = []
    for index, metric in enumerate(metrics, start=1):
        points = list(metric.get("points") or [])
        spec_lines = list(metric.get("spec_lines") or [])
        upper, lower = _parse_limit_values(spec_lines)
        stats = _month_vs_history_stats(points)
        cur_mean = stats["current_mean"] if stats else metric.get("mean")
        lines = [
            f"指标{index}：{metric.get('metric_label')}",
            f"样本数：{len(points)}",
            f"均值：{_fmt(metric.get('mean'))}",
            f"标准差：{_fmt(metric.get('std_dev'))}",
            "控制限（均值±3σ）："
            f"{_fmt(metric.get('lower_control_limit'))} ~ "
            f"{_fmt(metric.get('upper_control_limit'))}",
            "限度线（OOT/标准）：" f"{_format_spec_lines(spec_lines)}",
            f"指标方向：{_DIRECTION_LABELS.get(spec_direction(spec_lines), '-')}",
            f"当前水平距限度余量：{_margin_text(cur_mean, upper, lower)}",
        ]
        band_text = _all_history_band_text(points)
        if band_text:
            lines.append(band_text)
        month_vs_history = _format_month_vs_history(points)
        if month_vs_history:
            if stats and stats["history_mean"]:
                pct = stats["delta"] / abs(stats["history_mean"]) * 100
                month_vs_history += f"\n偏移幅度：{pct:+.1f}%（占历史均值）"
            lines.append("本月 vs 历史：\n" + month_vs_history)
        anomalies = list(metric.get("anomalies") or [])
        if anomalies:
            rule_lines = []
            for item in anomalies:
                evidence = item.get("evidence") or {}
                start = (
                    item.get("trend_start_batch")
                    or item.get("start_batch")
                    or "-"
                )
                end = item.get("trend_end_batch") or item.get("end_batch") or "-"
                line = (
                    f"- 规则[{_rule_label(str(item.get('rule_type')))}] "
                    f"严重度[{item.get('severity')}] 批次[{start}~{end}] "
                    f"事实：{item.get('description')}"
                )
                if evidence:
                    line += f"；证据：{evidence}"
                rule_lines.append(line)
            lines.append("粗筛提名（待终审，非既定结论）：\n" + "\n".join(rule_lines))
        else:
            lines.append("粗筛提名（待终审）：（无，仅按统计事实研判）")
        blocks.append("\n".join(lines))
    parts.append("【各指标统计事实与粗筛提名】\n" + "\n\n".join(blocks))

    parts.append(
        "你是本批趋势复核的**终审**：确定性粗筛只做提名，判据命中只是候选，"
        "是否算异常由你逐项复核裁决。裁决标准（业务第一，不认「统计显著」本身）：\n"
        "- abnormal（真异常）：变化朝限度方向、幅度有业务意义，且余量在被消耗；\n"
        "- normal（正常）：仍属正常波动（如落在全历史波动带内，或基线恰处低谷"
        "而本月只是回归常态）；\n"
        "- improved（改善）：变化方向是改善（如「越小越好」的指标在下降）。\n"
        "若偏移方向是改善、或距最近限度余量还很充足（如余量 >80%）且无恶化证据，"
        "应判 normal/improved，并在结论中明确「平稳、风险可控」，不要把它写成"
        "需要关注的异常；只有真正朝限度逼近的才判 abnormal 并列入 signals。"
        "历史段已发生的波动属既成事实，不要作为本次异常解读；逐批超出 "
        "均值±3σ/OOT 限度由系统即时告警，无需逐点复述。最后给出产品整体"
        "研判（以最严重指标为主导）与逐指标裁决。"
    )
    parts.append(
        "只输出 JSON，不要任何多余文字，结构严格如下：\n"
        "{\n"
        '  "summary": "产品整体趋势一句话研判（<=60字）",\n'
        '  "trend_reading": "自然语言解读整体趋势与风险（<=300字）",\n'
        '  "signals": [\n'
        '    {"metric_index": "所属指标序号（必填，与输入一致）",\n'
        '     "batch_no": "代表批次号", "rule_type": '
        '"month_level|month_slope|slope_change|month_over_month",\n'
        '     "severity": "low|medium|high", "note": "信号说明（<=120字）"}\n'
        "  ],\n"
        '  "outlook": {"direction": "up|down|flat", '
        '"batches_to_limit": "逼近限度线预计剩余批次数(整数,无法判断填null)", '
        '"risk": "风险说明(<=120字)"},\n'
        '  "recommendation": "建议动作（<=150字）",\n'
        '  "confidence": "low|medium|high",\n'
        '  "metric_findings": [\n'
        '    {"metric_index": "指标序号（必填，与输入一致）",\n'
        '     "metric_label": "指标名（与输入一致）",\n'
        '     "verdict": "abnormal|normal|improved",\n'
        '     "summary": "该指标的裁决结论（<=60字）"}\n'
        "  ]\n"
        "}"
    )
    parts.append(
        "metric_findings 必须覆盖输入的每一个指标序号（不得遗漏）；判据候选即使"
        "被你判为 normal/improved 也要给出该条结论。signals 只列 abnormal 的。"
    )
    return "\n\n".join(parts)
