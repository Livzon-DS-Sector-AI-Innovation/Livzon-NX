import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.llm import api as llm_api
from app.core.llm.capabilities import LLMCapabilities
from app.core.llm.config import LLMConfigModel
from app.core.llm.exceptions import LLMConfigError
from app.platform.identity.deps import require_admin

SimpleNamespace: Any = _SimpleNamespace


@pytest.fixture
async def llm_api_client() -> AsyncIterator[AsyncClient]:
    test_app = FastAPI()
    test_app.include_router(llm_api.router, prefix="/api/v1")
    test_app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id="admin")
    test_app.dependency_overrides[get_db] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_probe_config_tests_unsaved_url(
    llm_api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_probe_api_base_url(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(llm_api, "probe_api_base_url", fake_probe_api_base_url)

    response = await llm_api_client.post(
        "/api/v1/llm/configs/probe",
        json={
            "probe_type": "url",
            "api_base_url": "https://llm.example/v1",
            "api_key": "test-key",
            "timeout_seconds": 45,
        },
    )

    assert response.status_code == 200
    assert response.json()["detail"] == "API URL 与密钥连通正常"
    assert calls == [
        {
            "api_base_url": "https://llm.example/v1",
            "api_key": "test-key",
            "timeout_seconds": 45,
        }
    ]


@pytest.mark.asyncio
async def test_probe_config_tests_unsaved_model(
    llm_api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_detect_model_capabilities(**_kwargs: object) -> LLMCapabilities:
        return LLMCapabilities(supports_text=True, supports_vision=False)

    monkeypatch.setattr(
        llm_api, "detect_model_capabilities", fake_detect_model_capabilities
    )

    response = await llm_api_client.post(
        "/api/v1/llm/configs/probe",
        json={
            "probe_type": "model",
            "api_base_url": "https://llm.example/v1",
            "api_key": "test-key",
            "model_name": "test-model",
            "timeout_seconds": 30,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "probe_type": "model",
        "config_type": "text",
        "capabilities": ["text", "document"],
        "detail": "模型连通正常；已检测到文本和文档能力，模型不接受图片输入",
    }


@pytest.mark.asyncio
async def test_probe_config_maps_expected_provider_failure_to_400(
    llm_api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_probe_api_base_url(**_kwargs: object) -> None:
        raise LLMConfigError("URL 连通性测试失败：ConnectError")

    monkeypatch.setattr(llm_api, "probe_api_base_url", fake_probe_api_base_url)

    response = await llm_api_client.post(
        "/api/v1/llm/configs/probe",
        json={
            "probe_type": "url",
            "api_base_url": "https://llm.example/v1",
            "api_key": "test-key",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "URL 连通性测试失败：ConnectError"}


@pytest.mark.asyncio
@pytest.mark.parametrize("verified", [True, False])
async def test_probe_runs_real_detection_and_returns_inconclusive_error(
    llm_api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    verified: bool,
) -> None:
    import json

    import httpx

    from app.core.llm.capabilities import detect_model_capabilities
    from tests.core.llm.test_capabilities import answer_response, image_answer

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if isinstance(payload["messages"][0]["content"], list) and not verified:
            return answer_response("UNAVAILABLE")
        return answer_response(image_answer(payload))

    async def detect_with_transport(**kwargs: Any) -> LLMCapabilities:
        return await detect_model_capabilities(
            **kwargs,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(llm_api, "detect_model_capabilities", detect_with_transport)
    response = await llm_api_client.post(
        "/api/v1/llm/configs/probe",
        json={
            "probe_type": "model",
            "api_base_url": "https://llm.example/v1",
            "api_key": "test-key",
            "model_name": "arbitrary-alias",
        },
    )
    if verified:
        assert response.status_code == 200
        assert response.json()["config_type"] == "vision"
        assert "image" in response.json()["capabilities"]
    else:
        assert response.status_code == 400
        assert "未能验证图片内容" in response.json()["detail"]
        assert "config_type" not in response.json()


class FakeConfigDB:
    def __init__(self, config: LLMConfigModel | None = None) -> None:
        self.config = config
        self.deactivation_count = 0

    def add(self, config: LLMConfigModel) -> None:
        self.config = config

    async def flush(self) -> None:
        assert self.config is not None
        self.config.id = self.config.id or uuid.uuid4()
        self.config.created_at = self.config.created_at or datetime.now(UTC)
        self.config.updated_at = self.config.updated_at or datetime.now(UTC)

    async def execute(self, query: Any) -> Any:
        if getattr(query, "is_update", False):
            self.deactivation_count += 1
        return SimpleNamespace(
            scalar_one_or_none=lambda: self.config,
            scalar_one=lambda: self.config,
        )


@pytest.mark.asyncio
async def test_save_and_activate_do_not_contact_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeConfigDB()
    app = FastAPI()
    app.include_router(llm_api.router, prefix="/api/v1")
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: db

    async def unexpected_probe(**_kwargs: object) -> LLMCapabilities:
        raise AssertionError("saving or activating must not probe the provider")

    monkeypatch.setattr(llm_api, "detect_model_capabilities", unexpected_probe)
    monkeypatch.setattr(llm_api, "encrypt_api_key", lambda key: key)
    monkeypatch.setattr(llm_api, "mask_api_key", lambda _key: "****")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/llm/configs",
            json={
                "config_name": "test",
                "api_base_url": "https://llm.example/v1",
                "api_key": "test-key",
                "model_name": "test-model",
            },
        )
        assert created.status_code == 201
        assert created.json()["is_active"] is False
        assert created.json()["config_type"] == "unknown"
        assert created.json()["capabilities"] == []

        activated = await client.put(
            f"/api/v1/llm/configs/{created.json()['id']}",
            json={"is_active": True},
        )
        assert activated.status_code == 200
        assert activated.json()["is_active"] is True
        assert db.deactivation_count == 1

        assert db.config is not None
        db.config.config_type = "vision"
        edited = await client.put(
            f"/api/v1/llm/configs/{created.json()['id']}",
            json={"notes": "renamed"},
        )
        assert edited.status_code == 200
        assert edited.json()["config_type"] == "vision"
        assert db.deactivation_count == 1

        changed_model = await client.put(
            f"/api/v1/llm/configs/{created.json()['id']}",
            json={"model_name": "other-model"},
        )
        assert changed_model.status_code == 200
        assert changed_model.json()["config_type"] == "unknown"
        assert changed_model.json()["capabilities"] == []


@pytest.mark.asyncio
async def test_connection_uses_fast_text_probe_and_maps_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = LLMConfigModel(
        id=uuid.uuid4(),
        config_name="test",
        config_type="vision",
        api_base_url="https://llm.example/v1",
        encrypted_api_key="test-key",
        model_name="test-model",
        temperature=0.1,
        timeout_seconds=120,
        is_active=True,
        enable_thinking=False,
        context_window_tokens=200000,
        compress_threshold=0.8,
        stream_output=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db = FakeConfigDB(config)
    app = FastAPI()
    app.include_router(llm_api.router, prefix="/api/v1")
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(llm_api, "decrypt_api_key", lambda _key: "test-key")
    calls: list[dict[str, object]] = []

    async def successful_probe(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(llm_api, "probe_model_connection", successful_probe)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/llm/configs/test")
        assert response.status_code == 200
        assert response.json()["detail"] == "模型连接正常"
        assert len(calls) == 1

        async def failing_probe(**_kwargs: object) -> None:
            raise LLMConfigError("模型连通性测试未完成：ReadTimeout，请重试")

        monkeypatch.setattr(llm_api, "probe_model_connection", failing_probe)
        failed = await client.post("/api/v1/llm/configs/test")
        assert failed.status_code == 400
        assert "ReadTimeout" in failed.json()["detail"]
