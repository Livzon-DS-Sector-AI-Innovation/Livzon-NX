"""CSV 导出必须防止电子表格公式注入。"""

from __future__ import annotations

import pytest

from app.platform.identity.rbac_api import _csv_safe_cell


@pytest.mark.parametrize(
    "value",
    ['=HYPERLINK("http://evil")', "+1+1", "-2+3", "@SUM(A1)"],
)
def test_formula_like_cells_are_prefixed(value: str) -> None:
    assert _csv_safe_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["张三", "质量部", "", 0, None])
def test_plain_cells_are_unchanged(value: object) -> None:
    assert _csv_safe_cell(value) == value
