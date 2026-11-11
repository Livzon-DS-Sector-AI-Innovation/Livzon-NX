"""应急预案 AI 工作台 API 测试（AsyncClient 真实路由 + 测试库；LLM/后台任务 mock）。"""

import io
import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.llm.exceptions import LLMConfigError
from app.modules.safety.api.emergency_mgmt import emergency_mgmt_router
from app.modules.safety.api.emergency_plan_ai import emergency_plan_ai_router
from app.modules.safety.models import EmergencyPlan
from app.platform.identity.models import User
from tests.modules.safety.test_emergency_plan_workbench_unit import (
    _template_docx_bytes,
)

_PREFIX = "测试AI预案"
_BASE = "/api/v1/safety"


@pytest.fixture(autouse=True)
def _no_redis_jobs(monkeypatch: pytest.MonkeyPatch) -> dict:
    """后台任务与 Redis 状态改为内存假实现，避免测试依赖 Redis/真实 LLM。"""
    state: dict = {"running": set(), "submitted": []}

    async def fake_is_job_running(job_id: str) -> bool:
        return job_id in state["running"]

    async def fake_get_job_status(job_id: str):
        if job_id in state["running"]:
            return {"state": "running", "progress": "进行中", "kind": "generate"}
        return None

    async def fake_submit_job(fn, task_id=None, **kwargs):
        state["submitted"].append({"fn": fn.__name__, "task_id": task_id})
        state["running"].add(task_id)
        return task_id

    for target in (
        "app.modules.safety.service.emergency_plan_workbench",
        "app.modules.safety.api.emergency_plan_ai",
    ):
        monkeypatch.setattr(f"{target}.is_job_running", fake_is_job_running)
        monkeypatch.setattr(f"{target}.get_job_status", fake_get_job_status)
    monkeypatch.setattr(
        "app.modules.safety.service.emergency_plan_workbench.submit_job",
        fake_submit_job,
    )
    return state


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"预案AI测试{uuid4().hex[:8]}", role="user", status="active"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def sub_app(test_user: User) -> FastAPI:
    application = FastAPI()
    application.include_router(emergency_mgmt_router, prefix=_BASE)
    application.include_router(emergency_plan_ai_router, prefix=_BASE)
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


async def _cleanup(db: AsyncSession) -> None:
    await db.execute(
        delete(EmergencyPlan).where(EmergencyPlan.name.like(f"{_PREFIX}%"))
    )
    await db.commit()


async def _create_plan(client: AsyncClient) -> str:
    response = await client.post(
        f"{_BASE}/emergency-plans",
        json={"name": f"{_PREFIX}-{uuid4().hex[:6]}", "plan_type": "comprehensive"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


async def _import(client: AsyncClient, plan_id: str) -> dict:
    response = await client.post(
        f"{_BASE}/emergency-plans/{plan_id}/ai/import",
        files=[
            ("file", ("预案.docx", _template_docx_bytes(), "application/octet-stream"))
        ],
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_import_then_content_and_revisions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    plan_id = await _create_plan(client)

    empty = await client.get(f"{_BASE}/emergency-plans/{plan_id}/content")
    assert empty.status_code == 200
    assert empty.json()["data"]["content_status"] == "empty"
    assert empty.json()["data"]["content"] is None

    data = await _import(client, plan_id)
    assert data["content_status"] == "draft"
    assert data["revision_no"] == 1
    content = data["content"]
    assert content["cover"]["company"] == "丽珠集团（宁夏）制药有限公司"
    assert content["organization"]["commander"] == "史润"
    assert len(content["chapters"]) == 12

    revisions = await client.get(f"{_BASE}/emergency-plans/{plan_id}/revisions")
    assert revisions.status_code == 200
    items = revisions.json()["data"]["items"]
    assert [item["source"] for item in items] == ["import"]

    detail = await client.get(f"{_BASE}/emergency-plans/{plan_id}/revisions/1")
    assert detail.status_code == 200
    assert detail.json()["data"]["content"]["cover"]["title"]

    missing = await client.get(f"{_BASE}/emergency-plans/{plan_id}/revisions/99")
    assert missing.status_code == 404
    await _cleanup(db_session)


async def test_put_content_optimistic_lock_and_restore(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    plan_id = await _create_plan(client)
    data = await _import(client, plan_id)
    content = data["content"]
    content["preface"] = "修改后的引言。"

    stale = await client.put(
        f"{_BASE}/emergency-plans/{plan_id}/content",
        json={"content": content, "base_revision_no": 0},
    )
    assert stale.status_code == 409

    saved = await client.put(
        f"{_BASE}/emergency-plans/{plan_id}/content",
        json={"content": content, "base_revision_no": 1, "summary": "改引言"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["revision_no"] == 2
    assert saved.json()["data"]["content"]["preface"] == "修改后的引言。"

    restored = await client.post(
        f"{_BASE}/emergency-plans/{plan_id}/revisions/1/restore"
    )
    assert restored.status_code == 200
    assert restored.json()["data"]["revision_no"] == 3
    assert restored.json()["data"]["content"]["preface"] != "修改后的引言。"

    invalid = await client.put(
        f"{_BASE}/emergency-plans/{plan_id}/content",
        json={
            "content": {**content, "chapters": [{"key": "bad key", "title": "x"}]},
            "base_revision_no": 3,
        },
    )
    assert invalid.status_code == 422
    await _cleanup(db_session)


async def test_checks_finalize_and_export(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    plan_id = await _create_plan(client)

    no_content_export = await client.get(
        f"{_BASE}/emergency-plans/{plan_id}/export-docx"
    )
    assert no_content_export.status_code == 422
    no_content_finalize = await client.post(
        f"{_BASE}/emergency-plans/{plan_id}/finalize"
    )
    assert no_content_finalize.status_code == 422

    await _import(client, plan_id)
    checks = await client.get(f"{_BASE}/emergency-plans/{plan_id}/content/checks")
    assert checks.status_code == 200
    codes = {issue["code"] for issue in checks.json()["data"]["issues"]}
    assert "typo_leak" in codes  # 导入文档中的“泄露”被规则发现

    final = await client.post(f"{_BASE}/emergency-plans/{plan_id}/finalize")
    assert final.status_code == 200
    assert final.json()["data"]["content_status"] == "finalized"

    exported = await client.get(f"{_BASE}/emergency-plans/{plan_id}/export-docx")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    assert "filename*=utf-8''" in exported.headers["content-disposition"]
    from docx import Document

    exported_doc = Document(io.BytesIO(exported.content))
    assert any("指导思想" in p.text for p in exported_doc.paragraphs)
    await _cleanup(db_session)


async def test_generate_and_review_submit_jobs(
    client: AsyncClient, db_session: AsyncSession, _no_redis_jobs: dict
) -> None:
    await _cleanup(db_session)
    plan_id = await _create_plan(client)
    body = {
        "level": "company",
        "accident_type": "leak_fire",
        "location": "危险品库",
        "substances": [{"name": "乙醇"}],
        "start_time": "14:00",
    }
    review_without_content = await client.post(
        f"{_BASE}/emergency-plans/{plan_id}/ai/review"
    )
    assert review_without_content.status_code == 422

    submitted = await client.post(
        f"{_BASE}/emergency-plans/{plan_id}/ai/generate", json=body
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["kind"] == "generate"
    assert _no_redis_jobs["submitted"][-1]["fn"] == "run_generate_job"

    duplicate = await client.post(
        f"{_BASE}/emergency-plans/{plan_id}/ai/generate", json=body
    )
    assert duplicate.status_code == 409

    status = await client.get(f"{_BASE}/emergency-plans/{plan_id}/ai/job")
    assert status.status_code == 200
    assert status.json()["data"]["state"] == "running"

    bad = await client.post(
        f"{_BASE}/emergency-plans/{plan_id}/ai/generate",
        json={**body, "start_time": "25:99"},
    )
    assert bad.status_code == 422
    await _cleanup(db_session)


async def test_chat_stream_applies_edits(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup(db_session)
    plan_id = await _create_plan(client)
    await _import(client, plan_id)

    async def fake_chat_json(messages, expected_keys=None, **kwargs):
        return {
            "reply": "已将情景一改为夜班。",
            "edits": [
                {
                    "target": "chapter",
                    "chapter_key": "scenario",
                    "content": "（情景一）22时00分，夜班巡查发现泄漏。",
                    "summary": "改夜班",
                }
            ],
        }

    async def no_workflow(self, module_code):  # noqa: ARG001
        return None

    monkeypatch.setattr(
        "app.modules.safety.service.emergency_plan_ai.llm_client.chat_json",
        fake_chat_json,
    )
    monkeypatch.setattr(
        "app.modules.safety.repository.SafetyRepository."
        "get_ai_workflow_config_by_module",
        no_workflow,
    )
    response = await client.post(
        f"{_BASE}/emergency-plans/{plan_id}/ai/chat",
        json={"message": "把情景一改成夜班"},
    )
    assert response.status_code == 200
    frames = [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    keys = [next(iter(frame)) for frame in frames]
    assert keys[0] == "status"
    assert "reply" in keys and "revision" in keys and keys[-1] == "done"
    content_frame = next(frame for frame in frames if "content" in frame)
    scenario = next(
        chapter
        for chapter in content_frame["content"]["content"]["chapters"]
        if chapter["key"] == "scenario"
    )
    assert scenario["content"].startswith("（情景一）22时00分")

    messages = await client.get(f"{_BASE}/emergency-plans/{plan_id}/ai/messages")
    assert messages.status_code == 200
    roles = [item["role"] for item in messages.json()["data"]["items"]]
    assert roles == ["user", "assistant"]
    await _cleanup(db_session)


async def test_chat_stream_llm_config_error(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup(db_session)
    plan_id = await _create_plan(client)
    await _import(client, plan_id)

    async def raise_config(*args, **kwargs):
        raise LLMConfigError("no config")

    async def no_workflow(self, module_code):  # noqa: ARG001
        return None

    monkeypatch.setattr(
        "app.modules.safety.service.emergency_plan_ai.llm_client.chat_json",
        raise_config,
    )
    monkeypatch.setattr(
        "app.modules.safety.repository.SafetyRepository."
        "get_ai_workflow_config_by_module",
        no_workflow,
    )
    response = await client.post(
        f"{_BASE}/emergency-plans/{plan_id}/ai/chat", json={"message": "检查一下"}
    )
    assert response.status_code == 200
    assert "尚未配置" in response.text
    assert '"done": true' in response.text
    empty_message = await client.post(
        f"{_BASE}/emergency-plans/{plan_id}/ai/chat", json={"message": ""}
    )
    assert empty_message.status_code == 422
    await _cleanup(db_session)


async def test_options_and_unknown_plan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    options = await client.get(f"{_BASE}/emergency-plans/ai/options")
    assert options.status_code == 200
    data = options.json()["data"]
    assert {item["value"] for item in data["levels"]} == {"company", "workshop"}
    assert data["default_organization"]["groups"]
    assert data["default_company"]

    unknown = uuid4()
    for method, path in (
        ("get", f"/emergency-plans/{unknown}/content"),
        ("get", f"/emergency-plans/{unknown}/revisions"),
        ("get", f"/emergency-plans/{unknown}/ai/job"),
        ("get", f"/emergency-plans/{unknown}/export-docx"),
    ):
        response = await getattr(client, method)(f"{_BASE}{path}")
        assert response.status_code == 404, path
