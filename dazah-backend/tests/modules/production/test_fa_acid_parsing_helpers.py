"""fa_acid_sync 解析 helper 行为测试（日期/数值/百分比清洗）。"""

from app.modules.production.fa_acid_sync import _g, _n, _p, _pd


def test_g_bounds_and_strip() -> None:
    row = ["  A ", "B"]
    assert _g(row, 0) == "A"
    assert _g(row, 1) == "B"
    assert _g(row, 2) == ""


def test_pd_maps_month_day_to_year_aware_date() -> None:
    # 12 月数据属于上一年度（2025），其余按 2026 解释
    assert _pd("12月5日") == "2025-12-05"
    assert _pd("1月10日") == "2026-01-10"
    assert _pd("3月1日 ") == "2026-03-01"
    assert _pd("无日期") is None


def test_n_number_cleaning() -> None:
    assert _n(" 3.5 ") == "3.5"
    assert _n("12%") == "12.0"
    assert _n("-") == "NULL"
    assert _n("#DIV/0!") == "NULL"
    assert _n("") == "NULL"


def test_p_percentage_formatting() -> None:
    assert _p("0.875") == "'88%'"
    assert _p("95.4") == "'95%'"
    assert _p("-") == "NULL"
    assert _p("") == "NULL"
    # 区间边界：n==1 保留原值
    assert _p("1") == "'1'"
