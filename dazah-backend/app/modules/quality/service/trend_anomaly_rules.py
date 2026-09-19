"""成品检测趋势异常确定性规则引擎 v3（纯 stdlib，不含 LLM）。

**角色：粗筛提名器（不是终审）**——本引擎只把"值得复核"的指标提给 AI；
标红与推送由 AI 终审裁决（AI 判 abnormal 才标红/进卡），见
trend_ai_analysis / inspection_dashboard_calc。

评估口径（2026-09-08 与业务对齐）：**近期历史做基线，本月对基线比**——基线
是评估月前 1~2 个日历月（不是全部历史：台阶发生的当月会相对近期基线被报
出，之后成为新平台便不再反复报旧事；全历史基线会被新平台污染且永久追着旧
台阶报）。四条规则全部锚定"当前评估月（数据中最后一个有批号的月份）"：

- 当月 vs 历史（month_level）：本月均值较历史均值抬升/下移 ≥1.5σ_hist
  （有带宽时叠加 ≥8% 带宽）；
- 当月内趋势（month_slope）：本月批次自身呈持续上升/下降，当月累计变化
  ≥1.5σ_hist 且斜率显著；
- 斜率较历史变化（slope_change）：本月斜率较历史斜率突变（t≥3）且方向朝
  限度；
- 月度整体趋势（month_over_month）：≥3 个月度均值连续同向，给整体走向。

2026-09-11 增补三道粗筛业务约束（治"正常波动被标异常"误报）：
1. **方向**（spec_direction）：单边上限指标（越小越好）下降=改善不提名；
   单边下限反之；仅双边/无限度线才双向提名；
2. **全历史波动带**：当月均值仍在除当月外全部历史的 ±2σ 内 → 属正常波动；
3. **相对幅度**：偏移/当月累计变化须达基线均值的 10% 才提名。

逐批超出 均值±3σ / OOT 限度线属于点位异常，由仪表盘既有的即时告警链路
（_materialize_dashboard_alert → 飞书推送 + 落库）"立即报告记录"，不在本
引擎职责内。批号无法解析年月时，评估月退化为"最后 K 批"（K=min(20,
max(5, n//20))），证据里标 time_basis="sequence"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean, pstdev
from typing import Any
from zoneinfo import ZoneInfo

# ─── 规则与严重度常量 ─────────────────────────────────────────────

RULE_MONTH_LEVEL = "month_level"
RULE_MONTH_SLOPE = "month_slope"
RULE_SLOPE_CHANGE = "slope_change"
RULE_MONTH_OVER_MONTH = "month_over_month"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

TREND_RULE_TYPES = (
    RULE_MONTH_LEVEL,
    RULE_MONTH_SLOPE,
    RULE_SLOPE_CHANGE,
    RULE_MONTH_OVER_MONTH,
)

# ─── 判据参数（集中常量，便于调参与回归） ─────────────────────────

# 评估月最少批数（不足则退化为最后 K 批近似）
MIN_CURRENT_POINTS = 3
# 无日期时的"本期"批数：min(20, max(5, n//20))
SEQ_CURRENT_MIN = 5
SEQ_CURRENT_MAX = 20
# 当月 vs 历史：Δ 门槛（历史σ 倍数）与带宽占比；严重度分级带宽占比
MONTH_LEVEL_DELTA_SIGMA = 1.5
MONTH_LEVEL_BAND_RATIO = 0.08
MONTH_LEVEL_HIGH_BAND_RATIO = 0.15
MONTH_LEVEL_HIGH_T = 8.0
# 当月内趋势：当月累计变化门槛（历史σ 倍数）；斜率 t 门槛
MONTH_SLOPE_MOVE_SIGMA = 1.5
MONTH_SLOPE_T = 2.0
MONTH_SLOPE_HIGH_MOVE_SIGMA = 3.0
# 斜率较历史变化：t 门槛；严重度 t 门槛
SLOPE_CHANGE_T = 3.0
SLOPE_CHANGE_HIGH_T = 6.0
# 月度整体趋势：最少月数 / 连续同向月数
MONTH_OVER_MONTH_MIN_MONTHS = 3
MONTH_OVER_MONTH_CONSECUTIVE = 3
MONTH_OVER_MONTH_LEVEL_SIGMA = 0.5

# 粗筛业务约束（AI 终审前的提名门槛，防"正常波动被标异常"）：
# 全历史波动带：当月均值仍落在"除当月外全部历史"±Nσ 内 → 不提名
# （治"基线恰处低谷、回升到常态被报抬升"）
MONTH_LEVEL_ALL_BAND_SIGMA = 2.0
# 相对幅度：偏移/当月累计变化还须吃掉"距最近限度余量"的 N 倍才提名
# （无限度线时退化为基线均值的 N 倍；治极平数据/极远限度的"数字游戏"误报，
#  如干燥失重 σ≈0.005 偏 0.01 就统计显著）
MONTH_LEVEL_MIN_REL_DELTA = 0.10
MONTH_SLOPE_MIN_REL_MOVE = 0.10

# 每规则/每图最多上报条数（防刷屏）；标红只取本期尾部批次数
MAX_ANOMALIES_PER_RULE = 1
MAX_ANOMALIES_PER_CHART = 4
HIGHLIGHT_TAIL_BATCHES = 8


@dataclass(frozen=True)
class TrendAnomaly:
    """一条趋势异常事实（确定性判据产物）。"""

    rule_type: str
    severity: str
    start_batch: str
    end_batch: str
    description: str
    evidence: dict[str, Any]
    affected_batches: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_type": self.rule_type,
            "severity": self.severity,
            "start_batch": self.start_batch,
            "end_batch": self.end_batch,
            "description": self.description,
            "evidence": self.evidence,
            "affected_batches": list(self.affected_batches),
        }


# ─── 批号日期解析（评估月锚点） ───────────────────────────────────
# 业务批号口径：年月 + 流水号（如 USMC-M-2607007T = 2026-07 第 7 批）。


def _month_key_from_digits(digits: str) -> int | None:
    """把一段纯数字批号段解析为 YYYY*100+MM；月份非法返回 None。

    支持形态（按优先级）：
    - YYYYMMDD：8 位完整日期（20260815）
    - YYYYMM：6 位且以 20 开头（202608）
    - YYMMDD：6 位（260801）
    - YYMM+流水号：≥6 位数字段取前 4 位年月（2607007 → 2026-07）
    """
    if len(digits) >= 8 and digits.startswith("20"):
        year = int(digits[:4])
        month = int(digits[4:6])
        if 1 <= month <= 12:
            return year * 100 + month
    if len(digits) == 6 and digits.startswith("20"):
        year = int(digits[:4])
        month = int(digits[4:6])
        if 1 <= month <= 12:
            return year * 100 + month
    if len(digits) >= 6:
        yy = int(digits[:2])
        month = int(digits[2:4])
        if 1 <= month <= 12:
            return (2000 + yy) * 100 + month
    return None


def parse_batch_month(batch_no: str) -> int | None:
    """从批号解析月份键（YYYY*100+MM）；解析不出返回 None。"""
    text = str(batch_no or "").strip()
    if not text:
        return None
    for match in re.finditer(r"\d+", text):
        key = _month_key_from_digits(match.group(0))
        if key is not None:
            return key
    return None


def batch_is_current_month(
    batch_no: str, reference: datetime | None = None
) -> bool:
    """批号是否属于参照时间（默认北京时间当前月）所在月份。

    批号解析不出年月时返回 False（调用方可用"末尾 N 批"兜底）。
    """
    reference_dt = reference or datetime.now(ZoneInfo("Asia/Shanghai"))
    current_ym = reference_dt.year * 100 + reference_dt.month
    return parse_batch_month(batch_no) == current_ym


# ─── 内部工具 ─────────────────────────────────────────────────────


def _linear_slope(values: list[float]) -> float:
    """最小二乘斜率（单位：值/点）。点数 <2 时返回 0。"""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = fmean(xs)
    mean_y = fmean(values)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n)) / denom


def _slope_se(values: list[float], noise: float) -> float:
    """最小二乘斜率的标准误（给定残差噪声）。"""
    n = len(values)
    if n < 3:
        return 0.0
    sxx = sum((i - (n - 1) / 2) ** 2 for i in range(n))
    return noise / (sxx**0.5) if sxx > 0 else 0.0


def _diff_noise(values: list[float]) -> float:
    """差分噪声：相邻批次差的 σ/√2。对水位台阶/漂移稳健。"""
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    if len(diffs) < 2:
        return 0.0
    sd = pstdev(diffs)
    return sd / (2**0.5) if sd > 0 else 0.0


def _nearest_limits(
    spec_lines: list[dict[str, Any]] | None,
    upper_control_limit: float | None,
    lower_control_limit: float | None,
) -> tuple[float | None, float | None]:
    """取最紧的行动上限/下限：控制限与 OOT/标准线里更靠近中心者。"""
    upper = upper_control_limit
    lower = lower_control_limit
    for line in spec_lines or []:
        label = str(line.get("label") or "")
        raw_value = line.get("value")
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if "上限" in label:
            upper = value if upper is None else min(upper, value)
        elif "下限" in label:
            lower = value if lower is None else max(lower, value)
    return upper, lower


def spec_direction(spec_lines: list[dict[str, Any]] | None) -> str:
    """按标准/OOT 限度线判断指标业务方向（±3σ 控制限是统计带，不参与）。

    - 只给上限（如 杂质 ≤3.0% / 水分 ≤0.5% / 警戒与纠偏限度）→ "up_only"：
      越小越好，此时**下降是改善**，不应作为异常提名；
    - 只给下限（如 ≥90.0%）→ "down_only"：越大越好，上升是改善；
    - 双边（范围）或无限度线 → "both"：两个方向都可能是风险。
    """
    labels = [str(line.get("label") or "") for line in spec_lines or []]
    has_lower = any("下限" in label for label in labels)
    # 非"下限"标签（标准上限/OOT上限/警戒限度/纠偏限度）都按上限语义处理
    has_upper = any("下限" not in label for label in labels)
    if has_lower and not has_upper:
        return "down_only"
    if has_upper and not has_lower:
        return "up_only"
    return "both"


def _is_worsening(direction: str, delta: float) -> bool:
    """按业务方向判断变化方向是否为"恶化"（只有恶化才提名）。"""
    if direction == "up_only":
        return delta > 0
    if direction == "down_only":
        return delta < 0
    return True


def _amplitude_reference(
    hist_mean: float,
    upper_limit: float | None,
    lower_limit: float | None,
) -> float:
    """相对幅度门槛的参照量：优先"距最近限度的余量"，无限度线时退化 |基线均值|。

    业务含义="偏移至少要吃掉一定比例的剩余余量"才算有业务意义——这样
    0.100±0.002 的极平数据（余量 0.4）偏 0.005 会被拦（数字游戏），而
    100.5%（余量 3.5）掉到 97.5% 这种真实漂移仍会提名。
    """
    margins = [
        abs(limit - hist_mean)
        for limit in (upper_limit, lower_limit)
        if limit is not None
    ]
    positive = [m for m in margins if m > 0]
    if positive:
        return min(positive)
    return abs(hist_mean)


def _cap_batches(batches: list[str]) -> list[str]:
    return batches[-HIGHLIGHT_TAIL_BATCHES:]


# ─── 本期/基线切分 ────────────────────────────────────────────────


def split_current_history(
    batches: list[str], values: list[float]
) -> tuple[list[int], list[int], str]:
    """切出"评估月"（本期）与"基线"（紧邻的近期历史）索引。

    评估月 = 数据中最后一个有批号的月份；基线 = 其前 1~2 个日历月（点数不足
    时向前扩到 3 个月，仍不足则退化）。关键：基线是**近期**历史而非全部历史
    ——台阶发生当月会相对近期基线被报出，之后成为新平台便不再反复报旧事。
    批号完全解析不出时，本期取最后 K 批（K=min(20, max(5, n//20))），基线取
    其前等长段（time_basis="sequence"）。

    返回 (本期索引, 基线索引, time_basis)。
    """
    n = len(values)
    months = [parse_batch_month(b) for b in batches]
    parsed = sum(1 for m in months if m is not None)

    def _sequence_fallback() -> tuple[list[int], list[int], str]:
        k = min(SEQ_CURRENT_MAX, max(SEQ_CURRENT_MIN, n // 20))
        k = min(k, max(n // 2, 1))
        cur = list(range(n - k, n))
        base_len = min(max(2 * k, 10), n - k)
        base = list(range(n - k - base_len, n - k))
        return cur, base, "sequence"

    if parsed < max(MIN_CURRENT_POINTS, n // 2) or parsed == 0:
        return _sequence_fallback()

    groups: dict[int, list[int]] = {}
    for i, m in enumerate(months):
        if m is not None:
            groups.setdefault(m, []).append(i)
    keys = sorted(groups)
    latest = keys[-1]
    current = groups[latest]
    if len(current) < MIN_CURRENT_POINTS:
        return _sequence_fallback()

    base: list[int] = []
    # 依次向前取最近的 1~3 个日历月作为基线（超出 3 个月的历史不再纳入，
    # 避免旧台阶污染近期基线）；点数仍不足时继续向后兼容至点数足够
    prior_keys = list(reversed(keys[:-1]))
    for month_count, key in enumerate(prior_keys, start=1):
        base = groups[key] + base
        if len(base) >= max(MIN_CURRENT_POINTS * 2, 10):
            break
        if month_count >= 3:
            break
    if len(base) < MIN_CURRENT_POINTS:
        return _sequence_fallback()
    return current, base, "batch_month"


# ─── 四类确定性趋势判据（全部锚定评估月 vs 历史） ─────────────────


def _detect_month_level(
    current: list[float],
    history: list[float],
    hist_mean: float,
    hist_sigma: float,
    band: float | None,
    labels: dict[str, Any],
    *,
    direction: str,
    all_history: list[float],
    amplitude_reference: float,
) -> TrendAnomaly | None:
    """当月 vs 历史：本月均值较历史均值抬升/下移（粗筛提名，AI 终审）。"""
    if hist_sigma <= 0 or not current or not history:
        return None
    cur_mean = fmean(current)
    delta = cur_mean - hist_mean
    # 方向约束：单边上限指标下移=改善、单边下限指标抬升=改善，不提名
    if not _is_worsening(direction, delta):
        return None
    # 全历史波动带：当月均值仍在除当月外全部历史的 ±Nσ 内 → 属正常波动
    if len(all_history) >= 3:
        all_sigma = pstdev(all_history)
        if all_sigma > 0 and (
            abs(cur_mean - fmean(all_history))
            < MONTH_LEVEL_ALL_BAND_SIGMA * all_sigma
        ):
            return None
    delta_gate = MONTH_LEVEL_DELTA_SIGMA * hist_sigma
    if band is not None and band > 0:
        delta_gate = max(delta_gate, MONTH_LEVEL_BAND_RATIO * band)
    if abs(delta) < delta_gate:
        return None
    # 相对幅度：偏移须吃掉距最近限度余量的 N 倍（防极平数据/极远限度的数字游戏）
    if (
        amplitude_reference > 0
        and abs(delta) < MONTH_LEVEL_MIN_REL_DELTA * amplitude_reference
    ):
        return None
    noise = _diff_noise(list(history) + list(current))
    se = noise * ((1 / len(current) + 1 / len(history)) ** 0.5)
    t_like = abs(delta) / se if se > 0 else float("inf")
    if t_like < 3.0:
        return None

    word = "抬升" if delta > 0 else "下移"
    severity = SEVERITY_MEDIUM
    band_high = (
        band is not None
        and band > 0
        and abs(delta) >= MONTH_LEVEL_HIGH_BAND_RATIO * band
    )
    if band_high or t_like >= MONTH_LEVEL_HIGH_T:
        severity = SEVERITY_HIGH
    return TrendAnomaly(
        rule_type=RULE_MONTH_LEVEL,
        severity=severity,
        start_batch=labels["current_start"],
        end_batch=labels["current_end"],
        description=(
            f"本月均值 {cur_mean:g} 较历史均值 {hist_mean:g} {word} {abs(delta):g}"
            f"（显著性 t≈{t_like:.0f}），当月水平较历史发生偏移"
        ),
        evidence={
            "current_mean": round(cur_mean, 6),
            "history_mean": round(hist_mean, 6),
            "delta": round(delta, 6),
            "t_like": round(t_like, 2),
            "current_points": len(current),
            "history_points": len(history),
            **labels["extra"],
        },
        affected_batches=labels["tail"],
    )


def _detect_month_slope(
    current: list[float],
    hist_mean: float,
    hist_sigma: float,
    labels: dict[str, Any],
    *,
    direction: str,
    amplitude_reference: float,
) -> TrendAnomaly | None:
    """当月内趋势：本月批次自身呈持续上升/下降（粗筛提名，AI 终审）。"""
    if len(current) < MIN_CURRENT_POINTS or hist_sigma <= 0:
        return None
    slope = _linear_slope(current)
    # 方向约束：单边上限指标当月下降=改善、单边下限指标上升=改善，不提名
    if not _is_worsening(direction, slope):
        return None
    move = slope * len(current)
    if abs(move) < MONTH_SLOPE_MOVE_SIGMA * hist_sigma:
        return None
    # 相对幅度：当月累计变化须吃掉距最近限度余量的 N 倍
    if (
        amplitude_reference > 0
        and abs(move) < MONTH_SLOPE_MIN_REL_MOVE * amplitude_reference
    ):
        return None
    noise = _diff_noise(current)
    se = _slope_se(current, noise)
    t_like = abs(slope) / se if se > 0 else float("inf")
    if t_like < MONTH_SLOPE_T:
        return None

    word = "上升" if slope > 0 else "下降"
    severity = (
        SEVERITY_HIGH
        if abs(move) >= MONTH_SLOPE_HIGH_MOVE_SIGMA * hist_sigma
        else SEVERITY_MEDIUM
    )
    return TrendAnomaly(
        rule_type=RULE_MONTH_SLOPE,
        severity=severity,
        start_batch=labels["current_start"],
        end_batch=labels["current_end"],
        description=(
            f"本月呈持续{word}（斜率 {slope:+g}/批，本月累计 {move:+g}，"
            f"t≈{t_like:.0f}）"
        ),
        evidence={
            "slope_per_batch": round(slope, 6),
            "month_move": round(move, 6),
            "t_like": round(t_like, 2),
            "current_points": len(current),
            **labels["extra"],
        },
        affected_batches=labels["tail"],
    )


def _detect_slope_change(
    current: list[float],
    history: list[float],
    hist_mean: float,
    labels: dict[str, Any],
    *,
    direction: str,
) -> TrendAnomaly | None:
    """斜率较历史变化：本月斜率与历史斜率显著不同且朝限度方向。"""
    if len(current) < MIN_CURRENT_POINTS or len(history) < MIN_CURRENT_POINTS:
        return None
    slope_current = _linear_slope(current)
    # 方向约束：单边上限指标当月下降加速=改善，单边下限指标上升加速=改善
    if not _is_worsening(direction, slope_current):
        return None
    slope_history = _linear_slope(history)
    delta_slope = slope_current - slope_history
    if delta_slope == 0:
        return None
    noise_current = _diff_noise(current)
    noise_history = _diff_noise(history)
    noise = (noise_current + noise_history) / 2 or max(noise_current, noise_history)
    if noise <= 0:
        return None
    se = (
        _slope_se(current, noise) ** 2 + _slope_se(history, noise) ** 2
    ) ** 0.5
    t_like = abs(delta_slope) / se if se > 0 else float("inf")
    if t_like < SLOPE_CHANGE_T:
        return None
    # 方向须朝限度：新斜率方向上，当月水位已偏离历史中心
    if slope_current > 0 and fmean(current) <= hist_mean:
        return None
    if slope_current < 0 and fmean(current) >= hist_mean:
        return None

    if delta_slope > 0:
        word = "上升加速（较历史）"
    else:
        word = "下降加速（较历史）"
    severity = SEVERITY_HIGH if t_like >= SLOPE_CHANGE_HIGH_T else SEVERITY_MEDIUM
    return TrendAnomaly(
        rule_type=RULE_SLOPE_CHANGE,
        severity=severity,
        start_batch=labels["current_start"],
        end_batch=labels["current_end"],
        description=(
            f"斜率较历史变化：历史 {slope_history:+g}/批 → 本月 {slope_current:+g}/批"
            f"（{word}，t≈{t_like:.0f}）"
        ),
        evidence={
            "slope_history": round(slope_history, 6),
            "slope_current": round(slope_current, 6),
            "slope_delta": round(delta_slope, 6),
            "t_like": round(t_like, 2),
            "current_points": len(current),
            "history_points": len(history),
            **labels["extra"],
        },
        affected_batches=labels["tail"],
    )


def _detect_month_over_month(
    batches: list[str],
    values: list[float],
    hist_mean: float,
    hist_sigma: float,
    *,
    direction: str,
) -> TrendAnomaly | None:
    """月度整体趋势：≥3 个月度均值连续同向，给整体走向。"""
    months = [parse_batch_month(b) for b in batches]
    parsed = sum(1 for m in months if m is not None)
    n = len(values)
    if parsed < max(MONTH_OVER_MONTH_MIN_MONTHS, n // 2) or parsed == 0:
        return None
    groups: dict[int, list[float]] = {}
    for month, value in zip(months, values, strict=True):
        if month is None:
            continue
        groups.setdefault(month, []).append(value)
    keys = sorted(groups)
    if len(keys) < MONTH_OVER_MONTH_MIN_MONTHS:
        return None
    means = [(k, fmean(groups[k])) for k in keys]
    mean_series = [v for _, v in means]

    consecutive = 0
    for i in range(len(mean_series) - 1, 0, -1):
        step = mean_series[i] - mean_series[i - 1]
        if step == 0:
            break
        if consecutive == 0:
            consecutive = 1 if step > 0 else -1
        elif (step > 0) != (consecutive > 0):
            break
        else:
            consecutive += 1 if consecutive > 0 else -1
    if abs(consecutive) < MONTH_OVER_MONTH_CONSECUTIVE:
        return None
    # 方向约束：单边上限指标连续下降=改善、单边下限指标连续上升=改善
    if not _is_worsening(direction, float(consecutive)):
        return None
    level_offset = abs(mean_series[-1] - hist_mean)
    if hist_sigma > 0 and level_offset < MONTH_OVER_MONTH_LEVEL_SIGMA * hist_sigma:
        return None  # 走了几个来回、当前仍在中心带内，不报

    word = "连续上升" if consecutive > 0 else "连续下降"
    tail = " → ".join(
        f"{keys[i] // 100}-{keys[i] % 100:02d} {mean_series[i]:g}"
        for i in range(max(0, len(mean_series) - 3), len(mean_series))
    )
    return TrendAnomaly(
        rule_type=RULE_MONTH_OVER_MONTH,
        severity=SEVERITY_MEDIUM if abs(consecutive) < 4 else SEVERITY_HIGH,
        start_batch=str(keys[0]),
        end_batch=str(keys[-1]),
        description=(
            f"月度整体趋势：{word} {abs(consecutive)} 个月（{tail}）"
        ),
        evidence={
            "consecutive_months": int(consecutive),
            "monthly_means": {str(k): round(v, 6) for k, v in means},
            "months_compared": len(mean_series) - 1,
        },
        affected_batches=[],
    )


# ─── 对外入口 ─────────────────────────────────────────────────────


def detect_trend_anomalies(
    points: list[dict[str, Any]],
    *,
    mean: float | None = None,
    std_dev: float | None = None,
    upper_control_limit: float | None = None,
    lower_control_limit: float | None = None,
    spec_lines: list[dict[str, Any]] | None = None,
) -> list[TrendAnomaly]:
    """对单指标趋势点序列（``[{"batch_no", "value"}, ...]``，按批序）跑全部规则。

    评估口径：历史做基线、本月对基线比（水位/当月斜率/斜率变化/月度整体走向）。
    ``mean/std_dev/控制限/spec_lines`` 由调用方传入，仅作基线兜底与带宽计算。

    返回按严重度排序的异常列表；每规则最多 1 条、每图最多 4 条；样本不足或
    无命中返回空列表。结果只含确定性统计事实，不含任何模型输出。
    """
    if len(points) < 3:
        return []
    batches: list[str] = []
    values: list[float] = []
    for item in points:
        try:
            value = float(item["value"])
        except (KeyError, TypeError, ValueError):
            continue
        batches.append(str(item.get("batch_no") or ""))
        values.append(value)
    n = len(values)
    if n < 3:
        return []

    current_idx, baseline_idx, time_basis = split_current_history(batches, values)
    current_set = set(current_idx)
    baseline_set = set(baseline_idx)
    history_idx = [i for i in range(n) if i not in current_set and i in baseline_set]
    current = [values[i] for i in current_idx]
    history = [values[i] for i in history_idx]
    if not current or len(history) < 3:
        return []

    hist_mean = fmean(history)
    hist_sigma = pstdev(history) if len(history) >= 2 else 0.0
    if hist_sigma <= 0:
        hist_sigma = std_dev or 0.0
    if hist_sigma <= 0:
        hist_sigma = _diff_noise(values)
    upper_limit, lower_limit = _nearest_limits(
        spec_lines, upper_control_limit, lower_control_limit
    )
    band = (
        abs(upper_limit - lower_limit)
        if upper_limit is not None and lower_limit is not None
        else None
    )
    # 指标业务方向（只认标准/OOT 限度线）：越小越好 / 越大越好 / 双向
    direction = spec_direction(spec_lines)
    # 除当月外的全部历史（用于"是否仍在历史正常波动带内"判定）
    all_history = [values[i] for i in range(n) if i not in current_set]
    # 粗筛相对幅度参照量：距最近限度的余量（无限度线时退化基线均值的绝对值）
    amplitude_reference = _amplitude_reference(
        hist_mean, upper_limit, lower_limit
    )

    extra = {"time_basis": time_basis, "direction_mode": direction}
    labels = {
        "current_start": batches[current_idx[0]],
        "current_end": batches[current_idx[-1]],
        "tail": _cap_batches(batches),
        "extra": extra,
    }

    by_rule: dict[str, TrendAnomaly | None] = {
        RULE_MONTH_LEVEL: _detect_month_level(
            current,
            history,
            hist_mean,
            hist_sigma,
            band,
            labels,
            direction=direction,
            all_history=all_history,
            amplitude_reference=amplitude_reference,
        ),
        RULE_MONTH_SLOPE: _detect_month_slope(
            current,
            hist_mean,
            hist_sigma,
            labels,
            direction=direction,
            amplitude_reference=amplitude_reference,
        ),
        RULE_SLOPE_CHANGE: _detect_slope_change(
            current, history, hist_mean, labels, direction=direction
        ),
        RULE_MONTH_OVER_MONTH: _detect_month_over_month(
            batches,
            values,
            hist_mean,
            hist_sigma,
            direction=direction,
        ),
    }

    order = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}
    anomalies = [a for a in by_rule.values() if a is not None]
    anomalies.sort(key=lambda a: (order.get(a.severity, 3), a.rule_type))
    return anomalies[:MAX_ANOMALIES_PER_CHART]
