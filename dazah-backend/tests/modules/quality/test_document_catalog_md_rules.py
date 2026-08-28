from __future__ import annotations

import builtins
from io import BytesIO
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest
from docx import Document

from app.core.exceptions import AppException
from app.modules.quality.service import document_catalog_md as md

SimpleNamespace: Any = _SimpleNamespace


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("审核及颁发 / Review and issue", True),
        ("Distribution 分发", True),
        ("正文", False),
    ],
)
def test_section_marker_detection(line: str, expected: bool) -> None:
    assert md.is_section_marker_to_delete(line) is expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("", False),
        ("Prepared by", True),
        ("Distribution-1", True),
        ("颁发：", True),
        (" ( signature ) ", True),
        ("date", True),
        ("日期 date", False),
        ("正常正文", False),
    ],
)
def test_boilerplate_detection(line: str, expected: bool) -> None:
    assert md.is_boilerplate_text_line(line) is expected


def test_row_helpers_cover_empty_separator_and_number_cases() -> None:
    assert md.strip_bold("**1**") == "1"
    assert md.non_empty([" a ", "", " b "]) == ["a", "b"]
    assert md.parse_row("| a | b |") == ["a", "b"]
    assert md.is_sep_row([]) is False
    assert md.is_sep_row(["---", ":---:"]) is True
    assert md.is_dash_row(["", " "]) is False
    assert md.is_dash_row(["—", "-"]) is True
    assert md.is_distribution_list([["ordinary"], ["分发-1"]]) is True
    assert md.is_distribution_list([["ordinary"]]) is False
    assert md.is_approval_row(["审核1", "签名"]) is True
    assert md.is_approval_row(["正文"]) is False
    assert md.is_placeholder(["/", "--"]) is True
    assert md.is_placeholder(["无斜线"]) is False
    assert md.is_placeholder(["/", "签名"]) is False
    assert md.is_num_row([]) is False
    assert md.is_num_row(["**1.2.**", "标题"]) is True


def test_render_outline_and_flat_cover_all_layouts() -> None:
    assert md.render_outline(
        [[], ["引言", "正文"], ["1", "一级"], ["1.1", "二级"], ["结尾"]]
    ) == ["引言 正文", "1 一级", "", "  1.1 二级", "结尾"]
    assert md.render_flat(
        [[], ["/", "--"], ["名称", "值"], ["A", "1", "B", "2"], ["单项"]]
    ) == ["名称：值", "A：1；B：2", "单项"]


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        (["|---|---|", "|—|-|"], []),
        (["|名称|Distribution-1|"], []),
        (["|Prepared by|Signature|"], []),
        (
            ["|字段|值|", "|---|---|", "|1|一级|", "|1.1|二级|"],
            ["字段：值", "1 一级", "", "  1.1 二级"],
        ),
    ],
)
def test_convert_table(rows: list[str], expected: list[str]) -> None:
    assert md.convert_table(rows) == expected


def test_transform_text_removes_markers_tables_and_boilerplate() -> None:
    result = md.transform_text(
        [
            "审核及颁发 / Review and issue",
            "**保留标题**",
            "|字段|值|",
            "|---|---|",
            "|名称|内容|",
            "Prepared by",
            "正文",
            "",
            "",
            "结尾",
        ]
    )
    assert result == ["**保留标题**", "字段：值", "名称：内容", "正文", "", "结尾"]


def test_docx_helpers_and_word_conversion_preserve_tables() -> None:
    document = Document()
    document.add_paragraph("正文")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "字段"
    table.cell(0, 1).text = "值"
    table.cell(1, 0).text = "名称"
    table.cell(1, 1).text = "内容"
    nested = table.cell(1, 1).add_table(rows=1, cols=1)
    nested.cell(0, 0).text = "嵌套"
    stream = BytesIO()
    document.save(stream)

    markdown = md.word_to_markdown(stream.getvalue())
    assert "正文" in markdown
    assert "| 字段 | 值 |" in markdown
    assert "嵌套" in markdown
    assert md.convert_word_attachment("test.docx", stream.getvalue())


def test_cell_and_nested_table_helpers_cover_dedup_and_depth_limit() -> None:
    tc: Any = object()
    first: Any = SimpleNamespace(_tc=tc)
    second: Any = SimpleNamespace(_tc=tc)
    third: Any = SimpleNamespace(_tc=object())
    assert md._dedup_merged_cells([first, second, third]) == [first, third]

    cell: Any = SimpleNamespace(
        paragraphs=[
            SimpleNamespace(text=" a "),
            SimpleNamespace(text=""),
            SimpleNamespace(text="b"),
        ]
    )
    assert md._cell_text(cell) == "a<br>b"
    assert md._cell_text(SimpleNamespace(paragraphs=[])) == ""
    assert md._collect_nested_tables(SimpleNamespace(rows=[]), depth=6) == []


def test_find_soffice_prefers_config_then_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(md, "DOC_CONVERTER_BIN", "configured")
    monkeypatch.setattr(md.os.path, "exists", lambda path: path == "configured")  # type: ignore[attr-defined]
    assert md._find_soffice() == "configured"

    monkeypatch.setattr(md, "DOC_CONVERTER_BIN", "")
    monkeypatch.setattr(
        md.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "office-bin" if name == "libreoffice" else None,
    )
    assert md._find_soffice() == "office-bin"
    monkeypatch.setattr(md.shutil, "which", lambda _name: None)  # type: ignore[attr-defined]
    assert md._find_soffice() is None


def test_soffice_conversion_handles_missing_binary_and_process_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(md, "_find_soffice", lambda: None)
    assert md._convert_doc_via_soffice(b"doc", "test.doc") == b""

    monkeypatch.setattr(md, "_find_soffice", lambda: "office-bin")
    monkeypatch.setattr(
        md.subprocess,  # type: ignore[attr-defined]
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("failed")),
    )
    assert md._convert_doc_via_soffice(b"doc", "test.doc") == b""


def test_convert_doc_to_docx_uses_primary_converter_or_reports_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(md, "_convert_doc_via_soffice", lambda *_args: b"docx")
    assert md.convert_doc_to_docx(b"doc", "test.doc") == b"docx"

    monkeypatch.setattr(md, "_convert_doc_via_soffice", lambda *_args: b"")
    original_import = builtins.__import__

    def import_without_win32(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "win32com.client":
            raise ImportError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_win32)
    with pytest.raises(AppException, match="不支持 .doc"):
        md.convert_doc_to_docx(b"doc", "test.doc")


def test_doc_attachment_runs_conversion_before_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        md, "convert_doc_to_docx", lambda content, _name: content + b"x"
    )
    monkeypatch.setattr(md, "word_to_markdown", lambda content: f"正文-{content!r}")
    result = md.convert_word_attachment("legacy.DOC", b"a")
    assert result == "正文-b'ax'"
