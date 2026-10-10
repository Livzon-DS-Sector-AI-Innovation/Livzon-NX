"""安全知识库 EHS 法规同步与附件端点的路由测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.safety.api import knowledge as api


@pytest.fixture
def sub_app() -> FastAPI:
    application = FastAPI()
    application.include_router(api.knowledge_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_db] = lambda: None
    application.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    return application


@pytest.fixture
def client(sub_app: FastAPI):
    return AsyncClient(transport=ASGITransport(app=sub_app), base_url="http://test")


async def test_sync_endpoint_returns_counts(client, monkeypatch):
    fake = AsyncMock(
        return_value={"created": 2, "updated": 1, "removed": 0, "failed": 0, "total": 3}
    )
    monkeypatch.setattr(api.knowledge_feishu, "sync_knowledge_from_feishu", fake)

    resp = await client.post("/api/v1/safety/knowledge-articles/feishu/sync")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["created"] == 2 and data["total"] == 3
    fake.assert_awaited_once()


async def test_attachment_content_streams_with_disposition(client, monkeypatch):
    fake = AsyncMock(return_value=(b"%PDF-fake", "application/pdf", "法规 001.pdf"))
    monkeypatch.setattr(api.knowledge_feishu, "get_knowledge_attachment", fake)

    resp = await client.get(
        "/api/v1/safety/knowledge-articles/feishu/records/rec1/attachments/tok1/content"
    )
    assert resp.status_code == 200
    assert resp.content == b"%PDF-fake"
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.headers["content-disposition"].startswith("attachment")


async def test_attachment_preview_inline_for_pdf(client, monkeypatch):
    fake = AsyncMock(return_value=(b"%PDF-fake", "application/pdf", "a.pdf"))
    monkeypatch.setattr(api.knowledge_feishu, "get_knowledge_attachment", fake)

    resp = await client.get(
        "/api/v1/safety/knowledge-articles/feishu/records/rec1/attachments/tok1/preview"
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("inline")


async def test_attachment_preview_falls_back_to_download_for_unknown_type(
    client, monkeypatch
):
    fake = AsyncMock(
        return_value=(b"PK-zip", "application/vnd.ms-excel", "台账.xls")
    )
    monkeypatch.setattr(api.knowledge_feishu, "get_knowledge_attachment", fake)

    resp = await client.get(
        "/api/v1/safety/knowledge-articles/feishu/records/rec1/attachments/tok1/preview"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/octet-stream"
    assert resp.headers["content-disposition"].startswith("attachment")
