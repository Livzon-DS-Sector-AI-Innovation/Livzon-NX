from contextlib import asynccontextmanager
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import AppException
from app.main import app
from app.modules.registration.api import (
    certificates,
)
from app.modules.registration.api import (
    declaration_progress as declaration_api,
)
from app.modules.registration.api import (
    project_ledger as project_api,
)
from app.modules.registration.service import (
    certificate,
    declaration_progress,
    project_ledger,
)

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(
    params=[
        (
            "certificate-management",
            certificates,
            certificate,
            "CertificateWorkbookService",
        ),
        ("project-ledger", project_api, project_ledger, "ProjectLedgerWorkbookService"),
        (
            "declaration-progress",
            declaration_api,
            declaration_progress,
            "DeclarationProgressWorkbookService",
        ),
    ],
    ids=["certificate", "project-ledger", "declaration-progress"],
)
async def workbook_http(request, monkeypatch, tmp_path):
    slug, api, service_module, class_name = request.param
    test_app = FastAPI(exception_handlers=app.exception_handlers)
    test_app.include_router(api.router, prefix=f"/{slug}")
    state = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        authorized=True,
        source=tmp_path / "source.xlsx",
    )
    test_app.dependency_overrides[get_db] = lambda: None
    test_app.dependency_overrides[get_current_user] = lambda: state.user

    @asynccontextmanager
    async def authorize(*_):
        if not state.authorized:
            raise AppException(403, "内部权限策略")
        yield

    monkeypatch.setattr(service_module, "authorized_workbook", authorize)
    monkeypatch.setattr(
        service_module, "get_settings", lambda: SimpleNamespace(MAX_UPLOAD_SIZE_MB=1)
    )
    if service_module is project_ledger:
        monkeypatch.setattr(project_ledger, "_get_workbook_path", lambda: state.source)
    if service_module is declaration_progress:
        monkeypatch.setattr(
            declaration_progress, "_parse_workbook_definitions", lambda: ([], None)
        )
    seed = AsyncMock()
    monkeypatch.setattr(getattr(service_module, class_name), "ensure_seeded", seed)

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client, f"/{slug}/workbook/import", state, seed


async def test_workbook_upload_uses_http_status_for_generic_errors(workbook_http):
    client, url, state, seed = workbook_http
    files = {"file": ("test.xlsx", b"x" * (1024 * 1024 + 1), XLSX_MEDIA_TYPE)}
    response = await client.post(url, files=files)
    assert response.status_code == 413
    assert "detail" not in response.json()

    state.authorized = False
    response = await client.post(url, files=files)
    assert response.status_code == 403
    assert "detail" not in response.json()

    state.user = None
    response = await client.post(url, files=files)
    assert response.status_code == 401
    assert "detail" not in response.json()
    seed.assert_not_awaited()


async def test_workbook_invalid_excel_package_returns_stable_code_before_writes(
    workbook_http,
):
    client, url, _, seed = workbook_http
    with BytesIO() as file:
        with ZipFile(file, "w") as archive:
            archive.writestr("xl/workbook.xml", "<workbook />")
        content = file.getvalue()
    response = await client.post(
        url, files={"file": ("bad.xlsx", content, XLSX_MEDIA_TYPE)}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "error_code": "REGISTRATION_WORKBOOK_UNREADABLE"
    }
    seed.assert_not_awaited()


async def test_workbook_template_mismatch_needs_a_different_correction(
    workbook_http, monkeypatch
):
    client, url, state, seed = workbook_http
    if "project-ledger" in url:
        state.source.touch()
        monkeypatch.setattr(
            project_ledger,
            "_parse_workbook_definitions",
            lambda: ([SimpleNamespace(worksheet_title="台账子表")], None),
        )
    with BytesIO() as file:
        workbook = Workbook()
        workbook.save(file)
        workbook.close()
        content = file.getvalue()
    response = await client.post(
        url, files={"file": ("plain.xlsx", content, XLSX_MEDIA_TYPE)}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "error_code": "REGISTRATION_WORKBOOK_TEMPLATE_MISMATCH"
    }
    seed.assert_not_awaited()
