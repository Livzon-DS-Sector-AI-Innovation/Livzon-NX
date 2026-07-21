import json

import httpx
import pytest

from app.core.llm.capabilities import detect_model_capabilities
from app.core.llm.exceptions import LLMConfigError


@pytest.mark.asyncio
async def test_detect_model_capabilities_identifies_vision_model() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = payload["messages"][0]["content"]
        answer = "white" if isinstance(content, list) else "OK"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answer}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="multimodal-model",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_text is True
    assert capabilities.supports_vision is True
    assert capabilities.config_type == "vision"
    assert len(requests) == 2
    assert requests[1]["messages"][0]["content"][1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_detect_model_capabilities_identifies_text_only_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = payload["messages"][0]["content"]
        if isinstance(content, list):
            return httpx.Response(
                400,
                json={"error": {"message": "image input is not supported"}},
                request=request,
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="text-model",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_text is True
    assert capabilities.supports_vision is False
    assert capabilities.config_type == "text"


@pytest.mark.asyncio
async def test_detect_model_capabilities_rejects_broken_text_connection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "invalid key"}},
            request=request,
        )

    with pytest.raises(LLMConfigError, match="文本能力检测失败"):
        await detect_model_capabilities(
            api_base_url="https://llm.example/v1",
            api_key="bad-key",
            model_name="model",
            timeout_seconds=30,
            transport=httpx.MockTransport(handler),
        )
