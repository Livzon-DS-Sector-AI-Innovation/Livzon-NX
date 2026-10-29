"""平台附件在线预览内容解析测试（纯函数 + soffice 子进程 mock）。"""

from __future__ import annotations

import os
import subprocess

import pytest

from app.platform.storage.preview import (
    PREVIEWABLE_EXTS,
    _find_soffice,
    _flatten_file_name,
    convert_office_to_pdf,
    resolve_preview_content,
)


def test_flatten_file_name_strips_path_segments() -> None:
    assert _flatten_file_name("..\\..\\etc\\危险品 MSDS.doc") == "危险品 MSDS.doc"
    assert _flatten_file_name("../../etc/passwd.doc") == "passwd.doc"
    assert _flatten_file_name("   ") == "attachment.doc"
    assert _flatten_file_name("/a/b/报告.docx") == "报告.docx"


def test_find_soffice_prefers_doc_converter_bin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.platform.storage.preview._DOC_CONVERTER_BIN", "/opt/bin/soffice"
    )
    monkeypatch.setattr(os.path, "exists", lambda _: True)
    assert _find_soffice() == "/opt/bin/soffice"


def test_find_soffice_returns_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.platform.storage.preview as preview_module

    monkeypatch.setattr("app.platform.storage.preview._DOC_CONVERTER_BIN", "")
    monkeypatch.setattr(preview_module.shutil, "which", lambda name: None)
    assert _find_soffice() is None


def test_resolve_preview_content_images_and_pdf() -> None:
    content, mime, name = resolve_preview_content(b"png", "a.png")
    assert (content, mime, name) == (b"png", "image/png", "a.png")
    assert resolve_preview_content(b"gif", "x.gif")[1] == "image/gif"
    assert resolve_preview_content(b"%PDF", "报告.pdf") == (
        b"%PDF",
        "application/pdf",
        "报告.pdf",
    )


def test_resolve_preview_content_rejects_unknown_ext() -> None:
    with pytest.raises(ValueError, match="格式暂不支持在线预览"):
        resolve_preview_content(b"mz", "tool.exe")


def test_resolve_preview_content_office_converted_to_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.platform.storage.preview.convert_office_to_pdf",
        lambda content, name: b"%PDF-fake",
    )
    content, mime, name = resolve_preview_content(b"doc-bytes", "检测报告.doc")
    assert content == b"%PDF-fake"
    assert mime == "application/pdf"
    assert name == "检测报告.pdf"


def test_resolve_preview_content_office_failure_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.platform.storage.preview.convert_office_to_pdf", lambda *_: b""
    )
    with pytest.raises(ValueError, match="转 PDF 失败"):
        resolve_preview_content(b"doc-bytes", "检测报告.doc")


def test_convert_office_to_pdf_returns_empty_without_soffice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.platform.storage.preview._find_soffice", lambda: None
    )
    assert convert_office_to_pdf(b"doc", "a.doc") == b""


def test_convert_office_to_pdf_reads_converted_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.platform.storage.preview._find_soffice", lambda: "/usr/bin/soffice"
    )
    seen_cmds: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        seen_cmds.append(list(cmd))
        out_dir = cmd[cmd.index("--outdir") + 1]
        src = cmd[-1]
        base = os.path.splitext(os.path.basename(src))[0]
        with open(os.path.join(out_dir, f"{base}.pdf"), "wb") as f:
            f.write(b"%PDF-converted")
        run = subprocess.CompletedProcess(cmd, 0, b"", b"")
        return run

    monkeypatch.setattr(
        "app.platform.storage.preview.subprocess.run", fake_run
    )
    result = convert_office_to_pdf(b"doc", "车间 报告.wps")
    assert result == b"%PDF-converted"
    assert seen_cmds[0][0] == "/usr/bin/soffice"
    assert "--headless" in seen_cmds[0]


def test_convert_office_to_pdf_retries_then_empty_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.platform.storage.preview._find_soffice", lambda: "/usr/bin/soffice"
    )
    calls: list[int] = []

    def fake_run(_cmd, **_kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired(cmd="soffice", timeout=60)

    monkeypatch.setattr(
        "app.platform.storage.preview.subprocess.run", fake_run
    )
    assert convert_office_to_pdf(b"doc", "a.doc") == b""
    # 首次超时 + 重试一次
    assert len(calls) == 2


def test_convert_office_to_pdf_nonzero_returncode_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.platform.storage.preview._find_soffice", lambda: "/usr/bin/soffice"
    )
    calls: list[int] = []
    monkeypatch.setattr(
        "app.platform.storage.preview.subprocess.run",
        lambda cmd, **_kwargs: calls.append(1)
        or subprocess.CompletedProcess(cmd, 1, b"", b"boom"),
    )
    assert convert_office_to_pdf(b"doc", "a.doc") == b""
    assert len(calls) == 2


def test_previewable_ext_sets_cover_common_formats() -> None:
    assert ".pdf" in PREVIEWABLE_EXTS
    assert ".docx" in PREVIEWABLE_EXTS
    assert ".png" in PREVIEWABLE_EXTS
    assert ".exe" not in PREVIEWABLE_EXTS
