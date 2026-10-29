"""Shared LLM callers receive typed errors without provider diagnostics."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.llm import client as module
from app.core.llm.exceptions import LLMProviderError

SENSITIVE = "synthetic-api-key private-prompt /internal/database"


@pytest.mark.parametrize("kind", ["text", "vision"])
async def test_provider_error_body_is_not_retained_in_public_exception(
    monkeypatch, kind
):
    client = module.LLMClient()
    provider = SimpleNamespace(
        post=AsyncMock(return_value=httpx.Response(500, text=SENSITIVE)),
        aclose=AsyncMock(),
    )
    monkeypatch.setattr(
        client,
        "_get_client_and_config",
        AsyncMock(
            return_value=(
                provider,
                SimpleNamespace(model_name="test", temperature=0.1),
            )
        ),
    )
    with pytest.raises(LLMProviderError) as error:
        if kind == "text":
            await client.chat([{"role": "user", "content": "test"}])
        else:
            await client.chat_vision("test", [])
    assert error.value.raw_response is None
    assert SENSITIVE not in str(error.value)
    provider.aclose.assert_awaited_once()


@pytest.mark.parametrize("error_type", ["http", "event", "timeout"])
async def test_stream_exception_never_includes_upstream_text(monkeypatch, error_type):
    async def config(_kind):
        return SimpleNamespace(
            api_base_url="https://provider.example/v1",
            api_key="synthetic",
            model_name="test",
            temperature=0.1,
            timeout_seconds=10,
        )

    class FailingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if error_type == "timeout":
                raise httpx.ReadTimeout(SENSITIVE)
            yield ('data: {"error":{"message":"' + SENSITIVE + '"}}\n\n').encode()

    def handler(request):
        if error_type == "http":
            return httpx.Response(500, text=SENSITIVE)
        return httpx.Response(200, stream=FailingStream())

    monkeypatch.setattr(module, "get_config", config)
    monkeypatch.setattr(
        module,
        "provider_client",
        lambda **kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    with pytest.raises(LLMProviderError) as error:
        [chunk async for chunk in module.LLMClient().stream_chat([])]
    assert SENSITIVE not in str(error.value)
    assert error.value.raw_response is None


async def test_health_check_never_returns_raw_provider_exception(monkeypatch):
    monkeypatch.setattr(
        module, "get_config", AsyncMock(side_effect=RuntimeError(SENSITIVE))
    )
    result = await module.LLMClient().health_check()
    assert result["status"] == "error"
    assert SENSITIVE not in result["detail"]
