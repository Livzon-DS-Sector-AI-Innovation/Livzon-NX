"""知识库异步任务测试：锁定 GET /tasks/{task_id} 的响应契约。

任务基础设施迁移到 app/core/jobs.py（Redis 存储）后，前端轮询依赖的
{task_id, status, result, error} 形状必须保持不变。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core import jobs, storage
from app.modules.registration.service import knowledge_ai

PDF_CONTENT = b"%PDF-1.4\npdf-bytes"


@pytest.fixture
def fake_job_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """用内存字典替代 jobs 的 Redis 存取。

    契约测试目的是锁定任务状态端点的响应形状，不验证 Redis 基础设施；
    同时避免测试框架每用例新建事件循环导致 Redis 连接跨循环复用报错。
    """
    store: dict[str, str] = {}

    async def _set(key: str, value: str, ex: int | None = None) -> None:
        store[key] = value

    async def _get(key: str) -> str | None:
        return store.get(key)

    async def _delete(key: str) -> None:
        store.pop(key, None)

    monkeypatch.setattr(jobs, "cache_set", _set)
    monkeypatch.setattr(jobs, "cache_get", _get)
    monkeypatch.setattr(jobs, "cache_delete", _delete)
    return store


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, tuple[bytes, str]]:
    """用内存字典模拟 MinIO 存储。"""
    store: dict[str, tuple[bytes, str]] = {}
    monkeypatch.setattr(storage, "is_enabled", lambda: True)

    def _upload(module, object_key, data, length, content_type=""):
        store[object_key] = (data, content_type)
        return object_key

    monkeypatch.setattr(storage, "upload_object", _upload)
    monkeypatch.setattr(
        storage, "get_object", lambda module, object_key: store.get(object_key)
    )
    monkeypatch.setattr(
        storage,
        "delete_object",
        lambda module, object_key: store.pop(object_key, None),
    )
    return store


async def _wait_task_terminal(client: AsyncClient, task_id: str) -> dict:
    """等待任务到达终态（completed/failed）。

    使用单次长等待而非循环短轮询：测试框架每个用例会新建事件循环，
    中途返回会导致后台 Redis 任务的连接跨循环复用而报错。
    契约测试 mock 的任务主体瞬间完成，长等待仅在任务异常时消耗。
    """
    import asyncio

    await asyncio.sleep(2)
    response = await client.get(f"/api/v1/registration/knowledge/tasks/{task_id}")
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.asyncio
async def test_extract_task_contract_completes_with_result(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_job_store: dict[str, str],
) -> None:
    async def fake_extract(file_name: str, content_type: str, file_content: bytes):
        return {"title": "提取标题", "content": "提取正文", "source_file": file_name}

    monkeypatch.setattr(knowledge_ai, "extract_article_from_content", fake_extract)

    submit_response = await client.post(
        "/api/v1/registration/knowledge/articles/extract",
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )
    assert submit_response.status_code == 200
    submitted = submit_response.json()["data"]
    assert "task_id" in submitted
    assert submitted["status"] == "pending"

    final = await _wait_task_terminal(client, submitted["task_id"])
    assert final["task_id"] == submitted["task_id"]
    assert final["status"] == "completed"
    assert final["result"]["title"] == "提取标题"


@pytest.mark.asyncio
async def test_extract_task_contract_reports_failure(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_job_store: dict[str, str],
) -> None:
    async def failing_extract(file_name: str, content_type: str, file_content: bytes):
        raise ValueError("LLM 服务不可用")

    monkeypatch.setattr(knowledge_ai, "extract_article_from_content", failing_extract)

    submit_response = await client.post(
        "/api/v1/registration/knowledge/articles/extract",
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )
    assert submit_response.status_code == 200
    task_id = submit_response.json()["data"]["task_id"]

    final = await _wait_task_terminal(client, task_id)
    assert final["status"] == "failed"
    assert "error" in final


@pytest.mark.asyncio
async def test_task_status_unknown_returns_404(
    client: AsyncClient,
    fake_job_store: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/registration/knowledge/tasks/nonexistent-task-id"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_summarize_task_contract_completes_with_ai_summary(
    client: AsyncClient,
    fake_storage: dict[str, tuple[bytes, str]],
    monkeypatch: pytest.MonkeyPatch,
    fake_job_store: dict[str, str],
) -> None:
    async def fake_summary(db, attachment_id):
        return "这是 AI 摘要"

    monkeypatch.setattr(knowledge_ai, "generate_attachment_summary", fake_summary)

    # 先创建分类/文章/附件
    category_response = await client.post(
        "/api/v1/registration/knowledge/categories",
        json={"name": "任务测试分类"},
    )
    assert category_response.status_code == 200
    article_response = await client.post(
        "/api/v1/registration/knowledge/articles",
        json={
            "title": "任务测试文章",
            "category_id": category_response.json()["data"]["id"],
            "content": "正文",
        },
    )
    assert article_response.status_code == 200
    upload_response = await client.post(
        f"/api/v1/registration/knowledge/articles/{article_response.json()['data']['id']}/attachments",
        files={"file": ("doc.pdf", PDF_CONTENT, "application/pdf")},
    )
    assert upload_response.status_code == 200
    attachment_id = upload_response.json()["data"]["id"]

    submit_response = await client.post(
        f"/api/v1/registration/knowledge/attachments/{attachment_id}/summarize"
    )
    assert submit_response.status_code == 200
    submitted = submit_response.json()["data"]
    assert submitted["status"] == "pending"

    final = await _wait_task_terminal(client, submitted["task_id"])
    assert final["status"] == "completed"
    assert final["result"]["ai_summary"] == "这是 AI 摘要"
