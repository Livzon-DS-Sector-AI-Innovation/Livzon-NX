"""Document catalog attachment markdown conversion service.

word（.doc/.docx/.wps）→ 标准 MD 两段式：
  ① .doc/.wps 经 LibreOffice headless 转 .docx（Windows 下 .doc 另有 Word COM 兜底）；
  ② .docx 走 `document_catalog_docx_md` 的模板化转换管线（移植自公司文件库
     脚本）：序号转标题层级、正文/嵌套表格保留为 Markdown 表格、图片提取。

转换失败抛出异常，由调用方决定降级策略（附件服务降级为原样存储）。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.exceptions import AppException
from app.modules.quality.service.document_catalog_docx_md import (
    ExtractedImage,
    convert_docx_content_to_md,
)

logger = logging.getLogger(__name__)

DOC_CONVERTER_BIN = os.environ.get("DOC_CONVERTER_BIN", "")

LEGACY_WORD_EXTS = frozenset({".doc", ".wps"})

__all__ = [
    "DOC_CONVERTER_BIN",
    "ExtractedImage",
    "LEGACY_WORD_EXTS",
    "convert_legacy_to_docx",
    "convert_word_attachment",
]


def _find_soffice() -> str | None:
    if DOC_CONVERTER_BIN and os.path.exists(DOC_CONVERTER_BIN):
        return DOC_CONVERTER_BIN
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _convert_doc_via_soffice(content: bytes, file_name: str) -> bytes:
    soffice = _find_soffice()
    if not soffice:
        return b""
    with tempfile.TemporaryDirectory() as tmp_dir:
        src_path = os.path.join(tmp_dir, file_name)
        out_dir = os.path.join(tmp_dir, "out")
        os.makedirs(out_dir, exist_ok=True)
        with open(src_path, "wb") as f:
            f.write(content)
        try:
            result = subprocess.run(
                [
                    soffice,
                    "--headless",
                    # 容器内 HOME 常不可写（如源码挂载覆盖 /app），
                    # 每次调用用独立配置目录，避免权限问题与并发实例锁冲突
                    f"-env:UserInstallation={Path(tmp_dir).joinpath('lo_profile').as_uri()}",
                    "--convert-to",
                    "docx",
                    "--outdir",
                    out_dir,
                    src_path,
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning(
                "soffice convert failed",
                extra={"business_module": "quality", "error": str(exc)},
            )
            return b""
        dst_path = os.path.join(out_dir, os.path.splitext(file_name)[0] + ".docx")
        if result.returncode != 0 or not os.path.exists(dst_path):
            logger.warning(
                "soffice convert non-zero",
                extra={"component": "quality", "returncode": result.returncode},
            )
            return b""
        with open(dst_path, "rb") as f:
            return f.read()


def _convert_doc_via_word_com(content: bytes, file_name: str) -> bytes:
    """Windows Word COM 兜底（需 pywin32），仅用于 .doc。"""
    import win32com.client  # type: ignore[import-untyped]

    with tempfile.TemporaryDirectory() as tmp_dir:
        src_path = os.path.join(tmp_dir, file_name)
        dst_path = os.path.join(tmp_dir, os.path.splitext(file_name)[0] + ".docx")
        with open(src_path, "wb") as f:
            f.write(content)
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        try:
            doc = word.Documents.Open(src_path)
            doc.SaveAs2(dst_path, FileFormat=16)  # 16 = wdFormatXMLDocument (.docx)
            doc.Close(False)
        finally:
            word.Quit()
        with open(dst_path, "rb") as f:
            return f.read()


def convert_legacy_to_docx(content: bytes, file_name: str) -> bytes:
    """.doc/.wps → .docx：优先 LibreOffice headless（.wps 依赖其 Works/Kingsoft
    过滤器），.doc 失败时回退 Windows Word COM（需 pywin32，可选）。"""
    converted = _convert_doc_via_soffice(content, file_name)
    if converted:
        return converted
    if os.path.splitext(file_name)[1].lower() == ".doc":
        try:
            return _convert_doc_via_word_com(content, file_name)
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Word COM convert failed",
                extra={"business_module": "quality", "error": str(exc)},
            )
    raise AppException(
        message="当前环境不支持该格式转换，请转换为 .docx 后上传"
    )


def convert_word_attachment(
    file_name: str, content: bytes
) -> tuple[str, list[ExtractedImage]]:
    """word（.doc/.docx/.wps）→ (标准 MD 文本, 内嵌图片列表)。

    md 中图片以 `img_000.png` 等占位名引用，由调用方存储并替换为实际 URL。
    """
    if os.path.splitext(file_name)[1].lower() in LEGACY_WORD_EXTS:
        content = convert_legacy_to_docx(content, file_name)
    return convert_docx_content_to_md(content, file_name)
