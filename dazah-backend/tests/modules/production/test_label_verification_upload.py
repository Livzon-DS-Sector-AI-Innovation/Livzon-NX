"""标签复核视频上传必须清洗文件名、限制大小并限制读取目录。"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import UploadFile

from app.core.exceptions import AppException
from app.modules.production import label_verification_api as api


def _video_upload(
    filename: str,
    content: bytes = b"\x00\x00\x00\x18ftypmp42",
) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers={"content-type": "video/mp4"},  # type: ignore[arg-type]
    )


def test_resolve_upload_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(HTTPException) as exc_info:
        api.resolve_upload_path(str(tmp_path), "../../etc/passwd")

    assert getattr(exc_info.value, "status_code", None) == 400


@pytest.mark.parametrize(
    "file_key",
    [
        "C:\\Windows\\win.ini",
        "C:/Windows/win.ini",
        "/etc/passwd",
        "\\\\server\\share\\clip.mp4",
        "\\Windows\\win.ini",
        "C:clip.mp4",
    ],
)
def test_resolve_upload_path_rejects_absolute_path(
    tmp_path: Path, file_key: str
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        api.resolve_upload_path(str(tmp_path), file_key)

    assert getattr(exc_info.value, "status_code", None) == 400


def test_resolve_upload_path_accepts_relative_key(tmp_path: Path) -> None:
    target = tmp_path / "label-verification" / "clip.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"video")

    resolved = api.resolve_upload_path(str(tmp_path), "label-verification/clip.mp4")

    assert resolved == target.resolve()


@pytest.mark.anyio
async def test_analysis_route_rejects_absolute_keys_before_file_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        api, "get_settings", lambda: SimpleNamespace(UPLOAD_DIR=str(tmp_path))
    )
    application = FastAPI()
    application.include_router(api.router, prefix="/api/v1/production")
    application.dependency_overrides[api.get_label_verification_service] = object
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        for key, status in (
            ("C:\\Windows\\win.ini", 400),
            ("/etc/passwd", 400),
            ("\\\\server\\share\\clip.mp4", 400),
            ("label-verification/missing.mp4", 404),
        ):
            response = await client.post(
                "/api/v1/production/label-verifications/analyze-video",
                params={"file_key": key},
            )
            assert response.status_code == status
            assert response.json() == {
                "detail": "文件路径非法" if status == 400 else "视频文件不存在"
            }


@pytest.mark.anyio
async def test_upload_rejects_traversal_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        api,
        "get_settings",
        lambda: SimpleNamespace(UPLOAD_DIR=str(tmp_path), VIDEO_UPLOAD_MAX_MB=1),
    )

    with pytest.raises(AppException) as exc_info:
        await api.upload_label_verification_video(
            file=_video_upload("../../app/main.py"), service=object()  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    assert list(tmp_path.rglob("*.py")) == []


@pytest.mark.anyio
async def test_upload_stores_generated_name_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        api,
        "get_settings",
        lambda: SimpleNamespace(UPLOAD_DIR=str(tmp_path), VIDEO_UPLOAD_MAX_MB=1),
    )

    response = await api.upload_label_verification_video(
        file=_video_upload("现场复核.mp4", b"video-bytes"),
        service=object(),  # type: ignore[arg-type]
    )

    body: dict[str, Any] = json.loads(bytes(response.body))
    file_key = body["data"]["file_key"]
    stored = Path(tmp_path) / file_key
    assert stored.is_file()
    assert stored.read_bytes() == b"video-bytes"
    assert "现场复核" not in stored.name
    assert body["data"]["file_name"] == "现场复核.mp4"
    assert body["data"]["file_size"] == len(b"video-bytes")
