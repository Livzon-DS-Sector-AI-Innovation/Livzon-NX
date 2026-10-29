"""通用附件在线预览内容解析（平台共享，无业务归属）。

把附件字节转换为浏览器可直接呈现的内容：
- 图片（jpg/png/gif/webp/bmp）原样返回（inline）；
- PDF 原样返回；
- doc/docx/wps 等 office 文档用 LibreOffice headless 转 PDF 后返回；
- 其余扩展名不支持在线预览，由调用方返回 4xx 提示下载。

质量模块的飞书附件预览（feishu_attachment_preview）有同源实现；本模块
面向后续新接入的业务附件（如安全模块 MSDS），业务侧语义（缓存/权限/审计）
仍由所属模块负责。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PREVIEW_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})
PREVIEW_PDF_EXTS = frozenset({".pdf"})
PREVIEW_OFFICE_EXTS = frozenset(
    {".doc", ".docx", ".wps", ".xls", ".xlsx", ".csv", ".ppt", ".pptx"}
)
PREVIEWABLE_EXTS = PREVIEW_IMAGE_EXTS | PREVIEW_PDF_EXTS | PREVIEW_OFFICE_EXTS

# soffice 子进程超时（秒）；转换失败换新 profile 重试一次
_SOFFICE_TIMEOUT = 60
_SOFFICE_RETRIES = 1
_DOC_CONVERTER_BIN = os.environ.get("DOC_CONVERTER_BIN", "")

_IMAGE_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

__all__ = [
    "PREVIEWABLE_EXTS",
    "convert_office_to_pdf",
    "resolve_preview_content",
]


def _find_soffice() -> str | None:
    if _DOC_CONVERTER_BIN and os.path.exists(_DOC_CONVERTER_BIN):
        return _DOC_CONVERTER_BIN
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _flatten_file_name(file_name: str) -> str:
    """附件名压平为纯文件名：来自外部元数据，禁止携带路径分隔符。"""
    flat = os.path.basename(str(file_name).replace("\\", "/")).strip()
    return flat or "attachment.doc"


def convert_office_to_pdf(content: bytes, file_name: str) -> bytes:
    """LibreOffice headless office 文档 → PDF 字节；失败返回空字节。

    独立 profile（容器 HOME 常不可写）、start_new_session 隔离进程组、
    超时杀整组，崩溃换新 profile 重试一次。
    """
    soffice = _find_soffice()
    if not soffice:
        return b""
    flat_name = _flatten_file_name(file_name)
    for _attempt in range(_SOFFICE_RETRIES + 1):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src_path = os.path.join(tmp_dir, flat_name)
            out_dir = os.path.join(tmp_dir, "out")
            os.makedirs(out_dir, exist_ok=True)
            with open(src_path, "wb") as f:
                f.write(content)
            try:
                result = subprocess.run(
                    [
                        soffice,
                        "--headless",
                        f"-env:UserInstallation={Path(tmp_dir).joinpath('lo_profile').as_uri()}",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        out_dir,
                        src_path,
                    ],
                    capture_output=True,
                    timeout=_SOFFICE_TIMEOUT,
                    check=False,
                    start_new_session=True,
                )
            except (subprocess.SubprocessError, OSError):
                continue
            if result.returncode != 0:
                continue
            base = os.path.splitext(flat_name)[0] or "attachment"
            pdf_path = os.path.join(out_dir, f"{base}.pdf")
            if os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    return f.read()
    return b""


def resolve_preview_content(
    content: bytes, file_name: str
) -> tuple[bytes, str, str]:
    """按扩展名把附件字节转换为浏览器可呈现内容。

    返回 (content, content_type, filename)；office 文档转 PDF（文件名同步
    改为 .pdf）。不支持预览的扩展名或不支持预览且转换失败时抛 ValueError，
    由调用方转换为业务 4xx。
    """
    flat_name = _flatten_file_name(file_name)
    ext = os.path.splitext(flat_name)[1].lower()
    if ext in PREVIEW_IMAGE_EXTS:
        mime = _IMAGE_MIME_BY_EXT.get(ext, "application/octet-stream")
        return content, mime, flat_name
    if ext in PREVIEW_PDF_EXTS:
        return content, "application/pdf", flat_name
    if ext in PREVIEW_OFFICE_EXTS:
        pdf_bytes = convert_office_to_pdf(content, flat_name)
        if not pdf_bytes:
            raise ValueError(f"「{flat_name}」转 PDF 失败，暂不支持在线预览")
        pdf_name = f"{os.path.splitext(flat_name)[0] or 'attachment'}.pdf"
        return pdf_bytes, "application/pdf", pdf_name
    raise ValueError(f"「{flat_name}」格式暂不支持在线预览，请下载后查看")
