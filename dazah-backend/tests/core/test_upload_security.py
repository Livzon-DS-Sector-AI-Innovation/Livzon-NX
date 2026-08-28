from io import BytesIO

import pytest
from fastapi import UploadFile

from app.core.exceptions import AppException
from app.core.upload_security import read_upload_secure, safe_upload_filename


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
