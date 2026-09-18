from __future__ import annotations

from app.modules.quality.service.trend_ai_prompt import (
    _parse_limit_values,
    build_trend_ai_prompt,
)


def test_prompt_skips_none_limit_and_series_values() -> None:
    assert _parse_limit_values(
        [
            {"label": "标准上限", "value": None},
            {"label": "标准下限", "value": 1},
            {"label": "标准上限", "value": 5},
        ]
    ) == (5.0, 1.0)

    prompt = build_trend_ai_prompt(
        source_label="产品A",
        metric_label="含量",
        points=[
            {"batch_no": "B1", "value": None},
            {"batch_no": "B2", "value": 2},
        ],
        mean=2.0,
        std_dev=None,
        upper_control_limit=5.0,
        lower_control_limit=None,
        spec_lines=[{"label": "标准上限", "value": None}],
        anomalies=[],
    )

    assert "B2: 2" in prompt
    assert "B1: " not in prompt
