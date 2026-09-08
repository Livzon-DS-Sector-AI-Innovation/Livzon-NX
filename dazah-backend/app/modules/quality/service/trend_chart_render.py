"""成品检测趋势图服务端渲染（matplotlib Agg 无头）。

把趋势仪表盘单指标序列画成 PNG 字节流，供飞书卡片 image_key 上传。
全模块任何失败（未安装 matplotlib / 无 CJK 字体 / 数据异常）均返回 None，
调用方降级为“无图片仍正常发送卡片/展示”，绝不让渲染阻塞业务链路。
"""

from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 中文字体候选：生产镜像 fonts-noto-cjk 提供 Noto Sans CJK SC；
# 本地开发常见微软雅黑/文泉驿/思源，取首个可用。
_CJK_FONT_CANDIDATES = (
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "WenQuanYi Zen Hei",
    "Microsoft YaHei",
    "SimHei",
    "Source Han Sans SC",
    "PingFang SC",
)


def _select_cjk_font() -> str | None:
    try:
        from matplotlib import font_manager
    except Exception:  # noqa: BLE001 —— 未安装时静默降级
        return None
    try:
        available = {f.name for f in font_manager.fontManager.ttflist}
    except Exception:  # noqa: BLE001
        available = set()
    for name in _CJK_FONT_CANDIDATES:
        if name in available:
            return name
    return None


def render_trend_chart_png(
    *,
    metric_label: str,
    source_label: str,
    categories: list[str],
    actual_series: list[float],
    mean: float | None = None,
    upper_control_limit: float | None = None,
    lower_control_limit: float | None = None,
    spec_lines: list[dict[str, Any]] | None = None,
    highlight_batches: list[str] | None = None,
) -> bytes | None:
    """渲染趋势折线为 PNG 字节；失败返回 None（不抛异常）。"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001 —— matplotlib 缺失/初始化失败
        logger.warning(
            "trend chart skipped: matplotlib unavailable (%s)", type(exc).__name__
        )
        return None

    if not categories or not actual_series or len(categories) != len(actual_series):
        return None

    try:
        font = _select_cjk_font()
        if font:
            plt.rcParams["font.sans-serif"] = [font, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

        fig, ax = plt.subplots(figsize=(9, 4.2), dpi=120)
        x = list(range(len(categories)))
        ax.plot(
            x,
            actual_series,
            color="#52c41a",
            linewidth=2,
            marker="o",
            markersize=4,
            label="实际值",
        )

        if mean is not None:
            ax.axhline(mean, color="#91caff", linewidth=1.4, label="平均值")
        if upper_control_limit is not None:
            ax.axhline(
                upper_control_limit,
                color="#faad14",
                linestyle="--",
                linewidth=1.4,
                label="均值+3σ",
            )
        if lower_control_limit is not None:
            ax.axhline(
                lower_control_limit,
                color="#d4a017",
                linestyle="--",
                linewidth=1.4,
                label="均值-3σ",
            )

        for line in spec_lines or []:
            value = line.get("value")
            if value is None:
                continue
            label = str(line.get("label") or "")
            color = (
                "#722ed1"
                if "OOT上限" in label
                else "#eb2f96"
                if "下限" in label
                else "#ff4d4f"
            )
            ax.axhline(float(value), color=color, linewidth=1.2, label=label)

        # 高亮趋势异常涉及的批次点
        highlight = set(highlight_batches or [])
        if highlight:
            hx = [x[i] for i, c in enumerate(categories) if c in highlight]
            hy = [
                actual_series[i]
                for i, c in enumerate(categories)
                if c in highlight and i < len(actual_series)
            ]
            if hx:
                ax.scatter(
                    hx,
                    hy,
                    color="#ff4d4f",
                    s=70,
                    zorder=5,
                    edgecolors="white",
                    linewidths=1,
                    label="趋势异常批次",
                )

        # x 轴批号抽样，避免拥挤
        max_labels = 12
        step = max(1, len(categories) // max_labels)
        ticks = x[::step]
        ax.set_xticks(ticks)
        ax.set_xticklabels(
            [categories[i] for i in ticks],
            rotation=30,
            ha="right",
            fontsize=8,
        )
        ax.set_title(
            f"{source_label} · {metric_label} 趋势",
            fontsize=12,
        )
        ax.set_ylabel("检验结果", fontsize=10)
        ax.grid(True, linestyle=":", alpha=0.4)
        ax.legend(fontsize=8, loc="best", ncol=2)
        fig.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png")
        buffer.seek(0)
        data = buffer.getvalue()
        plt.close(fig)
        return data
    except Exception as exc:  # noqa: BLE001 —— 渲染失败降级为无图
        logger.warning("trend chart render failed: %s", type(exc).__name__)
        try:
            plt.close("all")  # type: ignore[name-defined]
        except Exception:  # noqa: BLE001
            pass
        return None
