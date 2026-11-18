from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from docx import Document
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.deps import get_current_user
from app.main import app
from app.modules.quality.api import (
    quality_capa,
    quality_change,
    quality_deviation,
    router,
)


@pytest.mark.parametrize(
    ("resource", "module", "scope_check"),
    [
        ("changes", quality_change, "_require_full_change_page_scope"),
        ("capas", quality_capa, "_require_full_capa_page_scope"),
        ("deviations", quality_deviation, None),
    ],
)
@pytest.mark.parametrize("operation", ["preview", "confirm"])
async def test_word_import_http_error_contract(
    resource, module, scope_check, operation, monkeypatch
) -> None:
    test_app = FastAPI(exception_handlers=app.exception_handlers)
    test_app.include_router(router, prefix="/api/v1/quality")
    test_app.dependency_overrides[get_db] = lambda: None
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4()
    )
    if scope_check:
        monkeypatch.setattr(module, scope_check, AsyncMock())

    path = f"/api/v1/quality/{resource}/import/{operation}"
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        malformed = await client.post(path, files={"file": ("bad.docx", b"broken")})
        assert malformed.status_code == 422
        assert malformed.json()["code"] == 422
        assert malformed.json()["detail"] == {
            "error_code": "QUALITY_IMPORT_INVALID_DOCUMENT"
        }
        missing = await client.post(path)
        assert missing.status_code == 422
        assert isinstance(missing.json()["detail"], str)
        unsupported = await client.post(path, files={"file": ("old.doc", b"old")})
        assert unsupported.status_code == 415
        assert unsupported.json()["code"] == 415
        assert "detail" not in unsupported.json()

        document = BytesIO()
        Document().save(document)
        success = await client.post(
            path, files={"file": ("empty.DOCX", document.getvalue())}
        )
        assert success.status_code == 200
        data = success.json()["data"]
        if operation == "preview":
            assert data["valid_rows"] == 0
            assert data["error_rows"][0]["error_message"] == "文档中未找到表格"
        else:
            assert data["success_count"] == 0
            assert data["error_details"] == [{"row": 0, "error": "文档中未找到表格"}]

        monkeypatch.setattr(module, "IMPORT_FILE_MAX_SIZE", 1)
        oversized = await client.post(path, files={"file": ("large.docx", b"big")})
        assert oversized.status_code == 413
        assert oversized.json()["code"] == 413
        assert "detail" not in oversized.json()

    response = app.openapi()["paths"][path]["post"]["responses"]["422"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/QualityImportErrorResponse"
    }
