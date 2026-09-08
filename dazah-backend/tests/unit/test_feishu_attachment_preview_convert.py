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
