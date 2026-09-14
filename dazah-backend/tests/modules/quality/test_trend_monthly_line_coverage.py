"""趋势 AI 月度定时的产品线覆盖测试：15 条目录线必须逐条可调度。

历史缺陷：月度任务只跑 9 个分组入口的默认线，霉酚酸（高规）、洛伐他汀（USP）、
多拉菌素（兽药）、汉光（K1）、色氨酸粉末、5%芬苯达唑粉 永远拿不到月度分析。
"""

from __future__ import annotations

from app.modules.quality.service.inspection_dashboard_config import (
    FINISHED_DASHBOARD_LINE_CATALOG,
)
from app.modules.quality.service.trend_monthly_analysis import (
    _GROUP_ENTRIES,
    iter_monthly_lines,
    resolve_line_group,
)


def test_monthly_lines_cover_full_catalog() -> None:
    lines = iter_monthly_lines()
    covered = {entity_code for entity_code, _label, _entry in lines}
    catalog = {entity_code for entity_code, _label in FINISHED_DASHBOARD_LINE_CATALOG}
    assert catalog, "产品线目录不应为空"
    assert covered == catalog, f"月度分析漏线：{sorted(catalog - covered)}"
    assert len(lines) == len(FINISHED_DASHBOARD_LINE_CATALOG) == 15


def test_monthly_lines_include_alternate_entity_codes() -> None:
    """同入口的备选线（非入口默认值）也必须在清单里。"""
    lines = iter_monthly_lines()
    default_codes = {
        "qc_finished_internal",
        "qc_finished_mvt",
        "qc_finished_lft_ep",
        "qc_finished_dor_gb",
        "qc_finished_lkms_vet",
        "qc_finished_fcc14",
        "qc_finished_trp_granule",
        "qc_finished_flu_powder",
        "qc_finished_pure_water",
    }
    covered = {entity_code for entity_code, _label, _entry in lines}
    alternates = covered - default_codes
    assert alternates == {
        "qc_finished_high_spec",
        "qc_finished_lft_usp",
        "qc_finished_dor_vet",
        "qc_finished_bbas_hanguang_k1",
        "qc_finished_trp_powder",
        "qc_finished_fen_powder",
    }


def test_every_entry_resolves_to_registered_group() -> None:
    for entity_code, label, entry in iter_monthly_lines():
        group = resolve_line_group(entity_code)
        assert group is not None, f"{entity_code}（{label}）未登记分组"
        assert _GROUP_ENTRIES.get(group) is entry
