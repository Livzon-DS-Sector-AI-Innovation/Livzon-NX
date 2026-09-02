"""document_catalog_docx_md 纯文本/表格 helper 测试。

覆盖文件名编号/标题解析、序号→标题层级、二维表转 MD、重复列去重、
表格等价判定——均为不依赖 python-docx 对象的纯函数。
"""

from app.modules.quality.service.document_catalog_docx_md import (
    _dedupe_table_columns,
    _extract_file_number,
    _extract_file_title,
    _heading_level,
    _is_section_number,
    _table_data_to_md,
    _tables_identical,
)


def test_is_section_number() -> None:
    assert _is_section_number("1、")
    assert _is_section_number("1.2.3")
    assert _is_section_number("10.")
    assert not _is_section_number("")
    assert not _is_section_number("第一章")
    assert not _is_section_number("1.2.3 目的")


def test_heading_level_maps_depth() -> None:
    assert _heading_level("1") == 2
    assert _heading_level("1.1") == 3
    assert _heading_level("1.1.1") == 4
    assert _heading_level("1.1.1.1") == 0  # 过深不转标题
    assert _heading_level("2、") == 2


def test_table_data_to_md_builds_header_and_rows() -> None:
    md = _table_data_to_md([["名称", "编号"], ["甲", "A1"], ["  ", "  "]])
    lines = md.splitlines()
    assert "| 名称 | 编号 |" in lines
    assert "|---|---|" in lines
    # 全空行被跳过
    assert "|   |   |" not in md
    assert _table_data_to_md([]) == ""


def test_dedupe_table_columns_collapses_identical_columns() -> None:
    rows = [
        ["表头", "表头", "不同"],
        ["a", "a", "b"],
        ["c", "c", "d"],
    ]
    out = _dedupe_table_columns(rows)
    assert out[0] == ["表头", "不同"]
    assert out[1] == ["a", "b"]
    # 单列或空表原样返回
    assert _dedupe_table_columns([["x"], ["y"]]) == [["x"], ["y"]]
    assert _dedupe_table_columns([]) == []


def test_extract_file_number_and_title() -> None:
    # 两段式前缀（SOP-QA-002）可识别编号并剥离出标题
    assert _extract_file_number("SOP-QA-002 取样管理.pdf") == "SOP-QA-002"
    assert _extract_file_title("SOP-QA-002 取样管理.pdf") == "取样管理"
    assert _extract_file_title("SOP-QA-002取样管理.pdf") == "取样管理"
    # 多段前缀与无编号文件名按原样返回（正则限两段式，属既有契约）
    stp = "STP-QS-MC-001-06设备校准规程.docx"
    assert _extract_file_number(stp) == "STP-QS-MC-001-06设备校准规程"
    assert _extract_file_number("无编号文件.docx") == "无编号文件"
    assert _extract_file_title("纯标题.docx") == "纯标题"


def test_tables_identical() -> None:
    a = [["1", "2"], ["3", "4"]]
    assert _tables_identical(a, [row[:] for row in a])
    assert not _tables_identical(a, [["1", "2"]])
    assert not _tables_identical(a, [["1", "9"], ["3", "4"]])
