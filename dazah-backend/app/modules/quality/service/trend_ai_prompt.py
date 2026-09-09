"""成品检测趋势 AI 分析提示词构建。

风格对齐 validation_review_prompt：角色人设 + 确定性事实注入 + 严格 JSON 契约。
本模块只负责把「已算好的趋势规则事实」拼成给模型的输入，不做任何业务判断；
确定性判据（见 trend_anomaly_rules）先于模型执行，LLM 仅用于辅助解读。
"""

from __future__ import annotations

from statistics import fmean
from typing import Any

from app.modules.quality.service.trend_anomaly_rules import (
    parse_batch_month,
    split_current_history,
)

# LLM 输出允许的严重度/规则白名单（超出即回退或丢弃，防编造）
SEVERITY_LEVELS = ("low", "medium", "high")
CONFIDENCE_LEVELS = ("low", "medium", "high")

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
    batches = [str(p.get("batch_no") or "") for p in points]
    vals = [float(p["value"]) for p in points if p.get("value") is not None]
    usable = [
        (b, v)
        for b, p, v in zip(batches, points, vals, strict=False)
        if p.get("value") is not None
    ]
    if len(usable) >= 6:
        from statistics import fmean as _fmean

        current_idx, baseline_idx, time_basis = split_current_history(batches, vals)
        cur = [v for i, v in enumerate(vals) if i in set(current_idx)]
        hist = [v for i, v in enumerate(vals) if i in set(baseline_idx)]
        if cur and hist:
            month_key = parse_batch_month(batches[current_idx[-1]])
            month_label = (
                f"{month_key // 100}-{month_key % 100:02d}"
                if month_key
                else "最近批次"
            )
            compare = [
                f"评估月：{month_label}（口径 {time_basis}，{len(cur)} 批）",
                f"本月均值：{_fmean(cur):g}",
                f"历史均值：{_fmean(hist):g}（{len(hist)} 批）",
                f"本月均值 − 历史均值：{_fmean(cur) - _fmean(hist):+g}",
            ]
            parts.append("【本月 vs 历史（评估主轴）】\n" + "\n".join(compare))

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
    series_rows = [
        f"{p.get('batch_no')}: {format(float(p.get('value')), 'g')}"
        for p in tail
        if p.get("value") is not None
    ]
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
