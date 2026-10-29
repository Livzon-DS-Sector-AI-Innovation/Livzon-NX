"""Template uploads validate all inputs before persisting any file."""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from docx import Document
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.exceptions import AppException
from app.modules.dossier_writer import api
from app.modules.dossier_writer import service as service_module
from app.modules.dossier_writer.service import DossierService


def docx_bytes():
    output = BytesIO()
    Document().save(output)
    return output.getvalue()


@pytest.fixture
def upload_context(tmp_path, monkeypatch):
    source = tmp_path / "templates"
    source.mkdir()
    dossier = SimpleNamespace(source_templates_path=str(source))
    repo = SimpleNamespace(
        get_product_dossier=AsyncMock(return_value=dossier),
        get_template_by_filename=AsyncMock(return_value=None),
        create_template=AsyncMock(side_effect=lambda value: value),
        update_product_dossier=AsyncMock(),
    )
    db = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock(), rollback=AsyncMock())
    settings = SimpleNamespace(STORAGE_ROOT=str(tmp_path), MAX_UPLOAD_SIZE_MB=1)
    monkeypatch.setattr(service_module, "get_settings", lambda: settings)
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(service_module, "DossierRepository", lambda _: repo)
    monkeypatch.setattr(
        DossierService, "match_assets_to_chapters", AsyncMock(return_value={})
    )
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_db] = lambda: db
    return SimpleNamespace(source=source, repo=repo, db=db, app=app)


@pytest.mark.parametrize(
    "filename",
    ["../escape.docx", "..\\escape.docx", "/tmp/escape.docx", "nested/escape.docx"],
)
async def test_rejects_path_names_before_writing(upload_context, filename):
    ctx = upload_context
    async with AsyncClient(
        transport=ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/products/{uuid4()}/templates",
            files=[("files", (filename, docx_bytes(), "application/octet-stream"))],
        )
    assert response.status_code == 400
    assert list(ctx.source.iterdir()) == []
    ctx.repo.create_template.assert_not_awaited()
    ctx.repo.update_product_dossier.assert_not_awaited()


async def test_rejects_invalid_later_file_without_partial_writes(upload_context):
    ctx = upload_context
    async with AsyncClient(
        transport=ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/products/{uuid4()}/templates",
            files=[
                ("files", ("valid.docx", docx_bytes())),
                ("files", ("invalid.docx", b"not a Word document")),
            ],
        )
    assert response.status_code == 400
    assert list(ctx.source.iterdir()) == []
    ctx.repo.create_template.assert_not_awaited()


async def test_rejects_oversized_file(upload_context):
    ctx = upload_context
    async with AsyncClient(
        transport=ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/products/{uuid4()}/templates",
            files=[("files", ("large.docx", b"x" * (1024 * 1024 + 1)))],
        )
    assert response.status_code == 413
    ctx.repo.create_template.assert_not_awaited()


async def test_valid_file_uses_generated_name_and_preserves_display_name(
    upload_context,
):
    ctx = upload_context
    content = docx_bytes()
    async with AsyncClient(
        transport=ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/products/{uuid4()}/templates",
            files=[("files", ("original.docx", content))],
        )
    assert response.status_code == 200
    assert response.json()["data"]["success_count"] == 1
    template = ctx.repo.create_template.call_args.args[0]
    assert template.original_filename == "original.docx"
    target = Path(template.file_path)
    assert target.parent == ctx.source.resolve()
    assert target.name != "original.docx"
    assert target.suffix == ".docx"
    assert target.read_bytes() == content


async def test_service_rejects_absolute_filename_without_api(upload_context):
    ctx = upload_context
    service = DossierService(ctx.db)
    with pytest.raises(AppException):
        await service.save_template_file(
            uuid4(), str(ctx.source.parent / "escape.docx"), b"x"
        )
    assert not (ctx.source.parent / "escape.docx").exists()


async def test_service_rejects_windows_drive_filename(upload_context):
    ctx = upload_context
    service = DossierService(ctx.db)
    with pytest.raises(AppException):
        await service.save_template_file(uuid4(), "C:\\temp\\escape.docx", b"x")
    ctx.repo.create_template.assert_not_awaited()


async def test_same_name_updates_existing_template(upload_context):
    ctx = upload_context
    service = DossierService(ctx.db)
    existing = await service.save_template_file(uuid4(), "original.docx", docx_bytes())
    old_path = Path(existing.file_path)
    ctx.repo.get_template_by_filename.return_value = existing
    content = docx_bytes()
    result = await service.save_template_file(uuid4(), "original.docx", content)
    assert result is existing
    assert Path(result.file_path) == old_path
    assert old_path.read_bytes() == content
    assert ctx.repo.create_template.await_count == 1


async def test_existing_template_cannot_redirect_write_outside_root(upload_context):
    ctx = upload_context
    outside = ctx.source.parent / "outside.docx"
    outside.write_bytes(b"unchanged")
    ctx.repo.get_template_by_filename.return_value = SimpleNamespace(
        file_path=str(outside)
    )
    with pytest.raises(AppException):
        await DossierService(ctx.db).save_template_file(uuid4(), "original.docx", b"x")
    assert outside.read_bytes() == b"unchanged"
    ctx.db.commit.assert_not_awaited()


async def test_rejects_too_many_files_before_writes(upload_context):
    ctx = upload_context
    async with AsyncClient(
        transport=ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/products/{uuid4()}/templates",
            files=[("files", (f"{index}.docx", b"x")) for index in range(21)],
        )
    assert response.status_code == 400
    ctx.repo.create_template.assert_not_awaited()
