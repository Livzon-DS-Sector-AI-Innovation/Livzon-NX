from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.deps import get_current_user
from app.main import app
from app.modules.quality.api import (
    quality_deviation_workbench,
    quality_historical_deviation,
)
from app.modules.quality.service import historical_deviation


async def test_uploaded_file_format_and_historical_batch_limit(monkeypatch) -> None:
    base = "/api/v1/quality"
    test_app = FastAPI(exception_handlers=app.exception_handlers)
    for module in (quality_historical_deviation, quality_deviation_workbench):
        test_app.include_router(module.router, prefix=base)
        monkeypatch.setattr(module, "_assert_quality_edit_scope", AsyncMock())
    test_app.dependency_overrides[get_db] = lambda: None
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="admin"
    )
    monkeypatch.setattr(historical_deviation, "MAX_BATCH_FILES", 1)
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        for path in (
            f"{base}/historical-deviations/{uuid4()}/attachments",
            f"{base}/deviation-workbench/attachments",
        ):
            wrong_type = await client.post(
                path, files={"file": ("wrong.zip", b"wrong")}
            )
            assert wrong_type.status_code == wrong_type.json()["code"] == 415
            assert "detail" not in wrong_type.json()
        limit = await client.post(
            f"{base}/historical-deviations/batch-import",
            files=[("files", ("a.pdf", b"fixture")), ("files", ("b.pdf", b"fixture"))],
        )
        assert limit.status_code == limit.json()["code"] == 400
        assert limit.json()["detail"] == {
            "error_code": "QUALITY_HISTORICAL_DEVIATION_BATCH_LIMIT",
        }
