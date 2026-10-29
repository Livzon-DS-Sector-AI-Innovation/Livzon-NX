"""External attachment metadata must not create same-origin active documents."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.hr import api, recruitment_repository
from app.platform.identity.deps import get_current_user


@pytest.mark.parametrize(
    "filename,disposition",
    [
        ("document.html", "attachment"),
        ("picture.svg", "attachment"),
        ("resume.pdf", "inline"),
        ("photo.png", "inline"),
        ("another-record.pdf", None),
    ],
)
async def test_external_attachment_is_safe_to_open(monkeypatch, filename, disposition):
    download = AsyncMock(return_value=b"external attachment content")
    monkeypatch.setattr(
        recruitment_repository,
        "RecruitmentBitableRepo",
        lambda: SimpleNamespace(
            _get_client=AsyncMock(
                return_value=SimpleNamespace(
                    client=SimpleNamespace(download_file=download)
                )
            )
        ),
    )
    service = SimpleNamespace(
        get_onboarding=AsyncMock(
            return_value={
                "other_attachment": [{"file_token": "owned-token", "name": filename}]
            }
        )
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/hr")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[api.get_recruitment_onboarding_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        requested_token = "foreign-token" if disposition is None else "owned-token"
        response = await client.get(
            f"/hr/onboarding/record/attachments/{requested_token}/content"
        )
    if disposition is None:
        assert response.status_code == 403
        download.assert_not_awaited()
        return
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith(disposition + ";")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.content == b"external attachment content"
    download.assert_awaited_once_with("owned-token")
