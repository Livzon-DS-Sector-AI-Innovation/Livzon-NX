"""知识库附件上传/预览测试：文件内容必须真正落盘并可读回。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core import storage

PDF_CONTENT = b"%PDF-1.4\nattachment-bytes-test"


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, tuple[bytes, str]]:
    """用内存字典模拟 MinIO 存储。"""
    store: dict[str, tuple[bytes, str]] = {}

    monkeypatch.setattr(storage, "is_enabled", lambda: True)

    def _upload(
        module: str, object_key: str, data: bytes, length: int, content_type: str = ""
    ) -> str:
        assert module == "registration"
        assert length == len(data)
        store[object_key] = (data, content_type)
        return object_key

    def _get(module: str, object_key: str):
        assert module == "registration"
        return store.get(object_key)

    def _delete(module: str, object_key: str) -> None:
        store.pop(object_key, None)

    monkeypatch.setattr(storage, "upload_object", _upload)
    monkeypatch.setattr(storage, "get_object", _get)
    monkeypatch.setattr(storage, "delete_object", _delete)
    return store


async def _create_article(client: AsyncClient) -> str:
    category_response = await client.post(
        "/api/v1/registration/knowledge/categories",
        json={"name": "附件测试分类"},
    )
    assert category_response.status_code == 200
    category_id = category_response.json()["data"]["id"]

    article_response = await client.post(
        "/api/v1/registration/knowledge/articles",
        json={
            "title": "附件测试文章",
            "category_id": category_id,
            "content": "正文",
        },
    )
    assert article_response.status_code == 200
    return article_response.json()["data"]["id"]


@pytest.mark.asyncio
async def test_upload_attachment_rejected_when_storage_disabled(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage, "is_enabled", lambda: False)
    article_id = await _create_article(client)

    response = await client.post(
        f"/api/v1/registration/knowledge/articles/{article_id}/attachments",
        files={"file": ("doc.pdf", b"%PDF-fake", "application/pdf")},
    )

    assert response.status_code == 503
    assert "文件存储" in response.json()["message"]


@pytest.mark.asyncio
async def test_upload_attachment_persists_content(
    client: AsyncClient,
    fake_storage: dict[str, tuple[bytes, str]],
) -> None:
    article_id = await _create_article(client)
    content = PDF_CONTENT

    response = await client.post(
        f"/api/v1/registration/knowledge/articles/{article_id}/attachments",
        files={"file": ("规范.pdf", content, "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["file_name"] == "规范.pdf"
    assert data["file_size"] == len(content)
    # 对象键带 uuid 前缀防覆盖，且包含文章 ID 前缀目录
    assert data["file_path"].startswith(f"knowledge/{article_id}/")
    assert data["file_path"].endswith("_规范.pdf")
    # 文件内容真正写入存储
    stored = list(fake_storage.values())
    assert len(stored) == 1
    assert stored[0][0] == content
    assert stored[0][1] == "application/pdf"


@pytest.mark.asyncio
async def test_preview_attachment_returns_real_content(
    client: AsyncClient,
    fake_storage: dict[str, tuple[bytes, str]],
) -> None:
    article_id = await _create_article(client)
    content = b"preview-content"

    upload_response = await client.post(
        f"/api/v1/registration/knowledge/articles/{article_id}/attachments",
        files={"file": ("preview.txt", content, "text/plain")},
    )
    assert upload_response.status_code == 200
    attachment_id = upload_response.json()["data"]["id"]

    preview_response = await client.get(
        f"/api/v1/registration/knowledge/attachments/{attachment_id}/preview"
    )
    assert preview_response.status_code == 200
    assert preview_response.content == content
    assert preview_response.headers["content-type"].startswith("text/plain")
    assert "inline" in preview_response.headers.get("content-disposition", "")

    download_response = await client.get(
        f"/api/v1/registration/knowledge/attachments/{attachment_id}/preview?download=true"
    )
    assert download_response.status_code == 200
    assert "attachment" in download_response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_preview_attachment_returns_404_when_object_missing(
    client: AsyncClient,
    fake_storage: dict[str, tuple[bytes, str]],
) -> None:
    article_id = await _create_article(client)
    upload_response = await client.post(
        f"/api/v1/registration/knowledge/articles/{article_id}/attachments",
        files={"file": ("gone.txt", b"data", "text/plain")},
    )
    assert upload_response.status_code == 200
    attachment_id = upload_response.json()["data"]["id"]

    # 模拟存储对象丢失（如历史幽灵附件）
    fake_storage.clear()

    response = await client.get(
        f"/api/v1/registration/knowledge/attachments/{attachment_id}/preview"
    )
    assert response.status_code == 404
