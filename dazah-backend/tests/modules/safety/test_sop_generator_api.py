"""操规标准化生成与导出 API 测试（真实服务 + 独立测试库）。

生成走 llm_client（一律 mock，不连真实模型）；导出返回可打印 HTML。
覆盖：生成成功、模型未配置 503、输出为空 502、非 docx 400、
导出 HTML、无内容 400。
"""

from __future__ import annotations

import io
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.llm import LLMConfigError, llm_client
from app.modules.safety.api.regulations import regulations_router
from app.modules.safety.models import OperationRegulation
from app.platform.identity.models import User


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"SOP测试{uuid4().hex[:8]}", role="user", status="active"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def sub_app(test_user: User) -> FastAPI:
    application = FastAPI()
    application.include_router(regulations_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_current_user] = lambda: test_user
    return application


@pytest.fixture
async def client(
    sub_app: FastAPI, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    sub_app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=sub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    sub_app.dependency_overrides.pop(get_db, None)


def _docx_bytes(text: str) -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def _cleanup(db: AsyncSession, regulation: OperationRegulation) -> None:
    await db.delete(regulation)
    await db.commit()
    for path in (regulation.document_path, regulation.source_document_path):
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


async def test_generate_creates_standardized_sop(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_chat_json(*args: object, **kwargs: object) -> dict[str, object]:
        assert "expected_keys" in kwargs
        return {
            "meta": {
                "product_name": "MV",
                "post_name": "工艺值班",
                "department": "101二车间",
                "doc_number": "",
                "effective_date": "",
                "company_name": "",
            },
            "content": (
                "# 一、目的\n\n规范工艺值班岗位操作。\n\n"
                "| 编制 | 审核 |\n| --- | --- |\n|  |  |"
            ),
        }

    monkeypatch.setattr(llm_client, "chat_json", _fake_chat_json)

    resp = await client.post(
        "/api/v1/safety/regulations/generate",
        files=[
            (
                "file",
                (
                    "101二车间工艺值班岗位标准操作规程.docx",
                    _docx_bytes("旧版值班操作要求"),
                    "application/octet-stream",
                ),
            )
        ],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["status"] == "generated"
    assert data["meta"]["post_name"] == "工艺值班"
    assert "一、目的" in data["content"]

    created = await db_session.get(OperationRegulation, data["regulation_id"])
    assert created is not None
    assert created.regulation_no is None  # 编号留空由文控填写
    assert created.content and "一、目的" in created.content
    assert created.status == "generated"

    await _cleanup(db_session, created)


async def test_generate_maps_llm_errors(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_llm(*args: object, **kwargs: object) -> dict[str, object]:
        raise LLMConfigError("模型未配置")

    monkeypatch.setattr(llm_client, "chat_json", _no_llm)
    resp = await client.post(
        "/api/v1/safety/regulations/generate",
        files=[
            (
                "file",
                ("操规.docx", _docx_bytes("内容"), "application/octet-stream"),
            )
        ],
    )
    assert resp.status_code == 503


async def test_generate_rejects_non_docx_and_empty_output(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    resp = await client.post(
        "/api/v1/safety/regulations/generate",
        files=[("file", ("操规.txt", b"text", "text/plain"))],
    )
    # 旧式 ApiResponse 包装：HTTP 200 + 业务 code 400
    assert resp.status_code == 200
    assert resp.json()["code"] == 400

    async def _empty_output(*args: object, **kwargs: object) -> dict[str, object]:
        return {"meta": {}, "content": ""}

    monkeypatch.setattr(llm_client, "chat_json", _empty_output)
    resp = await client.post(
        "/api/v1/safety/regulations/generate",
        files=[
            (
                "file",
                ("操规.docx", _docx_bytes("内容"), "application/octet-stream"),
            )
        ],
    )
    assert resp.status_code == 502


async def test_export_returns_printable_html(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    regulation = OperationRegulation(
        regulation_no=None,
        regulation_name="导出测试车间化测岗位安全操作规程",
        workshop="测试车间",
        content="# 一、目的\n\n规范化测岗位操作。",
        status="reviewed",
    )
    db_session.add(regulation)
    await db_session.flush()

    resp = await client.post(f"/api/v1/safety/regulations/{regulation.id}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "导出测试车间化测岗位安全操作规程" in body
    assert "规范化测岗位操作" in body
    assert "window.print" in body

    await _cleanup(db_session, regulation)

    resp = await client.post(f"/api/v1/safety/regulations/{uuid4()}/export")
    assert resp.status_code == 200  # ApiResponse 包装的业务 400
    assert resp.json()["code"] == 400
