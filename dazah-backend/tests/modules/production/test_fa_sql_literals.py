"""FA 飞书同步的文本单元格不得原样拼进 SQL 字面量。"""

from __future__ import annotations

import pytest

from app.modules.production.fa_acid_sync import _p as acid_percent
from app.modules.production.fa_feishu_scheduler import _p as scheduler_percent
from app.modules.production.fa_feishu_sync import _safe_pct

PAYLOAD = "12%'); DELETE FROM production.pack; --"


@pytest.mark.parametrize(
    "formatter",
    [scheduler_percent, acid_percent, _safe_pct],
)
def test_text_percent_value_is_quoted_and_escaped(formatter: object) -> None:
    formatted = formatter(PAYLOAD)  # type: ignore[operator]

    assert formatted == "'12%''); DELETE FROM production.pack; --'"
    assert formatted.count("''") == 1


def test_numeric_percent_values_stay_numeric_text() -> None:
    assert scheduler_percent("0.39") == "'39%'"
    assert acid_percent("0.5") == "'50%'"
