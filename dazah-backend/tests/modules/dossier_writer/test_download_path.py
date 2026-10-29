"""Dossier 导出文件下载必须限制在导出目录内。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.modules.dossier_writer.api import resolve_dossier_download_path


def test_resolves_plain_filename_inside_outputs_root(tmp_path: Path) -> None:
    target = tmp_path / "品种资料.docx"
    target.write_bytes(b"docx")

    resolved = resolve_dossier_download_path(str(tmp_path), target.name)

    assert resolved == target.resolve()


@pytest.mark.parametrize(
    "filename",
    [
        "../secret.docx",
        "..\\secret.docx",
        "../../etc/passwd",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "subdir/report.docx",
        ".",
        "..",
        "",
    ],
)
def test_rejects_traversal_and_absolute_paths(tmp_path: Path, filename: str) -> None:
    (tmp_path / "secret.docx").write_bytes(b"secret")

    with pytest.raises(HTTPException) as exc_info:
        resolve_dossier_download_path(str(tmp_path), filename)

    assert exc_info.value.status_code == 400
