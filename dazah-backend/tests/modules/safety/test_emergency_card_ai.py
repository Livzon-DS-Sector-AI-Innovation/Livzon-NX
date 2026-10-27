"""应急处置卡 AI 审阅端点测试（真实服务 + 独立测试库，mock llm_client）。

覆盖成功路径与最可能失败路径：未配置模型 400、输出不可解析 502、
限流 429、供应商错误 502、卡片不存在 404，以及非法条目被过滤的
业务校验行为。
"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.modules.safety.api.emergency_cards import emergency_cards_router
from app.modules.safety.models import EmergencyCard
from app.platform.identity.models import User


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"AI审阅测试{uuid4().hex[:8]}", role="user", status="active"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def sub_app(test_user: User) -> FastAPI:
    application = FastAPI()
    application.include_router(
        emergency_cards_router, prefix="/api/v1/safety"
    )
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
async def seeded_card(db_session: AsyncSession) -> EmergencyCard:
    card = EmergencyCard(
        workshop="103车间",
        position="配料",
        title="103车间AI审阅测试泄漏应急处置卡",
        subject="测试泄漏",
        accident_type="泄漏",
        steps=[
            {
                "order": "1",
                "step": "发现异常",
                "action": "立即示警",
                "person": "岗位员工",
            }
        ],
        extras=[],
        phones="消防：119",
        risks="",
        precautions="穿戴防护用品",
        source_file="test.html",
        search_text="",
    )
    db_session.add(card)
    await db_session.flush()
    return card


async def _cleanup(db: AsyncSession) -> None:
    await db.execute(
        delete(EmergencyCard).where(
            EmergencyCard.title.like("%AI审阅测试泄漏%")
        )
    )
    await db.commit()


VALID_REVIEW = {
    "summary": "处置步骤较完整，但缺少风险后果描述。",
    "completeness": [
        {"item": "报警与报告", "status": "ok", "note": "已包含报告要求"},
        {"item": "主要风险及后果", "status": "missing", "note": "未填写"},
    ],
    "suggestions": [
        {
            "section": "risks",
            "title": "补充泄漏风险",
            "content": "氨泄漏会气化扩散，浓度过高导致人员中毒窒息。",
        }
    ],
}


async def test_ai_review_success(
    client: AsyncClient,
    seeded_card: EmergencyCard,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_chat_json(*args: object, **kwargs: object) -> dict[str, object]:
        captured["kwargs"] = kwargs
        return dict(VALID_REVIEW)

    monkeypatch.setattr(llm_client, "chat_json", _fake_chat_json)
    resp = await client.post(
        f"/api/v1/safety/emergency-cards/{seeded_card.id}/ai-review"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["summary"] == VALID_REVIEW["summary"]
    assert len(data["completeness"]) == 2
    assert data["completeness"][1]["status"] == "missing"
    assert data["suggestions"][0]["section"] == "risks"
    kwargs = captured["kwargs"]
    assert set(kwargs["expected_keys"]) == {
        "summary",
        "completeness",
        "suggestions",
    }
    await _cleanup(db_session)


async def test_ai_review_filters_invalid_items(
    client: AsyncClient,
    seeded_card: EmergencyCard,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    async def _fake_chat_json(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "summary": "总体可用。",
            "completeness": [
                {"item": "报警与报告", "status": "ok", "note": "覆盖"},
                {"item": "坏条目", "status": "不是合法状态", "note": "x"},
                "不是对象",
            ],
            "suggestions": [
                {"section": "未知位置", "title": "坏建议", "content": "x"},
                {
                    "section": "precautions",
                    "title": "补充警戒要求",
                    "content": "警戒区域设置后清点人数。",
                },
            ],
        }

    monkeypatch.setattr(llm_client, "chat_json", _fake_chat_json)
    resp = await client.post(
        f"/api/v1/safety/emergency-cards/{seeded_card.id}/ai-review"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["completeness"]) == 1
    assert len(data["suggestions"]) == 1
    assert data["suggestions"][0]["section"] == "precautions"
    await _cleanup(db_session)


async def test_ai_review_card_not_found(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_chat_json(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("卡片不存在时不应调用模型")

    monkeypatch.setattr(llm_client, "chat_json", _fake_chat_json)
    resp = await client.post(f"/api/v1/safety/emergency-cards/{uuid4()}/ai-review")
    assert resp.status_code == 404


async def test_ai_review_without_llm_config(
    client: AsyncClient,
    seeded_card: EmergencyCard,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    async def _no_llm(*args: object, **kwargs: object) -> dict[str, object]:
        raise LLMConfigError("模型未配置")

    monkeypatch.setattr(llm_client, "chat_json", _no_llm)
    resp = await client.post(
        f"/api/v1/safety/emergency-cards/{seeded_card.id}/ai-review"
    )
    assert resp.status_code == 400
    assert "尚未配置分析模型" in resp.json()["detail"]
    await _cleanup(db_session)


async def test_ai_review_invalid_output(
    client: AsyncClient,
    seeded_card: EmergencyCard,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    async def _bad_output(*args: object, **kwargs: object) -> dict[str, object]:
        raise LLMOutputError("响应不是合法 JSON")

    monkeypatch.setattr(llm_client, "chat_json", _bad_output)
    resp = await client.post(
        f"/api/v1/safety/emergency-cards/{seeded_card.id}/ai-review"
    )
    assert resp.status_code == 502
    await _cleanup(db_session)


async def test_ai_review_empty_output(
    client: AsyncClient,
    seeded_card: EmergencyCard,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    async def _empty(*args: object, **kwargs: object) -> dict[str, object]:
        return {"summary": "", "completeness": [], "suggestions": []}

    monkeypatch.setattr(llm_client, "chat_json", _empty)
    resp = await client.post(
        f"/api/v1/safety/emergency-cards/{seeded_card.id}/ai-review"
    )
    assert resp.status_code == 502
    await _cleanup(db_session)


async def test_ai_review_rate_limited(
    client: AsyncClient,
    seeded_card: EmergencyCard,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    async def _rate_limited(*args: object, **kwargs: object) -> dict[str, object]:
        raise LLMRateLimitError("限流")

    monkeypatch.setattr(llm_client, "chat_json", _rate_limited)
    resp = await client.post(
        f"/api/v1/safety/emergency-cards/{seeded_card.id}/ai-review"
    )
    assert resp.status_code == 429
    await _cleanup(db_session)


async def test_ai_review_provider_error(
    client: AsyncClient,
    seeded_card: EmergencyCard,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    async def _provider_error(*args: object, **kwargs: object) -> dict[str, object]:
        raise LLMProviderError("供应商故障")

    monkeypatch.setattr(llm_client, "chat_json", _provider_error)
    resp = await client.post(
        f"/api/v1/safety/emergency-cards/{seeded_card.id}/ai-review"
    )
    assert resp.status_code == 502
    await _cleanup(db_session)
