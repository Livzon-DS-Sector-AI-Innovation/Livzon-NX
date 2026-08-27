from collections.abc import AsyncIterator
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.llm import api as llm_api
from app.core.llm.capabilities import LLMCapabilities
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
