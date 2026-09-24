import httpx
import pytest

from app.core.llm.capabilities import probe_model_connection
from app.core.llm.exceptions import LLMConfigError


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 429, 503])
async def test_connection_probe_reports_status_without_provider_body(
    status_code: int,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"message": "secret provider response"}},
        )

    with pytest.raises(LLMConfigError) as exc_info:
        await probe_model_connection(
            api_base_url="https://llm.example/v1",
            api_key="test-key",
            model_name="test-model",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )

    assert f"HTTP {status_code}" in str(exc_info.value)
    assert "secret provider response" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_connection_probe_maps_provider_timeout() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider detail")

    with pytest.raises(LLMConfigError) as exc_info:
        await probe_model_connection(
            api_base_url="https://llm.example/v1",
            api_key="test-key",
            model_name="test-model",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )

    assert "ReadTimeout" in str(exc_info.value)
    assert "provider detail" not in str(exc_info.value)
