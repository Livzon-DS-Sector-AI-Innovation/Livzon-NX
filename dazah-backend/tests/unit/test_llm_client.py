from unittest.mock import AsyncMock

import pytest

from app.core.llm.client import LLMClient, _apply_temperature
from app.core.llm.exceptions import LLMOutputError


def test_apply_temperature_omits_zero_value() -> None:
    body: dict = {}

    _apply_temperature(body, 0)

    assert "temperature" not in body


def test_apply_temperature_includes_positive_value() -> None:
    body: dict = {}

    _apply_temperature(body, 0.1)

    assert body["temperature"] == 0.1


def test_apply_temperature_omits_kimi_model_temperature() -> None:
    body: dict = {}

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
