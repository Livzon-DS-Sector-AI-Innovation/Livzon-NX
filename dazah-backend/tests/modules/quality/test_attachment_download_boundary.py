"""Record-scoped downloads remain usable and reject unrelated storage keys."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.quality.api import quality_historical_deviation as api
from app.modules.quality.service import historical_deviation as service
from app.platform.identity.deps import get_current_user


@pytest.mark.parametrize("case", ["authorized", "other_record_key", "deleted_record"])
async def test_record_membership_is_checked_before_reading_storage(monkeypatch, case):
    record_id = uuid4()
    key = "historical-deviations/attachment.pdf"
    record = SimpleNamespace(
        is_deleted=case == "deleted_record",
        attachments=[
            {
                "storage_key": key,
                "content_type": "application/pdf",
                "asset_keys": [],
            }
        ],
    )
    db = SimpleNamespace(get=AsyncMock(return_value=record))
    read = Mock(return_value=(b"authorized-content", "application/pdf"))
    monkeypatch.setattr(service, "read_file", read)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    requested_key = "another-record/secret.pdf" if case == "other_record_key" else key
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/historical-deviations/{record_id}/attachments/{requested_key}/content"
        )
    if case == "authorized":
        assert response.status_code == 200
        assert response.content == b"authorized-content"
        read.assert_called_once()
    else:
        assert response.status_code == 404
        read.assert_not_called()
