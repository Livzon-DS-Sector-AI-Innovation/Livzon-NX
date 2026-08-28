"""Shared validation for user-supplied uploads."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import UploadFile

from app.core.exceptions import AppException

UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_UPLOAD_FILES = 20
GENERIC_MIME_TYPES = {"", "application/octet-stream", "binary/octet-stream"}

_EXTENSION_MIMES: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".gif": {"image/gif"},
    ".webp": {"image/webp"},
    ".bmp": {"image/bmp"},
    ".doc": {"application/msword"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    ".xls": {"application/vnd.ms-excel"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    },
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".csv": {"text/csv", "text/plain"},
}


def safe_upload_filename(filename: str | None, *, fallback: str = "upload.bin") -> str:
    raw_value = filename or fallback
    if "/" in raw_value or "\\" in raw_value:
        raise AppException(message="上传文件名不得包含路径分隔符", status_code=400)
    value = raw_value
    name = Path(value).name
    if not name or name in {".", ".."} or "\x00" in name:
        raise AppException(message="上传文件名非法", status_code=400)
    if any(ord(char) < 32 for char in name):
        raise AppException(message="上传文件名包含非法控制字符", status_code=400)
    if len(name) > 255:
        raise AppException(message="上传文件名过长", status_code=400)
    return name


def validate_upload_metadata(
    file: UploadFile,
    *,
    allowed_extensions: set[str] | None = None,
    allowed_mimes: set[str] | None = None,
) -> str:
    filename = safe_upload_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if allowed_extensions is not None and extension not in allowed_extensions:
        raise AppException(
            message=f"不支持的文件类型：{extension or '未知'}", status_code=400
        )
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if (
        allowed_mimes
        and content_type not in GENERIC_MIME_TYPES
        and content_type not in allowed_mimes
    ):
        raise AppException(message="上传文件 MIME 类型不被允许", status_code=400)
    return filename


def sniff_upload_mime(filename: str, content: bytes) -> str:
    """Detect common upload formats from bytes, never from the client header."""
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"BM"):
        return "image/bmp"
    if content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        suffix = Path(filename).suffix.lower()
        return "application/msword" if suffix == ".doc" else "application/vnd.ms-excel"
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
    except (BadZipFile, OSError):
        names = set()
    if names:
        if "word/document.xml" in names:
            return (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            )
        if "xl/workbook.xml" in names:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if "ppt/presentation.xml" in names:
            return (
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            )
        return "application/zip"
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    return "text/plain"


def validate_upload_content(
    filename: str,
    content: bytes,
    *,
    allowed_extensions: set[str] | None = None,
    allowed_mimes: set[str] | None = None,
) -> str:
    detected_mime = sniff_upload_mime(filename, content)
    declared_extension = Path(filename).suffix.lower()
    extension_mimes = _EXTENSION_MIMES.get(declared_extension)
    if (
        allowed_extensions is not None
        and extension_mimes
        and detected_mime not in extension_mimes
    ):
        raise AppException(
            message="文件实际格式与扩展名或 MIME 不一致", status_code=400
        )
    if allowed_mimes and detected_mime not in allowed_mimes:
        raise AppException(
            message="文件实际格式与扩展名或 MIME 不一致", status_code=400
        )
    return detected_mime


async def read_upload_secure(
    file: UploadFile,
    *,
    max_bytes: int,
    allowed_extensions: set[str] | None = None,
    allowed_mimes: set[str] | None = None,
    what: str = "文件",
) -> tuple[str, bytes]:
    """Validate metadata, read in chunks, and return a sanitized name and bytes."""

    filename = validate_upload_metadata(
        file,
        allowed_extensions=allowed_extensions,
        allowed_mimes=allowed_mimes,
    )
    declared_size = getattr(file, "size", None)
    if declared_size is not None and declared_size > max_bytes:
        raise AppException(
            message=f"{what}大小超过 {max_bytes // (1024 * 1024)}MB 限制",
            status_code=413,
        )
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise AppException(
                message=f"{what}大小超过 {max_bytes // (1024 * 1024)}MB 限制",
                status_code=413,
            )
        chunks.append(chunk)
    if not chunks:
        raise AppException(message=f"{what}不能为空", status_code=400)
    content = b"".join(chunks)
    validate_upload_content(
        filename,
        content,
        allowed_extensions=allowed_extensions,
        allowed_mimes=allowed_mimes,
    )
    return filename, content
