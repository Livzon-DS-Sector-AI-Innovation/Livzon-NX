"""趋势图服务端渲染单测（matplotlib Agg 出图 + 无头降级）。"""

from __future__ import annotations

from unittest.mock import patch

from app.modules.quality.service import trend_chart_render as r

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _payload() -> dict:
    categories = [f"B{i:02d}" for i in range(1, 9)]
    return {
        "metric_label": "含量（干品）",
        "source_label": "霉酚酸（内控）",
        "categories": categories,
        "actual_series": [97.0, 97.5, 98.0, 98.6, 99.0, 99.5, 99.9, 100.3],
        "mean": 98.6,
        "upper_control_limit": 100.4,
        "lower_control_limit": 96.8,
        "spec_lines": [{"label": "标准上限", "value": 103.0}],
        "highlight_batches": ["B07", "B08"],
    }


def test_render_returns_png_bytes() -> None:
    data = r.render_trend_chart_png(**_payload())
    assert data is not None
    assert data[:8] == _PNG_MAGIC
    assert len(data) > 1000


def test_render_guards_bad_inputs() -> None:
    assert r.render_trend_chart_png(**{**_payload(), "categories": []}) is None
    assert (
        r.render_trend_chart_png(
            **{**_payload(), "actual_series": [1.0]}  # 长度不匹配
        )
        is None
    )


def test_render_degrades_when_matplotlib_missing() -> None:
    # 模拟 matplotlib 不可用：import 抛错 → 返回 None，不抛异常
    with patch.dict("sys.modules", {"matplotlib": None}):
        data = r.render_trend_chart_png(**_payload())
    assert data is None
