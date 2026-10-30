"""MSDS 多附件 API 测试：上传（含 AI 识别建议）/列表/下载/预览/删除。"""

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.safety.api.hazchem import hazchem_router
from app.modules.safety.models import (
    ChemicalMsdsAttachment,
    HazardousChemical,
)
from app.modules.safety.schemas.hazchem import MsdsExtractionSuggestion
from app.platform.identity.models import User

_CHEM_PREFIX = "测试化学品-"

_PDF_BYTES = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF"
)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"治理测试{uuid4().hex[:8]}", role="user", status="active"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def client(
    db_session: AsyncSession, test_user: User, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    # 宿主机测试无法解析容器内 MinIO 主机名：强制走本地存储回退
    monkeypatch.setattr(
        "app.modules.safety.service.hazchem.storage.is_enabled", lambda: False
    )
    application = FastAPI()
    application.include_router(hazchem_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_current_user] = lambda: test_user

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    application.dependency_overrides.pop(get_db, None)


async def _create_chemical(client: AsyncClient) -> str:
    name = f"{_CHEM_PREFIX}丙酮-{uuid4().hex[:6]}"
    created = await client.post(
        "/api/v1/safety/hazardous-chemicals",
        json={"name": name, "category": "flammable_liquid"},
    )
    assert created.status_code == 200, created.text
    return created.json()["data"]["id"]


async def _cleanup(db: AsyncSession) -> None:
    await db.execute(
        delete(ChemicalMsdsAttachment).where(
            ChemicalMsdsAttachment.chemical_id.in_(
                __import__("sqlalchemy")
                .select(HazardousChemical.id)
                .where(HazardousChemical.name.like(f"{_CHEM_PREFIX}%"))
            )
        )
    )
    await db.execute(
        delete(HazardousChemical).where(
            HazardousChemical.name.like(f"{_CHEM_PREFIX}%")
        )
    )
    await db.commit()


async def test_upload_list_download_preview_delete(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup(db_session)
    monkeypatch.chdir(tmp_path)
    suggestion = MsdsExtractionSuggestion(
        name="丙酮",
        cas_no="67-64-1",
        category="flammable_liquid",
        category_label="易燃液体",
        hazard_statements="高度易燃液体和蒸气",
    )
    extract_mock = AsyncMock(return_value=(suggestion, None))
    monkeypatch.setattr(
        "app.modules.safety.api.hazchem.extract_msds_suggestion", extract_mock
    )

    chem_id = await _create_chemical(client)
    upload = await client.post(
        f"/api/v1/safety/hazardous-chemicals/{chem_id}/msds-files",
        files={"file": ("丙酮MSDS.pdf", _PDF_BYTES, "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    payload = upload.json()["data"]
    assert payload["ai_suggestion"]["cas_no"] == "67-64-1"
    file_id = payload["file"]["id"]
    extract_mock.assert_awaited_once()

    listed = await client.get(
        f"/api/v1/safety/hazardous-chemicals/{chem_id}/msds-files"
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["file_name"] == "丙酮MSDS.pdf"

    content = await client.get(
        f"/api/v1/safety/hazardous-chemicals/{chem_id}/msds-files/{file_id}/content"
    )
    assert content.status_code == 200
    assert content.content.startswith(b"%PDF")
    assert "attachment" in content.headers["content-disposition"]

    preview = await client.get(
        f"/api/v1/safety/hazardous-chemicals/{chem_id}/msds-files/{file_id}/preview"
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "application/pdf"
    assert "inline" in preview.headers["content-disposition"]

    deleted = await client.delete(
        f"/api/v1/safety/hazardous-chemicals/{chem_id}/msds-files/{file_id}"
    )
    assert deleted.status_code == 200
    listed_after = await client.get(
        f"/api/v1/safety/hazardous-chemicals/{chem_id}/msds-files"
    )
    assert listed_after.json()["data"]["items"] == []


async def test_upload_rejects_unsupported_extension(
    client: AsyncClient, db_session: AsyncSession, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup(db_session)
    monkeypatch.chdir(tmp_path)
    chem_id = await _create_chemical(client)
    upload = await client.post(
        f"/api/v1/safety/hazardous-chemicals/{chem_id}/msds-files",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert upload.status_code in (400, 413, 415, 422)


async def test_upload_succeeds_when_ai_extraction_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup(db_session)
    monkeypatch.chdir(tmp_path)
    extract_mock = AsyncMock(return_value=(None, "平台未配置 AI 模型，无法自动识别"))
    monkeypatch.setattr(
        "app.modules.safety.api.hazchem.extract_msds_suggestion", extract_mock
    )

    chem_id = await _create_chemical(client)
    upload = await client.post(
        f"/api/v1/safety/hazardous-chemicals/{chem_id}/msds-files",
        files={"file": ("丙酮MSDS.pdf", _PDF_BYTES, "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    data = upload.json()["data"]
    assert data["ai_suggestion"] is None
    assert data["ai_error"] == "平台未配置 AI 模型，无法自动识别"

    reextract = await client.post(
        f"/api/v1/safety/hazardous-chemicals/{chem_id}"
        f"/msds-files/{data['file']['id']}/extract"
    )
    assert reextract.status_code == 200
    assert reextract.json()["data"]["ai_error"] is not None
