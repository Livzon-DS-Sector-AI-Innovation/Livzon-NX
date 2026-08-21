"""MC 飞书电子表格同步 + DR 追溯辅助纯函数测试。

覆盖 mc_feishu_sheets_sync 与 dr_lineage_api 中不依赖数据库/网络的可测纯函数，
把 CI 覆盖率里这些大面积未覆盖分支消化掉。
"""

from __future__ import annotations

from datetime import date

from app.modules.production import dr_lineage_api as dr
from app.modules.production import mc_feishu_sheets_sync as sync

# ═══════════ mc_feishu_sheets_sync 纯函数 ═══════════


def test_safe_float_variants():
    assert sync._safe_float(None) is None
    assert sync._safe_float("") is None
    assert sync._safe_float("#REF!") is None
    assert sync._safe_float("#N/A") is None
    assert sync._safe_float(" 3.5 ") == 3.5
    assert sync._safe_float("98%") == 98.0
    assert sync._safe_float("abc") is None
    assert sync._safe_float(7) == 7.0
    assert sync._safe_float([]) is None


def test_safe_int_variants():
    assert sync._safe_int(None) is None
    assert sync._safe_int("") is None
    assert sync._safe_int("#VALUE!") is None
    assert sync._safe_int("12") == 12
    assert sync._safe_int("1.7") == 1
    assert sync._safe_int("x") is None


def test_safe_date_variants():
    assert sync._safe_date(None) is None
    assert sync._safe_date("") is None
    assert sync._safe_date("#N/A") is None
    assert sync._safe_date("2026.03.01") == date(2026, 3, 1)
    assert sync._safe_date("2026-03-01") == date(2026, 3, 1)
    assert sync._safe_date("2026/03/01") == date(2026, 3, 1)
    # 只有月日 → 假定当年 2026
    assert sync._safe_date("03.01") == date(2026, 3, 1)
    assert sync._safe_date("not-a-date") is None


def test_safe_yield_scales_small_fractions():
    assert sync._safe_yield(0.91) == 91.0
    assert sync._safe_yield(1.0) == 1.0
    assert sync._safe_yield(98.5) == 98.5
    assert sync._safe_yield(None) is None


def test_parse_csv_line():
    assert sync._parse_csv_line("a,b,c") == ["a", "b", "c"]
    assert sync._parse_csv_line("a,b") == ["a", "b"]
    assert sync._parse_csv_line('"a,b",c') == ["a,b", "c"]
    assert sync._parse_csv_line('"",c') == ["", "c"]


def test_get_col_and_skip():
    assert sync._get_col(["a", " b ", "c"], 1) == "b"
    assert sync._get_col(["a"], 5) == ""
    assert sync._get_col([], 0) == ""

    # _is_skip_row：月份分隔行 / 空行 / 标题行
    assert sync._is_skip_row([]) is True
    assert sync._is_skip_row(["03月份"]) is True
    assert sync._is_skip_row(["", "", ""]) is True
    assert sync._is_skip_row(["霉酚酸粗提台账"]) is True
    assert sync._is_skip_row(["MC二次精制"]) is True
    assert sync._is_skip_row(["苯丙氨酸", "1号罐"]) is False


# ═══════════ dr_lineage_api 纯函数 ═══════════


def test_fmt_val():
    assert dr.fmt_val(3.5) == 3.5
    assert dr.fmt_val(None) == 0.0
    assert dr.fmt_val(0) == 0.0


def test_to_f1_normalization():
    assert dr._to_f1("DR-24019-1") == "DR-F1-24019-1"
    assert dr._to_f1("DR-F1-24019-1") == "DR-F1-24019-1"
    assert dr._to_f1("DR-24019-1 ") == "DR-F1-24019-1"
    assert dr._to_f1("OTHER") == "OTHER"


def test_f1_to_dr():
    assert dr._f1_to_dr("DR-F1-24019-1") == "DR-24019-1"
    assert dr._f1_to_dr("DR-24019-1") == "DR-24019-1"


def test_detect_stage_prefixes():
    assert dr._detect_stage("DR-GB-1") == "fourth_refinement"
    assert dr._detect_stage("DR-F3-1") == "third_refinement"
    assert dr._detect_stage("DR-F2-1") == "second_refinement"
    assert dr._detect_stage("DR-F1-1") == "first_refinement"
    assert dr._detect_stage("DR-H1") is None
    assert dr._detect_stage("DR-2601") is None


def test_split_feeds():
    assert dr._split_feeds("DR-F1-1 + DR-F1-2") == ["DR-F1-1", "DR-F1-2"]
    assert dr._split_feeds("DR-F1-1、DR-F1-2") == ["DR-F1-1", "DR-F1-2"]
    assert dr._split_feeds("DR-F1-1,DR-F1-2") == ["DR-F1-1", "DR-F1-2"]
    assert dr._split_feeds("DR-F1-1") == ["DR-F1-1"]
    assert dr._split_feeds("") == []


def test_feed_stage():
    assert dr._feed_stage("DR-F2-1") == "second_refinement"
    assert dr._feed_stage("DR-F1-1") == "first_refinement"
    assert dr._feed_stage("DR-F3-1") == "third_refinement"
    assert dr._feed_stage("DR-GB-1") == "fourth_refinement"
    assert dr._feed_stage("DR-H1/x") == "recovery"


def test_to_feeds():
    up = [("second_refinement", "DR-F1-1", 3.5), ("recovery", "回收粉", 0.0)]
    feeds = dr._to_feeds(up)
    assert len(feeds) == 2
    assert feeds[0].batch_no == "DR-F1-1"
    assert feeds[0].stage == "second_refinement"
    assert feeds[0].qty == 3.5
    assert feeds[1].qty == 0.0


def test_drg_models_and_labels():
    # 常量检查（无欲通过）
    assert dr.DR_STAGE_ORDER[0] == "fermentation"
    assert "fourth_refinement" in dr.DR_STAGE_LABELS
    assert dr._MAIN_TABLES["chromatography"][0] == "dr_chromatography_crystal"
