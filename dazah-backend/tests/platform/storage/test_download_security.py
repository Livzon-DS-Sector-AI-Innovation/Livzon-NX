"""Object keys and module grants are insufficient to authorize attachments."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.platform.identity.deps import require_current_user
from app.platform.storage import api


@pytest.mark.parametrize("role", ["user", "admin"])
async def test_generic_key_download_cannot_bypass_record_authorization(
    monkeypatch, role
):
    read = Mock(return_value=(b"private record", "text/plain"))
    monkeypatch.setattr(api, "get_object", read, raising=False)
    monkeypatch.setattr(api, "is_enabled", lambda: True, raising=False)
    monkeypatch.setattr(
        api,
        "get_settings",
        lambda: SimpleNamespace(effective_module_access_mode="all"),
        raising=False,
    )
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(role=role)
    app.dependency_overrides[get_db] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/uploads/quality/known-object.pdf")
    assert response.status_code == 403
    assert "private record" not in response.text
    read.assert_not_called()
