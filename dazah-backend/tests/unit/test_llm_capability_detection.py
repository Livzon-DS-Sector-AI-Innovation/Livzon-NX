"""Model-independent capability detection regression tests."""

import json

import httpx
import pytest

from app.core.llm.capabilities import detect_model_capabilities
from app.core.llm.exceptions import LLMConfigError


@pytest.mark.asyncio
async def test_generic_validation_error_is_not_text_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content)["messages"][0]["content"]
        if isinstance(content, list):
            return httpx.Response(400, json={"error": {"message": "invalid parameter"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    with pytest.raises(LLMConfigError):
        await detect_model_capabilities(
            api_base_url="https://llm.example/v1",
            api_key="test-key",
            model_name="arbitrary-alias",
            timeout_seconds=30,
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
async def test_fixed_answer_cannot_prove_vision() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content)["messages"][0]["content"]
        answer = "blue, yellow, red" if isinstance(content, list) else "OK"
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})

    with pytest.raises(LLMConfigError):
        await detect_model_capabilities(
            api_base_url="https://llm.example/v1",
            api_key="test-key",
            model_name="arbitrary-alias",
            timeout_seconds=30,
            transport=httpx.MockTransport(handler),
        )
