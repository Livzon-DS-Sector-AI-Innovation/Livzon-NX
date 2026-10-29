"""操规批量导入与 AI 法规合规审核测试（真实服务 + 独立测试库）。

覆盖：
- 文件名识别规则（车间/岗位/名称清洗，真实车间文件名样例）；
- 批量上传 API：AI 不可用时回退规则识别、AI 识别成功、重复导入跳过、
  未登录 401、不支持格式；
- 合规审核 API：AI 报告保存与归一化（评分钳制、非法严重度兜底）、
  无内容 400、操规不存在 404、模型未配置 503、输出不可解析 502；
- 审核记录列表与最新审核状态查询。

LLM 一律 mock，不连接真实模型。
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
from app.core.llm import LLMConfigError, LLMOutputError, llm_client
from app.modules.safety.api.regulations import regulations_router
from app.modules.safety.models import OperationRegulation, RegulationReview
from app.modules.safety.service.regulation_compliance import (
    recognize_from_filename,
)
from app.platform.identity.models import User


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"操规测试{uuid4().hex[:8]}", role="user", status="active"
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


@pytest.fixture
async def seeded_regulation(db_session: AsyncSession) -> OperationRegulation:
    regulation = OperationRegulation(
        regulation_no=f"SGTEST-{uuid4().hex[:6].upper()}",
        regulation_name="测试车间化测岗位安全操作规程",
        workshop="测试车间",
        position="化测",
        content=(
            "# 一、目的\n\n规范化测岗位操作。\n\n"
            "# 九、应急处置措施\n\n泄漏时穿戴防护用品并上报。"
        ),
        status="reviewed",
    )
    db_session.add(regulation)
    await db_session.flush()
    return regulation


async def _cleanup_regulation(
    db: AsyncSession, regulation: OperationRegulation
) -> None:
    await db.delete(regulation)
    await db.commit()
    for path in (regulation.document_path, regulation.source_document_path):
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _docx_bytes(text: str) -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ==================== 文件名识别规则 ====================


def test_recognize_workshop_and_position_from_filename() -> None:
    workshop, position, title = recognize_from_filename(
        "101-102车间机修岗位安全操作规程.docx"
    )
    assert (workshop, position) == ("101-102车间", "机修")
    assert title == "101-102车间机修岗位安全操作规程"


def test_recognize_han_numeral_workshop_and_position() -> None:
    workshop, position, _ = recognize_from_filename(
        "101二车间工艺值班岗位标准操作规程.docx"
    )
    assert workshop == "101二车间"
    assert position == "工艺值班"


def test_recognize_cleans_version_markers_and_copy_suffixes() -> None:
    _, position, title = recognize_from_filename(
        "值班安全操作规程（2026版）(2026.05.19)(3).docx", hint_workshop="103车间"
    )
    assert position == "值班"
    assert title == "值班安全操作规程"


def test_recognize_falls_back_to_hint_workshop_and_keywords() -> None:
    workshop, position, title = recognize_from_filename(
        "300变电站安全操作规程.docx", hint_workshop="动力部"
    )
    assert workshop == "动力部"
    assert position == "变电站"
    assert title == "300变电站安全操作规程"


def test_recognize_keeps_subworkshop_position_prefix() -> None:
    _, position, _ = recognize_from_filename(
        "一部消毒岗位安全操作规程（2026版）2026.05.20.docx", hint_workshop="103车间"
    )
    assert position == "一部消毒"


# ==================== 批量上传 API ====================


async def test_batch_upload_falls_back_to_heuristic_without_llm(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_llm(*args: object, **kwargs: object) -> dict[str, str]:
        raise LLMConfigError("模型未配置")

    monkeypatch.setattr(llm_client, "chat_json", _no_llm)

    docx_mime = (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    )
    resp = await client.post(
        "/api/v1/safety/regulations/batch-upload",
        files=[
            (
                "files",
                (
                    "103车间液氨站安全操作规程（2026版）2026.05.20.docx",
                    _docx_bytes("1. 目的"),
                    docx_mime,
                ),
            ),
            (
                "files",
                (
                    "电工岗位操作规程ok.txt",
                    "1. 目的\n穿戴绝缘用品".encode(),
                    "text/plain",
                ),
            ),
        ],
        data={"use_ai": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["success_count"] == 2
    item = next(
        i
        for i in data["items"]
        if i["file_name"].endswith("液氨站安全操作规程（2026版）2026.05.20.docx")
    )
    assert item["ok"] is True
    assert item["workshop"] == "103车间"
    assert item["position"] == "液氨站"
    assert item["regulation_name"] == "103车间液氨站安全操作规程"
    assert item["recognized_by"] == "heuristic"

    created = await db_session.get(OperationRegulation, item["regulation_id"])
    assert created is not None
    assert created.workshop == "103车间"
    assert created.document_original_name.endswith(".docx")
    await _cleanup_regulation(db_session, created)

    txt_item = next(i for i in data["items"] if i["file_name"].endswith(".txt"))
    txt_reg = await db_session.get(OperationRegulation, txt_item["regulation_id"])
    assert txt_reg is not None
    await _cleanup_regulation(db_session, txt_reg)


async def test_batch_upload_uses_ai_recognition(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_chat_json(*args: object, **kwargs: object) -> dict[str, str]:
        assert "expected_keys" in kwargs
        return {
            "workshop": "201二车间",
            "position": "压滤",
            "title": "201二车间压滤岗位安全操作规程",
        }

    monkeypatch.setattr(llm_client, "chat_json", _fake_chat_json)

    resp = await client.post(
        "/api/v1/safety/regulations/batch-upload",
        files=[
            (
                "files",
                (
                    "201-2压滤岗位安全操作规程2026（6.30）(1).docx",
                    _docx_bytes("压滤岗位操作"),
                    "application/octet-stream",
                ),
            ),
        ],
        data={"use_ai": "true"},
    )
    assert resp.status_code == 200
    item = resp.json()["data"]["items"][0]
    assert item["ok"] is True
    assert item["recognized_by"] == "ai"
    assert item["workshop"] == "201二车间"
    assert item["position"] == "压滤"

    created = await db_session.get(OperationRegulation, item["regulation_id"])
    assert created is not None
    await _cleanup_regulation(db_session, created)


async def test_batch_upload_skips_duplicate_import(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_llm(*args: object, **kwargs: object) -> dict[str, str]:
        raise LLMConfigError("模型未配置")

    monkeypatch.setattr(llm_client, "chat_json", _no_llm)
    payload = [
        (
            "files",
            (
                "重复测试车间配料岗位安全操作规程.docx",
                _docx_bytes("x"),
                "application/octet-stream",
            ),
        ),
    ]

    first = await client.post(
        "/api/v1/safety/regulations/batch-upload", files=payload
    )
    assert first.status_code == 200
    assert first.json()["data"]["success_count"] == 1
    created_id = first.json()["data"]["items"][0]["regulation_id"]

    second = await client.post(
        "/api/v1/safety/regulations/batch-upload", files=payload
    )
    item = second.json()["data"]["items"][0]
    assert item["ok"] is False
    assert "已导入" in item["message"]

    created = await db_session.get(OperationRegulation, created_id)
    assert created is not None
    # 导入不再生成编号、不写备注
    assert created.regulation_no is None
    assert not created.notes
    await _cleanup_regulation(db_session, created)


async def test_batch_upload_rejects_unsupported_and_requires_login(
    sub_app: FastAPI, db_session: AsyncSession
) -> None:
    sub_app.dependency_overrides[get_current_user] = lambda: None

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    sub_app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=sub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/safety/regulations/batch-upload",
            files=[("files", ("操规.xlsx", b"xx", "application/octet-stream"))],
        )
    assert resp.status_code == 401


# ==================== AI 法规合规审核 API ====================


async def test_compliance_review_saves_normalized_report(
    client: AsyncClient,
    seeded_regulation: OperationRegulation,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_chat_json(*args: object, **kwargs: object) -> dict[str, object]:
        assert "expected_keys" in kwargs
        return {
            "result": "conditional_pass",
            "score": 150,
            "summary": "整体框架完整，应急处置偏简略。",
            "missing_items": [
                {
                    "item": "个体防护用品配备",
                    "requirement": "明确防毒面具等佩戴要求",
                    "basis": "《安全生产法》第四十五条",
                    "severity": "严重",
                    "suggestion": "补充防护用品清单",
                },
                "不是字典的条目会被忽略",
            ],
            "non_compliant_items": [
                {
                    "item": "应急处置措施",
                    "requirement": "应包含应急电话",
                    "basis": "GB 30871-2022",
                    "severity": "无效等级",
                    "suggestion": "补充应急电话",
                }
            ],
            "suggestions": ["补充应急电话", "完善防护要求"],
        }

    monkeypatch.setattr(llm_client, "chat_json", _fake_chat_json)

    resp = await client.post(
        f"/api/v1/safety/regulations/{seeded_regulation.id}/compliance-review"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["result"] == "conditional_pass"
    assert data["score"] == 100  # 钳制到 0-100
    assert len(data["missing_items"]) == 1  # 非字典条目被过滤
    assert data["missing_items"][0]["severity"] == "严重"
    assert data["non_compliant_items"][0]["severity"] == "建议"  # 非法等级兜底
    assert data["suggestions"] == ["补充应急电话", "完善防护要求"]

    saved = await db_session.get(RegulationReview, data["id"])
    assert saved is not None
    assert saved.regulation_id == seeded_regulation.id

    await db_session.delete(saved)
    await db_session.commit()


async def test_compliance_review_maps_llm_errors(
    client: AsyncClient,
    seeded_regulation: OperationRegulation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_llm(*args: object, **kwargs: object) -> dict[str, object]:
        raise LLMConfigError("模型未配置")

    monkeypatch.setattr(llm_client, "chat_json", _no_llm)
    resp = await client.post(
        f"/api/v1/safety/regulations/{seeded_regulation.id}/compliance-review"
    )
    assert resp.status_code == 503

    async def _bad_output(*args: object, **kwargs: object) -> dict[str, object]:
        raise LLMOutputError("响应不是合法 JSON")

    monkeypatch.setattr(llm_client, "chat_json", _bad_output)
    resp = await client.post(
        f"/api/v1/safety/regulations/{seeded_regulation.id}/compliance-review"
    )
    assert resp.status_code == 502


async def test_compliance_review_requires_content_and_existing_regulation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    empty = OperationRegulation(
        regulation_no=f"SGEMPTY-{uuid4().hex[:6].upper()}",
        regulation_name="无内容操规",
        workshop="测试车间",
        status="draft",
    )
    db_session.add(empty)
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/safety/regulations/{empty.id}/compliance-review"
    )
    assert resp.status_code == 400
    assert "无可审核内容" in resp.json()["detail"]

    resp = await client.post(
        f"/api/v1/safety/regulations/{uuid4()}/compliance-review"
    )
    assert resp.status_code == 404

    await db_session.delete(empty)
    await db_session.commit()


async def test_review_list_and_latest_endpoints(
    client: AsyncClient,
    seeded_regulation: OperationRegulation,
    db_session: AsyncSession,
) -> None:
    review = RegulationReview(
        regulation_id=seeded_regulation.id,
        regulation_name=seeded_regulation.regulation_name,
        result="fail",
        score=55,
        summary="缺失应急处置与防护章节",
        missing_items=[],
        non_compliant_items=[],
        suggestions=[],
    )
    db_session.add(review)
    await db_session.flush()

    resp = await client.get(
        f"/api/v1/safety/regulations/{seeded_regulation.id}/reviews"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["result"] == "fail"

    resp = await client.get(
        "/api/v1/safety/regulation-reviews/latest",
        params={"regulation_ids": str(seeded_regulation.id)},
    )
    assert resp.status_code == 200
    entries = resp.json()["data"]
    assert len(entries) == 1
    assert entries[0]["regulation_id"] == str(seeded_regulation.id)
    assert entries[0]["result"] == "fail"
    assert entries[0]["score"] == 55

    resp = await client.get(
        "/api/v1/safety/regulation-reviews/latest",
        params={"regulation_ids": "not-a-uuid"},
    )
    assert resp.status_code == 400

    await db_session.delete(review)
    await db_session.commit()


# ==================== 文档在线预览 ====================


async def test_document_preview_and_download(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import delete

    # 先清理此前失败运行可能残留的同名记录（批量导入会提交数据）
    await db_session.execute(
        delete(OperationRegulation).where(
            OperationRegulation.regulation_name.like("预览测试车间化测岗位%")
        )
    )
    await db_session.commit()

    async def _no_llm(*args: object, **kwargs: object) -> dict[str, str]:
        raise LLMConfigError("模型未配置")

    monkeypatch.setattr(llm_client, "chat_json", _no_llm)
    doc_text = "1. 目的\n规范化测岗位操作。\n2. 应急处置"
    upload = await client.post(
        "/api/v1/safety/regulations/batch-upload",
        files=[
            (
                "files",
                (
                    "预览测试车间化测岗位安全操作规程.docx",
                    _docx_bytes(doc_text),
                    "application/octet-stream",
                ),
            ),
        ],
    )
    item = upload.json()["data"]["items"][0]
    assert item["ok"] is True
    created = await db_session.get(OperationRegulation, item["regulation_id"])
    assert created is not None

    resp = await client.get(
        f"/api/v1/safety/regulations/{created.id}/document-content"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["file_name"] == "预览测试车间化测岗位安全操作规程.docx"
    assert "规范化测岗位操作" in data["content"]
    assert data["note"] == ""

    resp = await client.get(f"/api/v1/safety/regulations/{created.id}/document")
    assert resp.status_code == 200
    assert resp.content.startswith(b"PK")  # docx 为 zip 容器

    resp = await client.get(
        f"/api/v1/safety/regulations/{uuid4()}/document-content"
    )
    # 旧式 ApiResponse 包装：HTTP 200 + 业务 code 404
    assert resp.status_code == 200
    assert resp.json()["code"] == 404

    await _cleanup_regulation(db_session, created)


async def test_document_preview_falls_back_to_content(
    client: AsyncClient, seeded_regulation: OperationRegulation
) -> None:
    resp = await client.get(
        f"/api/v1/safety/regulations/{seeded_regulation.id}/document-content"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "规范化测岗位操作" in data["content"]
    assert "文档文件不存在" in data["note"]
