from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi import UploadFile

from app.core.exceptions import AppException
from app.core.upload_security import (
    read_upload_secure,
    safe_upload_filename,
    sniff_upload_mime,
)


def test_safe_upload_filename_rejects_path_traversal() -> None:
    with pytest.raises(AppException):
        safe_upload_filename("..\\private\\secret.pdf")
    with pytest.raises(AppException):
        safe_upload_filename("../private/secret.pdf")


def test_safe_upload_filename_rejects_control_characters() -> None:
    with pytest.raises(AppException):
        safe_upload_filename("report\x00.pdf")


@pytest.mark.anyio
async def test_read_upload_secure_checks_extension_and_size() -> None:
    upload = UploadFile(
        filename="report.pdf",
        file=BytesIO(b"%PDF-1.7\nvalid-test-pdf"),
        headers={"content-type": "application/pdf"},  # type: ignore[arg-type]
    )
    filename, content = await read_upload_secure(
        upload,
        max_bytes=32,
        allowed_extensions={".pdf"},
        allowed_mimes={"application/pdf"},
    )
    assert filename == "report.pdf"
    assert content == b"%PDF-1.7\nvalid-test-pdf"

    oversized = UploadFile(filename="report.pdf", file=BytesIO(b"12345"))
    with pytest.raises(AppException):
        await read_upload_secure(
            oversized,
            max_bytes=4,
            allowed_extensions={".pdf"},
        )


@pytest.mark.anyio
async def test_read_upload_secure_rejects_mime_spoofing() -> None:
    upload = UploadFile(
        filename="report.pdf",
        file=BytesIO(b"this is not a PDF"),
        headers={"content-type": "application/pdf"},  # type: ignore[arg-type]
    )
    with pytest.raises(AppException):
        await read_upload_secure(
            upload,
            max_bytes=32,
            allowed_extensions={".pdf"},
            allowed_mimes={"application/pdf"},
        )


@pytest.mark.anyio
async def test_read_upload_secure_rejects_valid_format_with_wrong_extension() -> None:
    upload = UploadFile(
        filename="report.png",
        file=BytesIO(b"%PDF-1.7\nvalid-test-pdf"),
        headers={"content-type": "image/png"},  # type: ignore[arg-type]
    )
    with pytest.raises(AppException):
        await read_upload_secure(
            upload,
            max_bytes=32,
            allowed_extensions={".png", ".pdf"},
            allowed_mimes={"application/pdf", "image/png"},
        )


@pytest.mark.anyio
async def test_read_upload_secure_rejects_empty_upload() -> None:
    upload = UploadFile(filename="empty.pdf", file=BytesIO(b""))
    with pytest.raises(AppException):
        await read_upload_secure(upload, max_bytes=32, allowed_extensions={".pdf"})


def test_sniff_upload_mime_ole_compound_doc_variants() -> None:
    from app.core.upload_security import sniff_upload_mime

    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
    # .doc/.wps 同为 OLE 复合文档 → Word
    assert sniff_upload_mime("报告.doc", ole) == "application/msword"
    assert sniff_upload_mime("报告.wps", ole) == "application/msword"
    # 其它后缀的 OLE 归为 Excel
    assert sniff_upload_mime("表.xls", ole) == "application/vnd.ms-excel"


def test_sniff_upload_mime_office_zip_and_images() -> None:
    def _zip(names: list[str]) -> bytes:
        buf = BytesIO()
        with ZipFile(buf, "w") as z:
            for n in names:
                z.writestr(n, "x")
        return buf.getvalue()

    assert sniff_upload_mime(
        "a.docx", _zip(["word/document.xml"])
    ) == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert sniff_upload_mime(
        "a.xlsx", _zip(["xl/workbook.xml"])
    ) == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert sniff_upload_mime("a.gif", b"GIF89a....") == "image/gif"
    assert (
        sniff_upload_mime("a.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ")
        == "image/webp"
    )
    assert sniff_upload_mime("a.bmp", b"BM....") == "image/bmp"
    # 非 zip、非法 UTF-8 → 二进制兜底；合法 UTF-8 → text/plain
    assert sniff_upload_mime("a.bin", b"\xff\xfe\x00\x01") == "application/octet-stream"
    assert sniff_upload_mime("a.txt", "普通文本".encode()) == "text/plain"
