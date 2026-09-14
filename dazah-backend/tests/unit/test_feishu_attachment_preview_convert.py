"""飞书附件预览：office 转 PDF 的临时文件名压平防护单测。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import app.modules.quality.service.feishu_attachment_preview as preview_mod
from app.modules.quality.service.feishu_attachment_preview import (
    _flatten_attachment_name,
    convert_office_to_pdf,
)


def test_flatten_strips_path_separators() -> None:
    assert _flatten_attachment_name("..\\..\\evil.doc") == "evil.doc"
    assert _flatten_attachment_name("a/b/c.xlsx") == "c.xlsx"
    assert _flatten_attachment_name("正常 文档名.wps") == "正常 文档名.wps"


def test_flatten_empty_falls_back() -> None:
    assert _flatten_attachment_name("") == "attachment.doc"
    assert _flatten_attachment_name("../../") == "attachment.doc"


def test_convert_src_path_stays_in_tmp_dir(monkeypatch: Any) -> None:
    """附件名携带路径穿越片段时，写入临时目录的源文件路径必须已被压平。"""
    monkeypatch.setattr(preview_mod, "_find_soffice", lambda: "soffice")
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        calls.append(argv)
        return type("R", (), {"returncode": 1})()

    monkeypatch.setattr(preview_mod.subprocess, "run", fake_run)
    assert convert_office_to_pdf(b"x", "..\\..\\pwned.docx") == b""
    assert len(calls) == preview_mod._SOFFICE_RETRIES + 1
    for argv in calls:
        src = Path(argv[-1])
        out_dir = Path(argv[argv.index("--outdir") + 1])
        assert ".." not in src.parts
        assert src.parent == out_dir.parent


def test_convert_success_reads_pdf_from_out_dir(monkeypatch: Any) -> None:
    monkeypatch.setattr(preview_mod, "_find_soffice", lambda: "soffice")

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        src = Path(argv[-1])
        out_dir = Path(argv[argv.index("--outdir") + 1])
        assert ".." not in src.parts
        (out_dir / f"{src.stem}.pdf").write_bytes(b"%PDF-fake")
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(preview_mod.subprocess, "run", fake_run)
    pdf = convert_office_to_pdf(b"x", "报表 2026.xlsx")
    assert pdf == b"%PDF-fake"


def test_convert_without_soffice_returns_empty(monkeypatch: Any) -> None:
    monkeypatch.setattr(preview_mod, "_find_soffice", lambda: None)
    assert convert_office_to_pdf(b"x", "a.doc") == b""


def test_text_extensions_previewable_and_decoded() -> None:
    """文本类附件：txt/log/md/json/xml/yaml 支持预览并解码为 UTF-8。"""
    from app.core.exceptions import AppException
    from app.modules.quality.service.feishu_attachment_preview import (
        PREVIEWABLE_EXTS,
        decode_text_preview,
        resolve_preview_content,
    )

    for ext in (".txt", ".log", ".md", ".json", ".xml", ".yaml", ".yml"):
        assert ext in PREVIEWABLE_EXTS

    content = "中文校准记录\nline2".encode("gb18030")
    body, mime, filename = resolve_preview_content(content, "", "记录.txt")
    assert mime == "text/plain; charset=utf-8"
    assert body.decode("utf-8") == "中文校准记录\nline2"
    assert filename == "记录.txt"

    assert decode_text_preview("plain".encode("utf-8")) == "plain"

    # 超限文本提示下载
    big = b"x" * (2 * 1024 * 1024 + 1)
    try:
        resolve_preview_content(big, "", "big.log")
    except AppException as exc:
        assert exc.status_code == 400
        assert "下载" in exc.message
    else:  # pragma: no cover - 应当抛出
        raise AssertionError("oversize text should not be previewable")


def test_office_previewable_ext_unchanged() -> None:
    """csv 仍走 office→PDF 路径（保持既有行为），文本集合不与 office 交集。"""
    from app.modules.quality.service.feishu_attachment_preview import (
        PREVIEW_OFFICE_EXTS,
        PREVIEW_TEXT_EXTS,
    )

    assert ".csv" in PREVIEW_OFFICE_EXTS
    assert not (PREVIEW_OFFICE_EXTS & PREVIEW_TEXT_EXTS)
