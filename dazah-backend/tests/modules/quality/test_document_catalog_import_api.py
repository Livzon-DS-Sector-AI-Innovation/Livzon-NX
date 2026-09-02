"""文件目录附件批量导入接口测试（AsyncClient 真实调用路由）。

覆盖：编码匹配绑定+版本自动升级、word 转换图片资产、未匹配部分成功、
不支持的文件类型 4xx。存储走本地 tmp 目录，LLM/转换按模块规范打桩。
"""

from __future__ import annotations

import base64
import io
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.modules.quality.models.document_catalog import DocumentEntry
from app.modules.quality.service import document_catalog_attachment as service

PNG_1PX: bytes = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

IMPORT_URL = "/api/v1/quality/document-catalog/attachments/import"


async def _create_entry(db_session: AsyncSession, code: str) -> DocumentEntry:
    # 先清理历史运行 commit 遗留的同前缀行（同事务内删除即不可见），
    # 仅 flush 不 commit：路由同一会话可见，fixture 回滚即清理，不污染测试库
    await db_session.execute(
        DocumentEntry.__table__.delete().where(
            DocumentEntry.code.like("SOP-QA-001%")
        )
    )
    entry = DocumentEntry(
        department_id=uuid4(),
        seq_no=1,
        name="偏差处理程序",
        code=code,
        attachments=[],
    )
    db_session.add(entry)
    await db_session.flush()
    return entry


def _storage_to_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(service, "_local_upload_dir", lambda: tmp_path)
    monkeypatch.setattr(service, "minio_enabled", lambda: False)


def _real_docx_bytes() -> bytes:
    """构造可通过内容嗅探的真实 docx（zip + word/document.xml）。"""
    from docx import Document

    document = Document()
    document.add_paragraph("正文")
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


async def _post_files(db_session: AsyncSession, files: list[Any]) -> Any:
    """构建绑定 db_session 的路由客户端（同一会话便于断言写入结果），返回响应。"""

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            return await ac.post(IMPORT_URL, files=files)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.anyio
async def test_batch_import_binds_upgrades_version_and_reports_unmatched(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _storage_to_tmp(monkeypatch, tmp_path)
    entry = await _create_entry(db_session, "SOP-QA-001/02")

    from app.modules.quality.service.document_catalog_md import ExtractedImage

    image = ExtractedImage(name="img_000.png", data=PNG_1PX, content_type="image/png")
    # 端点从 document_catalog_md 模块局部导入转换函数，须 patch 该模块引用
    import app.modules.quality.service.document_catalog_md as md_conv_mod

    monkeypatch.setattr(
        md_conv_mod,
        "convert_word_attachment",
        lambda *_args: ("# 转换标准\n\n![image](img_000.png)", [image]),
    )

    response = await _post_files(
        db_session,
        [
            (
                "files",
                (
                    "SOP-QA-001-03偏差处理程序.md",
                    "# 目录".encode(),
                    "text/markdown",
                ),
            ),
            (
                "files",
                (
                    "SOP-QA-001-03偏差处理程序.docx",
                    _real_docx_bytes(),
                    "application/octet-stream",
                ),
            ),
            (
                "files",
                ("完全没有编码的文件.pdf", b"%PDF-1.7", "application/pdf"),
            ),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["bound"] == 2
    assert body["data"]["failed"] == 1
    assert body["data"]["version_updated_count"] == 1

    results = body["data"]["results"]
    by_name = {item["file_name"]: item for item in results}

    # .md 附件：编码匹配 + 版本 02 → 03 自动升级
    md_result = by_name["SOP-QA-001-03偏差处理程序.md"]
    assert md_result["matched"] is True
    assert md_result["match_type"] == "name"
    assert md_result["version_updated"] is True
    assert md_result["old_code"] == "SOP-QA-001/02"
    assert md_result["new_code"] == "SOP-QA-001/03"

    # .docx 附件：同名版本相同（03），转换但不重复升级
    docx_result = by_name["SOP-QA-001-03偏差处理程序.docx"]
    assert docx_result["matched"] is True
    assert docx_result["version_updated"] is False

    # 未匹配文件仅报告失败，不影响其余绑定（部分成功）
    unmatched = by_name["完全没有编码的文件.pdf"]
    assert unmatched["matched"] is False
    assert unmatched["match_type"] == "none"

    # NullPool 下 refresh 会用新连接读到未提交旧快照，直接断言同一会话对象
    assert entry.code == "SOP-QA-001/03"

    # word 附件转换产物：标准 MD 与图片资产均已真实存储并绑定
    entry_attachments = list(entry.attachments or [])
    docx_attachment = next(
        a
        for a in entry_attachments
        if a["file_name"] == "SOP-QA-001-03偏差处理程序.docx"
    )
    assert docx_attachment["converted"] is True
    assert len(docx_attachment["asset_keys"]) == 1
    assert docx_attachment.get("pipeline") == "v2"


@pytest.mark.anyio
async def test_batch_import_rejects_unsupported_file_type(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _storage_to_tmp(monkeypatch, tmp_path)
    await _create_entry(db_session, "SOP-QA-001/02")

    response = await _post_files(
        db_session,
        [("files", ("bad.exe", b"bin", "application/octet-stream"))],
    )

    assert response.status_code == 400
    assert "不支持的文件类型" in response.json()["message"]
