"""上传安全辅助：流式落盘、大小限制与失败清理。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from starlette.datastructures import UploadFile

from app.core.exceptions import AppException
from app.core.upload_security import (
    read_upload_secure,
    stream_upload_to_path,
)


def _upload(content: bytes, filename: str = "report.pdf") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


@pytest.mark.anyio
async def test_stream_upload_writes_file_and_returns_size(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "stored.pdf"

    filename, size = await stream_upload_to_path(
        _upload(b"%PDF-1.4 content"),
        destination,
        max_bytes=1024,
    )

    assert filename == "report.pdf"
    assert size == len(b"%PDF-1.4 content")
    assert destination.read_bytes() == b"%PDF-1.4 content"


@pytest.mark.anyio
async def test_stream_upload_rejects_oversized_file_and_removes_partial(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "stored.pdf"

    with pytest.raises(AppException) as exc_info:
        await stream_upload_to_path(
            _upload(b"0123456789"),
            destination,
            max_bytes=4,
        )

    assert exc_info.value.status_code == 413
    assert not destination.exists()


@pytest.mark.anyio
async def test_stream_upload_rejects_empty_file(tmp_path: Path) -> None:
    destination = tmp_path / "empty.pdf"

    with pytest.raises(AppException) as exc_info:
        await stream_upload_to_path(_upload(b""), destination, max_bytes=1024)

    assert exc_info.value.status_code == 400
    assert not destination.exists()


@pytest.mark.anyio
async def test_stream_upload_rejects_traversal_filename(tmp_path: Path) -> None:
    destination = tmp_path / "stored.pdf"

    with pytest.raises(AppException) as exc_info:
        await stream_upload_to_path(
            _upload(b"data", filename="../../evil.pdf"),
            destination,
            max_bytes=1024,
        )

    assert exc_info.value.status_code == 400
    assert not destination.exists()


@pytest.mark.anyio
async def test_read_upload_secure_still_enforces_size() -> None:
    with pytest.raises(AppException) as exc_info:
        await read_upload_secure(_upload(b"0123456789"), max_bytes=4)

    assert exc_info.value.status_code == 413


@pytest.mark.anyio
async def test_stream_upload_collision_preserves_existing_file(tmp_path: Path) -> None:
    destination = tmp_path / "existing.pdf"
    destination.write_bytes(b"existing authorized attachment")
    with pytest.raises(FileExistsError):
        await stream_upload_to_path(
            _upload(b"replacement"), destination, max_bytes=1024
        )
    assert destination.read_bytes() == b"existing authorized attachment"
