"""LLMClient.active_model_name 行为测试。

覆盖：返回当前激活配置的模型名、config_type 透传、无可用配置时抛出
LLMConfigError。不发真实网络请求，不接触密钥。
"""

from unittest.mock import AsyncMock

import pytest

from app.core.llm.client import LLMClient
from app.core.llm.config import LLMConfigData
from app.core.llm.exceptions import LLMConfigError


def _config(model_name: str = "test-model") -> LLMConfigData:
    return LLMConfigData(
        id="cfg-1",
        config_name="text",
        config_type="text",
        api_base_url="https://llm.test/v1",
        api_key="k",
        model_name=model_name,
        temperature=0.2,
        timeout_seconds=30,
        is_active=True,
    )


async def test_active_model_name_returns_active_model() -> None:
    client = LLMClient()
    client._get_client_and_config = AsyncMock(  # type: ignore[method-assign]
        return_value=(object(), _config("deepseek-v4-pro"))
    )

    assert await client.active_model_name() == "deepseek-v4-pro"


async def test_active_model_name_passes_config_type() -> None:
    client = LLMClient()
    mock = AsyncMock(return_value=(object(), _config("vision-model")))
    client._get_client_and_config = mock  # type: ignore[method-assign]

    assert await client.active_model_name("vision") == "vision-model"
    mock.assert_awaited_once_with("vision")


async def test_active_model_name_raises_without_active_config() -> None:
    client = LLMClient()
    client._get_client_and_config = AsyncMock(  # type: ignore[method-assign]
        side_effect=LLMConfigError("未配置可用的 LLM")
    )

    with pytest.raises(LLMConfigError):
        await client.active_model_name()
