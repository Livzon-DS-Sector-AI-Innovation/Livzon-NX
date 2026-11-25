"""公告通知 API 测试（裸 sub_app + 测试库 + mock LLM 全链路）。

用裸 FastAPI 挂载 notice 路由（与 OH 检测报告测试同模式）：全应用
MaintenanceMiddleware 的写保护在单测环境无 Redis 可用，绕开中间件后
专注本模块接口行为。重点断言：台账元数据响应永不包含公告内容字段；
内容与原文仅经 operate 绑定的专用端点下发；软删除后内容/原文/详情
一律 404。原文存档统一走本地回退（monkeypatch storage.is_enabled）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.administration.notice_service as notice_module
from app.core.database import get_db
from app.core.llm.exceptions import LLMProviderError
from app.modules.administration.api import router as administration_router
from app.modules.administration.models import AdministrationNotice
from app.modules.administration.notice_service import (
    _notice_local_path,
    build_notice_storage_key,
)
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_LLM_NOTICE_OUTPUT = {
    "notice_no": "2026-第03号",
    "title": "关于开展年度安全培训的通知",
    "publisher": "厂办公室",
    "published_at": "2026-03-05",
    "category": "安全公告",
    "content": "全厂定于下周开展年度安全培训……",
    "remark": "抄送：各车间",
}


def _notice_docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph("公告编号：2026-第03号")
    doc.add_paragraph("关于开展年度安全培训的通知")
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _mock_notice_llm(monkeypatch: pytest.MonkeyPatch, result: dict[str, Any]) -> None:
    fake = SimpleNamespace(
        chat_json=AsyncMock(return_value=result),
        chat_vision_json=AsyncMock(return_value=result),
    )
    monkeypatch.setattr(notice_module, "llm_client", fake)


@pytest.fixture(autouse=True)
def _isolated_notice_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """原文存档强制本地回退并落临时目录，避免污染真实 uploads/MinIO。"""
    monkeypatch.setattr(notice_module.storage, "is_enabled", lambda: False)

    def _fake_root() -> Path:
        root = tmp_path / "administration" / "notices"
        root.mkdir(parents=True, exist_ok=True)
        return root

    monkeypatch.setattr(notice_module, "_notice_local_root", _fake_root)


@pytest.fixture(autouse=True)
async def clean_notices() -> AsyncIterator[None]:
    """导入/删除接口会提交会话：复用 conftest 测试库工厂前后清空台账。"""
    from tests.modules.administration.conftest import _test_session_factory

    async def _clean() -> None:
        async with _test_session_factory() as session:
            await session.execute(delete(AdministrationNotice))
            await session.commit()

    await _clean()
    yield
    await _clean()


@pytest.fixture
async def notice_admin(db_session: AsyncSession) -> AsyncIterator[User]:
    user = User(
        name=f"公告测试员{uuid4().hex[:8]}",
        employee_no=f"EMP-NOTICE-{uuid4().hex[:8]}",
        role="admin",
        status="active",
        auth_source="local",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def notice_client(
    db_session: AsyncSession, notice_admin: User
) -> AsyncIterator[AsyncClient]:
    """裸 sub_app + 依赖覆盖：绕开全局维护中间件，专注模块接口行为。"""

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    application = FastAPI()
    application.include_router(administration_router, prefix="/api/v1/administration")
    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_current_user] = lambda: notice_admin
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed_notice(
    db_session: AsyncSession, *, notice_no: str, title: str, **extra: Any
) -> AdministrationNotice:
    notice = AdministrationNotice(
        notice_no=notice_no,
        title=title,
        publisher=extra.get("publisher", "厂办公室"),
        category=extra.get("category", ""),
        content=extra.get("content", "机密正文内容"),
        remark=extra.get("remark"),
        source_file_name=extra.get("source_file_name", "公告.docx"),
        source_storage_key=extra.get("source_storage_key", ""),
        search_text=" ".join(
            part
            for part in (notice_no, title, extra.get("publisher", "厂办公室"))
            if part
        ),
        created_by=extra.get("created_by"),
    )
    db_session.add(notice)
    await db_session.flush()
    return notice


async def test_parse_notice_returns_metadata_suggestion(
    notice_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_notice_llm(monkeypatch, dict(_LLM_NOTICE_OUTPUT))
    response = await notice_client.post(
        "/api/v1/administration/notices/parse",
        files={"file": ("年度培训公告.docx", _notice_docx(), _DOCX_MIME)},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["file_name"] == "年度培训公告.docx"
    suggestion = data["suggestion"]
    assert suggestion["notice_no"] == "2026-第03号"
    assert suggestion["published_at"] == "2026-03-05"
    # 解析预览契约不含公告内容
    assert "content" not in suggestion


async def test_parse_notice_maps_llm_outage_to_502(
    notice_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = SimpleNamespace(
        chat_json=AsyncMock(side_effect=LLMProviderError("down")),
        chat_vision_json=AsyncMock(),
    )
    monkeypatch.setattr(notice_module, "llm_client", fake)
    response = await notice_client.post(
        "/api/v1/administration/notices/parse",
        files={"file": ("公告.docx", _notice_docx(), _DOCX_MIME)},
    )
    assert response.status_code == 502
    assert "暂不可用" in response.json()["detail"]


async def test_parse_notice_rejects_unsupported_extension(
    notice_client: AsyncClient,
) -> None:
    response = await notice_client.post(
        "/api/v1/administration/notices/parse",
        files={"file": ("公告.txt", b"plain", "text/plain")},
    )
    assert response.status_code == 400
    assert "不支持的文件类型" in response.json()["detail"]


async def test_import_notice_stores_archive_and_ledger(
    notice_client: AsyncClient,
    db_session: AsyncSession,
    notice_admin: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_notice_llm(monkeypatch, dict(_LLM_NOTICE_OUTPUT))
    response = await notice_client.post(
        "/api/v1/administration/notices",
        files={"file": ("培训公告.docx", _notice_docx(), _DOCX_MIME)},
        data={
            "notice_no": "2026-第03号",
            "title": "年度安全培训通知",
            "publisher": "安全环保部",
            "published_at": "2026-03-05",
            "category": "安全公告",
            "remark": "手工确认导入",
        },
    )
    assert response.status_code == 200
    body_text = response.text
    assert "全厂定于下周开展年度安全培训" not in body_text, "台账响应不得包含公告内容"
    item = response.json()["data"]
    assert item["notice_no"] == "2026-第03号"
    assert item["title"] == "年度安全培训通知"
    assert item["source_file_name"] == "培训公告.docx"
    assert "content" not in item

    row = (
        await db_session.execute(
            select(AdministrationNotice).where(
                AdministrationNotice.notice_no == "2026-第03号"
            )
        )
    ).scalar_one()
    assert row.content == _LLM_NOTICE_OUTPUT["content"]
    assert row.created_by == notice_admin.id
    # 存档 MIME 取魔数嗅探结果，不信任客户端 Content-Type 头
    assert row.source_content_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert row.published_at is not None and row.published_at.isoformat() == "2026-03-05"
    # 搜索文本只含元数据，不含公告内容
    assert "全厂定于下周" not in row.search_text
    assert "年度安全培训通知" in row.search_text
    archive = _notice_local_path(row.source_storage_key)
    assert archive.exists(), "原文应存档到隔离目录"


async def test_import_notice_requires_title(notice_client: AsyncClient) -> None:
    response = await notice_client.post(
        "/api/v1/administration/notices",
        files={"file": ("公告.docx", _notice_docx(), _DOCX_MIME)},
        data={"title": "   "},
    )
    assert response.status_code == 422
    assert "标题" in response.json()["detail"]


async def test_list_and_detail_exclude_content(
    notice_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_notice(
        db_session, notice_no="2026-001", title="培训通知", category="安全公告"
    )
    await _seed_notice(
        db_session,
        notice_no="2026-002",
        title="放假通知",
        category="行政通知",
        publisher="人事部",
    )

    listed = await notice_client.get(
        "/api/v1/administration/notices", params={"page": 1, "page_size": 10}
    )
    assert listed.status_code == 200
    data = listed.json()["data"]
    assert data["total"] == 2
    assert set(data["categories"]) == {"安全公告", "行政通知"}
    assert all("content" not in item for item in data["items"])
    # 关键字只搜元数据：搜内容关键词不命中
    miss = await notice_client.get(
        "/api/v1/administration/notices", params={"keyword": "机密正文"}
    )
    assert miss.json()["data"]["total"] == 0
    hit = await notice_client.get(
        "/api/v1/administration/notices", params={"keyword": "2026-002"}
    )
    assert hit.json()["data"]["total"] == 1

    detail = await notice_client.get(
        f"/api/v1/administration/notices/{data['items'][0]['id']}"
    )
    assert detail.status_code == 200
    assert "content" not in detail.json()["data"]


async def test_content_and_file_only_via_dedicated_endpoints(
    notice_client: AsyncClient, db_session: AsyncSession
) -> None:
    notice = await _seed_notice(db_session, notice_no="2026-003", title="内容查看")

    content = await notice_client.get(
        f"/api/v1/administration/notices/{notice.id}/content"
    )
    assert content.status_code == 200
    assert content.json()["data"]["content"] == "机密正文内容"

    notice.source_storage_key = build_notice_storage_key(".docx")
    _notice_local_path(notice.source_storage_key).write_bytes(b"archive-bytes")
    await db_session.flush()

    download = await notice_client.get(
        f"/api/v1/administration/notices/{notice.id}/file"
    )
    assert download.status_code == 200
    assert download.content == b"archive-bytes"
    assert "filename*" in download.headers["content-disposition"]


async def test_delete_notice_soft_deletes_and_hides_content(
    notice_client: AsyncClient, db_session: AsyncSession
) -> None:
    notice = await _seed_notice(db_session, notice_no="2026-004", title="待删除公告")

    deleted = await notice_client.delete(f"/api/v1/administration/notices/{notice.id}")
    assert deleted.status_code == 200
    assert notice.is_deleted is True

    detail = await notice_client.get(f"/api/v1/administration/notices/{notice.id}")
    assert detail.status_code == 404
    content = await notice_client.get(
        f"/api/v1/administration/notices/{notice.id}/content"
    )
    assert content.status_code == 404
    again = await notice_client.delete(f"/api/v1/administration/notices/{notice.id}")
    assert again.status_code == 404


async def test_update_notice_rewrites_metadata(
    notice_client: AsyncClient, db_session: AsyncSession
) -> None:
    notice = await _seed_notice(db_session, notice_no="2026-005", title="原标题")
    response = await notice_client.put(
        f"/api/v1/administration/notices/{notice.id}",
        json={
            "notice_no": "2026-005(改)",
            "title": "新标题",
            "publisher": "新单位",
            "published_at": "2026-03-08",
            "category": "行政通知",
            "remark": "更正",
            "content": "人工更正后的内容",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["title"] == "新标题"
    assert notice.content == "人工更正后的内容"
    assert notice.published_at is not None
    assert notice.published_at.isoformat() == "2026-03-08"
    assert "新标题" in notice.search_text
