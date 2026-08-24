from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.llm.client import LLMClient, _apply_temperature
from app.core.llm.exceptions import LLMOutputError, LLMProviderError

SimpleNamespace: Any = _SimpleNamespace


def test_apply_temperature_omits_zero_value() -> None:
    body: dict[Any, Any] = {}

    _apply_temperature(body, 0)

    assert "temperature" not in body


def test_apply_temperature_includes_positive_value() -> None:
    body: dict[Any, Any] = {}

    _apply_temperature(body, 0.1)

    assert body["temperature"] == 0.1


def test_apply_temperature_omits_kimi_model_temperature() -> None:
    body: dict[Any, Any] = {}

    _apply_temperature(body, 0.1, "moonshotai/Kimi-K2.6")

    assert "temperature" not in body


async def test_chat_json_rejects_non_object_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient()
    monkeypatch.setattr(client, "chat", AsyncMock(return_value='"scalar"'))

    with pytest.raises(LLMOutputError, match="not a JSON object"):
        await client.chat_json([])


async def test_chat_vision_json_rejects_non_object_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient()
    monkeypatch.setattr(client, "chat_vision", AsyncMock(return_value="42"))

    with pytest.raises(LLMOutputError, match="not a JSON object"):
        await client.chat_vision_json("prompt", [])


def test_llm_output_error_does_not_expose_raw_response() -> None:
    error = LLMOutputError("输出格式无效", raw_response="secret-provider-payload")

    assert "secret-provider-payload" not in str(error)
    assert error.raw_response == "secret-provider-payload"


async def test_chat_maps_timeout_to_sanitized_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient()

    class TimeoutClient:
        async def post(self: Any, *_args: Any, **_kwargs: Any) -> Any:
            raise httpx.ReadTimeout("provider secret")

        async def aclose(self: Any) -> None:
            return None

    config: Any = SimpleNamespace(model_name="test-model", temperature=0.1)
    monkeypatch.setattr(
        client,
        "_get_client_and_config",
        AsyncMock(return_value=(TimeoutClient(), config)),
    )

    with pytest.raises(LLMProviderError, match="服务响应超时") as error:
        await client.chat([{"role": "user", "content": "hello"}])

    assert "provider secret" not in str(error.value)
